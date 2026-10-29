"""Bounded model retries and single-cause MCP error reporting."""
import asyncio
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from openai import APIStatusError

async def create_response(client, **kwargs):
    # Retry only the model request, never replay a whole agent/tool workflow.
    for attempt in range(4):
        try:
            return await client.responses.create(**kwargs)
        except APIStatusError as exc:
            if exc.status_code not in (429, 503):
                raise
            if attempt == 3:
                raise RuntimeError(
                    f"模型服务暂不可用（HTTP {exc.status_code}），4 次请求后仍失败；"
                    "请稍后再试或检查服务配额/负载。这不是 MCP 工具错误。"
                ) from exc
            delay = 2 ** attempt + random.uniform(0, 1)
            header = exc.response.headers.get("retry-after")
            if header:
                try:
                    delay = max(delay, float(header))
                except ValueError:
                    try:
                        deadline = parsedate_to_datetime(header)
                        if deadline.tzinfo is None:
                            deadline = deadline.replace(tzinfo=timezone.utc)
                        delay = max(delay, (deadline - datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        pass
            # Don't retry earlier than a long server deadline; let the user retry later.
            if delay > 20:
                raise RuntimeError(
                    "模型服务要求等待超过 20 秒，本轮停止；请按 Retry-After 稍后重试。"
                ) from exc
            print(f"[模型 HTTP {exc.status_code}，{delay:.1f} 秒后重试 {attempt + 1}/3]")
            await asyncio.sleep(delay)

def single_cause(group):
    """Unwrap only a single nested cause; preserve multi-error groups intact."""
    while isinstance(group, ExceptionGroup) and len(group.exceptions) == 1:
        group = group.exceptions[0]
    return group
