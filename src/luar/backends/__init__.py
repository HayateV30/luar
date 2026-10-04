from .base import Answer, Backend, BackendError, Progress
from .laya_backend import LayaBackend, LayaNotInstalledError, laya_installed

ENGINES = ("laya",)


def make_backend(engine: str = "laya", **options) -> Backend:
    """Build an engine by name. Laya takes checkpoint/device."""
    if engine == "laya":
        return LayaBackend(**options)
    raise ValueError(f"Unknown engine {engine!r}; use one of {', '.join(ENGINES)}.")


__all__ = [
    "Answer", "Backend", "BackendError", "ENGINES", "LayaBackend", "LayaNotInstalledError",
    "Progress", "laya_installed", "make_backend",
]
