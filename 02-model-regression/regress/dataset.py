"""Versioned golden dataset (guide Phase 2). Each case has a stable id, input, expected output,
difficulty, notes and a verification record. AI-drafted cases are labelled and do NOT count as
human-verified ground truth until a person verifies them in scripts/review_ui.py."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from .feature import Category


class Verification(BaseModel):
    status: str = "ai_generated"       # ai_generated | human_verified | rejected
    verified_by: str | None = None
    verified_at: str | None = None


class GoldenCase(BaseModel):
    id: str
    input: str
    expected_category: Category
    expected_summary: str
    expected_difficulty: str = Field(pattern="^(easy|medium|hard)$")
    tags: list[str] = []
    notes: str = ""
    verification: Verification = Verification()


class GoldenDataset(BaseModel):
    version: str
    created: str
    description: str = ""
    cases: list[GoldenCase]

    @classmethod
    def load(cls, path: Path) -> "GoldenDataset":
        return cls(**json.loads(path.read_text()))

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=1) + "\n")

    def fingerprint(self) -> str:
        """Content hash so a run records exactly which cases/labels it was scored against."""
        payload = json.dumps([c.model_dump(exclude={"verification"}) for c in self.cases], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def active(self, only_verified: bool = False) -> list[GoldenCase]:
        cases = [c for c in self.cases if c.verification.status != "rejected"]
        if only_verified:
            cases = [c for c in cases if c.verification.status == "human_verified"]
        return cases

    def counts(self) -> dict:
        from collections import Counter
        return {"total": len(self.cases),
                "by_status": dict(Counter(c.verification.status for c in self.cases)),
                "by_category": dict(Counter(c.expected_category for c in self.cases)),
                "by_difficulty": dict(Counter(c.expected_difficulty for c in self.cases))}
