import asyncio
import json
import os
import random
from nicegui import ui
from datetime import datetime
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from Question_Timer import Question_Timer
from chatbot import analyze_all_responses_for_survey
from dotenv import load_dotenv
from Base import Base
from fastapi import Request
from responses import Response
from time_per_question import Time_Per_Question
from survey_models import Survey, QuestionBank, SurveyQuestion
from authentication import login_page, register_page, logout_page
from admin_panel import (
    admin_home, admin_questions, admin_surveys, admin_analytics,
    question_new_page, question_edit_page,
    survey_new_page, survey_edit_page_route
)
import uuid


load_dotenv()
with open('student_sai_sentiment.json') as f:
    survey = json.load(f)

# Apply randomization if specified in settings
if survey['settings'].get('randomize'):
    # Find all questions with "IMI" tag
    imi_questions = []
    imi_indices = []
    
    for idx, q in enumerate(survey['questions']):
        if 'IMI' in q.get('tags', []):
            imi_questions.append(q)
            imi_indices.append(idx)
    
    # Shuffle only the IMI questions
    random.shuffle(imi_questions)
    
    # Put shuffled IMI questions back in their original positions
    for new_q, idx in zip(imi_questions, imi_indices):
        survey['questions'][idx] = new_q

    
current_index = {'value': 0}
answers = {}
dynamic_questions: list[dict] = []
timer = Question_Timer()

# Database setup
database_url = os.getenv('DATABASE_URL')
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

# ─── Survey State Management ─────────────────────────────────────
survey_state = {
    'mode': 'static',
    'static_count': len(survey['questions']),
}


def get_all_questions():
    return survey['questions'] + dynamic_questions


def save_answer(question, value):
    answers[question['id']] = {
        'questionId':   question['id'],
        'questionType': question['type'],
        'value':        value
    }


def handle_text_answer(question, value):
    save_answer(question, value)


async def generate_dynamic_questions():
    text_responses = []
    for q_id, answer in answers.items():
        if answer['questionType'] == 'text' and answer.get('value'):
            original_q = None
            for q in survey['questions']:
                if q['id'] == q_id:
                    original_q = q
                    break
            if original_q and original_q.get('adaptive', False):
                text_value = answer['value'].strip()
                if len(text_value) >= 15:
                    text_responses.append({
                        'question_id': q_id,
                        'text': text_value,
                        'prompt': original_q['prompt']
                    })
    
    if not text_responses:
        survey_state['mode'] = 'complete'
        survey_page.refresh()
        return
    
    try:
        result = await analyze_all_responses_for_survey(text_responses)
        data = json.loads(result)
        
        if data.get('needs_followup'):
            for idx, fq in enumerate(data.get('followup_questions', []), 1):
                source_q = fq.get('source_question_id', 'unknown')
                dynamic_questions.append({
                    "id": f"followup_{source_q}_{idx}",  # e.g., "followup_q_best_part_open_1"
                    "type": "text",
                    "prompt": fq['prompt'],
                    "triggered_by": source_q,
                })
        
        survey_state['mode'] = 'transition' if dynamic_questions else 'complete'
    except:
        survey_state['mode'] = 'complete'
    
    survey_page.refresh()


def next_page():
    current = current_index['value']
    static_count = survey_state['static_count']
    
    if current == static_count - 1 and survey_state['mode'] == 'static':
        survey_state['mode'] = 'loading'
        survey_page.refresh()
        asyncio.create_task(generate_dynamic_questions())
        return
    
    all_questions = get_all_questions()
    if current == len(all_questions) - 1 and survey_state['mode'] == 'dynamic':
        survey_state['mode'] = 'complete'
        survey_page.refresh()
        return
    
    if current < len(get_all_questions()) - 1:
        current_index['value'] += 1
        survey_page.refresh()


def prev_page():
    current = current_index['value']
    static_count = survey_state['static_count']
    
    if survey_state['mode'] == 'dynamic' and current <= static_count:
        ui.notify('Cannot return to previous questions', type='warning', position='top')
        return
    
    if current_index['value'] > 0:
        current_index['value'] -= 1
        survey_page.refresh()


def advance_to_dynamic():
    survey_state['mode'] = 'dynamic'
    current_index['value'] += 1
    survey_page.refresh()


def submit_survey(dialog, sid=None):
    timer.stop_all()
    uuid_str = str(uuid.uuid4())
    submission = {
        'id': uuid_str,
        'surveyId': survey['id'],
        'surveyVersion': survey['surveyVersion'],
        'submittedAt': datetime.utcnow().isoformat(),
        'answers': list(answers.values()),
    }

    session = Session()
    response_data = submission
    response = Response(response=response_data, uuid=uuid_str, sid = sid)
    session.add(response)
    session.flush()
    response_id = response.id

    timing_data = timer.get_all_times()
    for question_id, time_seconds in timing_data.items():
        time_record = Time_Per_Question(
            response_id=response_id,
            question_id=question_id,
            time_spent=time_seconds
        )
        session.add(time_record)
    
    session.commit()
    session.close()
    dialog.close()


@ui.refreshable
def survey_page(dialog, sid=None):
    mode = survey_state['mode']

    if mode == 'loading':
        with ui.column().classes('w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'):
            with ui.card().classes('w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center'):
                ui.label('Analyzing your responses...').classes('text-2xl font-bold text-gray-800 mb-4')
                ui.spinner(size='lg', color='blue-600')
        return
    
    if mode == 'transition':
        with ui.column().classes('w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'):
            with ui.card().classes('w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center'):
                ui.label('Thank you for your feedback!').classes('text-3xl font-bold text-gray-800 mb-3')
                ui.label(f'We have {len(dynamic_questions)} follow-up question{"s" if len(dynamic_questions) != 1 else ""}').classes('text-lg text-gray-600 mb-6')
                ui.button('Continue', on_click=advance_to_dynamic).classes('bg-blue-600 text-white text-lg px-8 py-3 rounded-lg hover:bg-blue-700')
        return
    
    if mode == 'complete':
        with ui.column().classes('w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'):
            with ui.card().classes('w-full max-w-xl bg-white shadow-lg border border-gray-200 rounded-lg px-8 py-12 text-center'):
                ui.label('Thank You!').classes('text-3xl font-bold text-gray-800 mb-3')
                ui.button('Submit Survey', on_click=lambda: submit_survey(dialog, sid=sid)).classes('bg-green-600 text-white text-lg px-8 py-3 rounded-lg hover:bg-green-700')
        return
    
    questions = get_all_questions()
    q = questions[current_index['value']]
    total = len(questions)
    current = current_index['value']
    timer.start_question(q['id'])
    
    with ui.column().classes('w-full h-screen bg-gray-100 flex flex-col items-center py-8 gap-4'):
        with ui.card().classes('w-full max-w-xl bg-white shadow-sm border border-gray-200 rounded-lg px-6 py-5'):
            ui.label(survey.get('title', '2026 SAI Project')).classes('text-2xl font-bold text-gray-800')
            ui.label(f'Question {current + 1} of {total}').classes('text-xs text-gray-400 mt-2')
            ui.linear_progress(value=(current + 1) / total, color='blue-600').classes('mt-1 h-1')
        
        with ui.card().classes('w-full max-w-xl bg-white shadow-sm border border-gray-200 rounded-lg px-6 py-6'):
            ui.label(q['prompt']).classes('text-base font-semibold text-gray-800 mb-4')

            if q['type'] == 'likert':
                labels = q['scale']['labels']
                options = [label for _, label in sorted(labels.items(), key=lambda x: int(x[0]))]
                ui.radio(options, value=answers.get(q['id'], {}).get('value'), on_change=lambda e: save_answer(q, e.value)).classes('gap-2')

            elif q['type'] == 'boolean':
                ui.radio([q['options']['trueLabel'], q['options']['falseLabel']], value=answers.get(q['id'], {}).get('value'),
                    on_change=lambda e: save_answer(q, e.value == q['options']['trueLabel'])).classes('gap-2')

            elif q['type'] == 'text':
                textarea = ui.textarea(placeholder=q.get('text', {}).get('placeholder', ''), value=answers.get(q['id'], {}).get('value', '')).classes('w-full')
                textarea.on('blur', lambda e: handle_text_answer(q, textarea.value))

            with ui.row().classes('w-full justify-between mt-6'):
                show_back = survey['settings'].get('allowBack', True) and current > 0
                if survey_state['mode'] == 'dynamic' and current == survey_state['static_count']:
                    show_back = False
                
                if show_back:
                    ui.button('Back', on_click=prev_page).classes('bg-gray-200 text-gray-700 hover:bg-gray-300')
                else:
                    ui.label('')

                is_last_static = (current == survey_state['static_count'] - 1 and survey_state['mode'] == 'static')
                is_truly_last = current >= len(questions) - 1
                
                if is_last_static:
                    ui.button('Next', on_click=next_page).classes('bg-blue-600 text-white hover:bg-blue-700')
                elif is_truly_last:
                    ui.button('Submit', on_click=lambda: submit_survey(dialog)).classes('bg-green-600 text-white hover:bg-green-700')
                else:
                    ui.button('Next', on_click=next_page).classes('bg-blue-600 text-white hover:bg-blue-700')


# ─── Landing Page ────────────────────────────────────────────────
@ui.page('/')
def landing_page(request: Request):
    params = request.query_params
    sid = params.get('sid', 'default')
    with ui.column().classes('w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6 px-4'):
        ui.label('2026 SAI Project').classes('text-4xl font-bold text-gray-800 text-center mb-4')
        ui.label('Complete the survey below to share your feedback').classes('text-gray-500 text-center max-w-md mb-8')

        with ui.dialog().props('maximized') as dialog:
            survey_page(dialog, sid=sid)

        with ui.row().classes('gap-6'):
            # Student Card
            with ui.card().classes('w-80 p-8 cursor-pointer hover:shadow-xl transition-shadow').on('click', dialog.open):
                ui.icon('school', size='3rem').classes('text-blue-600 mb-4')
                ui.label('Student').classes('text-3xl font-bold text-gray-800')
                ui.label('Start Survey').classes('text-gray-600 mt-2')
            
            # Admin Card
            with ui.card().classes('w-80 p-8 cursor-pointer hover:shadow-xl transition-shadow').on('click', lambda: ui.navigate.to('/login')):
                ui.icon('admin_panel_settings', size='3rem').classes('text-gray-700 mb-4')
                ui.label('Admin').classes('text-3xl font-bold text-gray-800')
                ui.label('Manage Surveys').classes('text-gray-600 mt-2')


ui.run(storage_secret='your-secret-key-change-this-in-production-12345')