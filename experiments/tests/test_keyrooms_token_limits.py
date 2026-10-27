import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from experiments.keyrooms.openrouter import OpenRouterClient,remaining_output_budget

class TokenLimitsTests(unittest.TestCase):
    def test_exact_remaining(self):
        for text in ["maximum context length is 131072; your request has 20000 input tokens", "requested 137964 tokens (20000 of text input, 117964 in output)"]:
            self.assertEqual(remaining_output_budget(text,117964,131072),111072)
        self.assertIsNone(remaining_output_budget('request has 131072 input tokens',117964,131072))
        self.assertIsNone(remaining_output_budget('context limit exceeded',117964,131072))

    def test_tool_tokens_and_lower_bound(self):
        text='requested about 133349 tokens (15116 of text input, 269 of tool input, 117964 in the output)'
        self.assertEqual(remaining_output_budget(text,117964,131072),115687)
        text='requested 107302 output tokens and prompt contains at least 23771 input tokens'
        self.assertEqual(remaining_output_budget(text,107302,131072),103206)

    def test_retry_preserves_full_history_and_records_cap(self):
        calls=[]
        def response(request,timeout):
            body=json.loads(request.data);calls.append(body)
            if len(calls)==1:
                payload={'error':{'message':'maximum context length is 131072; your request has 20000 input tokens'}}
                raise HTTPError(request.full_url,400,'bad',{},io.BytesIO(json.dumps(payload).encode()))
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'tool_calls','message':{'role':'assistant','tool_calls':[]}}],'usage':{'cost':0},'provider':'Together'}).encode())
        with patch('experiments.keyrooms.openrouter.load_key',return_value='test'),patch('experiments.keyrooms.openrouter.urlopen',side_effect=response):
            client=OpenRouterClient(Path('unused'));messages=[{'role':'user','content':'entire history'}];client.complete(messages,[])
        self.assertEqual([c['max_tokens'] for c in calls],[117964,111072])
        self.assertEqual(calls[0]['messages'],calls[1]['messages'])
        self.assertEqual(calls[1]['transforms'],[])
        self.assertEqual(client.last_metadata['requested_max_tokens'],111072)
