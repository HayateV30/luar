import pytest

from luar.backends.laya_backend import LayaBackend, extract_answer, pick_checkpoint
from luar.engine import accuracy, run_file
from luar.questions import load_questions

from .conftest import EXAMPLES

# Raw output captured from laya 0.3.21 (multilingual checkpoint)
RAW = {
    "team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.9965, "tech": 0.0035},
              "confidence": 0.9665, "answer_confidence": 0.9965},
    "level": {"type": "score", "score": 1.09, "legend": {"0": "low", "1": "medium", "2": "high"},
                 "probabilities": {"0": 0.2003, "1": 0.5094, "2": 0.2903}, "answer_confidence": 0.5094},
    "refund": {"type": "noul", "noul": 0.9878},
    "other": {"type": "noul", "noul": 0.1},
}


def test_extract_answer_formats():
    assert extract_answer(RAW["team"], "choice").value == "billing"
    assert extract_answer(RAW["team"], "choice").confidence == pytest.approx(0.9965)
    score = extract_answer(RAW["level"], "score")
    assert (score.value, score.confidence) == ("medium", pytest.approx(0.5094))
    assert extract_answer(RAW["refund"], "noul").value == "yes"
    no = extract_answer(RAW["other"], "noul")
    assert (no.value, no.confidence) == ("no", pytest.approx(0.9))
    missing = extract_answer(None, "choice")
    assert missing.value is None and missing.confidence is None


def test_score_answer_is_the_label_not_the_description():
    raw = {"type": "score", "legend": {"0": "none: no problem", "1": "major: item unusable"},
           "probabilities": {"0": 0.2, "1": 0.8}}
    assert extract_answer(raw, "score", ["none", "major"]).value == "major"


def test_pick_checkpoint_by_language():
    en_q = load_questions(EXAMPLES / "reviews_questions.json")
    pt_q = load_questions(EXAMPLES / "avaliacoes_perguntas.json")
    assert pick_checkpoint(["The package arrived late.", "Great sound, long battery."], en_q) == "english"
    assert pick_checkpoint(["O pacote chegou atrasado.", "Som excelente, bateria longa."], pt_q) == "multilingual"
    assert pick_checkpoint(["ok", "?"], []) == "multilingual"  # undecided -> safer default


def test_unknown_checkpoint():
    with pytest.raises(ValueError, match="Unknown checkpoint"):
        LayaBackend(checkpoint="xx")


@pytest.mark.slow
@pytest.mark.parametrize("data, questions, column", [
    ("reviews.csv", "reviews_questions.json", "review"),
    ("avaliacoes.csv", "avaliacoes_perguntas.json", "avaliacao"),
])
def test_real_model_on_examples(tmp_path, data, questions, column):
    """Runs the real model; needs the weights (downloaded on first use). `pytest -m slow -s`"""
    qs = load_questions(EXAMPLES / questions)
    res = run_file(EXAMPLES / data, qs, [column], LayaBackend(), out_dir=tmp_path)
    print("\n" + res.summary_path.read_text(encoding="utf-8"))
    for q in qs:
        hits, total = accuracy(res, q)
        assert hits / total >= 0.85, f"{q.id}: {hits}/{total}"
        if q.type == "noul":  # all-"no" would still score high; make sure it finds the yeses
            assert (res.table[q.id] == "yes").any(), f"{q.id}: no row answered yes"


def test_missing_laya_gives_install_hint(monkeypatch, capsys):
    from luar.backends.laya_backend import LayaNotInstalledError
    from luar.cli import main as cli_main

    monkeypatch.setitem(__import__("sys").modules, "laya", None)  # makes `import laya` fail
    with pytest.raises(LayaNotInstalledError, match=r'pip install "luar\[laya\]"'):
        LayaBackend().decide(["t"], load_questions(EXAMPLES / "reviews_questions.json"))

    code = cli_main(["run", str(EXAMPLES / "reviews.csv"), "-q", str(EXAMPLES / "reviews_questions.json"),
                     "-c", "review"])
    assert code == 2 and "luar[laya]" in capsys.readouterr().err
