"""The optional THX-01 engine. Fast tests use a stand-in for the model; `-m slow` runs the real one."""
import hashlib
import sys
import types

import pytest

from luar.backends import ENGINES, make_backend
from luar.backends import thx_backend as tb
from luar.backends.laya_backend import LayaBackend, ModelIntegrityError
from luar.cli import main as cli_main
from luar.questions import load_questions, parse_questions

from .conftest import EXAMPLES

QUESTIONS = parse_questions([
    {"id": "team", "type": "choice", "question": "Which team?", "options": {"billing": "money", "tech": "bugs"}},
    {"id": "level", "type": "score", "question": "How bad?", "options": ["low", "high"]},
    {"id": "refund", "type": "noul", "question": "Refund?"},
])
# Raw output of thx01 1.0.0: `confidence` is an entropy measure, not the probability of the answer
RAW = {
    "team": {"type": "choice", "choice": "tech", "probabilities": {"billing": 0.09, "tech": 0.91}, "confidence": 0.684},
    "level": {"type": "score", "score": 0.8, "legend": {"0": "low", "1": "high"},
              "probabilities": {"0": 0.2, "1": 0.8}, "confidence": 0.3},
    "refund": {"type": "noul", "noul": 0.1, "confidence": 0.9},
}


class FakeAgent:
    def __init__(self):
        self.calls = []

    def predict_batch(self, states, questions, batch_size=64):
        self.calls.append((list(states), questions, batch_size))
        return [{"model": "THX-01", "answers": RAW} for _ in states]


@pytest.fixture
def fake_thx(monkeypatch):
    """thx01 as a stand-in: records the folder it loads, and needs no model or network."""
    agent, loaded = FakeAgent(), []
    module = types.SimpleNamespace(load=lambda path, device=None: loaded.append((path, device)) or agent)
    monkeypatch.setitem(sys.modules, "thx01", module)
    monkeypatch.setattr(tb, "local_model", lambda: "model-folder")
    monkeypatch.setattr(tb, "verify_weights", lambda folder: None)
    return types.SimpleNamespace(agent=agent, loaded=loaded)


def test_answers_use_the_probability_of_the_option(fake_thx):
    row = tb.ThxBackend().decide(["some text"], QUESTIONS)[0]
    assert (row["team"].value, row["team"].confidence) == ("tech", pytest.approx(0.91))
    assert (row["level"].value, row["level"].confidence) == ("high", pytest.approx(0.8))
    assert (row["refund"].value, row["refund"].confidence) == ("no", pytest.approx(0.9))


def test_a_missing_answer_stays_empty():
    assert tb.extract_answer(None, "choice").value is None
    assert tb.extract_answer({"choice": None}, "choice").confidence is None


def test_questions_go_in_the_format_the_model_reads(fake_thx):
    tb.ThxBackend().decide(["some text"], QUESTIONS)
    _, spec, _ = fake_thx.agent.calls[0]
    assert spec == {q.id: q.to_laya() for q in QUESTIONS}


def test_batches_keep_the_order_and_report_progress(fake_thx):
    texts = [f"text {i}" for i in range(5)]
    seen = []
    results = tb.ThxBackend(batch_size=2).decide(texts, QUESTIONS, progress=lambda done, total: seen.append((done, total)))
    assert len(results) == 5
    assert [t for states, _, _ in fake_thx.agent.calls for t in states] == texts
    assert seen == [(2, 5), (4, 5), (5, 5)]


def test_no_rows_load_nothing_extra(fake_thx):
    assert tb.ThxBackend().decide([], QUESTIONS) == []
    assert fake_thx.agent.calls == []


def test_the_model_is_loaded_once_from_the_pinned_folder(fake_thx):
    backend = tb.ThxBackend(device="cpu")
    backend.decide(["a"], QUESTIONS)
    backend.decide(["b"], QUESTIONS)
    assert fake_thx.loaded == [("model-folder", "cpu")]


def test_a_missing_package_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "thx01", None)  # makes `import thx01` raise ImportError
    with pytest.raises(tb.ThxNotInstalledError, match=r'pip install "luar\[thx\]"'):
        tb.ThxBackend().decide(["a"], QUESTIONS)


def test_tampered_weights_are_refused(tmp_path, monkeypatch):
    import luar.backends.laya_backend as lb

    monkeypatch.setattr(lb, "VERIFIED_CACHE", tmp_path / "verified.json")
    (tmp_path / "model.safetensors").write_bytes(b"tampered")
    with pytest.raises(ModelIntegrityError, match="THX-01.*does not match"):
        tb.verify_weights(tmp_path)
    monkeypatch.setattr(tb, "WEIGHTS_SHA256", hashlib.sha256(b"tampered").hexdigest())
    tb.verify_weights(tmp_path)


def test_a_tampered_model_is_never_loaded(fake_thx, monkeypatch):
    def refuse(folder):
        raise ModelIntegrityError("no")

    monkeypatch.setattr(tb, "verify_weights", refuse)
    with pytest.raises(ModelIntegrityError):
        tb.ThxBackend().decide(["a"], QUESTIONS)
    assert fake_thx.loaded == []


def test_the_download_is_pinned_and_verified(fake_thx, monkeypatch):
    import huggingface_hub

    asked, verified = [], []
    monkeypatch.setattr(huggingface_hub, "snapshot_download",
                        lambda repo, **kw: asked.append((repo, kw)) or "downloaded")
    monkeypatch.setattr(tb, "verify_weights", verified.append)
    assert tb.download_model() == "downloaded"
    repo, options = asked[0]
    assert (repo, options["revision"]) == (tb.REPO, tb.REVISION)
    assert "NOTICE" in options["allow_patterns"]
    assert verified == ["downloaded"]


def test_laya_stays_the_default():
    assert ENGINES[0] == "laya"
    assert isinstance(make_backend(), LayaBackend)
    assert isinstance(make_backend("thx"), tb.ThxBackend)


def test_command_line_defaults_to_laya_and_can_choose_thx(monkeypatch):
    import luar.backends as backends

    asked = []

    def fake_make(name, **options):
        asked.append((name, options))
        raise ValueError("stop here")

    monkeypatch.setattr(backends, "make_backend", fake_make)
    questions = str(EXAMPLES / "avaliacoes_perguntas.json")
    base = ["run", str(EXAMPLES / "avaliacoes.csv"), "-q", questions, "-c", "avaliacao"]
    assert cli_main(base) == 2
    assert cli_main([*base, "--engine", "thx"]) == 2
    assert [name for name, _ in asked] == ["laya", "thx"]
    assert "checkpoint" not in asked[1][1]


def test_command_line_refuses_a_laya_variant_with_thx(capsys):
    args = ["run", str(EXAMPLES / "avaliacoes.csv"), "-q", str(EXAMPLES / "avaliacoes_perguntas.json"),
            "-c", "avaliacao", "--engine", "thx", "--checkpoint", "english"]
    assert cli_main(args) == 2
    assert "--checkpoint only applies" in capsys.readouterr().err


def test_download_command(monkeypatch):
    from luar.backends import laya_backend

    laya, thx = [], []
    monkeypatch.setattr(laya_backend, "download_checkpoints", lambda checkpoints: laya.append(checkpoints) or [])
    monkeypatch.setattr(tb, "download_model", lambda: thx.append(True) or "folder")
    assert cli_main(["download"]) == 0  # the default leaves the optional engine out
    assert (laya, thx) == ([("multilingual", "english")], [])
    assert cli_main(["download", "thx-01"]) == 0
    assert (laya, thx) == ([("multilingual", "english")], [True])


def test_the_page_offers_the_engine_with_laya_selected():
    app = pytest.importorskip("luar.app")
    demo = app.build()
    dropdowns = [c["props"] for c in demo.config["components"] if c["type"] == "dropdown"]
    engine = next(d for d in dropdowns if d.get("label") == "Engine")
    assert engine["value"] == "laya"
    relabel = next(fn for fn in demo.fns.values() if getattr(fn.fn, "__name__", "") == "relabel")
    out = relabel.fn("pt", app.questions_frame([]), None, None, "auto", "thx")
    assert len(out) == len(relabel.outputs)
    assert "Motor" in repr(out) and "THX-01 (opcional)" in repr(out)
    assert any(isinstance(u, dict) and u.get("value") == "thx" for u in out)


def test_the_page_uses_the_chosen_engine(monkeypatch):
    app = pytest.importorskip("luar.app")
    monkeypatch.setattr(app, "_backends", {})
    backend = app._backend("auto", ["texto"], QUESTIONS, "thx")
    assert isinstance(backend, tb.ThxBackend)
    assert app._backend("english", ["texto"], QUESTIONS, "thx") is backend  # reused between runs


@pytest.mark.slow
def test_real_model_runs_offline_once_downloaded(monkeypatch):
    """Needs `pip install "luar[thx]"` and `luar download thx-01`."""
    import socket

    pytest.importorskip("thx01")
    if tb.local_model() is None:
        pytest.skip("THX-01 model not downloaded")

    def refuse(*args, **kwargs):
        raise AssertionError("THX-01 tried to reach the network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    questions = load_questions(EXAMPLES / "avaliacoes_perguntas.json")
    answers = tb.ThxBackend().decide(["O pacote chegou atrasado."], questions)[0]
    assert answers["assunto"].value == "entrega"
    assert answers["quer_reembolso"].value in ("yes", "no")
    assert 0 <= answers["assunto"].confidence <= 1
