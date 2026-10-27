# Behavioral experiments

Use the public entry points:

- [Bash configuration repair](../environments/bash/README.md): `python -m environments.bash`.
- [KeyRooms navigation](../environments/keyrooms/README.md): `python -m environments.keyrooms`.

These implementation modules retain the existing transition, auditing and trace formats. Optional measurement hooks remain for compatibility, but analysis implementations and dependencies are not part of this release. The public CLIs collect behavior only.
