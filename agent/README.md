# Shared agent interfaces

`client.py` supplies an OpenAI-compatible Chat Completions HTTP client. Authentication comes from `MODEL_API_KEY`, never from model messages. `loop.py` supplies shared response validation and a general tool loop; `memory.py` supplies reusable message-history policies.

The experiment entry points use their domain-specific runners: `experiments/runner.py` for Bash and `experiments/keyrooms/run.py` for KeyRooms. These preserve a single initial task followed by assistant/tool exchanges and reject actions outside the environment contract.

A compatible client exposes `complete(messages, tools)` and a serializable `config` dictionary. It may expose `last_metadata` for API usage and provider metadata. Credentials must never be placed in `config`.
