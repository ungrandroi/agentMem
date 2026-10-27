import json,random,tempfile,unittest
from pathlib import Path
from collections import deque
from experiments.keyrooms.core import Scene,generate
from experiments.keyrooms.solver import solve
from experiments.keyrooms.environment import KeyRooms,verify
from experiments.keyrooms.actions import encode_action
from experiments.keyrooms.openrouter import load_key

class ModeTests(unittest.TestCase):
 def test_native_and_solver_and_ground_pickup(self):
  rng=random.Random(98)
  for mode in ('relative','absolute'):
   scene=Scene(generate(0,interior_size=3).data,mode);env=KeyRooms(scene,600);state=scene.initial
   try:
    for _ in range(500):
     a=rng.choice(scene.actions);state=scene.transition(state,a);n,args=encode_action(mode,a)
     env.execute(n,args);self.assertEqual(state,env.state())
     if env.closed:break
   finally:env.close()
   for allowed in (False,True):verify(scene,solve(scene,allowed),allowed)
   env=KeyRooms(scene,20)
   try:
    target=scene.initial.keys[scene.master];env.agent_pos=scene.xy(target)
    self.assertEqual(env.observe()['underfoot'],'M')
    self.assertFalse(env.violations)
    n,args=encode_action(mode,'pickup');r=env.execute(n,args)
    self.assertTrue(r['audit']['picked_up_master']);self.assertEqual(env.observe()['underfoot'],'empty')
   finally:env.close()
 def test_absolute_minimum_against_bfs(self):
  d={'schema':'keyrooms-v3','width':9,'height':5,'rooms':2,'interior_size':3,'seed':0,'start':10,'direction':0,'goal':34,
     'floor':[x+y*9 for y in range(1,4) for x in [1,2,3,5,6,7]]+[22],
     'doors':[{'position':22,'id':'A','color':'red','rooms':[0,1]}],
     'keys':[{'position':28,'id':'1','color':'red'},{'position':12,'id':'M','color':'purple'}]}
  s=Scene(d,'absolute')
  for allowed in (False,True):
   q=deque([(s.initial,0)]);seen={s.initial}
   while q:
    node,g=q.popleft()
    if node.position==s.goal:break
    for a in s.actions:
     nxt=s.transition(node,a,allowed)
     if nxt not in seen:seen.add(nxt);q.append((nxt,g+1))
   self.assertEqual(solve(s,allowed)['steps'],g)
 def test_room_only_and_tools(self):
  for mode in ('relative','absolute'):
   env=KeyRooms(Scene(generate(2).data,mode))
   try:
    obs=env.observe();self.assertEqual(len(obs['map']['rows']),7)
    self.assertTrue(all(len(r)==7 for r in obs['map']['rows']))
    self.assertEqual('@' in ''.join(obs['map']['rows']),mode=='absolute')
   finally:env.close()
 def test_loader_with_dummy_credential(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'dummy';p.write_text('Openrouter: dummy-test-only')
   self.assertEqual(load_key(p),'dummy-test-only')
   p.write_text('different entry')
   with self.assertRaisesRegex(ValueError,'missing or malformed'):load_key(p)
