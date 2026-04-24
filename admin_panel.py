"""
Admin Panel for Survey and Question Management
Provides CRUD operations for surveys and questions via NiceGUI interface
"""

import csv
import io
import json
import os
import secrets
from urllib.parse import quote

from nicegui import app, ui
from starlette.requests import Request
from sqlalchemy import create_engine, desc, func
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from Base import Base
from survey_models import Survey, QuestionBank, SurveyQuestion, generate_survey_public_id
from user import User
from survey_from_db import load_survey_from_db
from app_config import get_public_base_url
from authentication import (
    is_admin,
    is_ir,
    is_project_admin,
    can_access_ir_tools,
    get_current_user,
    get_current_user_id,
    get_current_user_role,
    logout_user,
)
from dotenv import load_dotenv

load_dotenv()

# Database setup
database_url = os.getenv('DATABASE_URL')
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

# Create all tables
Base.metadata.create_all(engine)


def _fmt_datetime_local(dt) -> str:
    if dt is None:
        return ''
    return dt.strftime('%Y-%m-%dT%H:%M')


def _parse_datetime_local(raw: str | None):
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip()[:16]
    try:
        return datetime.strptime(s, '%Y-%m-%dT%H:%M')
    except ValueError:
        return None


_USER_LIST_PAGER = {'page': 1, 'per_page': 10}
_USER_LIST_SEARCH = {'q': ''}


def _user_search_filter(query, q: str):
    """Case-insensitive email substring; escape LIKE metacharacters in ``q``."""
    t = (q or '').strip()
    if not t:
        return query
    escaped = (
        t.replace('\\', '\\\\')
        .replace('%', '\\%')
        .replace('_', '\\_')
        .lower()
    )
    pat = f'%{escaped}%'
    return query.filter(func.lower(User.email).like(pat, escape='\\'))


# ═══════════════════════════════════════════════════════════════
# QUESTION BANK CRUD
# ═══════════════════════════════════════════════════════════════

@ui.refreshable
def question_index_page():
    """Page 1 from mockups: Question Index - List all questions"""
    
    session = Session()
    current_user_id = get_current_user_id()
    # Show user's questions + default questions (created_by=NULL)
    questions = session.query(QuestionBank).filter(
        (QuestionBank.created_by == current_user_id) | (QuestionBank.created_by == None)
    ).order_by(desc(QuestionBank.updated_at)).all()
    session.close()
    
    with ui.column().classes('w-full p-8'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('Question Index').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                ui.button('← Back', on_click=lambda: ui.navigate.to('/admin')).classes('bg-gray-500 text-white')
                ui.button('➕ New', on_click=lambda: ui.navigate.to('/admin/questions/new')).classes('bg-blue-600 text-white')
        
        # Questions table
        if questions:
            with ui.card().classes('w-full'):
                columns = [
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                    {'name': 'type', 'label': 'Type', 'field': 'type', 'align': 'left'},
                    {'name': 'text', 'label': 'Text', 'field': 'text', 'align': 'left'},
                    {'name': 'version', 'label': 'Version', 'field': 'version', 'align': 'center'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'},
                ]
                
                rows = []
                for q in questions:
                    rows.append({
                        'id': q.id,
                        'name': q.name,
                        'type': q.question_type,
                        'text': q.question_text[:50] + '...' if len(q.question_text) > 50 else q.question_text,
                        'version': q.version,
                        'actions': q.id
                    })
                
                table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full')
                table.add_slot('body-cell-actions', '''
                    <q-td :props="props">
                        <q-btn flat round dense icon="edit" size="sm" color="blue" 
                               @click="$parent.$emit('edit', props.row.id)" />
                        <q-btn flat round dense icon="delete" size="sm" color="red" 
                               @click="$parent.$emit('delete', props.row.id)" />
                    </q-td>
                ''')
                table.on('edit', lambda e: ui.navigate.to(f'/admin/questions/edit/{e.args}'))
                table.on('delete', lambda e: delete_question(e.args))
        else:
            ui.label('No questions yet. Click "New" to create one.').classes('text-gray-500 text-center py-8')


def delete_question(question_id):
    """Delete a question from the bank"""
    session = Session()
    question = session.query(QuestionBank).filter_by(id=question_id).first()
    if question:
        session.delete(question)
        session.commit()
        ui.notify(f'Question "{question.name}" deleted', type='positive')
    session.close()
    question_index_page.refresh()


@ui.page('/admin/questions/new')
def question_new_page(return_survey_id: int = None):
    """Page 2 from mockups: Create new question"""
    question_form(None, return_survey_id)


@ui.page('/admin/questions/edit/{question_id}')
def question_edit_page(question_id: int):
    """Page 2 from mockups: Edit existing question"""
    session = Session()
    question = session.query(QuestionBank).filter_by(id=question_id).first()
    session.close()
    question_form(question, None)


def question_form(question=None, return_survey_id=None):
    """Page 2 from mockups: Question New/Edit form"""
    is_edit = question is not None
    
    # State for dynamic form fields
    form_state = {
        'name': question.name if is_edit else '',
        'text': question.question_text if is_edit else '',
        'type': question.question_type if is_edit else 'likert',
        'config': question.config if is_edit else {}
    }
    
    with ui.column().classes('w-full max-w-2xl mx-auto p-8'):
        # Header
        ui.label('Edit Question' if is_edit else 'New Question').classes('text-3xl font-bold mb-6')
        
        with ui.card().classes('w-full p-6'):
            # Name field
            name_input = ui.input('Name', value=form_state['name']).classes('w-full')
            name_input.bind_value(form_state, 'name')
            
            # Question text
            text_input = ui.textarea('Question Text', value=form_state['text']).classes('w-full')
            text_input.bind_value(form_state, 'text')
            
            # Type selector
            def handle_type_change(e):
                # Clear config when type changes
                print(f"Type changed to: {e.value}")
                form_state['type'] = e.value
                form_state['config'] = {}
                print(f"Config cleared: {form_state['config']}")
                config_section.refresh()
            
            type_select = ui.select(
                ['likert', 'boolean', 'text', 'multi'],
                label='Type',
                value=form_state['type'],
                on_change=handle_type_change
            ).classes('w-full')
            
            # Dynamic config section (refreshable based on type)
            @ui.refreshable
            def config_section():
                current_type = form_state['type']
                
                if current_type == 'likert':
                    ui.label('Likert Scale Options').classes('text-lg font-semibold mt-4 mb-2')
                    # Initialize options if not exist
                    if 'scale' not in form_state['config']:
                        form_state['config'] = {
                            'scale': {
                                'labels': {
                                    '1': 'Strongly Disagree',
                                    '2': 'Disagree',
                                    '3': 'Neutral',
                                    '4': 'Agree',
                                    '5': 'Strongly Agree'
                                }
                            }
                        }
                    
                    labels = form_state['config']['scale']['labels']
                    for key in sorted(labels.keys(), key=int):
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label(f'{key}:').classes('w-8')
                            ui.input(value=labels[key]).classes('flex-grow').on(
                                'change',
                                lambda e, k=key: form_state['config']['scale']['labels'].update({k: e.value})
                            )
                    
                    ui.button('➕ Add Option', on_click=lambda: add_likert_option(form_state, config_section)).classes('mt-2')
                
                elif current_type == 'multi':
                    ui.label('Multi-Select Options').classes('text-lg font-semibold mt-4 mb-2')
                    # Initialize options if not exist
                    if 'options' not in form_state['config'] or not isinstance(form_state['config'].get('options'), list):
                        form_state['config'] = {
                            'options': ['Option 1', 'Option 2', 'Option 3']
                        }
                    
                    options = form_state['config']['options']
                    for i, option in enumerate(options):
                        with ui.row().classes('w-full items-center gap-2'):
                            ui.label(f'{i+1}:').classes('w-8')
                            ui.input(value=option).classes('flex-grow').on(
                                'change',
                                lambda e, idx=i: update_multi_option(form_state, idx, e.value)
                            )
                            if len(options) > 2:
                                ui.button(icon='delete', on_click=lambda idx=i: remove_multi_option(form_state, idx, config_section)).props('flat round dense color=red')
                    
                    ui.button('➕ Add Option', on_click=lambda: add_multi_option(form_state, config_section)).classes('mt-2')
                
                elif current_type == 'boolean':
                    ui.label('Boolean Options').classes('text-lg font-semibold mt-4 mb-2')
                    
                    # Initialize boolean config
                    if 'options' not in form_state['config'] or 'trueLabel' not in form_state['config'].get('options', {}):
                        form_state['config'] = {
                            'options': {
                                'trueLabel': 'Yes',
                                'falseLabel': 'No'
                            }
                        }
                    
                    preset = ui.select(
                        ['yes/no', 'true/false', 'custom'],
                        label='Preset',
                        value='yes/no'
                    ).classes('w-full')
                    
                    def update_boolean_preset(e):
                        if e.value == 'yes/no':
                            form_state['config']['options'] = {'trueLabel': 'Yes', 'falseLabel': 'No'}
                        elif e.value == 'true/false':
                            form_state['config']['options'] = {'trueLabel': 'True', 'falseLabel': 'False'}
                        config_section.refresh()
                    
                    preset.on('change', update_boolean_preset)
                    
                    ui.input('Positive Label', value=form_state['config']['options']['trueLabel']).classes('w-full').on(
                        'change', lambda e: form_state['config']['options'].update({'trueLabel': e.value})
                    )
                    ui.input('Negative Label', value=form_state['config']['options']['falseLabel']).classes('w-full').on(
                        'change', lambda e: form_state['config']['options'].update({'falseLabel': e.value})
                    )
                
                elif current_type == 'text':
                    ui.label('Open Ended Options').classes('text-lg font-semibold mt-4 mb-2')
                    
                    # Initialize text config
                    if 'text' not in form_state['config']:
                        form_state['config'] = {
                            'text': {
                                'placeholder': 'Enter your response...',
                                'charLimit': 1000
                            }
                        }
                    
                    ui.select(
                        [500, 1000, 1500, 2000],
                        label='Character Limit',
                        value=form_state['config']['text']['charLimit']
                    ).classes('w-full').on(
                        'change', lambda e: form_state['config']['text'].update({'charLimit': e.value})
                    )
                    
                    ui.input(
                        'Placeholder',
                        value=form_state['config']['text']['placeholder']
                    ).classes('w-full').on(
                        'change', lambda e: form_state['config']['text'].update({'placeholder': e.value})
                    )
            
            config_section()
            
            # Save button
            with ui.row().classes('w-full justify-end gap-2 mt-6'):
                cancel_url = f'/admin/surveys/edit/{return_survey_id}' if return_survey_id else '/admin/questions'
                ui.button('Cancel', on_click=lambda: ui.navigate.to(cancel_url)).classes('bg-gray-500 text-white')
                ui.button(
                    'Update' if is_edit else 'Create',
                    on_click=lambda: save_question(form_state, question.id if is_edit else None, return_survey_id)
                ).classes('bg-blue-600 text-white')


def add_likert_option(form_state, refresh_func):
    """Add a new option to likert scale"""
    labels = form_state['config']['scale']['labels']
    new_key = str(len(labels) + 1)
    labels[new_key] = f'Option {new_key}'
    refresh_func.refresh()


def update_multi_option(form_state, idx, value):
    """Update a multi-select option"""
    form_state['config']['options'][idx] = value


def add_multi_option(form_state, refresh_func):
    """Add a new multi-select option"""
    form_state['config']['options'].append(f'Option {len(form_state["config"]["options"]) + 1}')
    refresh_func.refresh()


def remove_multi_option(form_state, idx, refresh_func):
    """Remove a multi-select option"""
    if len(form_state['config']['options']) > 2:
        form_state['config']['options'].pop(idx)
        refresh_func.refresh()


def save_question(form_state, question_id=None, return_survey_id=None):
    """Save question to database"""
    # Validation
    if not form_state['name'].strip():
        ui.notify('Question name is required', type='negative')
        return
    
    if not form_state['text'].strip():
        ui.notify('Question text is required', type='negative')
        return
    
    session = Session()
    
    if question_id:
        # Update existing
        question = session.query(QuestionBank).filter_by(id=question_id).first()
        question.name = form_state['name']
        question.question_text = form_state['text']
        question.question_type = form_state['type']
        question.config = form_state['config']
        question.version += 1
        message = f'Question "{question.name}" updated'
    else:
        # Create new
        question = QuestionBank(
            name=form_state['name'],
            question_text=form_state['text'],
            question_type=form_state['type'],
            config=form_state['config'],
            created_by=get_current_user_id()  # Set owner
        )
        session.add(question)
        session.flush()  # Get the ID
        
        # If called from survey edit, add to that survey
        if return_survey_id:
            max_order = session.query(SurveyQuestion).filter_by(survey_id=return_survey_id).count()
            sq = SurveyQuestion(
                survey_id=return_survey_id,
                question_id=question.id,
                order=max_order + 1
            )
            session.add(sq)
        
        message = f'Question "{form_state["name"]}" created'
    
    session.commit()
    session.close()
    
    ui.notify(message, type='positive')
    
    if return_survey_id:
        ui.navigate.to(f'/admin/surveys/edit/{return_survey_id}')
    else:
        ui.navigate.to('/admin/questions')


# ═══════════════════════════════════════════════════════════════
# SURVEY CRUD
# ═══════════════════════════════════════════════════════════════

@ui.refreshable
def survey_list_page():
    """Page 4 from mockups: Survey Pages - List all surveys"""
    
    session = Session()
    current_user_id = get_current_user_id()
    # Show user's surveys + default surveys (created_by=NULL)
    surveys = session.query(Survey).filter(
        (Survey.created_by == current_user_id) | (Survey.created_by == None)
    ).order_by(desc(Survey.updated_at)).all()
    session.close()
    
    with ui.column().classes('w-full p-8'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('Survey Pages').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                ui.button('← Back', on_click=lambda: ui.navigate.to('/admin')).classes('bg-gray-500 text-white')
                ui.button('➕ Add', on_click=lambda: ui.navigate.to('/admin/surveys/new')).classes('bg-blue-600 text-white')
                ui.button('Import JSON', on_click=lambda: _open_import_survey_dialog()).classes('bg-slate-700 text-white')
        
        # Surveys table
        if surveys:
            with ui.card().classes('w-full'):
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                    {'name': 'public_id', 'label': 'Public link ID', 'field': 'public_id', 'align': 'left'},
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                    {'name': 'version', 'label': 'Version', 'field': 'version', 'align': 'center'},
                    {'name': 'updated', 'label': 'Last Updated', 'field': 'updated', 'align': 'left'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'},
                ]
                
                rows = []
                for s in surveys:
                    pid = (s.public_id or '') or '—'
                    rows.append({
                        'id': s.id,
                        'public_id': pid if len(pid) <= 28 else pid[:28] + '…',
                        'name': s.name,
                        'version': s.version,
                        'updated': s.updated_at.strftime('%Y-%m-%d %H:%M') if s.updated_at else '',
                        'actions': s.id
                    })
                
                table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full')
                table.add_slot('body-cell-actions', '''
                    <q-td :props="props">
                        <q-btn flat round dense icon="edit" size="sm" color="blue" 
                               @click="$parent.$emit('edit', props.row.id)" />
                        <q-btn flat round dense icon="content_copy" size="sm" color="purple"
                               @click="$parent.$emit('copy', props.row.id)" />
                        <q-btn flat round dense icon="download" size="sm" color="teal"
                               @click="$parent.$emit('export', props.row.id)" />
                        <q-btn flat round dense icon="delete" size="sm" color="red" 
                               @click="$parent.$emit('delete', props.row.id)" />
                    </q-td>
                ''')
                table.on('edit', lambda e: ui.navigate.to(f'/admin/surveys/edit/{e.args}'))
                table.on('copy', lambda e: copy_survey(e.args))
                table.on('export', lambda e: export_survey(e.args))
                table.on('delete', lambda e: delete_survey(e.args))
        else:
            ui.label('No surveys yet. Click "Add" to create one.').classes('text-gray-500 text-center py-8')


def _open_import_survey_dialog() -> None:
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-xl p-6'):
        ui.label('Import survey from JSON').classes('text-xl font-bold mb-2')
        ui.label(
            'Choose a JSON file. It will be imported as a brand new survey under your account.'
        ).classes('text-sm text-gray-600 mb-4')

        def on_upload(e) -> None:
            try:
                raw = e.content.read()
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                ui.notify('Could not read JSON file', type='negative')
                return
            try:
                new_id = import_survey_json_dict(data)
            except Exception:
                ui.notify('Import failed (invalid JSON shape)', type='negative')
                return
            dialog.close()
            ui.notify('Survey imported', type='positive')
            ui.navigate.to(f'/admin/surveys/edit/{new_id}')

        ui.upload(
            label='Select JSON file',
            auto_upload=True,
            on_upload=on_upload,
        ).props('accept=.json').classes('w-full')

        with ui.row().classes('justify-end w-full mt-4'):
            ui.button('Close', on_click=dialog.close).classes('bg-gray-200 text-gray-700')

    dialog.open()


def import_survey_json_dict(data: dict) -> int:
    """Import a survey JSON dict as a new survey; return new internal survey id."""
    title = (data.get('title') or data.get('name') or 'Imported Survey').strip()
    description = (data.get('description') or '').strip()
    settings = data.get('settings') or {}
    landing_html = (data.get('participant_landing_html') or '').strip() or None
    questions = data.get('questions') or []
    if not isinstance(questions, list) or not questions:
        raise ValueError('No questions')

    session = Session()
    try:
        pid = generate_survey_public_id()
        while session.query(Survey).filter(Survey.public_id == pid).first() is not None:
            pid = generate_survey_public_id()

        survey = Survey(
            name=title,
            description=description,
            settings=settings if isinstance(settings, dict) else {},
            participant_landing_html=_normalize_landing_html(landing_html),
            is_active=True,
            public_id=pid,
            created_by=get_current_user_id(),
        )
        session.add(survey)
        session.flush()  # get survey.id

        for idx, q in enumerate(questions, 1):
            if not isinstance(q, dict):
                continue
            qtype = str(q.get('type') or q.get('question_type') or 'text').strip()
            prompt = str(q.get('prompt') or q.get('question_text') or '').strip()
            qid = str(q.get('id') or q.get('name') or f'q_{idx}').strip()

            cfg: dict = {}
            if isinstance(q.get('tags'), list):
                cfg['tags'] = list(q.get('tags'))
            if qtype == 'likert':
                cfg['scale'] = q.get('scale') or {}
            elif qtype == 'boolean':
                cfg['options'] = q.get('options') or {}
            elif qtype == 'text':
                cfg['text'] = q.get('text') or {}
            elif qtype == 'multi':
                cfg['options'] = q.get('options') or []

            qb = QuestionBank(
                name=qid,
                question_text=prompt or qid,
                question_type=qtype,
                version=int(q.get('version') or 1),
                created_by=get_current_user_id(),
                config=cfg,
            )
            session.add(qb)
            session.flush()

            session.add(
                SurveyQuestion(
                    survey_id=survey.id,
                    question_id=qb.id,
                    order=idx,
                    is_adaptive=bool(q.get('adaptive') or q.get('is_adaptive') or False),
                )
            )

        session.commit()
        return survey.id
    finally:
        session.close()


def delete_survey(survey_id):
    """Delete a survey"""
    session = Session()
    survey = session.query(Survey).filter_by(id=survey_id).first()
    if survey:
        session.delete(survey)
        session.commit()
        ui.notify(f'Survey "{survey.name}" deleted', type='positive')
    session.close()
    survey_list_page.refresh()


def copy_survey(survey_id: int) -> None:
    """Copy a survey (metadata + question ordering) into a new survey owned by the current user."""
    session = Session()
    try:
        src = session.query(Survey).filter_by(id=int(survey_id)).first()
        if not src:
            ui.notify('Survey not found', type='negative')
            return

        pid = generate_survey_public_id()
        while session.query(Survey).filter(Survey.public_id == pid).first() is not None:
            pid = generate_survey_public_id()

        copied = Survey(
            name=f'{src.name} Copy',
            description=src.description,
            settings=dict(src.settings or {}),
            participant_landing_html=getattr(src, 'participant_landing_html', None),
            opens_at=getattr(src, 'opens_at', None),
            closes_at=getattr(src, 'closes_at', None),
            is_active=bool(src.is_active),
            public_id=pid,
            created_by=get_current_user_id(),
        )
        session.add(copied)
        session.flush()

        src_qs = (
            session.query(SurveyQuestion)
            .filter_by(survey_id=src.id)
            .order_by(SurveyQuestion.order)
            .all()
        )
        for sq in src_qs:
            session.add(
                SurveyQuestion(
                    survey_id=copied.id,
                    question_id=sq.question_id,
                    order=sq.order,
                    is_adaptive=bool(sq.is_adaptive),
                )
            )

        session.commit()
        ui.notify('Survey copied', type='positive')
        ui.navigate.to(f'/admin/surveys/edit/{copied.id}')
    finally:
        session.close()


def export_survey(survey_id: int) -> None:
    """Export a survey (runtime JSON shape) for download."""
    session = Session()
    try:
        payload = load_survey_from_db(session, int(survey_id))
        if not payload:
            ui.notify('Survey not available for export', type='negative')
            return
        name = (payload.get('title') or f'survey_{survey_id}').strip().replace(' ', '_')
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        ui.download(body.encode('utf-8'), f'{name}.json')
    finally:
        session.close()


@ui.page('/admin/surveys/new')
def survey_new_page():
    """Create new survey"""
    survey_edit_form(None)


@ui.page('/admin/surveys/edit/{survey_id}')
def survey_edit_page_route(survey_id: int):
    """Page 5 from mockups: Survey Edit Page"""
    session = Session()
    survey = session.query(Survey).filter_by(id=survey_id).first()
    session.close()
    survey_edit_form(survey)


def survey_edit_form(survey=None):
    """Page 5 from mockups: Survey Edit Page with questions list"""
    is_edit = survey is not None
    survey_id = survey.id if is_edit else None
    
    with ui.column().classes('w-full max-w-4xl mx-auto p-8'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('Edit Survey' if is_edit else 'New Survey').classes('text-3xl font-bold')
            ui.button('← Back to Surveys', on_click=lambda: ui.navigate.to('/admin/surveys')).classes('bg-gray-500 text-white')
        
        # Survey metadata
        with ui.card().classes('w-full p-6 mb-4'):
            name_input = ui.input('Survey Name', value=survey.name if is_edit else '').classes('w-full')
            desc_input = ui.textarea('Description', value=survey.description if is_edit else '').classes('w-full')

            ui.label('Participant landing page (before questions)').classes('text-lg font-semibold mt-6 mb-1')
            ui.label(
                'Rich text: instructions, study summary, informed consent wording, and links. '
                'Participants must click Continue before the survey opens.'
            ).classes('text-sm text-gray-500 mb-2')
            _landing_default = (
                '<p><strong>Instructions:</strong> Replace this text with what participants should read before starting. '
                'You can use <em>formatting</em>, lists, and links (e.g. to a full consent PDF).</p>'
            )
            _existing_landing = (survey.participant_landing_html or '').strip() if is_edit else ''
            landing_editor = ui.editor(
                value=_existing_landing if _existing_landing else _landing_default,
            ).classes('w-full border border-gray-200 rounded').style('min-height: 280px')

            ui.label('Survey window (optional, UTC)').classes('text-lg font-semibold mt-6 mb-1')
            ui.label(
                'Leave blank for no limit. Times are interpreted as UTC and shown to participants in UTC.'
            ).classes('text-sm text-gray-500 mb-2')
            _opens = _fmt_datetime_local(survey.opens_at) if is_edit and getattr(survey, 'opens_at', None) else ''
            _closes = _fmt_datetime_local(survey.closes_at) if is_edit and getattr(survey, 'closes_at', None) else ''
            opens_input = ui.input('Opens at (UTC)', value=_opens).props('type=datetime-local').classes(
                'w-full max-w-md'
            )
            closes_input = ui.input('Closes at (UTC)', value=_closes).props('type=datetime-local').classes(
                'w-full max-w-md'
            )

            # Randomization settings
            ui.label('Randomization Settings').classes('text-lg font-semibold mt-4 mb-2')
            
            randomize_enabled = ui.checkbox('Randomize IMI-tagged questions', 
                value=bool(survey.settings.get('randomize')) if is_edit and survey.settings else False
            )
            
            ui.label('Questions with "IMI" tag will be shuffled randomly').classes('text-sm text-gray-500')
            
            if not is_edit:
                # Save survey first before adding questions
                ui.button('Create Survey', on_click=lambda: create_survey_initial(
                    name_input.value,
                    desc_input.value,
                    randomize_enabled.value,
                    landing_editor.value,
                    opens_input.value,
                    closes_input.value,
                )).classes('bg-blue-600 text-white mt-4')
            else:
                ui.button('Update Details', on_click=lambda: update_survey_details(
                    survey_id,
                    name_input.value,
                    desc_input.value,
                    randomize_enabled.value,
                    landing_editor.value,
                    opens_input.value,
                    closes_input.value,
                )).classes('bg-blue-600 text-white mt-4')
        
        # Questions section (only show if editing existing survey)
        if is_edit:
            with ui.card().classes('w-full p-6'):
                ui.label('Questions').classes('text-2xl font-bold mb-4')
                
                with ui.row().classes('gap-2 mb-4'):
                    ui.button('➕ New Question', on_click=lambda: ui.navigate.to(f'/admin/questions/new?return_survey_id={survey_id}')).classes(
                        'bg-green-600 text-white'
                    )
                    ui.button('➕ Select Question', on_click=lambda: show_question_selector(survey_id)).classes(
                        'bg-blue-600 text-white'
                    )
                
                # Questions list
                questions_list_display(survey_id)


@ui.refreshable
def questions_list_display(survey_id):
    """Display list of questions in a survey"""
    session = Session()
    survey_questions = session.query(SurveyQuestion).filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
    
    # Eagerly load the question data before closing session
    questions_data = []
    for sq in survey_questions:
        questions_data.append({
            'id': sq.id,
            'order': sq.order,
            'name': sq.question.name,
            'text': sq.question.question_text
        })
    
    session.close()
    
    if questions_data:
        for q_data in questions_data:
            with ui.card().classes('w-full p-4 mb-2'):
                with ui.row().classes('w-full justify-between items-center'):
                    with ui.column():
                        ui.label(f'{q_data["order"]}. {q_data["name"]}').classes('font-semibold')
                        ui.label(q_data["text"][:80] + '...' if len(q_data["text"]) > 80 else q_data["text"]).classes('text-sm text-gray-600')
                    with ui.row().classes('gap-2'):
                        # Capture sq.id in default argument to avoid closure issue
                        ui.button(icon='arrow_upward', on_click=lambda sq_id=q_data['id']: move_question_up(sq_id)).props('flat round dense')
                        ui.button(icon='arrow_downward', on_click=lambda sq_id=q_data['id']: move_question_down(sq_id)).props('flat round dense')
                        ui.button(icon='delete', on_click=lambda sq_id=q_data['id']: remove_question_from_survey(sq_id)).props('flat round dense color=red')
    else:
        ui.label('No questions added yet.').classes('text-gray-500')


def _normalize_landing_html(html: str | None) -> str | None:
    if html is None:
        return None
    if not str(html).strip():
        return None
    return str(html)


def create_survey_initial(
    name,
    description,
    randomize,
    participant_landing_html=None,
    opens_at_raw=None,
    closes_at_raw=None,
):
    """Create initial survey"""
    if not name.strip():
        ui.notify('Survey name is required', type='negative')
        return

    o = _parse_datetime_local(opens_at_raw)
    c = _parse_datetime_local(closes_at_raw)
    if (opens_at_raw and str(opens_at_raw).strip() and o is None) or (
        closes_at_raw and str(closes_at_raw).strip() and c is None
    ):
        ui.notify('Invalid open/close datetime (use the picker format, UTC).', type='negative')
        return
    if o and c and c <= o:
        ui.notify('Close time must be after open time.', type='negative')
        return

    settings = {}
    if randomize:
        settings['randomize'] = True

    session = Session()
    pid = generate_survey_public_id()
    while session.query(Survey).filter(Survey.public_id == pid).first() is not None:
        pid = generate_survey_public_id()
    survey = Survey(
        name=name,
        description=description,
        settings=settings,
        participant_landing_html=_normalize_landing_html(participant_landing_html),
        opens_at=o,
        closes_at=c,
        public_id=pid,
        created_by=get_current_user_id(),  # Set owner
    )
    session.add(survey)
    session.commit()
    survey_id = survey.id
    session.close()
    
    ui.notify(f'Survey "{name}" created!', type='positive')
    ui.navigate.to(f'/admin/surveys/edit/{survey_id}')


def update_survey_details(
    survey_id,
    name,
    description,
    randomize,
    participant_landing_html=None,
    opens_at_raw=None,
    closes_at_raw=None,
):
    """Update survey metadata"""
    o = _parse_datetime_local(opens_at_raw)
    c = _parse_datetime_local(closes_at_raw)
    if (opens_at_raw and str(opens_at_raw).strip() and o is None) or (
        closes_at_raw and str(closes_at_raw).strip() and c is None
    ):
        ui.notify('Invalid open/close datetime (use the picker format, UTC).', type='negative')
        return
    if o and c and c <= o:
        ui.notify('Close time must be after open time.', type='negative')
        return

    session = Session()
    survey = session.query(Survey).filter_by(id=survey_id).first()
    survey.name = name
    survey.description = description
    survey.participant_landing_html = _normalize_landing_html(participant_landing_html)
    survey.opens_at = o
    survey.closes_at = c

    settings = survey.settings or {}
    if randomize:
        settings['randomize'] = True
    else:
        settings.pop('randomize', None)  # Remove if disabled

    survey.settings = settings
    session.commit()
    session.close()
    ui.notify('Survey updated', type='positive')


def show_question_selector(survey_id):
    """Show dialog to select existing question from bank"""
    session = Session()
    current_user_id = get_current_user_id()
    # Show user's questions + default questions (created_by=NULL)
    questions = session.query(QuestionBank).filter(
        (QuestionBank.created_by == current_user_id) | (QuestionBank.created_by == None)
    ).all()
    session.close()
    
    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Select Question').classes('text-xl font-bold mb-4')
        
        if questions:
            for q in questions:
                with ui.card().classes('w-full p-3 mb-2'):
                    ui.label(q.name).classes('font-semibold')
                    ui.label(q.question_text[:60] + '...').classes('text-sm text-gray-600')
                    # Capture q.id in default argument
                    ui.button('Add', on_click=lambda qid=q.id: (add_question_to_survey(survey_id, qid), dialog.close())).classes('mt-2')
        else:
            ui.label('No questions in bank. Create questions first.').classes('text-gray-500')
    
    dialog.open()


def add_question_to_survey(survey_id, question_id):
    """Add existing question to survey"""
    session = Session()
    
    # Check if question already in survey
    existing = session.query(SurveyQuestion).filter_by(
        survey_id=survey_id,
        question_id=question_id
    ).first()
    
    if existing:
        session.close()
        ui.notify('Question already in survey', type='warning')
        return
    
    # Get current max order
    max_order = session.query(SurveyQuestion).filter_by(survey_id=survey_id).count()
    
    sq = SurveyQuestion(
        survey_id=survey_id,
        question_id=question_id,
        order=max_order + 1
    )
    session.add(sq)
    session.commit()
    session.close()
    
    ui.notify('Question added to survey', type='positive')
    questions_list_display.refresh()


def move_question_up(sq_id):
    """Move question up in order"""
    session = Session()
    sq = session.query(SurveyQuestion).filter_by(id=sq_id).first()
    if sq.order > 1:
        # Swap with previous
        prev_sq = session.query(SurveyQuestion).filter_by(
            survey_id=sq.survey_id,
            order=sq.order - 1
        ).first()
        if prev_sq:
            sq.order, prev_sq.order = prev_sq.order, sq.order
            session.commit()
    session.close()
    questions_list_display.refresh()


def move_question_down(sq_id):
    """Move question down in order"""
    session = Session()
    sq = session.query(SurveyQuestion).filter_by(id=sq_id).first()
    max_order = session.query(SurveyQuestion).filter_by(survey_id=sq.survey_id).count()
    if sq.order < max_order:
        # Swap with next
        next_sq = session.query(SurveyQuestion).filter_by(
            survey_id=sq.survey_id,
            order=sq.order + 1
        ).first()
        if next_sq:
            sq.order, next_sq.order = next_sq.order, sq.order
            session.commit()
    session.close()
    questions_list_display.refresh()


def remove_question_from_survey(sq_id):
    """Remove question from survey"""
    session = Session()
    sq = session.query(SurveyQuestion).filter_by(id=sq_id).first()
    if sq:
        survey_id = sq.survey_id
        deleted_order = sq.order
        
        session.delete(sq)
        session.flush()  # Delete first
        
        # Reorder remaining questions that came after the deleted one
        remaining = session.query(SurveyQuestion).filter(
            SurveyQuestion.survey_id == survey_id,
            SurveyQuestion.order > deleted_order
        ).all()
        
        for rsq in remaining:
            rsq.order -= 1
        
        session.commit()
    session.close()
    ui.notify('Question removed', type='positive')
    questions_list_display.refresh()


# ═══════════════════════════════════════════════════════════════
# ADMIN HOMEPAGE
# ═══════════════════════════════════════════════════════════════

@ui.page('/admin')
def admin_home():
    """Admin dashboard home"""
    if is_ir() and not is_admin():
        ui.navigate.to('/admin/ir/links')
        return
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return

    with ui.column().classes('w-full max-w-4xl mx-auto p-8'):
        with ui.row().classes('w-full justify-between items-center mb-8'):
            with ui.column():
                ui.label('Survey Admin Panel').classes('text-4xl font-bold')
                ui.label(f'Logged in as: {get_current_user()}').classes('text-sm text-gray-600')
            with ui.row().classes('gap-2'):
                ui.button('← Project home', on_click=lambda: ui.navigate.to('/')).classes('bg-gray-500 text-white')
                ui.button('Logout', on_click=lambda: ui.navigate.to('/logout')).classes('bg-red-600 text-white')

        with ui.row().classes('gap-4 flex-wrap'):
            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/surveys')):
                ui.label('📋 Surveys').classes('text-2xl font-bold')
                ui.label('Manage survey pages').classes('text-gray-600')

            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/questions')):
                ui.label('❓ Questions').classes('text-2xl font-bold')
                ui.label('Manage question bank').classes('text-gray-600')

            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/analytics')):
                ui.label('📊 Analytics').classes('text-2xl font-bold')
                ui.label('View response insights').classes('text-gray-600')

            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/ir/links')):
                ui.label('🔗 IR links').classes('text-2xl font-bold')
                ui.label('Personalized student URLs (CSV)').classes('text-gray-600')

            if is_project_admin():
                with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on(
                    'click', lambda: ui.navigate.to('/admin/users')
                ):
                    ui.label('👤 Users').classes('text-2xl font-bold')
                    ui.label('Roles and accounts').classes('text-gray-600')


@ui.page('/admin/questions')
def admin_questions():
    """Questions index page"""
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    question_index_page()


@ui.page('/admin/surveys')
def admin_surveys():
    """Surveys list page"""
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    survey_list_page()


@ui.page('/admin/analytics')
def admin_analytics():
    """Analytics dashboard"""
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    analytics_page()


def analytics_page():
    """Analytics dashboard - high level summary and insights"""
    
    current_user_id = get_current_user_id()
    session = Session()
    
    # Get user's surveys + default surveys (created_by=NULL)
    surveys = session.query(Survey).filter(
        (Survey.created_by == current_user_id) | (Survey.created_by == None)
    ).all()
    
    # Get total response count
    from responses import Response
    total_responses = session.query(Response).filter(
        Response.survey_id.in_([s.id for s in surveys]) if surveys else [0]
    ).count()
    
    session.close()
    
    with ui.column().classes('w-full max-w-6xl mx-auto p-8'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('Analytics Dashboard').classes('text-3xl font-bold')
            ui.button('← Back', on_click=lambda: ui.navigate.to('/admin')).classes('bg-gray-500 text-white')
        
        # High-level stats
        with ui.row().classes('gap-4 mb-8'):
            with ui.card().classes('p-6'):
                ui.label(f'{len(surveys)}').classes('text-4xl font-bold text-blue-600')
                ui.label('Total Surveys').classes('text-gray-600')
            
            with ui.card().classes('p-6'):
                ui.label(f'{total_responses}').classes('text-4xl font-bold text-green-600')
                ui.label('Total Responses').classes('text-gray-600')
        
        # Survey list with response counts
        ui.label('Survey Breakdown').classes('text-2xl font-bold mb-4')
        
        if surveys:
            session = Session()
            for survey in surveys:
                response_count = session.query(Response).filter_by(survey_id=survey.id).count()
                
                # Save survey data before closing
                survey_id = survey.id
                survey_name = survey.name
                survey_desc = survey.description
                
                with ui.card().classes('w-full p-4 mb-2 cursor-pointer hover:shadow-lg').on('click', lambda sid=survey_id: ui.navigate.to(f'/admin/analytics/survey/{sid}')):
                    with ui.row().classes('w-full justify-between items-center'):
                        with ui.column():
                            ui.label(survey_name).classes('font-semibold text-lg')
                            ui.label(survey_desc or 'No description').classes('text-sm text-gray-600')
                        ui.label(f'{response_count} responses').classes('text-blue-600 font-bold')
            session.close()
        else:
            ui.label('No surveys created yet.').classes('text-gray-500 text-center py-8')


@ui.page('/admin/analytics/survey/{survey_id}')
def survey_detail_route(survey_id: int):
    """Survey detail analytics page"""
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    survey_detail_page(survey_id)


def survey_detail_page(survey_id: int):
    """Detailed analytics for a specific survey"""
    
    session = Session()
    
    # Get survey
    survey = session.query(Survey).filter_by(id=survey_id).first()
    if not survey:
        session.close()
        ui.label('Survey not found').classes('text-red-600')
        return
    
    # Get questions in order (eager-load to avoid DetachedInstanceError after session close)
    from sqlalchemy.orm import joinedload

    survey_questions = (
        session.query(SurveyQuestion)
        .options(joinedload(SurveyQuestion.question))
        .filter_by(survey_id=survey_id)
        .order_by(SurveyQuestion.order)
        .all()
    )
    
    # Get all responses for this survey
    from responses import Response
    responses = session.query(Response).filter_by(survey_id=survey_id).all()
    
    # Extract response data
    response_data = [r.response for r in responses]
    total_responses = len(responses)
    
    # Save data before closing
    survey_name = survey.name
    survey_desc = survey.description
    
    session.close()
    
    with ui.column().classes('w-full max-w-6xl mx-auto p-8'):
        # Header
        with ui.row().classes('w-full justify-between items-center mb-6'):
            with ui.column():
                ui.label(survey_name).classes('text-3xl font-bold')
                if survey_desc:
                    ui.label(survey_desc).classes('text-gray-600')
            ui.button('← Back', on_click=lambda: ui.navigate.to('/admin/analytics')).classes('bg-gray-500 text-white')
        
        # Stats
        with ui.card().classes('p-4 mb-6'):
            ui.label(f'{total_responses} Total Responses').classes('text-2xl font-bold text-blue-600')
        
        # Questions and visualizations
        if total_responses == 0:
            ui.label('No responses yet for this survey.').classes('text-gray-500 text-center py-8')
        else:
            for sq in survey_questions:
                question = sq.question
                question_name = question.name
                question_text = question.question_text
                question_type = question.question_type
                
                with ui.card().classes('w-full p-6 mb-4'):
                    ui.label(f'Q{sq.order}: {question_text}').classes('text-xl font-semibold mb-4')
                    
                    if question_type == 'likert':
                        # Extract answers for this question
                        answers = []
                        for r_data in response_data:
                            answer = r_data.get(question_name)
                            if answer is not None:
                                answers.append(int(answer))
                        
                        if answers:
                            # Count distribution
                            scale_labels = question.config.get('scale', {}).get('labels', {})
                            max_scale = max([int(k) for k in scale_labels.keys()])
                            
                            counts = {i: 0 for i in range(1, max_scale + 1)}
                            for ans in answers:
                                if 1 <= ans <= max_scale:
                                    counts[ans] = counts.get(ans, 0) + 1
                            
                            # Calculate average
                            avg = sum(answers) / len(answers)
                            
                            # Bar chart
                            chart_data = {
                                'xAxis': {'type': 'category', 'data': [scale_labels.get(str(i), str(i)) for i in range(1, max_scale + 1)]},
                                'yAxis': {'type': 'value'},
                                'series': [{'data': [counts[i] for i in range(1, max_scale + 1)], 'type': 'bar', 'itemStyle': {'color': '#3b82f6'}}],
                                'tooltip': {'trigger': 'axis'}
                            }
                            
                            ui.echart(chart_data).classes('w-full h-64')
                            
                            # Stats
                            with ui.row().classes('gap-6 mt-4'):
                                ui.label(f'Average: {avg:.2f}/{max_scale}').classes('text-lg font-semibold text-blue-600')
                                ui.label(f'Responses: {len(answers)}').classes('text-lg text-gray-600')
                        else:
                            ui.label('No responses for this question').classes('text-gray-500')
                    
                    elif question_type == 'boolean':
                        # Extract yes/no answers
                        answers = []
                        for r_data in response_data:
                            answer = r_data.get(question_name)
                            if answer is not None:
                                answers.append(answer)
                        
                        if answers:
                            true_count = sum(1 for a in answers if a == True or a == 'true' or a == 'Yes')
                            false_count = len(answers) - true_count
                            
                            true_label = question.config.get('options', {}).get('trueLabel', 'Yes')
                            false_label = question.config.get('options', {}).get('falseLabel', 'No')
                            
                            # Pie chart
                            chart_data = {
                                'series': [{
                                    'type': 'pie',
                                    'data': [
                                        {'value': true_count, 'name': true_label},
                                        {'value': false_count, 'name': false_label}
                                    ]
                                }],
                                'tooltip': {'trigger': 'item'}
                            }
                            
                            ui.echart(chart_data).classes('w-full h-64')
                            ui.label(f'Responses: {len(answers)}').classes('text-lg text-gray-600 mt-4')
                        else:
                            ui.label('No responses for this question').classes('text-gray-500')
                    
                    elif question_type == 'text':
                        # Skip text for now - will handle with GPT later
                        ui.label('Text responses (visualization coming soon)').classes('text-gray-500 italic')
                    
                    elif question_type == 'multi':
                        # Skip multi for now
                        ui.label('Multi-select responses (visualization coming soon)').classes('text-gray-500 italic')
            # no DB session needed here; survey_questions were eager-loaded above


@ui.refreshable
def users_list_page_refreshable():
    if not is_project_admin():
        return

    session = Session()
    qtext = _USER_LIST_SEARCH.get('q', '').strip()
    base = session.query(User)
    base = _user_search_filter(base, qtext)
    total = base.count()
    per = _USER_LIST_PAGER['per_page']
    page = _USER_LIST_PAGER['page']
    max_page = max(1, (total + per - 1) // per) if total else 1
    if page > max_page:
        _USER_LIST_PAGER['page'] = max_page
        page = max_page

    rows_data = (
        base.order_by(User.id.asc())
        .offset((page - 1) * per)
        .limit(per)
        .all()
    )
    session.close()

    rows = []
    for u in rows_data:
        rows.append(
            {
                'id': u.id,
                'email': u.email,
                'role': u.role,
                'is_active': bool(u.is_active),
                'last_login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '—',
                'actions': u.id,
            }
        )

    with ui.column().classes('w-full max-w-5xl mx-auto p-8'):
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('User accounts').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                ui.button('← Admin home', on_click=lambda: ui.navigate.to('/admin')).classes('bg-gray-500 text-white')
                ui.button('Logout', on_click=lambda: ui.navigate.to('/logout')).classes('bg-red-600 text-white')

        with ui.row().classes('w-full gap-2 items-end mb-4 flex-wrap'):
            search_input = ui.input(
                'Search email',
                value=_USER_LIST_SEARCH['q'],
                placeholder='Substring match (case-insensitive)',
            ).classes('flex-grow min-w-[14rem] max-w-xl')

            def apply_search():
                _USER_LIST_SEARCH['q'] = (search_input.value or '').strip()
                _USER_LIST_PAGER['page'] = 1
                users_list_page_refreshable.refresh()

            def clear_search():
                _USER_LIST_SEARCH['q'] = ''
                _USER_LIST_PAGER['page'] = 1
                users_list_page_refreshable.refresh()

            ui.button('Search', on_click=apply_search).classes('bg-blue-600 text-white')
            ui.button('Clear', on_click=clear_search).classes('bg-gray-400 text-white')

        search_input.on('keydown.enter', lambda: apply_search())

        match_note = f' matching “{qtext}”' if qtext else ''
        ui.label(f'{total} user(s){match_note}').classes('text-sm text-gray-600 mb-4')

        def set_page(p: int):
            _USER_LIST_PAGER['page'] = max(1, min(max_page, p))
            users_list_page_refreshable.refresh()

        def set_per(e):
            _USER_LIST_PAGER['per_page'] = int(e.value)
            _USER_LIST_PAGER['page'] = 1
            users_list_page_refreshable.refresh()

        def handle_toggle_active(evt):
            args = evt.args
            if not isinstance(args, (list, tuple)) or len(args) < 2:
                return
            uid, new_val = int(args[0]), bool(args[1])
            if uid == get_current_user_id() and not new_val:
                ui.notify('You cannot deactivate your own account.', type='warning')
                users_list_page_refreshable.refresh()
                return
            sess = Session()
            u = sess.query(User).filter_by(id=uid).first()
            if u:
                u.is_active = new_val
                sess.commit()
            sess.close()
            ui.notify('Active status updated', type='positive')
            users_list_page_refreshable.refresh()

        with ui.row().classes('gap-4 items-center mb-4 flex-wrap'):
            ui.select([10, 25, 50, 100], value=per, label='Rows per page', on_change=set_per).classes('w-40')
            ui.label(f'Page {page} / {max_page}').classes('text-sm text-gray-600')
            ui.button('Previous', on_click=lambda: set_page(page - 1)).classes(
                'bg-gray-200' if page > 1 else 'opacity-40'
            )
            ui.button('Next', on_click=lambda: set_page(page + 1)).classes(
                'bg-gray-200' if page < max_page else 'opacity-40'
            )

        if not rows:
            ui.label('No users match this search.' if qtext else 'No users yet.').classes('text-gray-500')
            return

        columns = [
            {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
            {'name': 'email', 'label': 'Email', 'field': 'email', 'align': 'left'},
            {'name': 'role', 'label': 'Role', 'field': 'role', 'align': 'left'},
            {'name': 'is_active', 'label': 'Active', 'field': 'is_active', 'align': 'center'},
            {'name': 'last_login', 'label': 'Last login (UTC)', 'field': 'last_login', 'align': 'left'},
            {'name': 'actions', 'label': '', 'field': 'actions', 'align': 'center'},
        ]
        table = ui.table(columns=columns, rows=rows, row_key='id').classes('w-full')
        table.add_slot(
            'body-cell-is_active',
            '''
            <q-td :props="props">
                <q-toggle
                    dense
                    :model-value="props.row.is_active"
                    @update:model-value="val => $parent.$emit('toggle_active', props.row.id, val)"
                />
            </q-td>
        ''',
        )
        table.on('toggle_active', handle_toggle_active)
        table.add_slot(
            'body-cell-actions',
            '''
            <q-td :props="props">
                <q-btn flat dense color="primary" label="View" @click="$parent.$emit('open', props.row.id)" />
            </q-td>
        ''',
        )
        table.on('open', lambda e: ui.navigate.to(f'/admin/users/{e.args}'))


@ui.page('/admin/users')
def admin_users_list_page():
    if not is_project_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    users_list_page_refreshable()


@ui.page('/admin/users/{user_id}')
def admin_user_detail_page(user_id: int):
    if not is_project_admin():
        ui.navigate.to('/login?error=admin_only')
        return

    session = Session()
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        session.close()
        with ui.column().classes('p-8'):
            ui.label('User not found').classes('text-red-600')
            ui.button('Back', on_click=lambda: ui.navigate.to('/admin/users')).classes('mt-4')
        return

    uid = user.id
    email = user.email
    current_role = user.role
    current_active = bool(user.is_active)
    session.close()

    roles = ['admin', 'instructor', 'ir', 'student']

    with ui.column().classes('w-full max-w-lg mx-auto p-8 gap-4'):
        ui.label('Edit user').classes('text-3xl font-bold')
        ui.label(email).classes('text-lg text-gray-700 break-all')
        role_select = ui.select(roles, value=current_role, label='Role').classes('w-full')
        active_switch = ui.switch('Account active', value=current_active).classes('mt-2')

        def save():
            new_role = role_select.value
            new_active = bool(active_switch.value)
            if uid == get_current_user_id() and new_role != 'admin':
                ui.notify('You cannot remove your own admin role from this screen.', type='warning')
                return
            if uid == get_current_user_id() and not new_active:
                ui.notify('You cannot deactivate your own account.', type='warning')
                return
            sess = Session()
            u = sess.query(User).filter_by(id=uid).first()
            if not u:
                sess.close()
                return
            u.role = new_role
            u.is_active = new_active
            sess.commit()
            sess.close()
            if uid == get_current_user_id():
                app.storage.user['role'] = new_role
            ui.notify('User updated', type='positive')
            ui.navigate.to('/admin/users')

        ui.button('Save', on_click=save).classes('bg-blue-600 text-white')
        ui.button('← Back to list', on_click=lambda: ui.navigate.to('/admin/users')).classes('bg-gray-500 text-white')


def ir_survey_links_page(request: Request):
    """Generate personalized survey URLs (status, id, url) for the IR office."""
    base = get_public_base_url(request)
    session = Session()
    surveys = [
        s
        for s in session.query(Survey).filter_by(is_active=True).order_by(Survey.id).all()
        if s.public_id
    ]
    session.close()

    with ui.column().classes('w-full max-w-4xl mx-auto p-8 gap-4'):
        with ui.row().classes('w-full justify-between items-center flex-wrap gap-2'):
            ui.label('IR: personalized survey links').classes('text-3xl font-bold')
            with ui.row().classes('gap-2'):
                if is_admin():
                    ui.button('Admin panel', on_click=lambda: ui.navigate.to('/admin')).classes(
                        'bg-blue-700 text-white'
                    )
                ui.button('Project home', on_click=lambda: ui.navigate.to('/')).classes('bg-gray-500 text-white')
                ui.button('Logout', on_click=lambda: ui.navigate.to('/logout')).classes('bg-red-600 text-white')

        ui.label(f'Logged in as: {get_current_user()}').classes('text-sm text-gray-600')

        if base and not os.getenv('PUBLIC_BASE_URL', '').strip() and not os.getenv(
            'RAILWAY_PUBLIC_DOMAIN', ''
        ).strip() and not os.getenv('RAILWAY_ENVIRONMENT', '').strip():
            ui.label(
                f'Local dev: using your current site URL as the link base ({base}). '
                'Set PUBLIC_BASE_URL (and/or RAILWAY_PUBLIC_DOMAIN) on Railway for production links.'
            ).classes('text-xs text-slate-500')

        if not base:
            ui.label(
                'Set PUBLIC_BASE_URL (https://…) or RAILWAY_PUBLIC_DOMAIN. '
                'If you are debugging locally, unset RAILWAY_ENVIRONMENT in .env so the app can infer http://localhost:… from your browser.'
            ).classes('text-amber-800 bg-amber-50 border border-amber-200 p-4 rounded')

        ui.label(
            'Each row in the spreadsheet lists whether the participant token is new or reused, the token, '
            'and the full URL. Send only the URL column to students as instructed by your protocol.'
        ).classes('text-gray-600 text-sm')

        if not surveys:
            ui.label(
                'No active surveys with a public link ID (restart the app once to run DB migration/backfill, '
                'or create a new survey).'
            ).classes('text-orange-600')
            return

        labels = [f'{s.id}: {s.name}' for s in surveys]
        survey_select = ui.select(
            labels,
            value=labels[0],
            label='Survey',
        ).classes('w-full max-w-xl')

        id_to_label = {f'{s.id}: {s.name}': s.public_id for s in surveys}

        ids_input = ui.textarea(
            label='Existing IDs to reuse (optional)',
            placeholder='One per line, or comma-separated',
        ).classes('w-full').props('rows=5')

        n_input = ui.number('Number of new IDs to create', value=0, min=0, precision=0).classes('w-full max-w-xs')

        def generate_csv():
            if not base:
                ui.notify('Set PUBLIC_BASE_URL or RAILWAY_PUBLIC_DOMAIN first', type='warning')
                return
            label = survey_select.value
            survey_public_id = id_to_label[label]
            raw = ids_input.value or ''
            tokens = []
            for chunk in raw.replace(',', '\n').split('\n'):
                t = chunk.strip()
                if t:
                    tokens.append(t)
            seen: set[str] = set()
            ordered: list[str] = []
            for t in tokens:
                if t not in seen:
                    seen.add(t)
                    ordered.append(t)
            n_new = int(n_input.value or 0)
            if not ordered and n_new <= 0:
                ui.notify('Add at least one existing ID or set N > 0', type='warning')
                return
            rows_out: list[list[str]] = [['status', 'id', 'url']]
            for t in ordered:
                q = quote(t, safe='')
                rows_out.append(['existing', t, f'{base}/survey/{survey_public_id}?sid={q}'])
            for _ in range(n_new):
                nid = secrets.token_urlsafe(18)
                while nid in seen:
                    nid = secrets.token_urlsafe(18)
                seen.add(nid)
                qn = quote(nid, safe='')
                rows_out.append(['new', nid, f'{base}/survey/{survey_public_id}?sid={qn}'])
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerows(rows_out)
            safe_stub = survey_public_id.replace('/', '_').replace('+', '-')[:48]
            ui.download(buf.getvalue().encode('utf-8'), f'sai_survey_{safe_stub}_links.csv')

        ui.button('Download spreadsheet (CSV)', on_click=generate_csv).classes('bg-blue-600 text-white w-fit')


@ui.page('/admin/ir/links')
def admin_ir_links_page(request: Request):
    if not can_access_ir_tools():
        ui.navigate.to('/login?error=admin_only')
        return
    ir_survey_links_page(request)


# Run the admin panel
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Survey Admin Panel', port=8080)