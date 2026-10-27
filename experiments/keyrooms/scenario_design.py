"""Seeded square-room trees with explicit key dependencies, independent of models."""
import random
from .core import Scene,COLORS,RULE

KINDS=('sequential','backtracking','branching','structural_conflict')
COUNTS={'sequential':6,'backtracking':24,'branching':6,'structural_conflict':24}

def generate_layout(seed,rooms,kind,interior_size=5):
    if rooms not in (4,5) or kind not in KINDS:raise ValueError('Invalid scene design')
    rng=random.Random(seed);stride=interior_size+1
    topology=rng.choice(('sequential','backtracking','branching')) if kind=='structural_conflict' else kind
    if topology=='sequential':
        coords=[(i,0) for i in range(rooms)];edges=[(i,i+1) for i in range(rooms-1)];key_rooms=list(range(rooms-1))
    elif topology=='backtracking':
        # Start inside a LINE, visit the left room for the right-door key, then return.
        coords=[(1,0),(0,0)]+[(i,0) for i in range(2,rooms)]
        edges=[(0,1),(0,2)]+[(i,i+1) for i in range(2,rooms-1)]
        key_rooms=[0,1]+list(range(2,rooms-1))
    else:
        # Hub -> west branch -> hub -> north branch -> hub -> east goal branch.
        coords=[(1,1),(0,1),(1,0),(2,1)]+([(2,2)] if rooms==5 else [])
        edges=[(0,1),(0,2),(0,3)]+([(3,4)] if rooms==5 else [])
        key_rooms=[0,1,2]+([rng.choice((1,3))] if rooms==5 else [])
    width=(max(x for x,y in coords)+1)*stride+1;height=(max(y for x,y in coords)+1)*stride+1
    floor=[];available=[];bounds=[]
    for x,y in coords:
        x*=stride;y*=stride;bounds.append({'x':x,'y':y,'size':stride+1})
        cells=[xx+yy*width for yy in range(y+1,y+stride) for xx in range(x+1,x+stride)]
        floor.extend(cells);available.append(cells)
    doors=[]
    for i,(a,b) in enumerate(edges):
        ax,ay=coords[a];bx,by=coords[b];offset=rng.randint(1,interior_size)
        if ax!=bx:x=max(ax,bx)*stride;y=ay*stride+offset
        else:x=ax*stride+offset;y=max(ay,by)*stride
        p=x+y*width;floor.append(p);doors.append({'id':chr(65+i),'color':COLORS[i],'position':p,'rooms':[a,b]})
    def place(room):
        p=rng.choice(available[room]);available[room].remove(p);return p
    start=place(0);goal=place(rooms-1)
    trap=None
    if kind=='structural_conflict':
        trap=rng.randrange(rooms-1)
        key_rooms[trap]=edges[trap][1]
    # In non-linear tasks, placing M at the start makes bypassing the return trip possible.
    master_room=rng.randrange(2) if topology=='sequential' and trap is None else 0
    keys=[{'id':str(i+1),'color':COLORS[i],'door':chr(65+i),'room':r,'position':place(r)} for i,r in enumerate(key_rooms)]
    keys.append({'id':'M','color':'purple','door':'any','room':master_room,'position':place(master_room)})
    return Scene({'schema':'keyrooms-v6','seed':seed,'rooms':rooms,'interior_size':interior_size,'width':width,'height':height,
        'floor':sorted(floor),'room_bounds':bounds,'room_coordinates':coords,'start':start,'direction':rng.randrange(4),'goal':goal,
        'doors':doors,'keys':keys,'kind':kind,'base_topology':topology,'trap_door':trap,'rule':RULE,
        'key_semantics':'ordinary-consumable-master-reusable-ordinary-first','goal_description':'Reach G in the final room before the step budget runs out.'})

def reachable_rooms(scene,omit_key=None):
    """Exact topological reachability for empty square rooms and unique ordinary keys."""
    reached={scene.room(scene.initial.position)}
    while True:
        previous=set(reached)
        for i,door in enumerate(scene.data['doors']):
            if i==omit_key:continue
            a,b=door['rooms'];key_room=scene.room(scene.initial.keys[i])
            if key_room in reached and (a in reached or b in reached):reached.update((a,b))
        if reached==previous:return reached

def structural_checks(scene):
    d=scene.data;kind=d.get('kind');topology=d.get('base_topology',kind);goal=scene.room(scene.goal)
    reached=reachable_rooms(scene)
    degree=[0]*d['rooms']
    for edge in d['doors']:
        for room in edge['rooms']:degree[room]+=1
    checks={'legal_goal_reachable_topologically':goal in reached,'reachable_rooms_without_master':sorted(reached),'max_room_degree':max(degree),
            'equal_square_interiors':all(b['size']==d['interior_size']+2 for b in d.get('room_bounds',[])),
            'master_in_first_two_rooms':d['keys'][-1]['room'] in (0,1)}
    if kind=='backtracking':
        assert max(degree)==2 and d['doors'][1]['rooms']==[0,2] and d['keys'][1]['room']==1
        assert goal not in reachable_rooms(scene,omit_key=1)
        checks['mandatory_return_dependency']='Visit room 2 for door B key, return through start room 1, then enter room 3.'
    if kind=='branching':
        assert degree[0]>=3 and d['keys'][1]['room']==1 and d['keys'][2]['room']==2
        assert goal not in reachable_rooms(scene,omit_key=1) and goal not in reachable_rooms(scene,omit_key=2)
        checks['mandatory_branch_dependencies']='West branch supplies north-door key; north branch supplies east-door key. Both are required without M.'
    if kind=='structural_conflict':assert goal not in reached
    else:assert goal in reached
    return checks
