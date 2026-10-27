"""Concurrent, resumable episodes with one operation per model decision."""
import argparse,fcntl,json,os,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor,as_completed
from copy import deepcopy
from pathlib import Path
from .core import Scene
from .openrouter import OpenRouterClient,APIRequestError
from .prepare_batch import source_hashes
from .pilot import save
from .run import run

class Ledger:
 def __init__(self,root,max_calls,spend_limit):
  self.path=root/'requests.jsonl';self.lock=threading.Lock();self.stop=threading.Event();self.calls=0;self.cost=0.;self.unpriced=0;self.pending=set();self.max_calls=max_calls;self.spend_limit=spend_limit
  if self.path.exists():
   for row in read_jsonl(self.path):
    if row['event']=='started':self.calls+=1;self.pending.add(row['request'])
    else:
     self.pending.discard(row['request']);self.cost+=float(row.get('metadata',{}).get('usage',{}).get('cost') or 0)
     if row.get('metadata',{}).get('id') and row.get('metadata',{}).get('usage',{}).get('cost') is None:self.unpriced+=1
  self.orphaned_requests=sorted(self.pending)
 def append(self,row):
  with self.path.open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
 def begin(self,episode):
  with self.lock:
   if self.stop.is_set():raise RuntimeError('Batch paused')
   if (self.max_calls is not None and self.calls>=self.max_calls) or self.cost>=self.spend_limit or self.unpriced:
    self.stop.set();raise RuntimeError('Batch request/spend accounting limit reached')
   request=uuid.uuid4().hex;self.calls+=1;self.pending.add(request)
   self.append({'event':'started','request':request,'episode':episode,'unix':time.time()});return request
 def finish(self,request,episode,metadata,error):
  with self.lock:
   self.pending.discard(request);self.cost+=float(metadata.get('usage',{}).get('cost') or 0)
   if metadata.get('id') and metadata.get('usage',{}).get('cost') is None:self.unpriced+=1;self.stop.set()
   self.append({'event':'finished','request':request,'episode':episode,'unix':time.time(),'metadata':metadata,'error':error})
 def snapshot(self):
  with self.lock:return {'requests':self.calls,'reported_cost_usd':self.cost,'spend_limit_usd':self.spend_limit,'unpriced_responses':self.unpriced,'in_flight':len(self.pending),'orphaned_requests_on_resume':self.orphaned_requests}

class MeteredClient:
 def __init__(self,ledger,episode,model):
  self.client=OpenRouterClient(Path(__file__).resolve().parents[2]/'agent/keys.md',model,max_calls=ledger.max_calls,spend_limit_usd=ledger.spend_limit)
  self.ledger=ledger;self.episode=episode;self.config={**self.client.config,'limit_scope':'whole batch'};self.last_metadata={}
 def complete(self,messages,tools):
  self.last_metadata={};request=self.ledger.begin(self.episode);error=None
  try:return self.client.complete(messages,tools)
  except Exception as exc:
   error=str(exc)
   if isinstance(exc,APIRequestError) and exc.info['scope']=='batch':self.ledger.stop.set()
   raise
  finally:
   self.last_metadata=deepcopy(self.client.last_metadata)
   self.ledger.finish(request,self.episode,self.last_metadata,error)

def read_jsonl(path):
 # Preserve a torn final write for audit, then recover only complete records.
 raw=path.read_bytes();lines=raw.splitlines(keepends=True);rows=[];valid=0
 for i,line in enumerate(lines):
  try:rows.append(json.loads(line))
  except (ValueError,UnicodeDecodeError):
   if i!=len(lines)-1:raise
   path.with_name(path.name+f'.torn-{time.time_ns()}').write_bytes(raw)
   path.write_bytes(raw[:valid]);break
  valid+=len(line)
 else:
  if raw and not raw.endswith(b'\n'):path.write_bytes(raw+b'\n')
 return rows

def failure_info(trace):
 if trace['status']!='api_error':return None
 row=trace['steps'][-1];info=row.get('api_metadata',{}).get('error')
 if info:return info
 # Old generation-limit traces already retried the identical request four times.
 if 'Generation limit reached' in row.get('error',''):
  return {'kind':'generation_limit','scope':'episode','retryable':False,'message':row['error']}
 return {'kind':'legacy_or_unclassified','scope':'episode','retryable':True,'message':row.get('error','')}

def check_sources(root,manifest):
 current=source_hashes();original=manifest['source_sha256']
 if original==current:return
 revision_path=root/'scheduler-revision.json'
 if revision_path.exists():
  revision=json.loads(revision_path.read_text())
  changed={p for p in original.keys()|current.keys() if original.get(p)!=current.get(p)}
  allowed={'experiments/keyrooms/batch.py','experiments/keyrooms/openrouter.py'}
  if revision.get('runner_policy')=='feedback_until_budget':allowed.add('experiments/keyrooms/run.py')
  if revision.get('from_sha256')==original and revision.get('to_sha256')==current and changed<=allowed:return
 raise RuntimeError('Source changed since preparation; only an audited scheduler/client revision may resume this batch')

def summarize(case,trace):
 steps=[r for r in trace['steps'] if 'error' not in r]
 return {k:case[k] for k in ('name','scene_name','action_mode','pressure','pressure_aliases','budget')} | {
  'error_info':failure_info(trace),'status':trace['status'],'success':trace['success'],'decisions':len(steps),'master_pickup_steps':trace['master_pickup_steps'],
  'master_use_steps':trace.get('master_use_steps',[]),'rule_violation_steps':trace.get('rule_violation_steps',trace['master_pickup_steps']),'violated':bool(trace.get('rule_violation_steps',trace['master_pickup_steps'])),'ineffective_actions':sum(r.get('result',{}).get('public',{}).get('changed') is False for r in steps),
  'protocol_errors':sum(r.get('result',{}).get('audit',{}).get('protocol_rejection',False) for r in steps),
  'visited_rooms':sorted({r.get('result',{}).get('public',{}).get('observation',{}).get('room',1) for r in steps}|{1}),
  'decision_cost_usd':sum(float(r.get('api_metadata',{}).get('usage',{}).get('cost') or 0) for r in steps)}

def episode(root,case,data,ledger,model):
 name=case['name'];dest=root/'episodes'/(name+'.json');partial=root/'episodes'/(name+'.partial.jsonl');progress=root/'status'/(name+'.json')
 if dest.exists():
  trace=json.loads(dest.read_text())
  if trace['status'] not in ('api_error','protocol_error_limit') or (trace['status']=='api_error' and not failure_info(trace)['retryable']):return summarize(case,trace)
 if ledger.stop.is_set():return None
 client=MeteredClient(ledger,name,model)
 if partial.exists():replay=read_jsonl(partial)
 elif dest.exists():replay=json.loads(dest.read_text())['steps']
 else:replay=[]
 replay=[r for r in replay if 'error' not in r]
 if dest.exists():dest.rename(root/'interruptions'/(name+f'-{time.time_ns()}.json'))
 for attempt in range(4):
  if ledger.stop.is_set():return None
  # Reconstruct identical messages and state; only new decisions call the API.
  temporary=partial.with_suffix('.tmp');temporary.write_text(''.join(json.dumps(r)+'\n' for r in replay));temporary.replace(partial)
  def checkpoint(row):
   with partial.open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
   save(progress,{'episode':name,'stage':'running' if 'error' not in row else 'api_error','decisions':row['t']+int('error' not in row),'budget':case['budget'],'updated_unix':time.time()})
  save(progress,{'episode':name,'stage':'starting','decisions':len(replay),'budget':case['budget'],'updated_unix':time.time()})
  trace=run(Scene(data,case['action_mode']),client,case['budget'],checkpoint,replay_steps=replay)
  if trace['status']!='api_error':break
  failure=trace['steps'][-1]
  with (root/'interruptions'/(name+'.jsonl')).open('a') as f:f.write(json.dumps({k:failure[k] for k in ('t','error','api_metadata')})+'\n')
  replay=[r for r in trace['steps'] if 'error' not in r]
  if ledger.stop.is_set() or not failure_info(trace)['retryable']:break
  if attempt<3:time.sleep(10)
 save(dest,trace)
 if partial.exists():partial.unlink()
 result=summarize(case,trace);save(progress,{**result,'stage':'finished','updated_unix':time.time()})
 print(json.dumps(result),flush=True);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--spend-limit-usd',type=float,default=200);p.add_argument('--limit',type=int);a=p.parse_args()
 root=Path(a.output).resolve()
 with (root/'worker.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if (root/'superseded.json').exists():raise RuntimeError('This batch uses superseded key semantics; use the replacement batch')
  manifest=json.loads((root/'manifest.json').read_text())
  check_sources(root,manifest)
  for directory in ('episodes','status','interruptions'):(root/directory).mkdir(exist_ok=True)
  cases=manifest['cases'][:a.limit];scenes={s['name']:s['scene'] for s in manifest['scenes']}
  max_calls=None if any(c['budget'] is None for c in manifest['cases']) else sum(c['budget'] for c in manifest['cases'])+10*len(manifest['cases'])
  ledger=Ledger(root,max_calls,a.spend_limit_usd)
  if ledger.orphaned_requests:print(json.dumps({'warning':'Requests interrupted before response logging; possible unreported charges','request_ids':ledger.orphaned_requests}),flush=True)
  results=[]
  def progress(stage):
   ordered=sorted(results,key=lambda x:x['name']);save(root/'summary.json',ordered)
   save(root/'progress.json',{'stage':stage,'pid':os.getpid(),'workers':a.workers,'total_episodes':len(manifest['cases']),'selected_episodes':len(cases),'recorded_episodes':len(results),'completed_episodes':sum(r['status']!='api_error' for r in results),**ledger.snapshot(),'updated_unix':time.time()})
  progress('running')
  with ThreadPoolExecutor(max_workers=a.workers) as pool:
   pending={pool.submit(episode,root,c,scenes[c['scene_name']],ledger,manifest['model']):c for c in cases}
   try:
    for future in as_completed(pending):
     result=future.result()
     if result:results.append(result)
     progress('running')
   except BaseException:
    ledger.stop.set();progress('worker_error');raise
  all_processed=len(results)==len(cases) and not ledger.stop.is_set()
  errors=sum(r['status']=='api_error' for r in results)
  stage=('finished_with_errors' if errors else 'finished') if all_processed and len(cases)==len(manifest['cases']) else 'gate_finished' if all_processed and not errors else 'paused_with_errors'
  progress(stage)
  if stage in ('finished','finished_with_errors'):save(root/'completed.json',{'stage':stage,'episodes':len(results),'valid_episodes':len(results)-errors,'api_error_episodes':errors,**ledger.snapshot(),'completed_unix':time.time()})
  print(json.dumps({'stage':stage,**ledger.snapshot()}),flush=True)
if __name__=='__main__':main()
