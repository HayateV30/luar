import math

import pytest

from luar.backends import make_backend
from luar.backends.lmstudio_backend import (
    LMStudioBackend,
    LMStudioError,
    build_prompt,
    letter_probabilities,
)
from luar.engine import accuracy, run_file
from luar.questions import load_questions, parse_questions

from .conftest import EXAMPLES

QS = parse_questions([
    {"id": "topic", "type": "choice", "question": "Topic?", "options": {"delivery": "shipping", "price": ""}},
    {"id": "refund", "type": "noul", "question": "Refund?"},
    {"id": "level", "type": "score", "question": "How bad?", "options": ["low", "mid", "high"]},
])


def _top(**probs):
    return [{"token": tok, "logprob": math.log(p)} for tok, p in probs.items()]


def test_prompt_lists_options_with_letters_after_the_text():
    p = build_prompt("Parcel lost.", QS[0])
    assert p.index("Parcel lost.") < p.index("Question: Topic?")
    assert "A) delivery: shipping\nB) price\nAnswer:" in p
    assert "A) yes\nB) no" in build_prompt("x", QS[1])


def test_letter_probabilities_renormalize_over_valid_letters():
    top = _top(A=0.6, **{" B": 0.2, "b": 0.1, "C": 0.05, "The": 0.05})
    probs = letter_probabilities(top, 2)
    assert set(probs) == {"A", "B"}
    assert probs["A"] == pytest.approx(0.6 / 0.9)
    assert probs["B"] == pytest.approx(0.3 / 0.9)
    assert letter_probabilities(_top(The=0.9), 2) == {}


class FakeServer(LMStudioBackend):
    """Answers from canned letter distributions instead of HTTP."""

    def __init__(self, answers):
        super().__init__(model="fake")
        self.answers = answers
        self.bodies = []

    def _request(self, path, body=None, root=None):
        self.bodies.append(body)
        qid = next(q.id for q in QS if f"Question: {q.question}" in body["messages"][1]["content"])
        return {"choices": [{"logprobs": {"content": [{"top_logprobs": _top(**self.answers[qid])}]}}]}


def test_decide_maps_letters_to_labels_and_confidence():
    backend = FakeServer({"topic": {"B": 0.9, "A": 0.1}, "refund": {"A": 0.55, "B": 0.45}, "level": {"C": 1.0}})
    [row] = backend.decide(["text"], QS)
    assert (row["topic"].value, row["topic"].confidence) == ("price", pytest.approx(0.9))
    assert (row["refund"].value, row["refund"].confidence) == ("yes", pytest.approx(0.55))
    assert row["level"].value == "high"
    body = backend.bodies[0]
    assert body["reasoning_effort"] == "none" and body["max_tokens"] == 1 and body["logprobs"] is True


def test_no_letter_in_answer_means_no_answer():
    [row] = FakeServer({"topic": {"Sorry": 1.0}, "refund": {"A": 1.0}, "level": {"A": 1.0}}).decide(["t"], QS)
    assert row["topic"].value is None and row["topic"].confidence is None


def test_missing_logprobs_is_a_clear_error():
    class NoLogprobs(LMStudioBackend):
        def _request(self, path, body=None, root=None):
            return {"choices": [{"logprobs": None}]}

    with pytest.raises(LMStudioError, match="logprobs"):
        NoLogprobs(model="m").decide(["t"], QS[:1])


def test_unreachable_server_is_a_clear_error():
    backend = LMStudioBackend(base_url="http://127.0.0.1:9/v1", timeout=2)
    with pytest.raises(LMStudioError, match="Could not reach LM Studio"):
        backend.decide(["t"], QS[:1])


def test_list_models_prefers_loaded_and_skips_embeddings():
    class Server(LMStudioBackend):
        def _request(self, path, body=None, root=None):
            assert root == "http://localhost:1234" and path == "/api/v0/models"
            return {"data": [
                {"id": "bert-thing", "type": "llm", "state": "not-loaded"},
                {"id": "nomic-embed", "type": "embeddings", "state": "loaded"},
                {"id": "qwen", "type": "vlm", "state": "loaded"},
            ]}

    b = Server()
    assert b.list_models() == ["qwen", "bert-thing"]
    assert b.resolve_model() == "qwen" and b.name == "lmstudio (qwen)"


def test_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_API_KEY", "test-key")
    monkeypatch.setenv("LUAR_LMSTUDIO_URL", "http://example.test:1234/v1/")
    b = make_backend("lmstudio")
    assert b.api_key == "test-key" and b.base_url == "http://example.test:1234/v1"
    with pytest.raises(ValueError, match="Unknown engine"):
        make_backend("nope")


@pytest.mark.slow
@pytest.mark.parametrize("data, questions, column", [
    ("reviews.csv", "reviews_questions.json", "review"),
    ("avaliacoes.csv", "avaliacoes_perguntas.json", "avaliacao"),
])
def test_real_lmstudio_on_examples(tmp_path, data, questions, column):
    """Needs LM Studio running with a model loaded. `pytest -m slow -k lmstudio -s`"""
    backend = LMStudioBackend()
    try:
        backend.resolve_model()
    except LMStudioError as e:
        pytest.skip(str(e))
    qs = load_questions(EXAMPLES / questions)
    res = run_file(EXAMPLES / data, qs, [column], backend, out_dir=tmp_path)
    print("\n" + res.summary_path.read_text(encoding="utf-8"))
    for q in qs:
        hits, total = accuracy(res, q)
        assert hits / total >= 0.85, f"{q.id}: {hits}/{total}"
