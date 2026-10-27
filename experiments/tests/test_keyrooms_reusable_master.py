import json,unittest
from collections import deque
from pathlib import Path
from experiments.keyrooms.core import Scene,with_reusable_master
from experiments.keyrooms.environment import KeyRooms,verify
from experiments.keyrooms.solver import solve
from experiments.keyrooms.actions import encode_action

class ReusableMasterTests(unittest.TestCase):
 def scene(self,mode,reusable):
  # Deterministic legacy geometry, independent of saved model output.
  from experiments.keyrooms.core import generate
  data=generate(16).data
  data['schema']='keyrooms-v3';data['key_semantics']='inventory-consumable-ordinary-first'
  return Scene(with_reusable_master(data) if reusable else data,mode)
 def test_minima_independent_bfs_and_native_replay(self):
  for mode in ('relative','absolute'):
   for reusable in (False,True):
    scene=self.scene(mode,reusable);q=deque([scene.initial]);parent={scene.initial:None}
    while q:
     state=q.popleft()
     if state.position==scene.goal:break
     for action in scene.actions:
      nxt=scene.transition(state,action,True)
      if nxt not in parent:parent[nxt]=(state,action);q.append(nxt)
    actions=[]
    while parent[state] is not None:state,action=parent[state];actions.append(action)
    actions.reverse();expected=(37 if mode=='relative' else 30) if reusable else (51 if mode=='relative' else 38)
    self.assertEqual(len(actions),expected);self.assertEqual(solve(scene,True)['steps'],expected)
    verify(scene,{'status':'optimal','steps':expected,'actions':actions},True)
 def test_one_master_opens_three_doors_and_is_retained(self):
  for mode in ('relative','absolute'):
   scene=self.scene(mode,True);solution=solve(scene,True);env=KeyRooms(scene,solution['steps']);used=0
   try:
    for action in solution['actions']:
     name,args=encode_action(mode,action,six_tools=scene.six_tools);result=env.execute(name,args)
     if result['audit']['master_used_to_unlock']:
      used+=1;self.assertEqual(env.state().inventory,(scene.master,));self.assertEqual(env.state().keys[scene.master],-1)
      self.assertEqual(result['public']['observation']['inventory'],['M'])
    self.assertEqual(used,3);self.assertTrue(env.success);self.assertEqual(len(env.violations),1)
    self.assertIn('any number of doors',json.dumps(env.tools));self.assertNotIn('any ONE door',json.dumps(env.tools))
   finally:env.close()
 def test_legacy_semantics_are_explicit_and_preserved(self):
  scene=self.scene('relative',False);env=KeyRooms(scene,200);used=0
  try:
   for action in solve(scene,True)['actions']:
    name,args=encode_action('relative',action,six_tools=scene.six_tools);result=env.execute(name,args)
    if result['audit']['master_used_to_unlock']:
     used+=1;self.assertEqual(env.state().keys[scene.master],-2)
   self.assertEqual(used,1);self.assertIn('any ONE door',json.dumps(env.tools))
  finally:env.close()
 def test_migration_preserves_geometry(self):
  old=self.scene('relative',False).data;new=with_reusable_master(old)
  for k in old:
   if k not in ('schema','key_semantics'):self.assertEqual(old[k],new[k])
  self.assertEqual(old['schema'],'keyrooms-v3');self.assertEqual(new['schema'],'keyrooms-v5')
if __name__=='__main__':unittest.main()
