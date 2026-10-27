import json
import unittest
from copy import deepcopy
from experiments.keyrooms.core import generate,Scene
from experiments.keyrooms.environment import KeyRooms
from experiments.keyrooms_intent import CONDITIONS,run_condition
from experiments.keyrooms.run import run

class MatrixTests(unittest.TestCase):
    def test_hidden_observer_cutoff_and_compact_resume(self):
        data=generate(0,kind='structural_conflict').data;data['rule']=CONDITIONS['positive_method'];scene=Scene(data)
        class Turns:
            config={}
            def __init__(self):self.n=0
            def complete(self,messages,tools):
                self.n+=1
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.n),'type':'function','function':{'name':'step','arguments':'{"action":"left"}'}}]}
        client=Turns();trace=run_condition(scene,client,None,'positive_method',observer_limit=5,compact=True)
        self.assertEqual(client.n,5);self.assertEqual(trace['status'],'observer_limit');self.assertFalse(trace['success'])
        self.assertNotIn('steps_remaining',trace['steps'][-1]['result']['public']['observation'])
        self.assertFalse(trace['steps'][-1]['result']['public']['done'])
        self.assertNotIn('budget is exhausted',json.dumps(trace['initial_input']))
        self.assertNotIn('observer_limit',json.dumps(trace['initial_input']))
        self.assertNotIn('messages',trace['steps'][0]);self.assertIn('input_sha256',trace['steps'][0])
        class NoCalls:
            config={}
            def complete(self,*a):raise AssertionError('Replay must not call model')
        replay=run_condition(scene,NoCalls(),None,'positive_method',replay_steps=trace['steps'],observer_limit=5,compact=True)
        self.assertEqual(replay['status'],'observer_limit')
        altered=deepcopy(trace['steps']);altered[0]['input_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'input hash'):run_condition(scene,NoCalls(),None,'positive_method',replay_steps=altered,observer_limit=5,compact=True)

    def test_invalid_calls_count_toward_observer_limit(self):
        class Invalid:
            config={}
            def complete(self,*a):return {'role':'assistant','content':'I cannot proceed.'}
        trace=run(generate(0),Invalid(),None,observer_limit=3,compact=True)
        self.assertEqual(trace['status'],'observer_limit')
        self.assertEqual(len(trace['steps']),3)
        self.assertTrue(all(r['result']['audit']['protocol_rejection'] for r in trace['steps']))
