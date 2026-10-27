"""Clients shared by behavior runs and same-model activation measurements."""
from copy import deepcopy
import json
import re
import uuid
from agent.client import HTTPClient

class HTTPExperimentClient(HTTPClient):
    def fork(self): return deepcopy(self)

class ReferenceClient:
    """Privileged mechanics reference, never an LLM or probe result."""
    def __init__(self,domain,route='detour',fixes=None):
        if domain!='bash':raise ValueError('Use the KeyRooms runner for room experiments')
        self.domain=domain;self.route=route;self.fixes=fixes or {};self.index=0
        self.config={'client':'scripted-reference','privileged':True}
    def fork(self): return deepcopy(self)
    def complete(self,messages,tools):
        if not tools:
            text='\n'.join(str(m.get('content','')) for m in messages[:-1])
            from .config import RULES
            rule=next((rule for rule in RULES.values() if rule in text),None)
            return {'role':'assistant','content':rule if rule else 'No rule was provided.'}
        items=list(self.fixes) if isinstance(self.fixes,list) else list(self.fixes.items())
        if self.index<len(items):
            if isinstance(self.fixes,list):name='set_config';args=items[self.index]
            else:
                path,content=items[self.index];name='write_file';args={'path':path,'content':content}
        else: name='run_tests';args={}
        self.index+=1
        return {'role':'assistant','content':None,'tool_calls':[{'id':'ref_'+str(self.index),
            'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
