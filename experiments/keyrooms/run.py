"""Same messages and tools for a local server or remote compatible API."""
import argparse,json,hashlib
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from agent.client import HTTPClient
from agent.loop import validate_response
from .core import Scene
from .actions import decode_action
from .environment import KeyRooms

def input_digest(row):
    return hashlib.sha256(json.dumps({'messages':row['messages'],'tools':row['tools']},sort_keys=True).encode()).hexdigest()

def compact_row(row):
    row['input_sha256']=input_digest(row)
    row.pop('messages');row.pop('tools')

def run(scene,client,budget,checkpoint=None,replay_steps=None,*,observer_limit=None,compact=False):
    env=KeyRooms(scene,budget);messages=env.messages();KeyRooms_initial_messages=deepcopy(messages);steps=[];status='budget_exhausted';replay_steps=replay_steps or []
    try:
        while not env.closed:
            if observer_limit is not None and env.step_count>=observer_limit:
                status='observer_limit';break
            row={'t':len(steps),'state_before':asdict(env.state()),'messages':deepcopy(messages),'tools':deepcopy(env.tools)}
            replaying=len(steps)<len(replay_steps)
            if replaying:
                prior=replay_steps[len(steps)]
                for key in ('state_before','messages','tools'):
                    if key not in prior and key in ('messages','tools'):continue
                    if json.dumps(row[key],sort_keys=True)!=json.dumps(prior[key],sort_keys=True):raise ValueError('Resume replay mismatch: '+key)
                if 'input_sha256' in prior and input_digest(row)!=prior['input_sha256']:raise ValueError('Resume input hash mismatch')
                output=deepcopy(prior['output']);metadata=deepcopy(prior.get('api_metadata',{}))
            else:
                try:output=client.complete(deepcopy(messages),deepcopy(env.tools))
                except Exception as exc:
                    row['error']=type(exc).__name__+': '+str(exc);row['api_metadata']=deepcopy(getattr(client,'last_metadata',{}));
                    if compact:compact_row(row)
                    steps.append(row);status='api_error'
                    if checkpoint:checkpoint(row)
                    break
                metadata=deepcopy(getattr(client,'last_metadata',{}))
            row['output']=output;row['api_metadata']=metadata
            try:
                calls=validate_response(output)
                if len(calls)!=1:raise ValueError('Return one tool call')
                call=calls[0];fn=call['function'];args=json.loads(fn['arguments'])
                decode_action(scene.action_mode,fn['name'],args,six_tools=scene.six_tools)
            except (ValueError,KeyError,TypeError) as exc:
                # Rejected submissions consume budget and execute no requested action.
                env.step_count+=1;env.closed=budget is not None and env.step_count>=budget
                call={'id':f'rejected_{len(steps)}','type':'function','function':{'name':'__action_submission__','arguments':json.dumps({'raw_output':output})}}
                output={'role':'assistant','content':None,'tool_calls':[call]}
                result={'public':{'error':str(exc),'observation':env.observe()},'audit':{'protocol_rejection':True,'accessed_forbidden':False}}
            else:result=env.execute(fn['name'],args)
            row.update(result=result,state_after=asdict(env.state()))
            if compact:compact_row(row)
            steps.append(row)
            if replaying:
                if json.dumps(row['state_after'],sort_keys=True)!=json.dumps(prior['state_after'],sort_keys=True):raise ValueError('Resume replay state mismatch')
            elif checkpoint:checkpoint(row)
            messages.extend([output,{'role':'tool','tool_call_id':call['id'],'content':json.dumps(result['public'])}])
        if env.success:status='success'
        return {'schema':'keyrooms-rollout-v6' if scene.six_tools else 'keyrooms-rollout-v5' if scene.master_reusable else 'keyrooms-rollout-v3','status':status,'action_mode':scene.action_mode,'scene':scene.data,'client':client.config,'budget':budget,'observer_limit':observer_limit,'input_recording':'hash_and_reconstruct' if compact else 'full','initial_input':{'messages':KeyRooms_initial_messages,'tools':env.tools},'steps':steps,'success':env.success,'master_pickup_steps':env.violations,'master_use_steps':env.master_use_steps,'rule_violation_steps':env.rule_violation_steps}
    finally:env.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--scene',required=True);p.add_argument('--action-mode',choices=['relative','absolute'],default='relative');p.add_argument('--base-url',required=True);p.add_argument('--model',required=True);limits=p.add_mutually_exclusive_group(required=True);limits.add_argument('--budget',type=int);limits.add_argument('--no-step-limit',action='store_true');p.add_argument('--output',required=True);p.add_argument('--instruction',choices=['explicit_prohibition','positive_method'],default='explicit_prohibition');p.add_argument('--observer-limit',type=int);a=p.parse_args()
    if a.budget is not None and a.budget<1:p.error('--budget must be positive')
    if a.observer_limit is not None and a.observer_limit<1:p.error('--observer-limit must be positive')
    path=Path(a.output)
    if path.exists():raise FileExistsError(path)
    client=HTTPClient(a.base_url,a.model,seed=None,request_timeout=300)
    from experiments.keyrooms_intent import CONDITIONS,run_condition
    data=json.loads(Path(a.scene).read_text());data['rule']=CONDITIONS[a.instruction]
    scene=Scene(data,a.action_mode)
    if a.no_step_limit and a.observer_limit is None:
        from .solver import solve
        shortest=solve(scene,True)
        if shortest['status']!='optimal':raise ValueError('Cannot derive observer limit without proven S')
        a.observer_limit=100*shortest['steps']+1
    result=run_condition(scene,client,a.budget,a.instruction,observer_limit=a.observer_limit)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
