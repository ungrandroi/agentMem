"""Exact A* over position, heading, inventory, consumed keys and door states."""
import heapq,itertools,time
from .core import ACTIONS

def solve(scene,allow_master=False,max_states=500000,timeout=90):
    start=time.monotonic()
    from .scenario_design import reachable_rooms
    if not allow_master:
        reached=reachable_rooms(scene)
        if scene.room(scene.goal) not in reached:
            return {'status':'unreachable','steps':None,'actions':None,'expanded':0,
                'certificate':{'type':'locked_dependency_closure','reachable_rooms':sorted(reached),
                 'explanation':'Ordinary-key reachability reaches a fixed point excluding the goal. Master pickup forbidden.'}}
    distances=scene.distances();goal=scene.goal;master=scene.master
    graph={i:[] for i in range(scene.data['rooms'])}
    for i,d in enumerate(scene.data['doors']):
        a,b=d['rooms'];graph[a].append((b,i));graph[b].append((a,i))
    assert len(scene.data['doors'])==scene.data['rooms']-1, 'Solver requires a room tree'
    paths={}
    for source in graph:
        stack=[(source,frozenset())];seen=set()
        while stack:
            room,edges=stack.pop()
            if room in seen:continue
            seen.add(room);paths[source,room]=edges
            stack.extend((r,edges|{e}) for r,e in graph[room] if r not in seen)
        assert len(seen)==len(graph), 'Disconnected room tree'
    def mst(nodes):
        nodes=list(dict.fromkeys(nodes))
        visited={0};cost=0;best=[distances[nodes[0]][p] for p in nodes]
        while len(visited)<len(nodes):
            j=min((i for i in range(len(nodes)) if i not in visited),key=lambda i:best[i]);cost+=best[j];visited.add(j)
            for k,q in enumerate(nodes):
                if k not in visited:best[k]=min(best[k],distances[nodes[j]][q])
        return cost
    def heuristic(s):
        # Required edges form the subtree connecting current position, goal and
        # recursively required keys. Legacy masters bypass one dependency; v5
        # masters can bypass all locked edges after a single pickup.
        # Relax heading and door blocking in distances; MST + mandatory pickup/
        # toggle costs is a lower bound, including when irrelevant branches exist.
        room=scene.room(s.position);options=[None]
        if allow_master and s.keys[master]!=-2:
            options += ['reusable'] if scene.master_reusable else [i for i,d in enumerate(s.doors) if d==0]
        estimates=[]
        for bypass in options:
            edges=set(paths[room,scene.room(goal)]);required=set()
            while True:
                old=(len(edges),len(required))
                for i in tuple(edges):
                    if s.doors[i]!=0 or i in s.inventory:continue
                    key=master if bypass=='reusable' or i==bypass else i
                    if key not in s.inventory:
                        required.add(key)
                        edges.update(paths[room,scene.room(s.keys[key])])
                if old==(len(edges),len(required)):break
            nodes=[s.position,goal]+[scene.data['doors'][i]['position'] for i in edges]+[s.keys[k] for k in required]
            estimates.append(mst(nodes)+len(required)+sum(s.doors[i]!=2 for i in edges))
        return min(estimates)
    origin=scene.initial;best={origin:0};parent={};queue=[];serial=itertools.count();expanded=0
    heapq.heappush(queue,(heuristic(origin),0,next(serial),origin))
    while queue:
        _,negative_g,_,s=heapq.heappop(queue);g=-negative_g
        if best.get(s)!=g:continue
        if s.position==goal:
            path=[];node=s
            while node!=origin:
                node,a=parent[node];path.append(a)
            path.reverse()
            return {'status':'optimal','steps':g,'actions':path,'expanded':expanded,'seconds':time.monotonic()-start}
        if expanded>=max_states or time.monotonic()-start>timeout:
            return {'status':'unknown','steps':None,'actions':None,'expanded':expanded,'reason':'search_limit','seconds':time.monotonic()-start}
        expanded+=1
        for action in scene.actions:
            nxt=scene.transition(s,action,allow_master)
            if nxt==s or best.get(nxt,float('inf'))<=g+1:continue
            best[nxt]=g+1;parent[nxt]=(s,action)
            heapq.heappush(queue,(g+1+heuristic(nxt),-(g+1),next(serial),nxt))
    return {'status':'unreachable','steps':None,'actions':None,'expanded':expanded,'certificate':{'type':'exhaustive_search'}}
