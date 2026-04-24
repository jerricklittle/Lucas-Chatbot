"""
Per-client survey session state and UI (avoids shared globals for concurrent respondents).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from nicegui import ui

from Question_Timer import Question_Timer
from chatbot import analyze_all_responses_for_survey
from responses import Response
from time_per_question import Time_Per_Question

_survey_sessions: dict[str, dict[str, Any]] = {}


def _cid() -> str:
    from nicegui import context

    return str(context.client.id)


def _session() -> dict[str, Any]:
    cid = _cid()
    if cid not in _survey_sessions:
        _survey_sessions[cid] = {}
    return _survey_sessions[cid]


def reset_survey_session(survey: dict[str, Any], survey_db_id: int, sid: str) -> None:
    static_count = len(survey.get("questions", []))
    _survey_sessions[_cid()] = {
        "timer": Question_Timer(),
        "survey": survey,
        "survey_db_id": survey_db_id,
        "sid": sid,
        "current_index": 0,
        "answers": {},
        "survey_state": {"mode": "static", "static_count": static_count},
        "dynamic_questions": [],
    }


def clear_survey_session() -> None:
    _survey_sessions.pop(_cid(), None)


def _get_all_questions(s: dict[str, Any]) -> list[dict[str, Any]]:
    return s["survey"]["questions"] + s["dynamic_questions"]


def _save_answer(s: dict[str, Any], question: dict[str, Any], value: Any) -> None:
    s["answers"][question["id"]] = {
        "questionId": question["id"],
        "questionType": question["type"],
        "value": value,
    }


def _handle_text_answer(s: dict[str, Any], question: dict[str, Any], value: str) -> None:
    _save_answer(s, question, value)


async def _generate_dynamic_questions(s: dict[str, Any], refresh_fn) -> None:
    text_responses = []
    survey = s["survey"]
    for q_id, answer in s["answers"].items():
        if answer["questionType"] == "text" and answer.get("value"):
            original_q = None
            for q in survey["questions"]:
                if q["id"] == q_id:
                    original_q = q
                    break
            if original_q and original_q.get("adaptive", False):
                text_value = str(answer["value"]).strip()
                if len(text_value) >= 15:
                    text_responses.append(
                        {
                            "question_id": q_id,
                            "text": text_value,
                            "prompt": original_q["prompt"],
                        }
                    )

    if not text_responses:
        s["survey_state"]["mode"] = "complete"
        refresh_fn()
        return

    try:
        result = await analyze_all_responses_for_survey(text_responses)
        data = json.loads(result)
        if data.get("needs_followup"):
            for idx, fq in enumerate(data.get("followup_questions", []), 1):
                source_q = fq.get("source_question_id", "unknown")
                s["dynamic_questions"].append(
                    {
                        "id": f"followup_{source_q}_{idx}",
                        "type": "text",
                        "prompt": fq["prompt"],
                        "triggered_by": source_q,
                    }
                )
        s["survey_state"]["mode"] = "transition" if s["dynamic_questions"] else "complete"
    except Exception:
        s["survey_state"]["mode"] = "complete"

    refresh_fn()


def _next_page(s: dict[str, Any], refresh_fn) -> None:
    current = s["current_index"]
    static_count = s["survey_state"]["static_count"]

    if current == static_count - 1 and s["survey_state"]["mode"] == "static":
        s["survey_state"]["mode"] = "loading"
        refresh_fn()
        asyncio.create_task(_generate_dynamic_questions(s, refresh_fn))
        return

    all_questions = _get_all_questions(s)
    if current == len(all_questions) - 1 and s["survey_state"]["mode"] == "dynamic":
        s["survey_state"]["mode"] = "complete"
        refresh_fn()
        return

    if current < len(_get_all_questions(s)) - 1:
        s["current_index"] += 1
        refresh_fn()


def _prev_page(s: dict[str, Any], refresh_fn) -> None:
    current = s["current_index"]
    static_count = s["survey_state"]["static_count"]

    if s["survey_state"]["mode"] == "dynamic" and current <= static_count:
        ui.notify("Cannot return to previous questions", type="warning", position="top")
        return

    if s["current_index"] > 0:
        s["current_index"] -= 1
        refresh_fn()


def _advance_to_dynamic(s: dict[str, Any], refresh_fn) -> None:
    s["survey_state"]["mode"] = "dynamic"
    s["current_index"] += 1
    refresh_fn()


def submit_survey(dialog, session_factory, s: dict[str, Any]) -> None:
    s["timer"].stop_all()
    uuid_str = str(uuid.uuid4())
    survey = s["survey"]
    submission = {
        "id": uuid_str,
        "surveyId": survey["id"],
        "surveyVersion": survey["surveyVersion"],
        "submittedAt": datetime.utcnow().isoformat(),
        "answers": list(s["answers"].values()),
        "sid": s["sid"],
    }

    session = session_factory()
    response = Response(
        response=submission,
        uuid=uuid_str,
        sid=s["sid"],
        survey_id=s["survey_db_id"],
    )
    session.add(response)
    session.flush()
    response_id = response.id

    timing_data = s["timer"].get_all_times()
    for question_id, time_seconds in timing_data.items():
        session.add(
            Time_Per_Question(
                response_id=response_id,
                question_id=question_id,
                time_spent=time_seconds,
            )
        )

    session.commit()
    session.close()
    dialog.close()
    clear_survey_session()
    ui.notify("Thank you — your responses were submitted.", type="positive", position="top")
    ui.navigate.to("/")


@ui.refreshable
def survey_page(dialog, session_factory):
    s = _session()
    if not s.get("survey"):
        return

    survey = s["survey"]
    mode = s["survey_state"]["mode"]
    refresh = survey_page.refresh

    if mode == "loading":
        with ui.column().classes(
            "w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6"
        ):
            with ui.card().classes(
                "w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center"
            ):
                ui.label("Analyzing your responses...").classes(
                    "text-2xl font-bold text-gray-800 mb-4"
                )
                ui.spinner(size="lg", color="blue-600")
        return

    if mode == "transition":
        with ui.column().classes(
            "w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6"
        ):
            with ui.card().classes(
                "w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center"
            ):
                ui.label("Thank you for your feedback!").classes(
                    "text-3xl font-bold text-gray-800 mb-3"
                )
                n = len(s["dynamic_questions"])
                ui.label(
                    f"We have {n} follow-up question{'s' if n != 1 else ''}"
                ).classes("text-lg text-gray-600 mb-6")
                ui.button(
                    "Continue",
                    on_click=lambda: _advance_to_dynamic(s, refresh),
                ).classes("bg-blue-600 text-white text-lg px-8 py-3 rounded-lg hover:bg-blue-700")
        return

    if mode == "complete":
        with ui.column().classes(
            "w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6"
        ):
            with ui.card().classes(
                "w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center"
            ):
                ui.label("Thank You!").classes("text-3xl font-bold text-gray-800 mb-3")
                ui.button(
                    "Submit Survey",
                    on_click=lambda: submit_survey(dialog, session_factory, s),
                ).classes(
                    "bg-green-600 text-white text-lg px-8 py-3 rounded-lg hover:bg-green-700"
                )
        return

    questions = _get_all_questions(s)
    q = questions[s["current_index"]]
    total = len(questions)
    current = s["current_index"]
    s["timer"].start_question(q["id"])

    with ui.column().classes("w-full min-h-screen bg-gray-100 flex flex-col items-center py-8 gap-4"):
        with ui.card().classes(
            "w-full max-w-xl bg-white shadow-sm border border-gray-200 rounded-lg px-6 py-5"
        ):
            ui.label(survey.get("title", "SAI survey")).classes(
                "text-2xl font-bold text-gray-800"
            )
            ui.label(f"Question {current + 1} of {total}").classes("text-xs text-gray-400 mt-2")
            ui.linear_progress(value=(current + 1) / total, color="blue-600").classes("mt-1 h-1")

        with ui.card().classes(
            "w-full max-w-xl bg-white shadow-sm border border-gray-200 rounded-lg px-6 py-6"
        ):
            ui.label(q["prompt"]).classes("text-base font-semibold text-gray-800 mb-4")

            if q["type"] == "likert":
                labels = q["scale"]["labels"]
                options = [label for _, label in sorted(labels.items(), key=lambda x: int(x[0]))]
                ui.radio(
                    options,
                    value=s["answers"].get(q["id"], {}).get("value"),
                    on_change=lambda e: _save_answer(s, q, e.value),
                ).classes("gap-2")

            elif q["type"] == "boolean":
                ui.radio(
                    [q["options"]["trueLabel"], q["options"]["falseLabel"]],
                    value=s["answers"].get(q["id"], {}).get("value"),
                    on_change=lambda e: _save_answer(
                        s, q, e.value == q["options"]["trueLabel"]
                    ),
                ).classes("gap-2")

            elif q["type"] == "text":
                textarea = ui.textarea(
                    placeholder=q.get("text", {}).get("placeholder", ""),
                    value=s["answers"].get(q["id"], {}).get("value", ""),
                ).classes("w-full")
                textarea.on(
                    "blur",
                    lambda e: _handle_text_answer(s, q, textarea.value),
                )

            elif q["type"] == "multi":
                opts = q.get("options") or []
                current_vals = list(s["answers"].get(q["id"], {}).get("value") or [])
                ui.select(
                    opts,
                    multiple=True,
                    label="Select all that apply",
                    value=current_vals,
                    on_change=lambda e: _save_answer(s, q, list(e.value or [])),
                ).classes("w-full")

            with ui.row().classes("w-full justify-between mt-6"):
                show_back = survey["settings"].get("allowBack", True) and current > 0
                if s["survey_state"]["mode"] == "dynamic" and current == s["survey_state"]["static_count"]:
                    show_back = False

                if show_back:
                    ui.button("Back", on_click=lambda: _prev_page(s, refresh)).classes(
                        "bg-gray-200 text-gray-700 hover:bg-gray-300"
                    )
                else:
                    ui.label("")

                is_last_static = (
                    current == s["survey_state"]["static_count"] - 1
                    and s["survey_state"]["mode"] == "static"
                )
                is_truly_last = current >= len(questions) - 1

                if is_last_static:
                    ui.button(
                        "Next",
                        on_click=lambda: _next_page(s, refresh),
                    ).classes("bg-blue-600 text-white hover:bg-blue-700")
                elif is_truly_last:
                    ui.button(
                        "Submit",
                        on_click=lambda: submit_survey(dialog, session_factory, s),
                    ).classes("bg-green-600 text-white hover:bg-green-700")
                else:
                    ui.button(
                        "Next",
                        on_click=lambda: _next_page(s, refresh),
                    ).classes("bg-blue-600 text-white hover:bg-blue-700")


def render_survey_flow(session_factory, survey: dict[str, Any], survey_db_id: int, sid: str) -> None:
    reset_survey_session(survey, survey_db_id, sid)

    with ui.dialog().props("maximized") as dialog:
        survey_page(dialog, session_factory)

    dialog.open()


def render_survey_entry_with_landing(
    session_factory, survey: dict[str, Any], survey_db_id: int, sid: str
) -> None:
    """
    Optional HTML landing (instructions, consent) before opening the maximized survey dialog.
    Content is authored by staff in the admin survey editor (trusted HTML).
    """
    root = ui.column().classes("w-full min-h-screen bg-slate-50")

    def proceed() -> None:
        root.clear()
        render_survey_flow(session_factory, survey, survey_db_id, sid)

    landing = (survey.get("participant_landing_html") or "").strip()
    with root:
        if landing:
            with ui.column().classes("max-w-3xl mx-auto w-full px-4 py-8 gap-6"):
                ui.label(survey.get("title", "Survey")).classes("text-2xl font-bold text-slate-900")
                ui.html(landing, sanitize=False).classes(
                    "survey-landing text-slate-800 text-base leading-relaxed [&_a]:text-blue-700 [&_a]:underline"
                )
                ui.button(
                    "Continue to the survey",
                    on_click=proceed,
                ).classes("bg-blue-700 text-white px-6 py-2 rounded-lg w-fit")
        else:
            ui.timer(0.05, proceed, once=True)
