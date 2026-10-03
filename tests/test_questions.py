import pytest

from luar.questions import (
    MAX_OPTIONS,
    QuestionError,
    dump_questions,
    load_questions,
    parse_questions,
)

from .conftest import EXAMPLES


def test_luar_format_with_all_types():
    qs = parse_questions([
        {"id": "topic", "type": "choice", "question": "Topic?", "options": {"a": "first", "b": "second"}},
        {"id": "level", "type": "score", "question": "Level?", "options": ["low", "mid", "high"]},
        {"id": "flag", "type": "noul", "question": "Is it?"},
    ])
    assert [q.type for q in qs] == ["choice", "score", "noul"]
    assert qs[0].to_laya() == {"type": "choice", "instructions": "Topic?", "criteria": {"a": "first", "b": "second"}}
    assert qs[1].to_laya() == {"type": "score", "instructions": "Level?", "criteria": ["low", "mid", "high"]}
    assert qs[2].to_laya() == {"type": "noul", "instructions": "Is it?"}


def test_score_descriptions_reach_the_model():
    qs = parse_questions([{"id": "sev", "type": "score", "question": "How bad?",
                           "options": {"none": "no problem", "minor": "", "major": "item unusable"}}])
    assert qs[0].to_laya()["criteria"] == ["none: no problem", "minor", "major: item unusable"]


def test_laya_native_format_is_accepted():
    qs = parse_questions({
        "team": {"type": "choice", "instructions": "Which team?", "criteria": {"x": "desc x", "y": "desc y"}},
        "ok": {"type": "noul", "instructions": "Ok?"},
    })
    assert qs[0].id == "team" and qs[0].question == "Which team?"
    assert qs[0].options == {"x": "desc x", "y": "desc y"}


def test_options_as_text():
    qs = parse_questions([{"id": "t", "type": "choice", "question": "?", "options": "red: warm; blue\ngreen: cool"}])
    assert qs[0].options == {"red": "warm", "blue": "", "green": "cool"}
    # label without description is sent to the model as its own description
    assert qs[0].to_laya()["criteria"]["blue"] == "blue"


@pytest.mark.parametrize("bad, msg", [
    ({"id": "1x", "type": "noul", "question": "?"}, "Invalid question id"),
    ({"id": "a", "type": "multiple", "question": "?"}, "type must be"),
    ({"id": "a", "type": "noul", "question": "  "}, "empty"),
    ({"id": "a", "type": "choice", "question": "?", "options": ["only"]}, "at least 2"),
    ({"id": "a", "type": "noul", "question": "?", "options": ["x", "y"]}, "no options"),
    ({"id": "a", "type": "choice", "question": "?", "options": [f"o{i}" for i in range(MAX_OPTIONS + 1)]}, "at most"),
])
def test_invalid_questions(bad, msg):
    with pytest.raises(QuestionError, match=msg):
        parse_questions([bad])


def test_duplicate_and_empty():
    with pytest.raises(QuestionError, match="Duplicate"):
        parse_questions([{"id": "a", "type": "noul", "question": "?"}] * 2)
    with pytest.raises(QuestionError, match="at least one"):
        parse_questions([])


def test_example_files_load_and_round_trip():
    for name in ("reviews_questions.json", "avaliacoes_perguntas.json"):
        qs = load_questions(EXAMPLES / name)
        import json
        assert [q.to_dict() for q in parse_questions(json.loads(dump_questions(qs)))] == [q.to_dict() for q in qs]
