"""The "socket" every decision engine plugs into."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from ..questions import Question


@dataclass
class Answer:
    value: str | None        # chosen label; "yes"/"no" for noul; None if the engine gave nothing
    confidence: float | None  # 0..1, how sure the engine is about `value`


Progress = Callable[[int, int], None]


class Backend(Protocol):
    name: str

    def decide(
        self,
        texts: list[str],
        questions: list[Question],
        progress: Progress | None = None,
    ) -> list[dict[str, Answer]]:
        """Return one {question_id: Answer} per text, in the same order."""
        ...
