"""Run four retained operational-check episodes, then resume the complete suite."""
import argparse,json,subprocess,sys
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--spend-limit-usd',type=float,default=200);a=p.parse_args()
 root=Path(a.output).resolve()
 command=[sys.executable,'-u','-m','experiments.keyrooms.batch','--output',str(root),'--workers',str(a.workers),'--spend-limit-usd',str(a.spend_limit_usd)]
 if not (root/'gate-passed.json').exists():
  subprocess.run(command+['--limit','4'],check=True)
  progress=json.loads((root/'progress.json').read_text());summary=json.loads((root/'summary.json').read_text())
  if progress['stage']!='gate_finished' or any(r['status'] not in ('success','budget_exhausted') for r in summary):
   raise RuntimeError('Operational gate needs review; saved trials retained, full launch paused')
  from .pilot import save
  save(root/'gate-passed.json',{'episodes':[r['name'] for r in summary],'criterion':'Valid environment execution and no API/protocol failure; success and rule violation are study outcomes, not gate criteria.'})
 subprocess.run(command,check=True)
if __name__=='__main__':main()
