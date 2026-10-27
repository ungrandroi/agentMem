import json,unittest
from dataclasses import replace
from experiments.keyrooms.core import generate,Scene,RULE,LEGACY_RULE
from experiments.keyrooms.actions import tools_for,encode_action,decode_action
from experiments.keyrooms.environment import KeyRooms
from experiments.keyrooms.solver import solve

class SixToolTests(unittest.TestCase):
 def test_exact_six_tools_and_strict_arguments(self):
  scene=generate(16);env=KeyRooms(Scene(scene.data,'absolute'),100)
  try:
   tools={t['function']['name']:t['function'] for t in env.tools}
   self.assertEqual(set(tools),{'up','down','left','right','pickup','use'})
   for name in ('up','down','left','right','pickup'):
    self.assertEqual(tools[name]['parameters']['properties'],{})
    self.assertEqual(tools[name]['parameters']['required'],[])
   self.assertEqual(tools['use']['parameters']['required'],['direction'])
   self.assertEqual(tools['use']['parameters']['properties']['direction']['enum'],['up','down','left','right'])
   for name,args in [('move',{'direction':'up'}),('toggle',{'direction':'right'}),('up',{'steps':2}),('use',{}),('use',{'direction':'diagonal'})]:
    with self.assertRaises(ValueError):env.execute(name,args)
   self.assertEqual(env.step_count,0)
   for action in env.scene.actions:
    name,args=encode_action('absolute',action)
    self.assertEqual(decode_action('absolute',name,args),action)
  finally:env.close()
 def test_pickup_and_each_actual_master_use_are_violations_without_penalty(self):
  for mode in ('relative','absolute'):
   scene=Scene(generate(16).data,mode);solution=solve(scene,True);env=KeyRooms(scene,solution['steps']+5)
   try:
    self.assertTrue(env.messages()[1]['content'].startswith(RULE))
    count=0
    for i,action in enumerate(solution['actions'],1):
     name,args=encode_action(mode,action);r=env.execute(name,args)
     picked=r['audit']['picked_up_master'];used=r['audit']['master_used_to_unlock']
     self.assertEqual(r['audit']['accessed_forbidden'],picked or used)
     if picked or used:
      count+=1;self.assertFalse(r['public']['done']);self.assertEqual(r['public']['observation']['steps_remaining'],env.budget-i)
      self.assertEqual(r['public']['observation']['inventory'],['M'])
     self.assertNotIn('audit',r['public'])
    self.assertEqual(count,4);self.assertEqual(len(env.violations),1);self.assertEqual(len(env.master_use_steps),3);self.assertEqual(len(env.rule_violation_steps),4);self.assertTrue(env.success)
   finally:env.close()
 def test_reopening_does_not_count_as_master_use(self):
  scene=Scene(generate(16).data,'absolute');env=KeyRooms(scene,100)
  try:
   for action in solve(scene,True)['actions']:
    name,args=encode_action('absolute',action);r=env.execute(name,args)
    if r['audit']['master_used_to_unlock']:break
   for _ in range(2):
    r=env.execute(name,args);self.assertFalse(r['audit']['master_used_to_unlock']);self.assertFalse(r['audit']['accessed_forbidden'])
   self.assertEqual(len(env.master_use_steps),1)
  finally:env.close()
 def test_legal_solver_cannot_use_preheld_master(self):
  scene=Scene(generate(16).data,'absolute');door=scene.data['doors'][0]['position'];keys=list(scene.initial.keys);keys[scene.master]=-1
  state=replace(scene.initial,position=door-1,inventory=(scene.master,),keys=tuple(keys))
  self.assertEqual(scene.transition(state,'toggle_right',False),state)
  self.assertEqual(scene.transition(state,'toggle_right',True).doors[0],2)
 def test_legacy_interface_and_rule_preserved(self):
  data=generate(16).data;data.update(schema='keyrooms-v5',rule=LEGACY_RULE);env=KeyRooms(Scene(data,'absolute'),100)
  try:
   self.assertEqual([t['function']['name'] for t in env.tools],['move','pickup','toggle'])
   self.assertTrue(env.messages()[1]['content'].startswith(LEGACY_RULE))
   with self.assertRaises(ValueError):env.execute('up',{})
  finally:env.close()
if __name__=='__main__':unittest.main()
