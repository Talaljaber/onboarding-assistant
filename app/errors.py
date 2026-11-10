"""Exception types shared by the app."""

from __future__ import annotations


class StartupError(RuntimeError):
    """Raised at startup with a one-line fix in the message."""


class LLMUnavailable(RuntimeError):
    """The LLM layer cannot answer (no key, offline, deadline, budget, bad reply)."""


class ArtifactMissing(StartupError):
    """A built artifact (index, bands, embeddings) is missing."""


class ArtifactVersionMismatch(StartupError):
    """A built artifact was made for a different data or encoder version."""


class ApiError(Exception):
    """An error that becomes the JSON error shape of the API contract."""

    def __init__(self, code: str, status: int, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.field = field
