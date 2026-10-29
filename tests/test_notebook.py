import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import ast
import asyncio
import json
import os
import io
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import nbformat
from openai import AsyncOpenAI
from openai.types.responses import Response

ROOT = Path(__file__).resolve().parents[1]
NB = nbformat.read(ROOT / 'lecture/mini_agent.ipynb', as_version=4)

def response_data(content=None, calls=None, reasoning=False, status='completed', refusal=False):
    output = []
    if reasoning:
        output.append({'id': 'rs_1', 'type': 'reasoning', 'summary': [], 'encrypted_content': 'opaque-test'})
    output.extend(calls or [])
    if content is not None or refusal:
        part = {'type': 'refusal', 'refusal': 'denied'} if refusal else {
            'type': 'output_text', 'text': content, 'annotations': []}
        output.append({'id': 'msg_1', 'type': 'message', 'role': 'assistant',
                       'status': 'completed', 'content': [part]})
    return {'id': 'resp_test', 'created_at': 0, 'model': 'test', 'object': 'response',
            'status': status, 'output': output, 'parallel_tool_calls': True,
            'tool_choice': 'auto', 'tools': []}

def reply(**kwargs):
    return Response.model_validate(response_data(**kwargs))

def call(a=17, b=25, name='add', id='call_1'):
    return {'id': 'fc_' + id, 'call_id': id, 'type': 'function_call', 'name': name,
            'arguments': json.dumps({'a': a, 'b': b}), 'status': 'completed'}

class NotebookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_cwd = Path.cwd()
        os.chdir(ROOT / 'lecture')
        self.env = patch.dict(os.environ, {
            'OPENAI_BASE_URL': 'https://offline.example/v1',
            'OPENAI_API_KEY': 'dummy-not-a-real-key', 'OPENAI_MODEL': 'test-model',
        })
        self.env.start()
        self.ns = {}
        for cell in NB.cells:
            if cell.cell_type != 'code' or 'live-api' in cell.metadata.get('tags', []):
                continue
            if cell.source.strip() == 'await client.close()':
                continue
            compiled = compile(cell.source, '<notebook>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            result = eval(compiled, self.ns)
            if asyncio.iscoroutine(result):
                await result

    async def asyncTearDown(self):
        await self.ns['client'].close()
        self.env.stop()
        os.chdir(self.old_cwd)

    async def test_paths_from_lecture_and_project_root(self):
        self.assertEqual(self.ns['PROJECT_ROOT'], ROOT)
        self.assertEqual(self.ns['SRC_DIR'], ROOT / 'src')
        self.assertEqual(self.ns['SKILLS']['calc'], ROOT / 'skills/calc.md')
        os.chdir(ROOT)
        namespace = {}
        exec(NB.cells[2].source, namespace)
        try:
            self.assertEqual(namespace['PROJECT_ROOT'], ROOT)
        finally:
            await namespace['client'].close()

    async def test_notebook_structure_and_clean_outputs(self):
        nbformat.validate(NB)
        for cell in NB.cells:
            if cell.cell_type == 'code':
                self.assertEqual(cell.outputs, [])
                self.assertIsNone(cell.execution_count)
                compile(cell.source, '<cell>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    async def test_custom_responses_endpoint_wire_format(self):
        seen = []
        def handler(request):
            seen.append((str(request.url), json.loads(request.content)))
            return httpx.Response(200, json=response_data(content='ok'))
        real = self.ns['client']
        async with AsyncOpenAI(base_url='https://custom.example/v1', api_key='dummy',
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as c:
            self.ns['client'] = c
            try:
                capture = io.StringIO()
                with redirect_stdout(capture):
                    answer = await self.ns['ask'](self.ns['messages']('test'), [self.ns['ADD']])
            finally:
                self.ns['client'] = real
        import re
        badges = re.findall(r'LLM #(\d+)', capture.getvalue())
        self.assertEqual(len(badges), 2)
        self.assertEqual(badges[0], badges[1])
        self.assertIn('"content": "test"', capture.getvalue())
        self.assertIn('REQUEST →', capture.getvalue())
        self.assertIn('RESPONSE ←', capture.getvalue())
        self.assertEqual(answer.output_text, 'ok')
        url, body = seen[0]
        self.assertEqual(url, 'https://custom.example/v1/responses')
        self.assertEqual(body['model'], 'test-model')
        self.assertEqual(body['input'][1]['content'], 'test')
        self.assertFalse(body['store'])
        self.assertEqual(body['include'], ['reasoning.encrypted_content'])
        self.assertEqual(body['tools'][0]['name'], 'add')
        self.assertNotIn('function', body['tools'][0])
        self.assertNotIn('messages', body)

    async def test_dependent_loop_preserves_reasoning(self):
        steps = iter([reply(calls=[call()], reasoning=True),
                      reply(calls=[call(a=42, b=8, id='call_2')]), reply(content='50')])
        seen = []
        async def fake(work, tools=None):
            seen.append(list(work)); return next(steps)
        self.ns['ask'] = fake
        initial = self.ns['messages']('compute')
        answer, trace = await self.ns['agent'](initial, [self.ns['ADD']], self.ns['local_tool'])
        self.assertEqual(answer, '50')
        self.assertEqual(len(trace), 6)
        self.assertEqual(len(initial), 2)
        self.assertEqual(seen[1][-3]['type'], 'reasoning')
        self.assertEqual(seen[1][-3]['encrypted_content'], 'opaque-test')
        self.assertEqual(seen[1][-2]['type'], 'function_call')
        self.assertEqual(seen[1][-1]['call_id'], 'call_1')
        self.assertEqual(json.loads(seen[1][-1]['output'])['result'], 42)
        self.assertEqual(json.loads(seen[2][-1]['output'])['result'], 50)

    async def test_errors_and_call_pairing(self):
        calls = self.ns['calls'](reply(calls=[call(), call(name='delete', id='call_2')]))
        observed = await self.ns['observe'](calls, self.ns['local_tool'])
        self.assertEqual([r['call_id'] for r in observed], ['call_1', 'call_2'])
        self.assertTrue(all(r['type'] == 'function_call_output' for r in observed))
        self.assertFalse(json.loads(observed[1]['output'])['ok'])
        for args in [{'a': True, 'b': 3}, {'a': 1}, []]:
            with self.assertRaises(ValueError): self.ns['validate'](args)

    async def test_bounded_loop(self):
        async def fake(work, tools=None): return reply(calls=[call()])
        self.ns['ask'] = fake
        with self.assertRaisesRegex(RuntimeError, '上限'):
            await self.ns['agent']([], [self.ns['ADD']], self.ns['local_tool'], max_steps=2)

    async def test_incomplete_and_refusal_rejected(self):
        real = self.ns['client']
        for data in [response_data(content='partial', status='incomplete'), response_data(refusal=True)]:
            async with AsyncOpenAI(api_key='dummy', http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(lambda req: httpx.Response(200, json=data)))) as c:
                self.ns['client'] = c
                try:
                    with self.assertRaises(RuntimeError): await self.ns['ask']([])
                finally:
                    self.ns['client'] = real

    async def test_real_mcp_connection(self):
        async with self.ns['mcp_tools']() as (tools, execute):
            self.assertEqual([t['name'] for t in tools], ['add', 'mcp_multiply'])
            result = await execute('mcp_multiply', {'a': 42, 'b': 3})
            self.assertIn('126', json.dumps(result))
            with self.assertRaises(ValueError): await execute('delete', {})

    async def test_compaction_preserves_recent_turns(self):
        memory = self.ns['Memory'](limit=1)
        turns = [[{'role': 'user', 'content': str(i)}, call(id=f'c{i}'),
                  {'type': 'function_call_output', 'call_id': f'c{i}', 'output': '42'},
                  *self.ns['output_items'](reply(content='42'))] for i in range(4)]
        memory.turns = turns.copy()
        async def fake(work, tools=None): return reply(content='旧计算结果为42。')
        self.ns['ask'] = fake
        self.assertTrue(await memory.compact())
        self.assertEqual(memory.turns, turns[-2:])
        self.assertEqual(memory.history()[0]['role'], 'user')

    async def test_summary_failure_keeps_history(self):
        memory = self.ns['Memory'](limit=1)
        memory.turns = [[{'role': 'user', 'content': 'some previous data'}]] * 3
        before = memory.turns.copy()
        async def fake(work, tools=None): return reply(content='')
        self.ns['ask'] = fake
        with self.assertRaises(RuntimeError): await memory.compact()
        self.assertEqual(memory.turns, before)
        self.assertEqual(memory.summary, '')

    async def test_model_failure_unwrapped_after_real_mcp_cleanup(self):
        cause = RuntimeError('模型服务过载')
        with self.assertRaises(RuntimeError) as caught:
            async with self.ns['mcp_tools']():
                raise cause
        self.assertIs(caught.exception, cause)

    async def test_visible_llm_then_real_mcp_then_result_trace(self):
        steps = iter([reply(calls=[call(a=42, b=3, name='mcp_multiply')]),
                      reply(content='126')])
        async def fake(work, tools=None):
            from tracing import show, show_response
            show('LLM 请求：Responses API', {'tools': tools})
            result = next(steps)
            show_response(result)
            return result
        self.ns['ask'] = fake
        capture = io.StringIO()
        with redirect_stdout(capture):
            async with self.ns['mcp_tools']() as (tools, execute):
                answer, trace = await self.ns['agent'](self.ns['messages']('multiply'), tools, execute)
        text = capture.getvalue()
        markers = ['LLM 请求：Responses API', 'LLM 返回：真实 response.output',
                   '宿主分派：模型调用意图 → 执行器', 'MCP 实际请求：tools/call',
                   'MCP tools/call 响应', '准备回传 LLM：function_call_output',
                   'ReAct 结束：模型返回答案而非工具调用']
        positions = [text.index(m) for m in markers]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(answer, '126')
        self.assertIn('126', trace[1]['output'])

    async def test_visible_output_hides_encrypted_reasoning(self):
        from tracing import show_response
        capture = io.StringIO()
        with redirect_stdout(capture):
            show_response(reply(calls=[call()], reasoning=True))
        self.assertIn('function_call', capture.getvalue())
        self.assertIn('call_1', capture.getvalue())
        self.assertNotIn('opaque-test', capture.getvalue())

    async def test_skill_allowlist(self):
        self.assertIn('mcp_multiply', self.ns['load_skill']('calc'))
        with self.assertRaises(KeyError): self.ns['load_skill']('../../private')

if __name__ == '__main__':
    unittest.main()
