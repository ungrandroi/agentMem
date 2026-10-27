"""Chat Completions-compatible LLM client; no provider SDK required."""
import json
import os
from urllib.request import Request, urlopen


class HTTPClient:
    def __init__(self, base_url, model, temperature=0, seed=0, request_timeout=120):
        if request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        self.request_timeout = request_timeout
        self.base_url = base_url.rstrip('/')
        self.config = {'client':'http','base_url':self.base_url,'model':model,
                       'temperature':temperature,'seed':seed,'request_timeout':request_timeout}
        self.last_response = None

    def complete(self, messages, tools):
        body = {k:self.config[k] for k in ('model','temperature','seed')}
        if self.config['seed'] is None:
            body.pop('seed')
        self.last_response = None
        body.update(messages=messages, tools=tools, parallel_tool_calls=False)
        headers = {'Content-Type':'application/json'}
        key = os.environ.get('MODEL_API_KEY')
        if key:
            headers['Authorization'] = 'Bearer '+key
        request = Request(self.base_url+'/chat/completions',json.dumps(body).encode(),headers)
        with urlopen(request,timeout=self.request_timeout) as response:
            self.last_response = json.load(response)
        return self.last_response['choices'][0]['message']
