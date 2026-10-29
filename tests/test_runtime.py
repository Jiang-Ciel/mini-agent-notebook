import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from openai import APIStatusError, RateLimitError
from runtime import create_response, single_cause


def status_error(status, headers=None):
    response = httpx.Response(status, headers=headers,
                              request=httpx.Request('POST', 'https://offline.example/v1/responses'))
    cls = RateLimitError if status == 429 else APIStatusError
    return cls('overloaded', response=response, body=None)

class RetryTests(unittest.IsolatedAsyncioTestCase):
    def client(self, effects):
        return SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(side_effect=effects)))

    async def test_retry_then_success(self):
        client = self.client([status_error(429), 'ok'])
        with patch('runtime.asyncio.sleep', new_callable=AsyncMock) as sleep:
            self.assertEqual(await create_response(client, input=[]), 'ok')
        self.assertEqual(client.responses.create.await_count, 2)
        self.assertEqual(sleep.await_count, 1)

    async def test_exhaustion_is_bounded(self):
        client = self.client([status_error(429)] * 4)
        with patch('runtime.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(RuntimeError, '不是 MCP'):
                await create_response(client, input=[])
        self.assertEqual(client.responses.create.await_count, 4)
        self.assertEqual(sleep.await_count, 3)

    async def test_retry_after_and_503(self):
        client = self.client([status_error(503, {'retry-after': '8'}), 'ok'])
        with patch('runtime.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await create_response(client, input=[])
        sleep.assert_awaited_once_with(8.0)

    async def test_long_retry_after_stops_without_early_retry(self):
        client = self.client([status_error(429, {'retry-after': '120'})])
        with patch('runtime.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaisesRegex(RuntimeError, '超过 20 秒'):
                await create_response(client, input=[])
        sleep.assert_not_awaited()
        self.assertEqual(client.responses.create.await_count, 1)

    async def test_bad_request_not_retried(self):
        client = self.client([status_error(400)])
        with self.assertRaises(APIStatusError): await create_response(client, input=[])
        self.assertEqual(client.responses.create.await_count, 1)

    def test_single_group_only(self):
        cause = RuntimeError('model overload')
        group = ExceptionGroup('outer', [ExceptionGroup('inner', [cause])])
        self.assertIs(single_cause(group), cause)
        multiple = ExceptionGroup('multiple', [cause, ValueError('cleanup')])
        self.assertIs(single_cause(multiple), multiple)
