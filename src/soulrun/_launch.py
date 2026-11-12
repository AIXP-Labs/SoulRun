"""Run SoulRun's command line from this file's own copy of the package - what the model's shell is told to run.

    "<python>" "<this file>" --cmd next-node --cache-dir <run>
    "<python>" "<this file>" --program --cache-dir <run>

``python -m soulrun`` finds a package on the interpreter's search path, which the model's shell may not share with the
host (a source tree on PYTHONPATH, another environment): this file puts its own package first instead, so the command
SoulRun writes into the text always reaches this SoulRun and its bundled engine.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True                              # leave no __pycache__ inside an installed or checked-out package
sys.path[0] = str(Path(__file__).resolve().parents[1])     # the folder holding this package, not the package itself

from soulrun.cli import main  # noqa: E402

sys.exit(main())
