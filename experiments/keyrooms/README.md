# KeyRooms implementation

See the [KeyRooms environment guide](../../environments/keyrooms/README.md) for setup, actions, map generation, pressure budgets and API runs.

- `core.py`: scene/state definitions and transition semantics.
- `environment.py`: native MiniGrid execution and current-room observations.
- `actions.py`: relative and absolute tool schemas and validation.
- `scenario_design.py`: seeded sequential, backtracking, branching and structural-conflict maps.
- `solver.py`: exact shortest-path search, with distinct unknown/unreachable outcomes.
- `run.py`: one-action agent loop and checkpoint replay.
- `openrouter.py`, `batch.py`: API transport, request accounting and resume utilities.
- `prepare_batch.py`: solver and pressure helpers, plus the older 60-map suite generator.

The supported balanced 16-map entry point is `python -m environments.keyrooms batch`.
