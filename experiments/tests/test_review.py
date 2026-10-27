"""Regressions found by the cross-environment experimental-validity review."""
import unittest
from dataclasses import replace
from experiments.config import Config
from experiments.clients import ReferenceClient
from experiments.runner import run_episode
from experiments.audit import parse_trace
from experiments.tests.test_rules import Counter

class ReviewTests(unittest.TestCase):


    def test_unrecognized_and_fd_directory_audits(self):
        for raw in ('garbage','1 --- SIGCHLD {si_signo=SIGCHLD} ---',
                    '1 open_by_handle_at(3</workspace>, 0x123, O_RDONLY) = 4',
                    '1 exit_group(0) = ?\nstrace: truncated trace'):
            self.assertFalse(parse_trace(raw)['audit_complete'])
        r=parse_trace('1 fchdir(3</workspace/secret>) = 0')
        self.assertTrue(r['audit_complete']);self.assertTrue(r['accessed_forbidden'])

    def test_final_text_never_executes_hidden_tool(self):
        class EndClient:
            config={'client':'review-test'}
            def complete(self,*args,**kwargs):return {'role':'assistant','content':'Finished.'}
        class Env:
            closed=False;success=False
            def observe(self):return {'task':'test'}
            def snapshot(self):return {'state':0}
            def execute(self,*args):raise AssertionError('Unexpected automatic execution')
        r=run_episode(Config(domain='bash',recall=False),Env(),EndClient(),[],Counter())
        self.assertEqual(r['status'],'error')
        self.assertFalse(r['metrics']['run_valid'])
        self.assertFalse(r['metrics']['task_success'])
        self.assertNotIn('final_evaluation',r['steps'][0])

    def test_failed_measurement_not_reported_available(self):
        class Failure:
            model=object()
            def __call__(self,*args):raise RuntimeError('readout failed')
        reader=Failure();client=ReferenceClient('bash');client.model=reader.model
        from experiments.tests.test_runner_inputs import BashStub
        from experiments.strict_bash import TOOLS
        r=run_episode(Config(domain='bash',recall=False),BashStub(),client,TOOLS,Counter(),reader)
        self.assertEqual(r['status'],'error')
        self.assertTrue(r['metrics']['measurement_requested'])
        self.assertFalse(r['metrics']['measurement_available'])
        self.assertFalse(r['metrics']['run_valid'])
        self.assertEqual(r['metrics']['measured_decisions'],0)

if __name__=='__main__':unittest.main()
