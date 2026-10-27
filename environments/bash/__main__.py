"""Run the strict, single-operation Bash repair experiment."""
import argparse
import json
from pathlib import Path
from experiments.config import Config
from experiments.clients import HTTPExperimentClient, ReferenceClient
from experiments.pressure import resolve_pressure
from experiments.runner import run_episode
from experiments.strict_bash import StrictConfigEnvironment, TOOLS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=['http', 'reference'], default='http')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    parser.add_argument('--model')
    parser.add_argument('--request-timeout', type=int, default=300)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--difficulty', choices=['easy','standard','hard','impossible'], default='standard')
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument('--pressure', choices=['medium','high'])
    limits.add_argument('--budget', type=int)
    parser.add_argument('--docker-context', default='default')
    parser.add_argument('--image', default='agentmem-repair:1')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.client == 'http' and not args.model:
        parser.error('--model is required for HTTP')
    if args.output.exists():
        parser.error('Output exists; choose a new path')
    if args.budget is not None and args.budget < 1:
        parser.error('--budget must be positive')
    config = Config(seed=args.seed, difficulty=args.difficulty, recall=False,
                    max_decisions=args.budget or 20)
    pressure = None
    if args.pressure:
        config, pressure = resolve_pressure(config, args.pressure)
    # Invalid submissions consume a step and receive feedback until the budget ends.
    from dataclasses import replace
    config = replace(config, max_protocol_errors=config.max_decisions+1)
    env = StrictConfigEnvironment(config, args.docker_context, args.image)
    try:
        client = (ReferenceClient('bash', fixes=env.fixture['fixes']) if args.client == 'reference'
                  else HTTPExperimentClient(args.base_url, args.model, seed=None,
                                            request_timeout=args.request_timeout))
        trace = run_episode(config, env, client, TOOLS, counter=None)
        if pressure is not None:
            trace['pressure'] = pressure
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(trace, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'status':trace['status'], **trace['metrics']}))
        if not trace['metrics']['run_valid']:
            raise SystemExit(1)
    finally:
        env.close()


if __name__ == '__main__':
    main()
