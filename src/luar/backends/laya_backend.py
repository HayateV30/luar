"""Laya backend: local Jev-style decision model (https://huggingface.co/convaiinnovations/laya)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

from ..i18n import t
from ..questions import Question
from .base import Answer, BackendError, Progress

INSTALL_HINT = 'pip install "laya>=0.3.21"'

CHECKPOINTS = {
    "auto": None,                    # picks english or multilingual from the file's language
    "multilingual": "multilingual",  # best tested option for non-English text
    "english": None,                 # clearly better than multilingual on English text
    "typed-decisions": "typed-decisions",
}
ENGLISH_SHARE = 0.8
LANGUAGE_SAMPLE = 200


class LayaNotInstalledError(BackendError):
    pass


def laya_installed() -> bool:
    return importlib.util.find_spec("laya") is not None


class LibraryBlockedError(BackendError):
    pass


WINERROR_APP_CONTROL = 4551  # "An Application Control policy has blocked this file"


def is_library_error(e: OSError) -> bool:
    """A DLL that failed to load (Windows), not a missing model file or a network error."""
    text = str(e)
    return getattr(e, "winerror", None) is not None and (".dll" in text.lower() or "WinError" in text)


def library_error(e: OSError) -> LibraryBlockedError:
    """Explain a PyTorch DLL that failed to load (Laya imports PyTorch on first use)."""
    if getattr(e, "winerror", None) == WINERROR_APP_CONTROL or f"WinError {WINERROR_APP_CONTROL}" in str(e):
        return LibraryBlockedError(t("b_app_control", error=e))
    return LibraryBlockedError(t("b_torch", error=e))


def import_laya():
    """Import the `laya` package (a LUAR dependency), or explain how to repair a broken install."""
    try:
        import laya  # heavy import (torch); only when actually needed
    except ImportError as e:
        raise LayaNotInstalledError(t("b_laya_missing", hint=INSTALL_HINT)) from e
    except OSError as e:
        if is_library_error(e):  # a PyTorch DLL refused to load
            raise library_error(e) from e
        raise
    return laya


def pick_checkpoint(texts: list[str], questions: list[Question]) -> str:
    """"english" when the questions and at least 80% of the (sampled) rows are English."""
    laya = import_laya()

    sample = texts[:LANGUAGE_SAMPLE] + [q.question for q in questions]
    decided = [d for d in map(laya.detect_language, sample) if not d["language_undecided"]]
    if not decided:
        return "multilingual"
    english = sum(d["is_english"] for d in decided) / len(decided)
    return "english" if english >= ENGLISH_SHARE else "multilingual"


def extract_answer(raw: dict | None, qtype: str, labels: list[str] | None = None) -> Answer:
    """Normalize one Laya answer (package 0.3.x format):
      choice -> {"choice": "x", "answer_confidence": p}
      score  -> {"legend": {"0": "low", ...}, "probabilities": {"0": p, ...}}
      noul   -> {"noul": P(yes)}
    For score, `labels` maps the level index back to the option label; the legend holds the
    text sent to the model, which includes the description when the option has one."""
    if not isinstance(raw, dict):
        return Answer(None, None)
    if qtype == "noul":
        p = float(raw["noul"])
        return Answer("yes" if p >= 0.5 else "no", max(p, 1 - p))
    if qtype == "score":
        probs = raw["probabilities"]
        k = max(probs, key=probs.get)
        return Answer(labels[int(k)] if labels else raw["legend"][k], float(probs[k]))
    conf = raw.get("answer_confidence", raw.get("confidence"))
    return Answer(raw.get("choice"), None if conf is None else float(conf))


MODEL_FILES = ("rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*")
DEFAULT_REPO = "convaiinnovations/laya"
# Pinned revision of DEFAULT_REPO and the SHA-256 of its weights, as published on the Hub. LUAR only
# loads weights that match, so a corrupted or tampered download is refused instead of run.
REVISION = "55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851"
WEIGHTS_SHA256 = {
    None: "891102d372688fc2a094dac56a384bc537b87c63f21f9f3dac0be2b7cbc8d86c",              # english
    "multilingual": "9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204",
    "typed-decisions": "4fa56de72383a9d3efa9cfa78955733c81b9fc8067a587ca4beb82c78107a24e",
}
VERIFIED_CACHE = Path.home() / ".cache" / "luar" / "verified-weights.json"


class ModelIntegrityError(BackendError):
    pass


def _revision(repo: str) -> str | None:
    return REVISION if repo == DEFAULT_REPO else None


def verify_weights(folder: str | Path, subfolder: str | None, repo: str = DEFAULT_REPO) -> None:
    """Check model.safetensors against the published hash. Hashing 650-850 MB takes a few seconds,
    so a file already checked (same size and modification time) is not hashed again."""
    expected = WEIGHTS_SHA256.get(subfolder) if repo == DEFAULT_REPO else None
    if expected is None:
        return  # another repo: nothing to compare with
    weights = (Path(folder) / subfolder if subfolder else Path(folder)) / "model.safetensors"
    stat = weights.stat()
    key, mark = str(weights.resolve()), [stat.st_size, stat.st_mtime_ns, expected]
    try:
        cache = json.loads(VERIFIED_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if cache.get(key) == mark:
        return
    digest = hashlib.sha256()
    with weights.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ModelIntegrityError(t("b_integrity", path=weights))
    cache[key] = mark
    try:
        VERIFIED_CACHE.parent.mkdir(parents=True, exist_ok=True)
        VERIFIED_CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    except OSError:
        pass  # only a speed-up


def local_checkpoint(repo: str, subfolder: str | None) -> str | None:
    """The downloaded copy of the repo when it holds this checkpoint, without touching the network;
    None when it was never downloaded (the first run then fetches it)."""
    from huggingface_hub import snapshot_download

    prefix = f"{subfolder}/" if subfolder else ""
    try:
        path = Path(snapshot_download(
            repo, revision=_revision(repo), local_files_only=True,
            allow_patterns=[prefix + f for f in MODEL_FILES],
        ))
    except Exception:  # not in the cache (or no huggingface_hub cache at all)
        return None
    folder = path / subfolder if subfolder else path
    if all((folder / name).is_file() for name in ("rl_agent_config.json", "model.safetensors")):
        return str(path)
    return None


def download_checkpoints(repo: str = DEFAULT_REPO,
                         checkpoints: tuple[str, ...] = ("multilingual", "english")) -> list[str]:
    """Fetch the checkpoints (pinned revision, verified hash) so later runs never need the network.
    Returns the local folders."""
    import_laya()
    from huggingface_hub import snapshot_download

    folders = []
    for name in checkpoints:
        subfolder = CHECKPOINTS[name]
        prefix = f"{subfolder}/" if subfolder else ""
        path = snapshot_download(repo, revision=_revision(repo), allow_patterns=[prefix + f for f in MODEL_FILES])
        verify_weights(path, subfolder, repo)
        folders.append(str(Path(path) / subfolder) if subfolder else path)
    return folders


class LayaBackend:
    def __init__(
        self,
        checkpoint: str = "auto",
        device: str | None = None,
        repo: str = "convaiinnovations/laya",
        batch_size: int = 16,
    ):
        if checkpoint not in CHECKPOINTS:
            raise ValueError(t("b_unknown_checkpoint", name=repr(checkpoint), names=", ".join(CHECKPOINTS)))
        self.checkpoint = checkpoint
        self.device = device
        self.repo = repo
        self.batch_size = batch_size
        self.name = f"laya ({checkpoint})"
        self._agent = None

    def _load(self, texts: list[str], questions: list[Question]):
        if self.checkpoint == "auto":
            self.checkpoint = pick_checkpoint(texts, questions)
            self.name = f"laya ({self.checkpoint}, {t('engine_auto')})"
        if self._agent is None:
            laya = import_laya()

            kwargs = {}
            if self.device:
                kwargs["device"] = self.device
            subfolder = CHECKPOINTS[self.checkpoint]
            if subfolder:
                kwargs["subfolder"] = subfolder
            # load from disk (laya.load(repo) would ask the Hub for updates on every run); the first
            # run downloads the pinned revision; either way the weights must match the published hash
            path = local_checkpoint(self.repo, subfolder)
            if path is None:
                name = next(k for k, v in CHECKPOINTS.items() if v == subfolder and k != "auto")
                path = download_checkpoints(self.repo, (name,))[0]
                path = str(Path(path).parent) if subfolder else path
            verify_weights(path, subfolder, self.repo)
            try:
                self._agent = laya.load(path, **kwargs)
            except OSError as e:
                if is_library_error(e):  # laya imports PyTorch lazily, here
                    raise library_error(e) from e
                raise
        return self._agent

    def decide(
        self,
        texts: list[str],
        questions: list[Question],
        progress: Progress | None = None,
    ) -> list[dict[str, Answer]]:
        agent = self._load(texts, questions)
        laya_questions = {q.id: q.to_laya() for q in questions}
        results: list[dict[str, Answer]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start:start + self.batch_size]
            raws = agent.predict_batch(chunk, laya_questions, batch_size=self.batch_size)
            for raw in raws:
                answers = raw.get("answers", raw) if isinstance(raw, dict) else {}
                results.append({
                    q.id: extract_answer(answers.get(q.id), q.type, list(q.options)) for q in questions
                })
            if progress:
                progress(len(results), len(texts))
        return results
