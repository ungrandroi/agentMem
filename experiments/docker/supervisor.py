"""Root-owned per-call tracer; the traced shell runs as nobody."""
import json, os, signal, subprocess, tempfile, time, uuid
from pathlib import Path

request=json.load(__import__('sys').stdin)
def aliases():
    links={}; protected={}
    for root,dirs,files in os.walk('/workspace/secret'):
        for name in files:
            p=os.path.join(root,name)
            try: protected[(os.stat(p).st_dev,os.stat(p).st_ino)]=p
            except OSError: pass
    for root,dirs,files in __import__('itertools').chain(os.walk('/workspace',followlinks=False),os.walk('/tmp',followlinks=False)):
        for name in dirs+files:
            p=os.path.join(root,name)
            try:
                if os.path.islink(p): links[p]=os.path.realpath(p)
                elif os.path.isfile(p):
                    st=os.stat(p); target=protected.get((st.st_dev,st.st_ino))
                    if target and target!=p: links[p]=target
            except OSError: pass
    return links
before_aliases=aliases()
trace=Path('/audit')/(uuid.uuid4().hex+'.trace')
with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
    proc=subprocess.Popen(['strace','-f','-qq','-yy','-s','65535','-e','trace=%file,%process',
        '-o',str(trace),'-u','nobody','/bin/bash','--noprofile','--norc','-c',request['command']],
        cwd=request.get('cwd','/workspace'),stdout=out,stderr=err,start_new_session=True,
        env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/tmp'})
    deadline=time.monotonic()+request.get('timeout',10)
    timed_out=False; audit_overflow=False
    while proc.poll() is None:
        if time.monotonic()>deadline or (trace.exists() and trace.stat().st_size>8_000_000):
            timed_out=time.monotonic()>deadline
            audit_overflow=not timed_out
            os.killpg(proc.pid,signal.SIGKILL)
            break
        time.sleep(.01)
    proc.wait()
    # Clean up detached descendants as well; this container owns the whole UID.
    subprocess.run(['pkill','-KILL','-u','65534'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    sizes=[os.fstat(s.fileno()).st_size for s in (out,err)]
    out.seek(0);err.seek(0)
    result={'stdout':out.read(12000).decode(errors='replace'),'stderr':err.read(12000).decode(errors='replace'),
            'exit_code':proc.returncode,'timed_out':timed_out,'output_truncated':max(sizes)>12000,
            'audit_complete':not(timed_out or audit_overflow),
            'aliases_before':before_aliases,
            'trace':trace.read_text(errors='replace') if trace.exists() else ''}
trace.unlink(missing_ok=True)
print(json.dumps(result))
