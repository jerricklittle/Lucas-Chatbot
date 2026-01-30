import json
from nicegui import ui
from datetime import datetime
from chatbot import analyze_response_for_survey
import uuid

with open('course_survey_embedded.json') as f:
    survey = json.load(f)
current_index = {'value': 0}

answers = {}  # key = questionId, value = response object
dynamic_questions = []

def get_all_questions():
    return survey['questions'] + dynamic_questions
def save_answer(question, value):
    answers[question['id']] = {
        'questionId': question['id'],
        'questionType': question['type'],
        'value': value,
    }

def handle_text_answer(question, value):
    # 1. Always save the answer
    save_answer(question, value)
    print("CALLING GPT FOR FOLLOWUPS...")
    print("STUDENT TEXT:", value)

    # 2. Guardrails
    if not question.get('adaptive', False):
        return

    if question.get('triggered_by'):
        return  # never trigger follow-ups from follow-ups

    if not value or len(value.strip()) < 15:
        return

    # 3. Call the chatbot
    result = analyze_response_for_survey(value)

    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return  # fail silently, don't break survey

    # 4. Add follow-up questions (if needed)
    if data.get('needs_followup'):
        for fq in data.get('followup_questions', []):
            dynamic_questions.append({
                "id": f"{question['id']}__{fq['id']}",
                "type": "text",
                "prompt": fq['prompt'],
                "triggered_by": question['id'],
            })
        survey_page.refresh()

def next_page():
    if current_index['value'] < len(get_all_questions()) - 1:
        current_index['value'] += 1
        survey_page.refresh()

def prev_page():
    if current_index['value'] > 0:
        current_index['value'] -= 1
        survey_page.refresh()
@ui.refreshable
def survey_page(dialog):
    questions = get_all_questions()
    q = questions[current_index['value']]

    ui.label(q['prompt']).classes('text-lg font-semibold')

    # --- Likert ---
    if q['type'] == 'likert':
        labels = q['scale']['labels']
        options = [label for _, label in sorted(labels.items(), key=lambda x: int(x[0]))]

        ui.radio(
            options,
            value=answers.get(q['id'], {}).get('value'),
            on_change=lambda e: save_answer(q, e.value),
        )

    # --- Boolean ---
    elif q['type'] == 'boolean':
        ui.radio(
            [
                q['options']['trueLabel'],
                q['options']['falseLabel'],
            ],
            value=answers.get(q['id'], {}).get('value'),
            on_change=lambda e: save_answer(
                q,
                e.value == q['options']['trueLabel'],
            ),
        )

    # --- Text ---
    elif q['type'] == 'text':
        ui.textarea(
            placeholder = q.get('text', {}).get('placeholder', ''),
            value=answers.get(q['id'], {}).get('value', ''),
            on_change=lambda e: handle_text_answer(q, e.value),
        )
        # ui.textarea.on(
        #     'blur',
        #     lambda e: handle_text_answer(q, textarea.value)
        # )


    ui.separator()

    # --- Navigation ---
    with ui.row().classes('w-full justify-between'):
        if survey['settings'].get('allowBack', True) and current_index['value'] > 0:
            ui.button('Back', on_click=prev_page)

        with ui.row():
            if current_index['value'] < len(get_all_questions()) - 1:
                ui.button('Next', on_click=next_page)
            else:
                ui.button('Submit', on_click=lambda: submit_survey(dialog))

            ui.button('Close', on_click=dialog.close)
def submit_survey(dialog):
    submission = {
        'id': str(uuid.uuid4()),
        'surveyId': survey['id'],
        'surveyVersion': survey['surveyVersion'],
        'submittedAt': datetime.utcnow().isoformat(),
        'answers': list(answers.values()),
    }

    print(json.dumps(submission, indent=2))
    dialog.close()
with ui.dialog() as dialog:
    with ui.card().classes('w-[600px]'):
        survey_page(dialog)

ui.button('Start Survey', on_click=dialog.open)

ui.run()
