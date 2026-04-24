import os

from dotenv import load_dotenv
from nicegui import app, ui
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from Base import Base

load_dotenv()

try:
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
except ImportError:
    pass

database_url = os.getenv("DATABASE_URL")
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def _ensure_survey_extra_columns() -> None:
    """Add columns missing on older DBs (create_all does not alter existing tables)."""
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import OperationalError

    insp = inspect(engine)
    if not insp.has_table("surveys"):
        return
    cols = {c["name"] for c in insp.get_columns("surveys")}
    specs = [
        ("participant_landing_html", "TEXT"),
        ("opens_at", "TIMESTAMP"),
        ("closes_at", "TIMESTAMP"),
    ]
    for name, sql_type in specs:
        if name in cols:
            continue
        if engine.dialect.name == "postgresql":
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE surveys ADD COLUMN IF NOT EXISTS {name} {sql_type}"))
        else:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE surveys ADD COLUMN {name} {sql_type}"))
            except OperationalError:
                pass


_ensure_survey_extra_columns()

import googleSSO  # noqa: E402, F401
import authentication  # noqa: E402, F401
import admin_panel  # noqa: E402, F401

from app_config import get_informed_consent_url  # noqa: E402
from survey_browser_flow import render_survey_entry_with_landing  # noqa: E402
from survey_from_db import student_survey_access  # noqa: E402

TEAM = [
    ("Research team", "Principal investigator and instrument design"),
    ("Assessment & analytics", "Data handling under IR and FERPA guidance"),
]


@ui.page("/")
def landing_page():
    external_consent = get_informed_consent_url()
    with ui.column().classes("w-full min-h-screen bg-slate-50"):
        with ui.column().classes("max-w-3xl mx-auto px-6 py-12 gap-6"):
            ui.label("Student Assessment Instrument (SAI)").classes(
                "text-3xl md:text-4xl font-bold text-slate-900"
            )
            ui.label("Research Project").classes("text-xl text-slate-600 -mt-2")

            ui.markdown(
                """
This site supports **SAI (Student Assessment Instrument)** research: designing and
evaluating how we gather instructional feedback while protecting respondents.

Student participation is **by invitation only**, using a **personalized link** issued by
your institution’s research office. Those links carry a pseudonymous identifier so the
office can manage consent and longitudinal tracking **without** this application storing
directly identifying student information in the survey link itself.
"""
            ).classes("text-slate-700 leading-relaxed")

            with ui.row().classes("flex-wrap gap-4 items-center"):
                ui.button(
                    "Informed consent (summary)",
                    on_click=lambda: ui.navigate.to("/consent"),
                ).classes("bg-blue-700 text-white px-4 py-2 rounded-lg")
                if external_consent:
                    ui.link("Official consent document (opens in new tab)", external_consent, new_tab=True).classes(
                        "text-blue-800 underline"
                    )

            ui.separator().classes("my-2")

            ui.label("Meet the team").classes("text-2xl font-bold text-slate-900")
            with ui.column().classes("gap-3 w-full"):
                for name, role in TEAM:
                    with ui.card().classes("w-full p-4 bg-white border border-slate-200 shadow-sm"):
                        ui.label(name).classes("font-semibold text-slate-900")
                        ui.label(role).classes("text-slate-600 text-sm")

            ui.separator().classes("my-2")

            ui.label("Staff access").classes("text-lg font-semibold text-slate-800")
            ui.label(
                "Administrators, faculty, and institutional research staff sign in here."
            ).classes("text-sm text-slate-600")
            ui.button("Staff sign-in", on_click=lambda: ui.navigate.to("/login")).classes(
                "bg-slate-800 text-white px-5 py-2 rounded-lg w-fit"
            )


@ui.page("/consent")
def consent_page():
    external = get_informed_consent_url()
    with ui.column().classes("w-full min-h-screen bg-slate-50 px-6 py-10"):
        with ui.card().classes("max-w-3xl mx-auto w-full p-8 bg-white border border-slate-200"):
            ui.label("Informed consent — summary").classes("text-2xl font-bold text-slate-900 mb-4")
            ui.markdown(
                """
Participation is voluntary. You may skip questions or stop at any time. Responses are
used for research and quality improvement under protocols approved by your institution.

**Who sees your answers:** authorized researchers and institutional research staff, under
FERPA and local policy. This system stores survey responses linked to a **pseudonymous
identifier** (`sid`) supplied by your institution—not your email or student ID entered
in this form by default.

For the full consent language and data retention details, use the official document
linked from the project home page when your IR office provides it.
"""
            ).classes("text-slate-700 leading-relaxed")
            if external:
                ui.link("Open the official informed consent document", external, new_tab=True).classes(
                    "text-blue-800 underline mt-4 block"
                )
            ui.button("← Back to home", on_click=lambda: ui.navigate.to("/")).classes(
                "mt-6 bg-slate-200 text-slate-800"
            )


@ui.page("/survey/{survey_id}")
def student_survey_entry(survey_id: int, request: Request):
    sid = (request.query_params.get("sid") or "").strip()
    if not sid:
        with ui.column().classes(
            "w-full min-h-screen bg-slate-100 flex flex-col items-center justify-center px-6"
        ):
            with ui.card().classes("max-w-lg w-full p-8 text-center"):
                ui.label("Personalized link required").classes("text-xl font-bold text-slate-900 mb-2")
                ui.label(
                    "Open the survey using the link emailed to you by your institution. "
                    "It includes a secure participant code."
                ).classes("text-slate-600")
                ui.button("Project home", on_click=lambda: ui.navigate.to("/")).classes("mt-6")
        return

    db_session = Session()
    try:
        survey, access_error = student_survey_access(db_session, survey_id)
    finally:
        db_session.close()

    if access_error:
        with ui.column().classes(
            "w-full min-h-screen bg-slate-100 flex flex-col items-center justify-center px-6"
        ):
            with ui.card().classes("max-w-lg w-full p-8 text-center"):
                ui.label("Survey unavailable").classes("text-xl font-bold text-slate-900 mb-2")
                ui.label(access_error).classes("text-slate-600")
                ui.button("Project home", on_click=lambda: ui.navigate.to("/")).classes("mt-6")
        return

    render_survey_entry_with_landing(Session, survey, survey_id, sid)


storage_secret = os.getenv("NICEGUI_STORAGE_SECRET", "your-secret-key-change-this-in-production-12345")
ui.run(storage_secret=storage_secret)
