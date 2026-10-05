"""Question definitions: what the user wants to catalog in each row."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import t

QUESTION_TYPES = ("choice", "score", "noul")
EXPERIMENTAL_TYPES = ("score",)
MAX_OPTIONS = 20
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class QuestionError(ValueError):
    """Raised when a question definition is invalid."""


@dataclass
class Question:
    id: str
    type: str
    question: str
    # choice: {label: description}; score: {label: ""} in ascending order; noul: empty
    options: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not _ID_RE.match(self.id or ""):
            raise QuestionError(t("q_bad_id", id=repr(self.id)))
        if self.type not in QUESTION_TYPES:
            raise QuestionError(t("q_bad_type", id=repr(self.id), types=", ".join(QUESTION_TYPES)))
        if not self.question.strip():
            raise QuestionError(t("q_empty", id=repr(self.id)))
        if self.type == "noul":
            if self.options:
                raise QuestionError(t("q_noul_options", id=repr(self.id)))
            return
        if len(self.options) < 2:
            raise QuestionError(t("q_few_options", id=repr(self.id), type=self.type))
        if len(self.options) > MAX_OPTIONS:
            raise QuestionError(t("q_many_options", id=repr(self.id), n=len(self.options), max=MAX_OPTIONS))

    def to_laya(self) -> dict:
        q: dict = {"type": self.type, "instructions": self.question}
        if self.type == "choice":
            q["criteria"] = {k: (v or k) for k, v in self.options.items()}
        elif self.type == "score":
            # levels in ascending order; the description tells the model what each level means
            q["criteria"] = [f"{k}: {v}" if v else k for k, v in self.options.items()]
        return q

    def to_dict(self) -> dict:
        d: dict = {"id": self.id, "type": self.type, "question": self.question}
        if self.type == "choice":
            d["options"] = dict(self.options) if any(self.options.values()) else list(self.options)
        elif self.type == "score":
            d["options"] = list(self.options)
        return d


def _parse_options(raw) -> dict[str, str]:
    """Accept a list of labels, a {label: description} dict, or text like
    "a; b; c" / "a: description; b: description" (also one option per line)."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return {str(k).strip(): str(v or "").strip() for k, v in raw.items()}
    if isinstance(raw, (list, tuple)):
        return {str(x).strip(): "" for x in raw if str(x).strip()}
    if isinstance(raw, str):
        opts: dict[str, str] = {}
        for part in re.split(r"[;\n]", raw):
            part = part.strip()
            if not part:
                continue
            label, _, desc = part.partition(":")
            opts[label.strip()] = desc.strip()
        return opts
    raise QuestionError(t("q_bad_options", raw=repr(raw)))


def question_from_dict(d: dict, qid: str | None = None) -> Question:
    """Build a Question from LUAR's format ({id, type, question, options})
    or from Laya's native format ({type, instructions, criteria})."""
    qid = d.get("id", qid)
    text = d.get("question", d.get("instructions", ""))
    options = d.get("options", d.get("criteria"))
    return Question(
        id=str(qid or "").strip(),
        type=str(d.get("type", "")).strip().lower(),
        question=str(text or "").strip(),
        options=_parse_options(options),
    )


def parse_questions(data) -> list[Question]:
    """Accept a list of question dicts, or a Laya-style {id: {...}} mapping."""
    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]
    if isinstance(data, dict):
        questions = [question_from_dict(v, k) for k, v in data.items()]
    elif isinstance(data, list):
        questions = [question_from_dict(v) for v in data]
    else:
        raise QuestionError(t("q_bad_structure"))
    validate_questions(questions)
    return questions


def validate_questions(questions: list[Question]) -> None:
    if not questions:
        raise QuestionError(t("q_none"))
    seen = set()
    for q in questions:
        q.validate()
        if q.id in seen:
            raise QuestionError(t("q_duplicate", id=repr(q.id)))
        seen.add(q.id)


def load_questions(path: str | Path) -> list[Question]:
    with open(path, encoding="utf-8-sig") as f:
        return parse_questions(json.load(f))


def dump_questions(questions: list[Question]) -> str:
    return json.dumps([q.to_dict() for q in questions], indent=2, ensure_ascii=False)
