"""SoulRun - the AISOP execution engine as one call.

    import soulrun

    ctx = soulrun(user_message="...")     # start a run, or continue the one this message belongs to
    ctx = soulrun()                       # the guide
    out = soulrun(cmd="next-node", cache_dir=ctx.cache_dir)

The package itself is callable; ``soulrun.run`` is the same function under an ordinary name.
"""
from __future__ import annotations

import sys
import types

__version__ = "1.0.1"

from . import _engine                                    # noqa: E402
from ._api import DEFAULT_SESSION, KINDS, Ctx, run       # noqa: E402
from ._cmd import COMMANDS, CmdResult                    # noqa: E402
from .errors import EngineUnavailable, SoulRunError, UsageError   # noqa: E402

__all__ = [
    "__version__", "ENGINE_VERSION", "run", "Ctx", "CmdResult", "COMMANDS", "KINDS", "DEFAULT_SESSION",
    "SoulRunError", "UsageError", "EngineUnavailable", "engine_info", "guide",
]


def __getattr__(name: str):
    # ENGINE_VERSION is read when it is asked for, not at import: a copy whose engine files are damaged must still
    # import, so that `soulrun --doctor` and `--verify-engine` can say what is wrong instead of failing to start.
    if name == "ENGINE_VERSION":
        return _engine.version()
    if name == "host":                    # `import soulrun` then `soulrun.host....`: loaded when first used
        import importlib
        return importlib.import_module(".host", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def engine_info() -> dict:
    """Which engine is bundled: version, where it came from, its recorded fingerprint."""
    return _engine.info()


def guide() -> str:
    """The guide text (what ``soulrun()`` hands back)."""
    return run().text


class _CallableModule(types.ModuleType):
    """Lets ``import soulrun; soulrun(...)`` work. The module is otherwise an ordinary module."""

    def __call__(self, *args, **kwargs):
        return run(*args, **kwargs)


sys.modules[__name__].__class__ = _CallableModule
