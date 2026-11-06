from .base import Answer, Backend, BackendError, Progress
from .laya_backend import LayaBackend, LayaNotInstalledError, laya_installed
from .thx_backend import ThxBackend, ThxNotInstalledError

ENGINES = ("laya", "thx")


def make_backend(engine: str = "laya", **options) -> Backend:
    """Build an engine by name. Laya takes checkpoint/device; THX-01 takes device."""
    if engine == "laya":
        return LayaBackend(**options)
    if engine == "thx":
        return ThxBackend(**options)
    raise ValueError(f"Unknown engine {engine!r}; use one of {', '.join(ENGINES)}.")


__all__ = [
    "Answer", "Backend", "BackendError", "ENGINES", "LayaBackend", "LayaNotInstalledError",
    "Progress", "ThxBackend", "ThxNotInstalledError", "laya_installed", "make_backend",
]
