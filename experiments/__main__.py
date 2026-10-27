"""Compatibility entry point for the Bash experiment."""
import sys
from environments.bash.__main__ import main

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] != 'bash':
        raise SystemExit('Use python -m experiments bash --help or python -m environments.keyrooms --help')
    del sys.argv[1]
    main()
