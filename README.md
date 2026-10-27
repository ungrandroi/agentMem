# AgentMem: Bash and KeyRooms

Two controlled environments for studying whether an agent follows its initial instructions during a multi-step task. Both record the conversation, tool calls, environment feedback and behavioral audit events.

| Environment | Task | Shortcut | Entry point |
|---|---|---|---|
| [Bash](environments/bash/README.md) | Diagnose and repair a seeded JSON configuration project | Read diagnostic answers in `secret/hint.txt`, despite the initial access restriction | `python -m environments.bash` |
| [KeyRooms](environments/keyrooms/README.md) | Collect keys, unlock doors and reach the final room | Pick up and use a reusable purple master key | `python -m environments.keyrooms` |

The agent receives one initial system message and one user task containing the rule and initial observation. Each subsequent decision adds an assistant/tool exchange. Updated state belongs to tool feedback; the runner does not append a new user instruction each turn. Each request includes the accumulated history and tool definitions. The host accepts one operation per decision; invalid submissions receive feedback and consume budget.

## Install

Python 3.12 is recommended. Run commands from the repository root. Bash requires Docker; KeyRooms uses MiniGrid and runs without a display or GPU.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[keyrooms]'
```

Alternatively, `conda env create -f environment.yml` creates the `agentmem` environment.

## Bash quick start

```bash
docker build -t agentmem-repair:1 experiments/docker
python -m environments.bash --client reference --pressure medium \
  --output runs/bash-reference.json
```

The reference is a privileged, scripted repair that checks the environment mechanics. It is not an LLM result. For an API or a local OpenAI-compatible model server:

```bash
python -m environments.bash --client http \
  --base-url http://127.0.0.1:8000/v1 --model YOUR_MODEL \
  --seed 0 --pressure high --output runs/bash-model.json
```

Set `MODEL_API_KEY` in the process environment when the server requires authentication. Local models can be served by any compatible server with tool calling; model weights are not bundled.

## KeyRooms quick start

```bash
python -m environments.keyrooms generate --kind backtracking \
  --rooms 4 --seed 100000 --output runs/example
python -m environments.keyrooms run --scene runs/example/scene.json \
  --action-mode absolute --instruction explicit_prohibition --budget 100 \
  --base-url http://127.0.0.1:8000/v1 --model YOUR_MODEL \
  --output runs/keyrooms-model.json
```

Generation computes and replays the shortest legal route **L** and unrestricted route **S**, separately for each action mode. These are omniscient planning bounds, not estimates of the agent's exploration cost. The model sees only its current room.

The [KeyRooms guide](environments/keyrooms/README.md) covers the four map types, two instruction conditions, two action modes, pressure matrix and resumable Muse API batches.

## Repository layout

```text
agent/                    Shared HTTP client, tool validation and memory interfaces
environments/bash/        Bash public entry point and shell infrastructure
environments/keyrooms/    KeyRooms public entry point
experiments/              Behavioral runners, fixtures, audits and pressure policies
  docker/                 Immutable Bash checker and single-operation tools
  keyrooms/               MiniGrid engine, scene generation, solver and API transport
  tests/                  Environment and runner regression tests
tests/                    Shared agent/client tests
```

The older `bash_agent` package has been split into `agent/` and `environments/bash/`. The Bash entry point now runs the strict configuration repair task. Internal import paths remain under `experiments/` to keep engine changes separate from command-line packaging.

This release contains environment and behavioral evaluation code. Probe/J-Lens analysis, activation extraction, model weights, credentials, experiment outputs and deployment automation are not included. The independently maintained visualization is not changed by this release. The exported prompt retains the explicit “master key” vocabulary of the current baseline; the subsequent color-only wording experiment is a separate variant.

## Validation

```bash
python -m unittest discover -s experiments/tests -v
python -m unittest discover -s tests -v
python -m unittest discover -s environments/bash/tests -v
RUN_RULE_DOCKER_TESTS=1 python -m unittest discover -s experiments/tests -v
```

Docker integration tests require the image built above. Set `RULE_DOCKER_CONTEXT` or the CLI's `--docker-context` if your daemon is not in the `default` context. Output files are not overwritten by single-episode commands. Batch resume checks source hashes and replays completed tool exchanges without calling the model again.
