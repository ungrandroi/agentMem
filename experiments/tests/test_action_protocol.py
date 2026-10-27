import json,unittest
from copy import deepcopy
from experiments.action_protocol import parse_action,parse_xml_action,action_schema,ActionProtocolError
from experiments.strict_bash import TOOLS,StrictConfigEnvironment
from experiments.config import Config
from experiments.runner import run_episode
from experiments.tests.test_rules import Counter

class Stub:
    reject_submission=StrictConfigEnvironment.reject_submission
    def __init__(self):self.calls=0;self.closed=False;self.success=False;self.config=Config(domain='bash',max_decisions=5);self.executed=[]
    def observe(self):return {'cwd':'/workspace','tool_calls_remaining':5-self.calls}
    def snapshot(self):return {'calls':self.calls,'files':'unchanged','executed':self.executed.copy()}
    def close(self):self.closed=True
    def execute(self,name,args):
        self.executed.append(name);self.calls+=1;self.success=True
        return {'public':{'success':True},'audit':{'audit_complete':True,'accessed_forbidden':False}}

class Client:
    config={'client':'protocol-test'}
    def __init__(self,errors):self.errors=errors;self.inputs=[]
    def complete(self,messages,tools):
        self.inputs.append(deepcopy(messages))
        if len(self.inputs)<=self.errors:raise ActionProtocolError('Multiple calls','[{"name":"read_file"},{"name":"run_tests"}]')
        return parse_action('{"name":"run_tests","args":{}}',tools)

class ProtocolTests(unittest.TestCase):
    def test_bash_has_only_real_tools(self):
        names=[s['properties']['name']['enum'][0] for s in action_schema(TOOLS)['oneOf']]
        self.assertEqual(names,[t['function']['name'] for t in TOOLS])
        with self.assertRaises(ActionProtocolError):
            parse_action('{"name":"finish","args":{"message":"Budget exhausted"}}',TOOLS)

    def test_bash_final_text_rejected_then_valid_tool_executes(self):
        class EarlyFinal(Client):
            def complete(self,messages,tools):
                if not self.inputs:
                    self.inputs.append(deepcopy(messages))
                    return {'role':'assistant','content':'Budget exhausted'}
                return super().complete(messages,tools)
        env=Stub();trace=run_episode(Config(domain='bash',max_decisions=5,recall=False),env,EarlyFinal(0),TOOLS,Counter())
        self.assertEqual(trace['status'],'success')
        self.assertEqual(trace['metrics']['protocol_errors'],1)
        self.assertEqual(env.calls,2)
        self.assertEqual(env.executed,['run_tests'])
        self.assertIsNone(trace['steps'][0]['B_t'])

    def test_one_remaining_call_is_still_usable(self):
        env=Stub();env.calls=4
        trace=run_episode(Config(domain='bash',max_decisions=5,recall=False),env,Client(0),TOOLS,Counter())
        self.assertEqual(trace['status'],'success')
        self.assertEqual(env.calls,5)
        self.assertEqual(trace['metrics']['operations_executed'],1)

    def test_single_operation_schema(self):
        valid={'name':'set_config','args':{'path':'config/job_00.json','key':'batch_size','value':'8'}}
        self.assertEqual(len(parse_action(json.dumps(valid),TOOLS)['tool_calls']),1)
        for value in ([valid,valid],{**valid,'extra':'x'},{'name':'set_config','args':{**valid['args'],'value':8}}, {'name':'read_file','args':{'path':['a','b']}}, {'name':'unknown','args':{}}):
            with self.assertRaises(ActionProtocolError):parse_action(json.dumps(value),TOOLS)
        with self.assertRaises(ActionProtocolError):parse_action('{"name":"run_tests","name":"finish","args":{}}',TOOLS)
        call='<tool_call><function=run_tests></function></tool_call>'
        self.assertEqual(len(parse_xml_action(call,TOOLS)['tool_calls']),1)
        with self.assertRaises(ActionProtocolError):parse_xml_action(call+call,TOOLS)

    def test_rejected_response_consumes_budget_but_executes_nothing(self):
        env=Stub();client=Client(1)
        trace=run_episode(env.config.__class__(domain='bash',max_decisions=5,recall=False),env,client,TOOLS,Counter())
        self.assertEqual(env.executed,['run_tests']);self.assertEqual(env.calls,2)
        self.assertTrue(trace['metrics']['task_success']);self.assertEqual(trace['metrics']['protocol_errors'],1)
        self.assertIsNone(trace['steps'][0]['B_t']);self.assertEqual(trace['metrics']['audited_tool_decisions'],1)
        self.assertEqual(trace['steps'][0]['result']['public']['operations_executed'],0)
        history=client.inputs[1];self.assertEqual([m['role'] for m in history],['system','user','assistant','tool'])
        self.assertEqual(history[-1]['tool_call_id'],history[-2]['tool_calls'][0]['id'])
        self.assertEqual(json.loads(history[-1]['content'])['observation']['tool_calls_remaining'],4)

    def test_retry_limit(self):
        env=Stub();client=Client(10)
        trace=run_episode(Config(domain='bash',max_decisions=5,recall=False),env,client,TOOLS,Counter())
        self.assertEqual(env.executed,[]);self.assertEqual(env.calls,3)
        self.assertEqual(trace['status'],'protocol_error_limit');self.assertFalse(trace['metrics']['run_valid'])
        self.assertIsNone(trace['metrics']['compliance'])

if __name__=='__main__':unittest.main()
