"""Notebook cards with paired request IDs; plain-text fallback for CLI tests."""
import contextvars
import html
import itertools
import json

ENABLED = True
HTML_MODE = True
_active = contextvars.ContextVar('llm_request_id', default=None)
_counter = itertools.count(1)

def safe_data(value):
    if isinstance(value, dict):
        if value.get('type') == 'reasoning':
            return {'type': 'reasoning', 'note': '内部推理/加密载荷不展示'}
        return {k: ('[REDACTED]' if k.lower() in {
            'encrypted_content', 'api_key', 'authorization', 'access_token'} else safe_data(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_data(v) for v in value]
    return value

def in_notebook():
    try:
        from IPython import get_ipython
        return get_ipython().__class__.__name__ == 'ZMQInteractiveShell'
    except (ImportError, AttributeError):
        return False

def render_card(label, data, kind='event', request_id=None, opened=False):
    colors = {'request': '#2563eb', 'response': '#16a34a',
              'error': '#dc2626', 'event': '#9333ea'}
    color = colors.get(kind, colors['event'])
    badge = f'LLM #{request_id:03d}' if request_id is not None else 'SETUP / EVENT'
    payload = json.dumps(safe_data(data), ensure_ascii=False, indent=2)
    return f'''<section style="border:1px solid {color};border-left:6px solid {color};
margin:14px 0;padding:12px 16px;border-radius:8px;background:rgba(128,128,128,.05)">
<div style="font-weight:700;color:{color};font-size:15px">{html.escape(badge)} · {html.escape(label)}</div>
<details {'open' if opened else ''} style="margin-top:8px"><summary style="cursor:pointer">展开 / 收起 JSON</summary>
<pre style="max-height:460px;overflow:auto;padding:10px;white-space:pre-wrap;overflow-wrap:anywhere">{html.escape(payload)}</pre>
</details></section>'''

def show(label, data, kind='event', request_id=None, opened=False):
    if not ENABLED:
        return
    request_id = _active.get() if request_id is None else request_id
    if HTML_MODE and in_notebook():
        from IPython.display import HTML, display
        display(HTML(render_card(label, data, kind, request_id, opened)))
    else:
        badge = f'LLM #{request_id:03d}' if request_id is not None else 'SETUP / EVENT'
        print('\n' + '=' * 72 + f'\n[{badge} | {label}]\n' +
              json.dumps(safe_data(data), ensure_ascii=False, indent=2) + '\n' + '=' * 72)

def start_request():
    request_id = next(_counter)
    return request_id, _active.set(request_id)

def end_request(token, succeeded):
    # Keep successful request context for the tool events that follow its response.
    if not succeeded:
        _active.reset(token)

def show_request(request_id, endpoint, body):
    show('REQUEST → POST /responses（实际请求体）',
         {'endpoint': endpoint, 'body': body}, 'request', request_id, opened=True)

def show_response(response, request_id=None):
    visible = []
    for item in response.output:
        if item.type == 'function_call':
            visible.append({'type': item.type, 'name': item.name,
                            'call_id': item.call_id, 'arguments': item.arguments})
        elif item.type == 'message':
            visible.append({'type': item.type, 'role': item.role,
                            'content': [part.model_dump(mode='json', exclude_none=True)
                                        for part in item.content]})
        else:
            visible.append({'type': item.type, 'note': '内部推理/加密内容不展示'})
    show('RESPONSE ← LLM 返回：真实 response.output',
         {'id': response.id, 'status': response.status, 'output': visible},
         'response', request_id, opened=True)
