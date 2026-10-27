import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from agent.client import HTTPClient
# Keep the shared client's transport test independent of experiment packages.
TOOLS = [{"type": "function", "function": {
    "name": "pwd", "description": "Get the current directory",
    "parameters": {"type": "object", "properties": {}, "required": []}}}]


class HTTPClientTests(unittest.TestCase):
    def test_request_and_raw_response(self):
        received={}
        response={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[
            {'id':'p','type':'function','function':{'name':'pwd','arguments':'{}'}}]}}],
            'model':'fixed-model','usage':{'prompt_tokens':10},'system_fingerprint':'test-only'}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                received['path']=self.path
                received['body']=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received['authorization']=self.headers.get('Authorization')
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            with patch.dict('os.environ',{'MODEL_API_KEY':'fake-test-key'}):
                client=HTTPClient(f'http://127.0.0.1:{server.server_port}/v1','fixed-model',seed=7)
                messages=[{'role':'user','content':'Get current directory.'}]
                actual=client.complete(messages,TOOLS)
            self.assertEqual(actual,response['choices'][0]['message'])
            self.assertEqual(client.last_response,response)
            self.assertEqual(received['path'],'/v1/chat/completions')
            self.assertEqual(received['body'],{'model':'fixed-model','temperature':0,'seed':7,
                                             'messages':messages,'tools':TOOLS,'parallel_tool_calls':False})
            self.assertEqual(received['authorization'],'Bearer fake-test-key')
            self.assertNotIn('fake-test-key',json.dumps(client.config))
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

if __name__=='__main__': unittest.main()
