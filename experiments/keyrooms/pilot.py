"""Atomic JSON checkpoint writer shared by experiment runners."""
import json

def save(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)
