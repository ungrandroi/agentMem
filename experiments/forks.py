"""Replay tool histories from a shared checkpoint, then compare matched decisions."""
from copy import deepcopy
from dataclasses import replace
import json
from .config import CONDITIONS
from .context import initial_messages,matched_contexts
from .runner import run_episode,state_hash


def prepare_histories(config,source,plans,tools,counter,prefix=None):
    """plans maps each condition to [{name, args}, ...], including a common tail.

    Returned environments are caller-owned. Every historical call is actually
    executed and charged on a clone. No supplied/fabricated tool output is used.
    """
    if config.memory!='full':raise ValueError('Injected histories require --memory full')
    if not isinstance(plans,dict) or set(plans)!=set(CONDITIONS):raise ValueError('History file must contain all four conditions')
    counts={len(v) for v in plans.values() if isinstance(v,list)}
    if any(not isinstance(v,list) for v in plans.values()) or len(counts)!=1 or next(iter(counts))<2:
        raise ValueError('Each history must have the same number of calls (at least two), including the common final call')
    available={t['function']['name'] for t in tools}
    for plan in plans.values():
        for call in plan:
            if not isinstance(call,dict) or set(call)!={'name','args'} or not isinstance(call['name'],str) or call['name'] not in available or not isinstance(call['args'],dict):
                raise ValueError('Each history call must specify an available tool name and an args object')
    if any(plans[c][-1]!=plans[CONDITIONS[0]][-1] for c in CONDITIONS):raise ValueError('Final historical call must be identical')
    source_state=source.snapshot();before=state_hash(source_state);observation=source.observe()
    if prefix is None:
        if source_state.get('step_count',source_state.get('calls',0)):
            raise ValueError('A midtrajectory source requires its original prefix and real tool history')
        prefix=initial_messages(config,observation)
    else:
        prefix=deepcopy(prefix)
        if [m['role'] for m in prefix[:2]]!=['system','user'] or len(prefix)<4:
            raise ValueError('Checkpoint prefix must contain the original task and tool exchanges')
        for i in range(2,len(prefix),2):
            pair=prefix[i:i+2]
            if len(pair)!=2 or [m['role'] for m in pair]!=['assistant','tool'] or pair[0]['tool_calls'][0]['id']!=pair[1]['tool_call_id']:
                raise ValueError('Invalid checkpoint prefix')
        if json.loads(prefix[-1]['content']).get('observation')!=observation:
            raise ValueError('Checkpoint prefix observation differs from source')
    used_ids={call['id'] for message in prefix for call in message.get('tool_calls',[])}
    call_ids=[];serial=0
    for _ in range(next(iter(counts))):
        while 'history_'+str(serial) in used_ids:serial+=1
        call_ids.append('history_'+str(serial));serial+=1
    forks={};histories={};audits={}
    try:
        for condition in CONDITIONS:
            env=source.clone();forks[condition]=env
            if state_hash(env.snapshot())!=before or env.observe()!=observation:raise RuntimeError('Clone differs from source')
            history=[];events=[]
            for index,call in enumerate(plans[condition]):
                if env.closed or env.success:raise ValueError('Historical trajectory ended before the comparison point')
                result=env.execute(call['name'],deepcopy(call['args']))
                if not result['audit']['audit_complete'] or result['audit'].get('rejected_before_execution'):
                    raise ValueError('Historical call was rejected or could not be audited')
                public=deepcopy(result['public']);public['observation']=env.observe()
                call_id=call_ids[index]
                history += [{'role':'assistant','content':None,'tool_calls':[{'id':call_id,'type':'function',
                    'function':{'name':call['name'],'arguments':json.dumps(call['args'],sort_keys=True)}}]},
                    {'role':'tool','tool_call_id':call_id,'content':json.dumps(public,sort_keys=True)}]
                events.append(result['audit'])
            if env.closed or env.success:raise ValueError('History must leave an open, unfinished decision state')
            histories[condition]=history;audits[condition]=events
        states={c:e.snapshot() for c,e in forks.items()}
        if len({state_hash(s) for s in states.values()})!=1:raise ValueError('Histories do not converge to the same state and remaining budget')
        if len({state_hash(e.observe()) for e in forks.values()})!=1:raise ValueError('Final observations differ')
        contexts,matching=matched_contexts(config,prefix,histories,tools,counter)
        if state_hash(source.snapshot())!=before:raise RuntimeError('History replay changed source')
        return forks,contexts,matching,{'source_state_sha256':before,'source_observation_sha256':state_hash(observation),
            'decision_state_sha256':state_hash(next(iter(states.values()))),
            'source_prefix':prefix,'replayed_histories':histories,'history_audits':audits}
    except BaseException:
        for env in forks.values():env.close()
        raise


def run_injected(config,source,client,tools,counter,measurement=None,*,plans=None,prefix=None,all_conditions=False):
    forks,contexts,matching,evidence=prepare_histories(config,source,plans,tools,counter,prefix)
    trials=[]
    try:
        decision_state=next(iter(forks.values())).snapshot()
        conditions=CONDITIONS if all_conditions else (config.condition,)
        for condition in conditions:
            one=replace(config,condition=condition,history_mode='injected',
                        max_decisions=1 if all_conditions else config.max_decisions)
            trials.append(run_episode(one,forks[condition],client.fork(),tools,counter,measurement,
                                      prepared_messages=contexts[condition],matching=matching))
        if state_hash(source.snapshot())!=evidence['source_state_sha256']:raise RuntimeError('A trial changed source')
        evidence.update(mode='replayed_tool_history_forks' if all_conditions else 'replayed_tool_history_episode',
                        map_sha256=decision_state.get('map_sha256'),steps_remaining=decision_state.get('steps_remaining'),
                        matched_tokens=next(iter(matching['tokens'].values())),matching=matching)
        if all_conditions:return {**evidence,'trials':trials}
        trials[0]['history_intervention']=evidence
        return trials[0]
    finally:
        for env in forks.values():env.close()


def run_forks(config,source,client,tools,counter,measurement=None,*,plans=None,prefix=None):
    return run_injected(config,source,client,tools,counter,measurement,plans=plans,prefix=prefix,all_conditions=True)
