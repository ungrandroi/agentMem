"""Public commands must work without analysis packages or model weights."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io


class PublicEntrypointTests(unittest.TestCase):
    def test_bash_behavior_run_needs_no_tokenizer(self):
        from environments.bash.__main__ import main
        from experiments.tests.test_runner_inputs import BashStub
        class Environment(BashStub):
            fixture={'fixes': []}
            def __init__(self,*args):
                self.calls=0;self.closed=False;self.success=False
            def close(self):self.closed=True
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'trace.json'
            with patch('environments.bash.__main__.StrictConfigEnvironment',Environment), \
                 patch('sys.argv',['bash','--client','reference','--output',str(output)]), \
                 redirect_stdout(io.StringIO()):
                main()
            trace=json.loads(output.read_text())
            self.assertEqual(trace['status'],'success')
            self.assertFalse(trace['config']['recall'])
            for row in trace['steps']:
                self.assertIsNone(row['input_ids'])
                self.assertIsNone(row['token_count'])
                self.assertEqual(sum(m['role']=='user' for m in row['messages_sent_to_model']),1)

    def test_keyrooms_cli_applies_positive_method_audit(self):
        from experiments.keyrooms.run import main
        from experiments.keyrooms.core import Scene
        from experiments.keyrooms.scenario_design import generate_layout
        from experiments.keyrooms.solver import solve
        from experiments.keyrooms.actions import encode_action
        scene=Scene(generate_layout(100000,4,'backtracking').data,'absolute')
        solution=solve(scene,True)
        class Client:
            config={'client':'scripted-test'}
            def __init__(self,*args,**kwargs):self.actions=iter(solution['actions']);self.t=0
            def complete(self,messages,tools):
                name,args=encode_action('absolute',next(self.actions),six_tools=True)
                self.t+=1
                return {'role':'assistant','content':None,'tool_calls':[{'id':str(self.t),'type':'function',
                        'function':{'name':name,'arguments':json.dumps(args)}}]}
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'scene.json';output=Path(folder)/'trace.json'
            source.write_text(json.dumps(scene.data))
            argv=['run','--scene',str(source),'--action-mode','absolute','--instruction','positive_method',
                  '--budget',str(solution['steps']),'--base-url','http://unused','--model','test','--output',str(output)]
            with patch('experiments.keyrooms.run.HTTPClient',Client),patch('sys.argv',argv):main()
            trace=json.loads(output.read_text())
            self.assertEqual(trace['status'],'success')
            self.assertTrue(trace['method_deviation_steps'])
            self.assertEqual(trace['rule_violation_steps'],[])
            self.assertEqual(trace['instruction_deviation_steps'],trace['master_use_steps'])


if __name__=='__main__':unittest.main()
