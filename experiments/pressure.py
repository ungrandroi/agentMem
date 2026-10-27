"""Resolve pressure presets before cloning environments or constructing histories."""
from dataclasses import replace

LEVELS = ('medium', 'high', 'conflict')

def resolve_pressure(config, level):
    if level not in LEVELS:
        raise ValueError('Unknown pressure level')
    if config.domain == 'bash':
        if level == 'conflict':
            raise ValueError('Bash conflict budget has not been calibrated')
        if config.bash_mode != 'strict':
            raise ValueError('Bash pressure presets require strict single-operation tools')
        budget = {'medium': 20, 'high': 12}[level]
        return replace(config, max_decisions=budget), {
            'level': level, 'budget': budget, 'basis': 'fixed_single_operation_budget'}
    raise ValueError('Use KeyRooms mode-specific L/S budgets for room experiments')
