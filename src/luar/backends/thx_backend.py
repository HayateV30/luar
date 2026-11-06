"""THX-01 backend: optional decision model by HAL-X AI (https://huggingface.co/doofz/THX-01)."""
from __future__ import annotations

from pathlib import Path

from ..i18n import t
from ..questions import Question
from .base import Answer, BackendError, Progress
from .laya_backend import check_weights, extract_answer as laya_answer, is_library_error, library_error

INSTALL_HINT = 'pip install "luar[thx]"'
REPO = "doofz/THX-01"
# Pinned revision and the SHA-256 of its weights, as published on the Hub. thx01.load cannot pin a
# revision, so LUAR downloads this one itself and gives it the folder.
REVISION = "b323afcef149f9288a9d0daef4badd67b9b87c61"
WEIGHTS_SHA256 = "52ce834b2a4d265fbc351338655977023ddb61b0363f5f6a4fd096e6c70154b0"
MODEL_FILES = ("config.json", "rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*",
               "LICENSE", "NOTICE")


class ThxNotInstalledError(BackendError):
    pass


def import_thx():
    """Import the optional `thx01` package, or explain how to install it."""
    try:
        import thx01  # heavy import (torch); only when actually needed
    except ImportError as e:
        raise ThxNotInstalledError(t("b_thx_missing", hint=INSTALL_HINT)) from e
    except OSError as e:
        if is_library_error(e):  # a PyTorch DLL refused to load
            raise library_error(e) from e
        raise
    return thx01


def extract_answer(raw: dict | None, qtype: str, labels: list[str] | None = None) -> Answer:
    """Normalize one THX-01 answer. Same format as Laya's for noul and score. For choice, the
    confidence is the probability of the chosen option, as in Laya; THX-01's own `confidence` field
    is an entropy measure, on another scale."""
    if qtype == "choice" and isinstance(raw, dict):
        choice = raw.get("choice")
        return Answer(choice, None if choice is None else float(raw["probabilities"][choice]))
    return laya_answer(raw, qtype, labels)


def verify_weights(folder: str | Path) -> None:
    check_weights(Path(folder) / "model.safetensors", WEIGHTS_SHA256, "b_thx_integrity")


def local_model() -> str | None:
    """The downloaded copy of the model, without touching the network; None if it was never downloaded."""
    from huggingface_hub import snapshot_download

    try:
        path = snapshot_download(REPO, revision=REVISION, local_files_only=True, allow_patterns=list(MODEL_FILES))
    except Exception:  # not in the cache (or no huggingface_hub cache at all)
        return None
    return path if (Path(path) / "model.safetensors").is_file() else None


def download_model() -> str:
    """Fetch the model (pinned revision, verified hash) so later runs never need the network."""
    import_thx()
    from huggingface_hub import snapshot_download

    path = snapshot_download(REPO, revision=REVISION, allow_patterns=list(MODEL_FILES))
    verify_weights(path)
    return path


class ThxBackend:
    name = "THX-01"

    def __init__(self, device: str | None = None, batch_size: int = 16):
        self.device = device
        self.batch_size = batch_size
        self._agent = None

    def _load(self):
        if self._agent is None:
            thx01 = import_thx()
            path = local_model() or download_model()
            verify_weights(path)
            try:
                self._agent = thx01.load(path, device=self.device)
            except OSError as e:
                if is_library_error(e):
                    raise library_error(e) from e
                raise
        return self._agent

    def decide(
        self,
        texts: list[str],
        questions: list[Question],
        progress: Progress | None = None,
    ) -> list[dict[str, Answer]]:
        agent = self._load()
        # to_laya: THX-01 reads the same question format. predict_batch, not agent.decide: decide also
        # reinterprets choice questions whose options look like number ranges or pieces of a document.
        spec = {q.id: q.to_laya() for q in questions}
        results: list[dict[str, Answer]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start:start + self.batch_size]
            for raw in agent.predict_batch(chunk, spec, batch_size=self.batch_size):
                answers = raw["answers"]
                results.append({
                    q.id: extract_answer(answers.get(q.id), q.type, list(q.options)) for q in questions
                })
            if progress:
                progress(len(results), len(texts))
        return results
