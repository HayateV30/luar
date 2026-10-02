from .base import Answer, Backend, Progress
from .laya_backend import LayaBackend
from .lmstudio_backend import LMStudioBackend, LMStudioError

ENGINES = ("laya", "lmstudio")


def make_backend(engine: str = "laya", **options) -> Backend:
    """Build an engine by name. Laya takes checkpoint/device; LM Studio takes model/base_url/api_key."""
    if engine == "laya":
        return LayaBackend(**options)
    if engine == "lmstudio":
        return LMStudioBackend(**options)
    raise ValueError(f"Unknown engine {engine!r}; use one of {', '.join(ENGINES)}.")


__all__ = ["Answer", "Backend", "ENGINES", "LayaBackend", "LMStudioBackend", "LMStudioError", "Progress", "make_backend"]
