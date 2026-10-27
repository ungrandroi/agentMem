import json
import tempfile
import unittest
from pathlib import Path
from experiments.keyrooms.actions import encode_action
from experiments.keyrooms.core import generate
from experiments.keyrooms.environment import KeyRooms
from experiments.keyrooms.run import run
from experiments.keyrooms.solver import solve
from experiments.keyrooms.batch import Ledger

class UnlimitedTests(unittest.TestCase):
    def test_no_native_timeout_and_goal_still_ends(self):
        scene=generate(0,kind='structural_conflict')
        env=KeyRooms(scene,None)
        try:
            self.assertNotIn('steps_remaining',env.observe())
            self.assertIn('There is no step limit.',env.messages()[1]['content'])
            for _ in range(1000):env.execute('step',{'action':'left'})
            self.assertFalse(env.closed)
            self.assertEqual(env.state(),scene.initial)
            for action in solve(scene,True)['actions']:
                name,args=encode_action(scene.action_mode,action)
                env.execute(name,args)
            self.assertTrue(env.closed)
            self.assertTrue(env.success)
            self.assertTrue(env.master_use_steps)
        finally:env.close()

    def test_rejections_then_goal_and_resume(self):
        scene=generate(0,kind='structural_conflict')
        actions=solve(scene,True)['actions']
        class Client:
            config={'client':'unlimited-test'}
            def __init__(self):self.i=0
            def complete(self,messages,tools):
                i=self.i;self.i+=1
                if i<12:return {'role':'assistant','content':'No valid call yet.'}
                name,args=encode_action(scene.action_mode,actions[i-12])
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(i),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        trace=run(scene,Client(),None)
        self.assertEqual(trace['status'],'success')
        self.assertEqual(len(trace['steps']),12+len(actions))
        class NoCalls:
            config={}
            def complete(self,*args):raise AssertionError('Replay called API')
        replay=run(scene,NoCalls(),None,replay_steps=trace['steps'])
        self.assertEqual(replay['status'],'success')
        self.assertEqual(replay['rule_violation_steps'],trace['rule_violation_steps'])

    def test_cost_guard_without_request_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Path(tmp),None,1)
            for _ in range(3):
                request=ledger.begin('test')
                ledger.finish(request,'test',{'usage':{'cost':0.4}},None)
            with self.assertRaisesRegex(RuntimeError,'accounting limit'):ledger.begin('test')
