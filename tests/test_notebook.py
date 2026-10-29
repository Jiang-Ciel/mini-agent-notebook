import ast
import asyncio
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import nbformat
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

ROOT = Path(__file__).resolve().parents[1]
NB = nbformat.read(ROOT / 'mini_agent.ipynb', as_version=4)

def reply(content=None, calls=None):
    return ChatCompletion.model_validate({
        'id': 'offline', 'object': 'chat.completion', 'created': 0, 'model': 'test',
        'choices': [{'index': 0, 'finish_reason': 'tool_calls' if calls else 'stop',
                     'message': {'role': 'assistant', 'content': content, 'tool_calls': calls}}],
    }).choices[0].message

def call(a=17, b=25, name='add', id='call_1'):
    return {'id': id, 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps({'a': a, 'b': b})}}

class NotebookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_cwd = Path.cwd()
        os.chdir(ROOT)
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

    async def test_notebook_structure_and_clean_outputs(self):
        nbformat.validate(NB)
        for cell in NB.cells:
            if cell.cell_type == 'code':
                self.assertEqual(cell.outputs, [])
                self.assertIsNone(cell.execution_count)
                compile(cell.source, '<cell>', 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    async def test_custom_endpoint_wire_format(self):
        seen = []
        def handler(request):
            seen.append((str(request.url), json.loads(request.content)))
            return httpx.Response(200, json={
                'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'test',
                'choices': [{'index': 0, 'finish_reason': 'stop',
                             'message': {'role': 'assistant', 'content': 'ok'}}],
            })
        real = self.ns['client']
        async with AsyncOpenAI(base_url='https://custom.example/v1', api_key='dummy',
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as c:
            self.ns['client'] = c
            try:
                answer = await self.ns['ask'](self.ns['messages']('test'), [self.ns['ADD']])
            finally:
                self.ns['client'] = real
        self.assertEqual(answer.content, 'ok')
        self.assertEqual(seen[0][0], 'https://custom.example/v1/chat/completions')
        self.assertEqual(seen[0][1]['model'], 'test-model')
        self.assertEqual(seen[0][1]['tools'][0]['function']['name'], 'add')

    async def test_dependent_tool_loop(self):
        steps = iter([reply(calls=[call()]), reply(calls=[call(a=42, b=8, id='call_2')]), reply('50')])
        seen = []
        async def fake(work, tools=None):
            seen.append(list(work)); return next(steps)
        self.ns['ask'] = fake
        initial = self.ns['messages']('compute')
        answer, trace = await self.ns['agent'](initial, [self.ns['ADD']], self.ns['local_tool'])
        self.assertEqual(answer, '50')
        self.assertEqual(len(trace), 5)
        self.assertEqual(len(initial), 2)
        self.assertEqual(json.loads(seen[1][-1]['content'])['result'], 42)
        self.assertEqual(json.loads(seen[2][-1]['content'])['result'], 50)

    async def test_errors_and_call_pairing(self):
        calls = reply(calls=[call(), call(name='delete', id='call_2')]).tool_calls
        observed = await self.ns['observe'](calls, self.ns['local_tool'])
        self.assertEqual([r['tool_call_id'] for r in observed], ['call_1', 'call_2'])
        self.assertFalse(json.loads(observed[1]['content'])['ok'])
        for args in [{'a': True, 'b': 3}, {'a': 1}, []]:
            with self.assertRaises(ValueError): self.ns['validate'](args)

    async def test_bounded_loop(self):
        async def fake(work, tools=None): return reply(calls=[call()])
        self.ns['ask'] = fake
        with self.assertRaisesRegex(RuntimeError, '上限'):
            await self.ns['agent']([], [self.ns['ADD']], self.ns['local_tool'], max_steps=2)

    async def test_real_mcp_connection(self):
        async with self.ns['mcp_tools']() as (tools, execute):
            self.assertEqual([t['function']['name'] for t in tools], ['add', 'mcp_multiply'])
            result = await execute('mcp_multiply', {'a': 42, 'b': 3})
            self.assertIn('126', json.dumps(result))
            with self.assertRaises(ValueError): await execute('delete', {})

    async def test_compaction_preserves_recent_turns(self):
        memory = self.ns['Memory'](limit=1)
        turns = [[{'role': 'user', 'content': str(i)},
                  {'role': 'assistant', 'tool_calls': [call(id=f'c{i}')]},
                  {'role': 'tool', 'tool_call_id': f'c{i}', 'content': '42'},
                  {'role': 'assistant', 'content': '42'}] for i in range(4)]
        memory.turns = turns.copy()
        async def fake(work, tools=None): return reply('旧计算结果为42。')
        self.ns['ask'] = fake
        self.assertTrue(await memory.compact())
        self.assertEqual(memory.turns, turns[-2:])
        self.assertEqual(memory.history()[0]['role'], 'user')

    async def test_summary_failure_keeps_history(self):
        memory = self.ns['Memory'](limit=1)
        memory.turns = [[{'role': 'user', 'content': 'some previous data'}]] * 3
        before = memory.turns.copy()
        async def fake(work, tools=None): return reply('')
        self.ns['ask'] = fake
        with self.assertRaises(RuntimeError): await memory.compact()
        self.assertEqual(memory.turns, before)
        self.assertEqual(memory.summary, '')

    async def test_skill_allowlist(self):
        self.assertIn('mcp_multiply', self.ns['load_skill']('calc'))
        with self.assertRaises(KeyError): self.ns['load_skill']('../../private')

if __name__ == '__main__':
    unittest.main()
