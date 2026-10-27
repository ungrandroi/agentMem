import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from contextlib import redirect_stdout
from experiments.keyrooms.openrouter import http_error_info
from experiments.keyrooms.batch import main,check_sources
from experiments.keyrooms.prepare_batch import source_hashes
from experiments.keyrooms.scenario_design import generate_layout
from experiments.keyrooms.core import Scene
from experiments.keyrooms.solver import solve
from experiments.keyrooms.actions import encode_action

class SchedulerTests(unittest.TestCase):
 def test_error_details_are_bounded_and_redacted(self):
  info=http_error_info(400,{'error':{'message':'maximum context length exceeded dummy-private-secret Bearer another-token sk-test-123','metadata':{'raw':json.dumps({'error':{'message':'maximum context exceeded dummy-private-secret'}})}}},'dummy-private-secret')
  self.assertEqual(info['kind'],'context_limit');self.assertEqual(info['scope'],'episode');self.assertFalse(info['retryable'])
  for value in ('dummy-private-secret','another-token','sk-test-123'):self.assertNotIn(value,json.dumps(info))
  for code in (401,402,403,404):self.assertEqual(http_error_info(code,{},'')['scope'],'batch')
  for code in (408,429,500,502,503,504):self.assertTrue(http_error_info(code,{},'')['retryable'])
 def run_batch(self,error):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);scene=Scene(generate_layout(2,4,'backtracking').data,'absolute');actions=solve(scene,True)['actions']
   cases=[{'name':name,'scene_name':'scene','action_mode':'absolute','pressure':'loose','pressure_aliases':['loose'],'budget':len(actions)+1} for name in ('bad','good')]
   (root/'manifest.json').write_text(json.dumps({'model':'test','source_sha256':source_hashes(),'scenes':[{'name':'scene','scene':scene.data}],'cases':cases}))
   calls=[]
   def response(request,timeout):
    body=json.loads(request.data);calls.append(body)
    if len(calls)==1:
     if isinstance(error,int):raise HTTPError(request.full_url,error,'test',{},io.BytesIO(json.dumps({'error':{'message':'maximum context length exceeded'}}).encode()))
     return io.BytesIO(json.dumps({'choices':[{'finish_reason':'length','message':{'role':'assistant','content':''}}],'usage':{'cost':0.01}}).encode())
    t=sum(m['role']=='assistant' for m in body['messages']);name,args=encode_action('absolute',actions[t])
    message={'role':'assistant','content':None,'tool_calls':[{'id':str(t),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
    return io.BytesIO(json.dumps({'choices':[{'finish_reason':'tool_calls','message':message}],'usage':{'cost':0.001}}).encode())
   with patch('experiments.keyrooms.openrouter.load_key',return_value='dummy-secret'),patch('experiments.keyrooms.openrouter.urlopen',side_effect=response),patch('sys.argv',['batch','--output',str(root),'--workers','1']),redirect_stdout(io.StringIO()):
    main()
    progress=json.loads((root/'progress.json').read_text())
    if error==401:
     self.assertEqual(progress['stage'],'paused_with_errors');self.assertEqual(len(calls),1);self.assertFalse((root/'episodes/good.json').exists())
    else:
     self.assertEqual(progress['stage'],'finished_with_errors')
     done=json.loads((root/'completed.json').read_text());self.assertEqual(done['valid_episodes'],1);self.assertEqual(done['api_error_episodes'],1)
     self.assertTrue(json.loads((root/'episodes/good.json').read_text())['success'])
     count=len(calls);main();self.assertEqual(len(calls),count,'Resume must not repeat terminal errors or completed trials')
 def test_http_400_does_not_stop_other_episodes(self):self.run_batch(400)
 def test_generation_limit_not_retried(self):self.run_batch('length')
 def test_authentication_stops_batch(self):self.run_batch(401)
 def test_source_revision_cannot_change_environment(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);current=source_hashes();original=dict(current);original['experiments/keyrooms/batch.py']='old'
   manifest={'source_sha256':original}
   with self.assertRaises(RuntimeError):check_sources(root,manifest)
   (root/'scheduler-revision.json').write_text(json.dumps({'from_sha256':original,'to_sha256':current}));check_sources(root,manifest)
   original['experiments/keyrooms/environment.py']='different'
   (root/'scheduler-revision.json').write_text(json.dumps({'from_sha256':original,'to_sha256':current}))
   with self.assertRaises(RuntimeError):check_sources(root,manifest)
if __name__=='__main__':unittest.main()
