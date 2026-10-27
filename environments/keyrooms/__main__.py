"""Generate a scene, run one episode, or prepare/run the balanced matrix."""
import argparse
import json
import sys
from pathlib import Path


def generate():
    from experiments.keyrooms.scenario_design import KINDS, generate_layout, structural_checks
    from experiments.keyrooms.core import Scene
    from experiments.keyrooms.solver import solve
    from experiments.keyrooms.environment import verify
    parser = argparse.ArgumentParser(description='Generate and solve one seeded map (no model calls)')
    parser.add_argument('--kind', choices=KINDS, default='backtracking')
    parser.add_argument('--rooms', type=int, choices=[4,5], default=4)
    parser.add_argument('--seed', type=int, default=100000)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output directory already exists')
    scene = generate_layout(args.seed, args.rooms, args.kind)
    checks = structural_checks(scene)
    solutions = {}
    for mode in ('relative','absolute'):
        s = Scene(scene.data, mode)
        legal, permitted = solve(s, False), solve(s, True)
        if legal['status'] not in ('optimal','unreachable') or permitted['status'] != 'optimal':
            raise RuntimeError('Shortest paths not proven; no scene saved')
        solutions[mode] = {'L':legal, 'S':permitted,
                           'verification':{'legal':verify(s,legal,False), 'permitted':verify(s,permitted,True)}}
    args.output.mkdir(parents=True)
    (args.output/'scene.json').write_text(json.dumps(scene.data, indent=2)+'\n')
    (args.output/'solutions.json').write_text(json.dumps({'checks':checks,'solutions':solutions}, indent=2)+'\n')
    print(json.dumps({mode:{k:v[k]['steps'] for k in ('L','S')} for mode,v in solutions.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['generate','run','batch'])
    args = parser.parse_args(sys.argv[1:2])
    del sys.argv[1]
    if args.command == 'generate':
        generate()
    elif args.command == 'run':
        from experiments.keyrooms.run import main as run
        run()
    else:
        from experiments.keyrooms_matrix import main as batch
        batch()


if __name__ == '__main__':
    main()
