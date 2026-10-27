"""Natural agent inputs contain one user task followed only by tool exchanges."""
import json
import unittest
from copy import deepcopy
from experiments.config import Config
from experiments.strict_bash import TOOLS as BASH_TOOLS
from experiments.clients import ReferenceClient
from experiments.runner import run_episode
from experiments.tests.test_rules import Counter

class BashStub:
    """Unit-test the runner's feedback plumbing without invoking Docker."""
    closed=False;success=False;calls=0
    def observe(self):return {'cwd':'/workspace','tool_mode':'strict','tool_calls_remaining':4-self.calls}
    def snapshot(self):return {'calls':self.calls,'success':self.success}
    def execute(self,name,args):
        self.calls+=1;self.success=self.calls==4
        return {'public':{'stdout':json.dumps({'success':self.success}),'exit_code':0 if self.success else 1},
                'audit':{'audit_complete':True,'accessed_forbidden':False,'private_marker':'NEVER_FEED_THIS'}}

class RunnerInputTests(unittest.TestCase):
    def assert_trace(self,trace,summary=False):
        self.assertEqual(trace['input_protocol'],'single_task_tool_feedback_v1')
        first=trace['steps'][0]['messages_sent_to_model']
        self.assertEqual([m['role'] for m in first],['system','user'])
        initial=json.loads(first[1]['content'].split('Initial environment state:\n')[1])
        for i,step in enumerate(trace['steps']):
            messages=step['messages_sent_to_model']
            self.assertEqual(messages[:2],first)
            self.assertEqual(sum(m['role']=='user' for m in messages),1)
            self.assertEqual(sum(m['role']=='system' for m in messages),1)
            self.assertNotIn('Falcon',str(messages));self.assertNotIn('What rule',str(messages))
            self.assertNotIn('NEVER_FEED_THIS',str(messages))
            if not summary:self.assertEqual([m['role'] for m in messages],['system','user']+['assistant','tool']*i)
            if i:
                self.assertEqual(messages[-1]['role'],'tool')
                self.assertEqual(messages[-1]['tool_call_id'],messages[-2]['tool_calls'][0]['id'])
                self.assertEqual(json.loads(messages[-1]['content']),trace['steps'][i-1]['result']['public'])
            observation=initial if i==0 else json.loads(messages[-1]['content'])['observation']
            self.assertEqual(observation.get('steps_remaining',observation.get('tool_calls_remaining')),
                             step['state_before'].get('steps_remaining',4-step['state_before'].get('calls',0)))
        self.assertTrue(trace['metrics']['task_success'])


    def test_bash_natural_and_summary(self):
        for memory in ('full','summary'):
            trace=run_episode(Config(domain='bash',memory=memory,max_decisions=4),BashStub(),ReferenceClient('bash'),BASH_TOOLS,Counter())
            self.assert_trace(trace,memory=='summary')
            self.assertEqual(trace['steps'][-1]['result']['public']['observation']['tool_calls_remaining'],0)

if __name__=='__main__':unittest.main()
