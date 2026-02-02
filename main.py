import json
from nicegui import ui
from datetime import datetime
from chatbot import analyze_response_for_survey
from dotenv import load_dotenv
import uuid


load_dotenv()
# ─── Load survey data ────────────────────────────────────────────
with open('course_survey_embedded.json') as f:
    survey = json.load(f)

current_index = {'value': 0}
answers = {}                # key = questionId, value = response object
dynamic_questions = []      # follow-up questions injected at runtime



def get_all_questions():
    return survey['questions'] + dynamic_questions


def save_answer(question, value):
    answers[question['id']] = {
        'questionId':   question['id'],
        'questionType': question['type'],
        'value':        value,
    }


def handle_text_answer(question, value):
    """Save the answer, then optionally call the chatbot for follow-ups."""
    save_answer(question, value)
    print("CALLING GPT FOR FOLLOWUPS...")
    print("STUDENT TEXT:", value)

    # Guardrails: only run adaptive logic when appropriate
    if not question.get('adaptive', False):
        return
    if question.get('triggered_by'):
        return          # never trigger follow-ups from follow-ups
    if not value or len(value.strip()) < 15:
        return

    # Call the chatbot
    result = analyze_response_for_survey(value)

    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return          # fail silently — don't break the survey

    # Inject follow-up questions if the chatbot requested them
    if data.get('needs_followup'):
        for fq in data.get('followup_questions', []):
            dynamic_questions.append({
                "id":           f"{question['id']}__{fq['id']}",
                "type":         "text",
                "prompt":       fq['prompt'],
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

def submit_survey(dialog):
    submission = {
        'id':             str(uuid.uuid4()),
        'surveyId':       survey['id'],
        'surveyVersion':  survey['surveyVersion'],
        'submittedAt':    datetime.utcnow().isoformat(),
        'answers':        list(answers.values()),
    }
    print(json.dumps(submission, indent=2))
    dialog.close()


# ─── Survey Page (the refreshable card inside the dialog) ───────
@ui.refreshable
def survey_page(dialog):
    questions = get_all_questions()
    q = questions[current_index['value']]
    total = len(questions)
    current = current_index['value']
    with ui.column().classes(
        'w-full h-screen bg-gray-100 flex flex-col items-center py-8 gap-4'
    ):
        with ui.card().classes(
            'w-full max-w-xl bg-white shadow-sm border border-gray-200 '
            'rounded-lg px-6 py-5'
        ):
            # Survey title
            ui.label(survey.get('title', '2026 SAI Project')).classes(
                'text-2xl font-bold text-gray-800'
            )
            # Optional description / subtitle
            if survey.get('description'):
                ui.label(survey['description']).classes(
                    'text-sm text-gray-500 mt-1'
                )

            # Progress indicator
            ui.label(f'Question {current + 1} of {total}').classes(
                'text-xs text-gray-400 mt-2'
            )
            # Thin progress bar
            ui.linear_progress(
                value=(current + 1) / total,
                color='blue-600'
            ).classes('mt-1 h-1')
        with ui.card().classes(
            'w-full max-w-xl bg-white shadow-sm border border-gray-200 '
            'rounded-lg px-6 py-6'
        ):
            # Question prompt
            ui.label(q['prompt']).classes(
                'text-base font-semibold text-gray-800 mb-4'
            )

            # ── Likert scale ──
            if q['type'] == 'likert':
                labels = q['scale']['labels']
                options = [
                    label
                    for _, label in sorted(labels.items(), key=lambda x: int(x[0]))
                ]
                ui.radio(
                    options,
                    value=answers.get(q['id'], {}).get('value'),
                    on_change=lambda e: save_answer(q, e.value),
                ).classes('gap-2')

            # ── Boolean (yes / no) ──
            elif q['type'] == 'boolean':
                ui.radio(
                    [q['options']['trueLabel'], q['options']['falseLabel']],
                    value=answers.get(q['id'], {}).get('value'),
                    on_change=lambda e: save_answer(
                        q,
                        e.value == q['options']['trueLabel'],
                    ),
                ).classes('gap-2')

            # ── Free-text ──
            elif q['type'] == 'text':
                textarea = ui.textarea(
                    placeholder=q.get('text', {}).get('placeholder', ''),
                    value=answers.get(q['id'], {}).get('value', ''),
                ).classes('w-full')
                # Trigger adaptive logic on blur (when the user clicks away)
                textarea.on(
                    'blur',
                    lambda e: handle_text_answer(q, textarea.value),
                )

            # ── Navigation buttons at the bottom of the question card ──
            with ui.row().classes('w-full justify-between mt-6'):
                # Back button
                if (
                    survey['settings'].get('allowBack', True)
                    and current > 0
                ):
                    ui.button('Back', on_click=prev_page).classes(
                        'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    )
                else:
                    # Invisible spacer so Next/Submit stays on the right
                    ui.label('')

                # Next  or  Submit
                if current < total - 1:
                    ui.button('Next', on_click=next_page).classes(
                        'bg-blue-600 text-white hover:bg-blue-700'
                    )
                else:
                    ui.button(
                        'Submit',
                        on_click=lambda: submit_survey(dialog),
                    ).classes(
                        'bg-green-600 text-white hover:bg-green-700'
                    )


with ui.column().classes(
    'w-full h-screen bg-gray-100 flex flex-col items-center '
    'justify-center gap-6 px-4'
):
    # Title
    ui.label('2026 SAI Project').classes(
        'text-4xl font-bold text-gray-800 text-center'
    )
    # Short description
    ui.label(
        'Complete the survey below to share your feedback '
    ).classes('text-gray-500 text-center max-w-md')

    with ui.dialog().props('maximized') as dialog:
        survey_page(dialog)

    # Start button on the landing page
    ui.button(
        'Start Survey',
        on_click=dialog.open,
    ).classes(
        'bg-blue-600 text-white text-lg px-8 py-3 '
        'rounded-lg hover:bg-blue-700 shadow-md'
    )


ui.run()