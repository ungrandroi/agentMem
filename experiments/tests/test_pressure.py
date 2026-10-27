import unittest
from experiments.config import Config
from experiments.pressure import resolve_pressure

class PressureTests(unittest.TestCase):
    def test_bash_and_invalid_conflict(self):
        for level, budget in [('medium',20),('high',12)]:
            c,_=resolve_pressure(Config(domain='bash'),level)
            self.assertEqual(c.max_decisions,budget)
        for config in (Config(domain='bash'),):
            with self.assertRaises(ValueError):resolve_pressure(config,'conflict')
