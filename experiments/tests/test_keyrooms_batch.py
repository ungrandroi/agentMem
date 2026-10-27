import json,tempfile,unittest
from collections import deque
from pathlib import Path
from experiments.keyrooms.scenario_design import generate_layout,structural_checks,KINDS
from experiments.keyrooms.core import Scene
from experiments.keyrooms.solver import solve
from experiments.keyrooms.environment import KeyRooms,verify
from experiments.keyrooms.prepare_batch import pressure_budgets
from experiments.keyrooms.run import run
from experiments.keyrooms.actions import encode_action
from experiments.keyrooms.batch import read_jsonl

class BatchTests(unittest.TestCase):
 def test_new_topologies_native_replay_and_visibility(self):
  for kind in KINDS:
   for rooms in (4,5):
    data=generate_layout(7,rooms,kind).data
    for mode in ('relative','absolute'):
     scene=Scene(data,mode);structural_checks(scene)
     for allowed in (False,True):
      solution=solve(scene,allowed)
      self.assertEqual(solution['status'],'unreachable' if kind=='structural_conflict' and not allowed else 'optimal')
      verify(scene,solution,allowed)
     for room,b in enumerate(data['room_bounds']):
      from dataclasses import replace
      state=replace(scene.initial,position=b['x']+1+(b['y']+1)*scene.width)
      rows=scene.rows(state,room);self.assertEqual(len(rows),7);self.assertTrue(all(len(r)==7 for r in rows))
 def test_tree_solver_against_independent_bfs(self):
  for kind in ('backtracking','branching','structural_conflict'):
   for mode in ('relative','absolute'):
    scene=Scene(generate_layout(3,4,kind,interior_size=2).data,mode)
    for allowed in (False,True):
     q=deque([(scene.initial,0)]);seen={scene.initial};minimum=None
     while q:
      state,g=q.popleft()
      if state.position==scene.goal:minimum=g;break
      for action in scene.actions:
       nxt=scene.transition(state,action,allowed)
       if nxt not in seen:seen.add(nxt);q.append((nxt,g+1))
     result=solve(scene,allowed);self.assertEqual(result['steps'],minimum,(kind,mode,allowed))
 def test_budgets_and_aliases(self):
  self.assertEqual([p['budget'] for p in pressure_budgets(None,21)],[84,42,21])
  self.assertEqual([p['budget'] for p in pressure_budgets(45,33)],[90,68,45,39,33])
  self.assertEqual(pressure_budgets(34,33)[-1]['pressure_aliases'],['budget_conflict','extreme'])
 def test_resume_preserves_history_and_actions(self):
  scene=Scene(generate_layout(2,4,'backtracking').data,'absolute');actions=solve(scene,True)['actions']
  class Client:
   config={'client':'test'}
   def __init__(self,start=0):self.index=start
   def complete(self,messages,tools):
    name,args=encode_action('absolute',actions[self.index]);self.index+=1
    return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.index),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
  first=Client();trace=run(scene,first,len(actions)+1)
  resumed=Client(5);again=run(scene,resumed,len(actions)+1,replay_steps=trace['steps'][:5])
  self.assertEqual(trace,again);self.assertTrue(again['success']);self.assertTrue(again['master_pickup_steps'])
 def test_torn_final_checkpoint(self):
  with tempfile.TemporaryDirectory() as root:
   p=Path(root)/'trace.jsonl';p.write_bytes(b'{"t":0}\n{"t":')
   self.assertEqual(read_jsonl(p),[{'t':0}]);self.assertEqual(p.read_text(),'{"t":0}\n')
   self.assertEqual(len(list(Path(root).glob('*.torn-*'))),1)
if __name__=='__main__':unittest.main()
