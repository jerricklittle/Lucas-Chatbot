"""Build runtime survey JSON (same shape as legacy JSON files) from ORM models."""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from survey_models import QuestionBank, Survey, SurveyQuestion


def student_survey_access(session: Session, survey_id: int) -> tuple[dict[str, Any] | None, str | None]:
    """
    Enforce active survey, open/close window, and configured questions.
    Returns (runtime_survey_dict, error_message). error_message is None when OK.
    """
    row = session.query(Survey).filter_by(id=survey_id, is_active=True).first()
    if not row:
        return None, "This survey is not available."
    now = datetime.utcnow()
    opens_at = getattr(row, "opens_at", None)
    closes_at = getattr(row, "closes_at", None)
    if opens_at and now < opens_at:
        t = opens_at.strftime("%Y-%m-%d %H:%M UTC")
        return None, f"This survey is not open yet. It opens on {t}."
    if closes_at and now > closes_at:
        t = closes_at.strftime("%Y-%m-%d %H:%M UTC")
        return None, f"This survey has closed (as of {t} UTC) and is no longer accepting responses."
    payload = load_survey_from_db(session, survey_id)
    if not payload:
        return None, "This survey is not ready yet (no questions configured)."
    return payload, None


def _question_bank_to_item(q: QuestionBank, sq: SurveyQuestion) -> dict[str, Any]:
    cfg = q.config or {}
    item: dict[str, Any] = {
        "id": q.name,
        "version": q.version,
        "type": q.question_type,
        "prompt": q.question_text,
        "required": True,
        "order": sq.order,
        "tags": list((cfg.get("tags") or []) if isinstance(cfg.get("tags"), list) else []),
    }
    if q.question_type == "likert":
        labels = (cfg.get("scale") or {}).get("labels") or {}
        if labels:
            keys = [int(k) for k in labels]
            item["scale"] = {"min": min(keys), "max": max(keys), "labels": labels}
        else:
            item["scale"] = {"min": 1, "max": 5, "labels": {}}
    elif q.question_type == "boolean":
        opts = cfg.get("options") or {}
        item["options"] = {
            "trueLabel": opts.get("trueLabel", "Yes"),
            "falseLabel": opts.get("falseLabel", "No"),
        }
    elif q.question_type == "text":
        item["text"] = (cfg.get("text") or {}).copy()
        if sq.is_adaptive:
            item["adaptive"] = True
    elif q.question_type == "multi":
        item["options"] = cfg.get("options") or ["Option 1", "Option 2"]
    return item


def load_survey_from_db(session: Session, survey_id: int) -> dict[str, Any] | None:
    survey = session.query(Survey).filter_by(id=survey_id).first()
    if not survey or not survey.is_active:
        return None

    rows = (
        session.query(SurveyQuestion, QuestionBank)
        .join(QuestionBank, SurveyQuestion.question_id == QuestionBank.id)
        .filter(SurveyQuestion.survey_id == survey_id)
        .order_by(SurveyQuestion.order)
        .all()
    )
    if not rows:
        return None

    questions: list[dict[str, Any]] = []
    for sq, q in rows:
        questions.append(_question_bank_to_item(q, sq))

    settings = dict(survey.settings or {})
    if settings.get("randomize"):
        imi_questions: list[dict[str, Any]] = []
        imi_indices: list[int] = []
        for idx, q in enumerate(questions):
            if "IMI" in q.get("tags", []):
                imi_questions.append(q)
                imi_indices.append(idx)
        random.shuffle(imi_questions)
        for new_q, idx in zip(imi_questions, imi_indices):
            questions[idx] = new_q

    landing = getattr(survey, "participant_landing_html", None) or ""

    return {
        "schemaVersion": "1.0.0",
        "id": str(survey.id),
        "title": survey.name,
        "description": survey.description or "",
        "participant_landing_html": landing,
        "surveyVersion": survey.version,
        "status": "published",
        "locale": "en-US",
        "settings": settings,
        "metadata": {},
        "questions": questions,
    }
