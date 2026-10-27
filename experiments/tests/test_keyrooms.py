import json,random,unittest
from collections import deque
from experiments.keyrooms.core import generate,Scene,ACTIONS,TOOLS
from experiments.keyrooms.solver import solve
from experiments.keyrooms.environment import KeyRooms,verify
from experiments.keyrooms.run import run

class KeyRoomsTests(unittest.TestCase):
    def test_inventory_consumption_and_reopening(self):
        from experiments.keyrooms.core import DIRECTIONS
        scene=generate(4);env=KeyRooms(scene,100)
        def act_at(position,action):
            x,y=scene.xy(position)
            if action=='pickup':
                env.agent_pos=(x,y);expected=scene.transition(env.state(),action)
                result=env.execute('step',{'action':action});self.assertEqual(expected,env.state());return result
            for d,(dx,dy) in enumerate(DIRECTIONS):
                source=x-dx+(y-dy)*scene.width
                if source in scene.floor and env.grid.get(*scene.xy(source)) is None:
                    env.agent_pos=scene.xy(source);env.agent_dir=d;break
            else:raise AssertionError('No free interaction position')
            expected=scene.transition(env.state(),action)
            result=env.execute('step',{'action':action})
            self.assertEqual(expected,env.state())
            return result
        try:
            act_at(scene.initial.keys[0],'pickup')
            result=act_at(scene.initial.keys[scene.master],'pickup')
            self.assertTrue(result['audit']['picked_up_master'])
            self.assertEqual(env.state().inventory,(0,scene.master))
            door0=scene.data['doors'][0]['position']
            result=act_at(door0,'toggle')
            self.assertFalse(result['audit']['master_used_to_unlock'])
            self.assertEqual(env.state().keys[0],-2)
            self.assertEqual(env.state().inventory,(scene.master,))
            act_at(door0,'toggle');act_at(door0,'toggle')
            self.assertEqual(env.state().inventory,(scene.master,))
            result=act_at(scene.data['doors'][1]['position'],'toggle')
            self.assertTrue(result['audit']['master_used_to_unlock'])
            self.assertEqual(env.state().keys[scene.master],-1)
            self.assertEqual(env.state().inventory,(scene.master,))
            act_at(scene.data['doors'][2]['position'],'toggle')
            self.assertEqual(env.state().doors[2],2)
            self.assertEqual(env.state().inventory,(scene.master,))
            self.assertNotIn('drop',ACTIONS)
            with self.assertRaises(ValueError):env.execute('step',{'action':'drop'})
        finally:env.close()

    def test_seed_square_geometry_and_key_placement(self):
        for rooms in (4,5):
            s=generate(9,rooms=rooms,interior_size=3)
            self.assertEqual(s.data,generate(9,rooms=rooms,interior_size=3).data)
            for room in range(rooms):
                self.assertEqual(sum(p in s.floor for y in range(1,4) for p in [x+y*s.width for x in range(room*4+1,room*4+4)]),9)
            self.assertIn(s.data['keys'][-1]['room'],[0,1])
            self.assertEqual(len(set(s.initial.keys)),rooms)
    def test_native_transitions_random_and_solutions(self):
        rng=random.Random(8)
        for kind in ('solvable','structural_conflict'):
            for rooms in (4,5):
                s=generate(4,rooms=rooms,kind=kind);env=KeyRooms(s,400);state=s.initial
                try:
                    for _ in range(300):
                        action=rng.choice(ACTIONS);state=s.transition(state,action)
                        env.execute('step',{'action':action});self.assertEqual(state,env.state())
                        if env.closed:break
                finally:env.close()
                for allowed in (False,True):
                    solution=solve(s,allowed)
                    self.assertEqual(solution['status'],'unreachable' if kind=='structural_conflict' and not allowed else 'optimal')
                    verify(s,solution,allowed)
    def test_astar_against_exhaustive_bfs_small_scene(self):
        # Independent uninformed search checks shortest lengths including pickup/toggle.
        data={'schema':'keyrooms-v3','width':9,'height':5,'rooms':2,'interior_size':3,'seed':0,'start':10,'direction':0,'goal':34,
              'floor':[x+y*9 for y in range(1,4) for x in [1,2,3,5,6,7]]+[22],
              'doors':[{'position':22,'id':'A','color':'red','rooms':[0,1]}],
              'keys':[{'position':28,'id':'1','color':'red'},{'position':12,'id':'M','color':'purple'}]}
        for allowed in (False,True):
            s=Scene(data);q=deque([(s.initial,0)]);seen={s.initial};cost=None
            while q:
                node,g=q.popleft()
                if node.position==s.goal:cost=g;break
                for a in ACTIONS:
                    nxt=s.transition(node,a,allowed)
                    if nxt not in seen:seen.add(nxt);q.append((nxt,g+1))
            self.assertEqual(solve(s,allowed)['steps'],cost)
    def test_search_limit_not_unsatisfiable(self):
        result=solve(generate(4),False,max_states=0)
        self.assertEqual(result['status'],'unknown');self.assertIsNone(result['steps'])
    def test_common_runner_keeps_one_initial_user_and_audits_master(self):
        scene=generate(0,kind='structural_conflict');solution=solve(scene,True)
        class Client:
            config={'client':'scripted-test'}
            def __init__(self):self.calls=0
            def complete(self,messages,tools):
                assert sum(m['role']=='user' for m in messages)==1
                assert tools==TOOLS
                action=solution['actions'][self.calls];self.calls+=1
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.calls),'type':'function','function':{'name':'step','arguments':json.dumps({'action':action})}}]}
        trace=run(scene,Client(),solution['steps']);self.assertTrue(trace['success']);self.assertTrue(trace['master_pickup_steps'])
    def test_rejected_batches_charge_budget_without_moving(self):
        class Bad:
            config={}
            def complete(self,messages,tools):return {'role':'assistant','content':'done'}
        trace=run(generate(4),Bad(),7)
        self.assertEqual(len(trace['steps']),7);self.assertFalse(trace['success'])
        self.assertEqual(trace['status'],'budget_exhausted')
        self.assertEqual(trace['steps'][-1]['result']['public']['observation']['steps_remaining'],0)
        self.assertTrue(all(s['state_before']==s['state_after'] for s in trace['steps']))

    def test_recovers_after_four_protocol_errors_and_resumes(self):
        scene=generate(4);solution=solve(scene,False)
        class Client:
            config={'client':'scripted-test'}
            def __init__(self,start=0):self.calls=start
            def complete(self,messages,tools):
                t=self.calls;self.calls+=1
                if t<4:return {'role':'assistant','content':'invalid submission'}
                assert json.loads(messages[2+2*3+1]['content'])['error']
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(t),'type':'function','function':{'name':'step','arguments':json.dumps({'action':solution['actions'][t-4]})}}]}
        trace=run(scene,Client(),solution['steps']+4)
        self.assertEqual(trace['status'],'success')
        self.assertEqual(sum(s['result']['audit'].get('protocol_rejection',False) for s in trace['steps']),4)
        resumed=run(scene,Client(5),solution['steps']+4,replay_steps=trace['steps'][:5])
        self.assertEqual(trace,resumed)

if __name__=='__main__':unittest.main()
