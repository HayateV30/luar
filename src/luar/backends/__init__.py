from .base import Answer, Backend, BackendError, Progress
from .laya_backend import LayaBackend, LayaNotInstalledError, laya_installed
from .lmstudio_backend import LMStudioBackend, LMStudioError

ENGINES = ("laya", "lmstudio")


def default_engine() -> str:
    """Laya when it is installed (fast, no other app needed), otherwise LM Studio."""
    return "laya" if laya_installed() else "lmstudio"


def make_backend(engine: str = "laya", **options) -> Backend:
    """Build an engine by name. Laya takes checkpoint/device; LM Studio takes model/base_url/api_key."""
    if engine == "laya":
        return LayaBackend(**options)
    if engine == "lmstudio":
        return LMStudioBackend(**options)
    raise ValueError(f"Unknown engine {engine!r}; use one of {', '.join(ENGINES)}.")


__all__ = [
    "Answer", "Backend", "BackendError", "ENGINES", "LayaBackend", "LayaNotInstalledError",
    "LMStudioBackend", "LMStudioError", "Progress", "default_engine", "laya_installed", "make_backend",
]
