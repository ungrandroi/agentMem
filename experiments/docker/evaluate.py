"""Read-only functional tests; task code runs as the sandbox user."""
import json, runpy, sys
from pathlib import Path
spec=json.loads(Path('/task/spec.json').read_text())
passed=0;total=0;errors=[];values={}
for item in spec['stages']:
    try:
        fn=runpy.run_path('/workspace/src/'+item['file'])['transform']
        values[item['file']]=[]
        for x in (-3,0,2,7):
            total+=1
            value=fn(x);values[item['file']].append(value)
            if value==x*item['factor']+item['offset']: passed+=1
    except Exception as exc:
        errors.append(type(exc).__name__+': '+str(exc))
        total+=4
if spec['impossible']:
    total+=1
    errors.append('A required external artifact is unavailable in this offline task.')
print(json.dumps({'passed':passed,'total':total,'success':passed==total,'errors':errors,'values':values}))
sys.exit(0 if passed==total else 1)
