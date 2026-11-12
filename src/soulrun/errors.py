"""Errors raised by SoulRun itself.

Engine errors keep the engine's own shape (code, field, expected); SoulRun errors use the same shape
so a caller can always tell which item is wrong and what it should be.
"""
from __future__ import annotations

__all__ = ["SoulRunError", "UsageError", "EngineUnavailable"]


class SoulRunError(Exception):
    """A SoulRun failure with a stable ``code`` and, when known, the offending ``field`` and what was ``expected``."""

    def __init__(self, code: str, message: str, *, field: str | None = None, expected: object = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.expected = expected

    def __reduce__(self):
        """Rebuilt with every field when copied or sent between processes (a process pool hands errors back that way)."""
        return self.__class__, (self.code, self.message), {"field": self.field, "expected": self.expected}

    def as_dict(self) -> dict:
        data: dict = {"code": self.code, "message": self.message}
        if self.field is not None:
            data["field"] = self.field
        if self.expected is not None:
            data["expected"] = self.expected
        return data

    def __str__(self) -> str:
        tail = ""
        if self.field is not None:
            tail += f" [field: {self.field}]"
        if self.expected is not None:
            tail += f" [expected: {self.expected}]"
        return f"{self.code}: {self.message}{tail}"


class UsageError(SoulRunError, ValueError):
    """The call itself is wrong: an unknown ``cmd``, two exclusive arguments, an unusable folder."""


class EngineUnavailable(SoulRunError, RuntimeError):
    """The engine cannot be loaded (missing files, or its module names are taken by something else)."""
