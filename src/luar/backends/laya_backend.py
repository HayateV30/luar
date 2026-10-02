"""Laya backend: local Jev-style decision model (https://huggingface.co/convaiinnovations/laya)."""
from __future__ import annotations

import importlib.util

from ..questions import Question
from .base import Answer, BackendError, Progress

INSTALL_HINT = 'pip install "luar[laya]"'

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


def import_laya():
    """Import the optional `laya` package, or explain how to install it."""
    try:
        import laya  # heavy import (torch); only when actually needed
    except ImportError as e:
        raise LayaNotInstalledError(
            f"The Laya engine is not installed. Install it with: {INSTALL_HINT} "
            "(about 1.5 GB with the model), or use the LM Studio engine."
        ) from e
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


def extract_answer(raw: dict | None, qtype: str) -> Answer:
    """Normalize one Laya answer (package 0.3.x format):
      choice -> {"choice": "x", "answer_confidence": p}
      score  -> {"legend": {"0": "low", ...}, "probabilities": {"0": p, ...}}
      noul   -> {"noul": P(yes)}"""
    if not isinstance(raw, dict):
        return Answer(None, None)
    if qtype == "noul":
        p = float(raw["noul"])
        return Answer("yes" if p >= 0.5 else "no", max(p, 1 - p))
    if qtype == "score":
        probs = raw["probabilities"]
        k = max(probs, key=probs.get)
        return Answer(raw["legend"][k], float(probs[k]))
    conf = raw.get("answer_confidence", raw.get("confidence"))
    return Answer(raw.get("choice"), None if conf is None else float(conf))


class LayaBackend:
    def __init__(
        self,
        checkpoint: str = "auto",
        device: str | None = None,
        repo: str = "convaiinnovations/laya",
        batch_size: int = 16,
    ):
        if checkpoint not in CHECKPOINTS:
            raise ValueError(f"Unknown checkpoint {checkpoint!r}; use one of {', '.join(CHECKPOINTS)}.")
        self.checkpoint = checkpoint
        self.device = device
        self.repo = repo
        self.batch_size = batch_size
        self.name = f"laya ({checkpoint})"
        self._agent = None

    def _load(self, texts: list[str], questions: list[Question]):
        if self.checkpoint == "auto":
            self.checkpoint = pick_checkpoint(texts, questions)
            self.name = f"laya ({self.checkpoint}, chosen automatically)"
        if self._agent is None:
            laya = import_laya()

            kwargs = {}
            if self.device:
                kwargs["device"] = self.device
            if CHECKPOINTS[self.checkpoint]:
                kwargs["subfolder"] = CHECKPOINTS[self.checkpoint]
            self._agent = laya.load(self.repo, **kwargs)
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
                results.append({q.id: extract_answer(answers.get(q.id), q.type) for q in questions})
            if progress:
                progress(len(results), len(texts))
        return results
