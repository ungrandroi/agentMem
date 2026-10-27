import json
import unittest
from copy import deepcopy
from experiments.keyrooms.core import generate,Scene
from experiments.keyrooms.environment import KeyRooms
from experiments.keyrooms.actions import encode_action
from experiments.keyrooms.solver import solve
from experiments.keyrooms_intent import CONDITIONS,run_condition

class IntentTests(unittest.TestCase):
    def test_matched_prompt_and_physical_behavior(self):
        data=generate(0,kind='structural_conflict').data
        actions=solve(Scene(data),True)['actions']
        class Client:
            config={'client':'scripted'}
            def __init__(self):self.i=0
            def complete(self,messages,tools):
                action=actions[self.i];self.i+=1;name,args=encode_action('relative',action)
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.i),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        traces=[];inputs=[]
        for condition,instruction in CONDITIONS.items():
            d=deepcopy(data);d['rule']=instruction;scene=Scene(d)
            env=KeyRooms(scene,len(actions)+1)
            try:inputs.append((env.messages(),env.tools))
            finally:env.close()
            trace=run_condition(scene,Client(),len(actions)+1,condition);traces.append(trace)
            self.assertTrue(trace['success'])
            self.assertTrue(trace['master_pickup_steps'])
            self.assertTrue(trace['master_use_steps'])
        self.assertEqual(inputs[0][1],inputs[1][1])
        self.assertEqual(inputs[0][0][1]['content'].split('\n',1)[1],inputs[1][0][1]['content'].split('\n',1)[1])
        self.assertEqual([x['state_after'] for x in traces[0]['steps']],[x['state_after'] for x in traces[1]['steps']])
        self.assertEqual(traces[0]['instruction_deviation_steps'],traces[0]['master_use_steps'])
        self.assertEqual(traces[0]['rule_violation_steps'],[])
        self.assertGreater(len(traces[1]['instruction_deviation_steps']),len(traces[0]['instruction_deviation_steps']))
        pickup=traces[0]['steps'][traces[0]['master_pickup_steps'][0]-1]['result']['audit']
        self.assertFalse(pickup['instruction_deviation'])
        self.assertNotIn('accessed_forbidden',pickup)
        class NoCalls:
            config={}
            def complete(self,*args):raise AssertionError('Unexpected API call')
        d=deepcopy(data);d['rule']=CONDITIONS['positive_method']
        replay=run_condition(Scene(d),NoCalls(),len(actions)+1,'positive_method',replay_steps=traces[0]['steps'])
        self.assertEqual(replay['instruction_deviation_steps'],traces[0]['instruction_deviation_steps'])
