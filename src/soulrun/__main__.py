"""Allow running the CLI with ``python -m soulrun``."""

import sys

from .cli import main

sys.exit(main())
