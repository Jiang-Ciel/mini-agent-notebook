import contextlib
import io
import unittest
from unittest.mock import patch
import tracing

class TracingTests(unittest.TestCase):
    def test_safe_copy_preserves_sent_body(self):
        body = {'input': [{'role': 'user', 'content': '<hello>'},
                          {'type': 'reasoning', 'encrypted_content': 'private'}],
                'api_key': 'secret'}
        visible = tracing.safe_data(body)
        self.assertEqual(body['input'][1]['encrypted_content'], 'private')
        self.assertEqual(visible['api_key'], '[REDACTED]')
        self.assertNotIn('private', str(visible))
        self.assertEqual(visible['input'][0]['content'], '<hello>')

    def test_html_card_escape_and_pairing(self):
        card = tracing.render_card('REQUEST', {'input': '<script>alert(1)</script>'},
                                   kind='request', request_id=7, opened=True)
        self.assertIn('LLM #007', card)
        self.assertIn('<details open', card)
        self.assertIn('&lt;script&gt;', card)
        self.assertNotIn('<script>', card)
        self.assertIn('#2563eb', card)
        self.assertIn('overflow:auto', card)

    def test_request_context_tool_events_and_failure_restore(self):
        prior = tracing._active.set(None)
        try:
            first, token = tracing.start_request()
            tracing.end_request(token, True)
            with patch('tracing.in_notebook', return_value=False), contextlib.redirect_stdout(io.StringIO()) as capture:
                tracing.show('MCP tools/call', {'name': 'multiply'})
            self.assertIn(f'LLM #{first:03d}', capture.getvalue())
            second, token = tracing.start_request()
            self.assertGreater(second, first)
            tracing.end_request(token, False)
            self.assertEqual(tracing._active.get(), first)
        finally:
            tracing._active.reset(prior)

    def test_request_contains_complete_input(self):
        body = {'model': 'test', 'input': [{'role': 'system', 'content': 'system rules'},
                                         {'role': 'user', 'content': 'calculate 1+2'}],
                'tools': [{'type': 'function', 'name': 'add'}]}
        with patch('tracing.in_notebook', return_value=False), contextlib.redirect_stdout(io.StringIO()) as capture:
            tracing.show_request(10, 'https://example/v1/responses', body)
        self.assertIn('system rules', capture.getvalue())
        self.assertIn('calculate 1+2', capture.getvalue())
        self.assertIn('REQUEST', capture.getvalue())
        self.assertIn('LLM #010', capture.getvalue())
