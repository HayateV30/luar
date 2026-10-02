"""LM Studio backend: a local LLM behind LM Studio's OpenAI-compatible server.

Each option gets a letter (A, B, C…) and the model answers with one token. The
probability the model puts on each letter (logprobs) is the confidence, so it is a
real probability, not a number the model writes about itself."""
from __future__ import annotations

import json
import math
import os
import string
import urllib.error
import urllib.request

from ..questions import Question
from .base import Answer, BackendError, Progress

DEFAULT_URL = "http://localhost:1234/v1"
URL_ENV = "LUAR_LMSTUDIO_URL"
KEY_ENV = "LMSTUDIO_API_KEY"
LETTERS = string.ascii_uppercase  # questions are limited to 20 options
TOP_LOGPROBS = 20

SYSTEM_PROMPT = (
    "You label text. Read the text, then answer the question by choosing exactly one option. "
    "Reply with the letter of that option only."
)


class LMStudioError(BackendError):
    """The LM Studio server could not be used (not running, no model, auth…)."""


def option_labels(q: Question) -> list[tuple[str, str]]:
    """[(label, description)] in the order shown to the model."""
    if q.type == "noul":
        return [("yes", ""), ("no", "")]
    return list(q.options.items())


def build_prompt(text: str, q: Question) -> str:
    # The row text comes first so LM Studio can reuse its prompt cache across the
    # questions of the same row.
    lines = [f"Text:\n{text}", "", f"Question: {q.question}"]
    for letter, (label, desc) in zip(LETTERS, option_labels(q)):
        lines.append(f"{letter}) {label}: {desc}" if desc else f"{letter}) {label}")
    lines.append("Answer:")
    return "\n".join(lines)


def letter_probabilities(top_logprobs: list[dict], n_options: int) -> dict[str, float]:
    """Probability per option letter, renormalized over the valid letters only.
    Tokens like " B" or "b" count for B."""
    valid = LETTERS[:n_options]
    probs = dict.fromkeys(valid, 0.0)
    for item in top_logprobs:
        tok = item["token"].strip().upper()
        if tok in probs:
            probs[tok] += math.exp(item["logprob"])
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()} if total else {}


def answer_from_probs(probs: dict[str, float], q: Question) -> Answer:
    if not probs:
        return Answer(None, None)
    best = max(probs, key=probs.get)
    label = option_labels(q)[LETTERS.index(best)][0]
    return Answer(label, probs[best])


class LMStudioBackend:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 300,
    ):
        self.base_url = (base_url or os.environ.get(URL_ENV) or DEFAULT_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get(KEY_ENV)
        self.model = model
        self.timeout = timeout
        self.name = f"lmstudio ({model or 'loaded model'})"

    def _request(self, path: str, body: dict | None = None, root: str | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request((root or self.base_url) + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise LMStudioError(
                    f"LM Studio refused the request ({e.code}). If the server requires an API key, "
                    f"set the {KEY_ENV} environment variable."
                ) from e
            detail = e.read().decode(errors="replace")[:300]
            raise LMStudioError(f"LM Studio returned {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise LMStudioError(
                f"Could not reach LM Studio at {self.base_url}. Start the server "
                "(`lms server start`, or Developer > Start Server) and load a model."
            ) from e

    def list_models(self) -> list[str]:
        """Models the server can use, loaded ones first; embedding models left out.
        Uses LM Studio's own /api/v0/models (which says what is loaded) when available."""
        root = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        try:
            data = self._request("/api/v0/models", root=root).get("data", [])
        except LMStudioError:
            data = self._request("/models").get("data", [])
        usable = [m for m in data if m.get("type") != "embeddings" and "embed" not in m["id"].lower()]
        usable.sort(key=lambda m: m.get("state") != "loaded")  # stable: keeps server order otherwise
        return [m["id"] for m in usable]

    def resolve_model(self) -> str:
        if not self.model:
            models = self.list_models()
            if not models:
                raise LMStudioError("No model is available in LM Studio; load one (e.g. `lms load qwen3.5-4b`).")
            self.model = models[0]
            self.name = f"lmstudio ({self.model})"
        return self.model

    def ask(self, text: str, q: Question) -> Answer:
        body = {
            "model": self.resolve_model(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(text, q)},
            ],
            "max_tokens": 1,
            "temperature": 0,
            "logprobs": True,
            "top_logprobs": TOP_LOGPROBS,
            "reasoning_effort": "none",  # answer directly, no "thinking" tokens
        }
        resp = self._request("/chat/completions", body)
        try:
            top = resp["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
        except (KeyError, IndexError, TypeError) as e:
            raise LMStudioError(
                "LM Studio did not return token probabilities (logprobs); update LM Studio."
            ) from e
        return answer_from_probs(letter_probabilities(top, len(option_labels(q))), q)

    def decide(
        self,
        texts: list[str],
        questions: list[Question],
        progress: Progress | None = None,
    ) -> list[dict[str, Answer]]:
        results = []
        for i, text in enumerate(texts):
            results.append({q.id: self.ask(text, q) for q in questions})
            if progress:
                progress(i + 1, len(texts))
        return results
