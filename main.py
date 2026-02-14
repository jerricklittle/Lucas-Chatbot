import asyncio
import json
from nicegui import ui
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from chatbot import analyze_all_responses_for_survey
from dotenv import load_dotenv
from responses import Base, Response
import uuid


load_dotenv()
with open('course_survey_embedded.json') as f:
    survey = json.load(f)

current_index = {'value': 0}
answers = {}                # key = questionId, value = response object
dynamic_questions: list[dict] = []      # follow-up questions injected at runtime

# ─── Survey State Management ─────────────────────────────────────
survey_state = {
    'mode': 'static',  # Modes: 'static', 'loading', 'transition', 'dynamic', 'complete'
    'static_count': len(survey['questions']),  # Number of original JSON questions
}


def get_all_questions():
    """Returns combined list of static + dynamic questions"""
    return survey['questions'] + dynamic_questions


def save_answer(question, value):
    """Store answer in the answers dictionary"""
    answers[question['id']] = {
        'questionId':   question['id'],
        'questionType': question['type'],
        'value':        value
    }


def handle_text_answer(question, value):
    """Save text answer"""
    save_answer(question, value)


async def generate_dynamic_questions():
    """
    Async function that collects all text responses and generates
    all dynamic follow-up questions in a single GPT call.
    """
    
    # Collect all text responses from the survey
    text_responses = []
    for q_id, answer in answers.items():
        if answer['questionType'] == 'text' and answer.get('value'):
            # Find the original question to check if it's adaptive
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
                    print(f"  ✅ ADDED to text_responses")
                else:
                    print(f"  ❌ Text too short (need 15+ chars)")
            else:
                print(f"  ❌ Question is NOT adaptive")
    
    # If there are no text responses worth following up on, skip to complete
    if not text_responses:
        survey_state['mode'] = 'complete'
        survey_page.refresh()
        return
    
    try:
        # Call GPT with all text responses at once
        result = await analyze_all_responses_for_survey(text_responses)
        
        data = json.loads(result)
        
        # Populate dynamic_questions list
        if data.get('needs_followup'):
            for fq in data.get('followup_questions', []):
                dynamic_questions.append({
                    "id": fq['id'],
                    "type": "text",
                    "prompt": fq['prompt'],
                    "triggered_by": fq.get('source_question_id', 'batch'),
                })
        
        # Update state based on whether we got dynamic questions
        survey_state['mode'] = 'transition' if dynamic_questions else 'complete'

    
    except json.JSONDecodeError as e:
        survey_state['mode'] = 'complete'
    except Exception as e:
        import traceback
        traceback.print_exc()
        survey_state['mode'] = 'complete'
    
    # Refresh UI to show transition page or complete
    survey_page.refresh()


def next_page():
    """Handle next button - detects transition to dynamic questions"""
    current = current_index['value']
    static_count = survey_state['static_count']
    # Check: Are we finishing the last static question?
    if current == static_count - 1 and survey_state['mode'] == 'static':
        # Don't increment index - stay on current question
        # Transition to loading mode and kick off async generation
        survey_state['mode'] = 'loading'
        survey_page.refresh()  # Show loading screen
        asyncio.create_task(generate_dynamic_questions())
        return  # Don't increment index yet
    
    # Check: Are we finishing the last dynamic question?
    all_questions = get_all_questions()
    if current == len(all_questions) - 1 and survey_state['mode'] == 'dynamic':
        survey_state['mode'] = 'complete'
        survey_page.refresh()  # Show completion screen
        return  # Don't increment index
    
    # Normal navigation
    if current < len(get_all_questions()) - 1:
        current_index['value'] += 1
        survey_page.refresh()
    else:
        print("  → Already at last question")


def prev_page():
    """Handle back button"""
    current = current_index['value']
    static_count = survey_state['static_count']
    
    # If we're in dynamic mode, only allow going back within dynamic questions
    if survey_state['mode'] == 'dynamic' and current <= static_count:
        ui.notify(
            'Cannot return to previous questions after follow-ups have been generated',
            type='warning',
            position='top'
        )
        return  # Don't allow going back to static questions
    
    if current_index['value'] > 0:
        current_index['value'] -= 1
        survey_page.refresh()


def advance_to_dynamic():
    """Move from transition page to first dynamic question"""
    survey_state['mode'] = 'dynamic'
    current_index['value'] += 1
    survey_page.refresh()


def submit_survey(dialog):
    """Save survey submission to database"""
    uuid_str = str(uuid.uuid4())
    submission = {
        'id': uuid_str,
        'surveyId': survey['id'],
        'surveyVersion': survey['surveyVersion'],
        'submittedAt': datetime.utcnow().isoformat(),
        'answers': list(answers.values()),
    }

    engine = create_engine("postgresql://postgres:postgres@localhost/sai_db") 
    Session = sessionmaker(bind=engine)
    session = Session()

    Base.metadata.create_all(engine)

    response_data = submission
    response = Response(response=response_data, uuid=uuid_str)

    session.add(response)
    session.commit()

    dialog.close()


# ─── Survey Page (the refreshable card inside the dialog) ───────
@ui.refreshable
def survey_page(dialog):
    """Main survey UI - switches between question view and transition screens"""
    mode = survey_state['mode']
    
    # ═══ LOADING SCREEN ═══
    if mode == 'loading':
        with ui.column().classes(
            'w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'
        ):
            with ui.card().classes(
                'w-full max-w-xl bg-white shadow-lg border border-gray-200 '
                'rounded-lg px-8 py-12 text-center'
            ):
                ui.label('Analyzing your responses...').classes(
                    'text-2xl font-bold text-gray-800 mb-4'
                )
                ui.spinner(size='lg', color='blue-600')
                ui.label(
                    'We\'re generating personalized follow-up questions based on your feedback.'
                ).classes('text-sm text-gray-500 mt-4')
        return
    
    # ═══ TRANSITION SCREEN ═══
    if mode == 'transition':
        with ui.column().classes(
            'w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'
        ):
            with ui.card().classes(
                'w-full max-w-xl bg-white shadow-lg border border-gray-200 '
                'rounded-lg px-8 py-12 text-center'
            ):
                ui.label('Thank you for your feedback!').classes(
                    'text-3xl font-bold text-gray-800 mb-3'
                )
                ui.label(
                    f'We have {len(dynamic_questions)} follow-up question{"s" if len(dynamic_questions) != 1 else ""} '
                    'based on your responses.'
                ).classes('text-lg text-gray-600 mb-6')
                ui.label(
                    'These questions will help us better understand your experience '
                    'and make meaningful improvements to the course.'
                ).classes('text-sm text-gray-500 mb-8')
                ui.button(
                    'Continue to Follow-up Questions',
                    on_click=advance_to_dynamic
                ).classes(
                    'bg-blue-600 text-white text-lg px-8 py-3 '
                    'rounded-lg hover:bg-blue-700 shadow-md'
                )
        return
    
    # ═══ COMPLETE SCREEN (After all questions - static + dynamic) ═══
    if mode == 'complete':
        with ui.column().classes(
            'w-full h-screen bg-gray-100 flex flex-col items-center justify-center gap-6'
        ):
            with ui.card().classes(
                'w-full max-w-xl bg-white shadow-lg border border-gray-200 '
                'rounded-lg px-8 py-12 text-center'
            ):
                ui.label('Thank You!').classes(
                    'text-3xl font-bold text-gray-800 mb-3'
                )
                ui.label(
                    'Your feedback is complete and will help us improve the course.'
                ).classes('text-lg text-gray-600 mb-8')
                ui.button(
                    'Submit Survey',
                    on_click=lambda: submit_survey(dialog)
                ).classes(
                    'bg-green-600 text-white text-lg px-8 py-3 '
                    'rounded-lg hover:bg-green-700 shadow-md'
                )
        return
    
    # ═══ NORMAL QUESTION VIEW ═══
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
                # Save answer on blur (when user clicks away)
                textarea.on(
                    'blur',
                    lambda e: handle_text_answer(q, textarea.value),
                )

            # ── Navigation buttons at the bottom of the question card ──
            with ui.row().classes('w-full justify-between mt-6'):
                # Back button logic
                # Don't show back button if:
                # 1. We're at the first question (current == 0), OR
                # 2. We're in dynamic mode at the first dynamic question (don't allow going back to static)
                show_back = survey['settings'].get('allowBack', True) and current > 0
                
                # If in dynamic mode and at first dynamic question, hide back button
                if survey_state['mode'] == 'dynamic' and current == survey_state['static_count']:
                    show_back = False
                
                if show_back:
                    ui.button('Back', on_click=prev_page).classes(
                        'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    )
                else:
                    # Invisible spacer so Next/Submit stays on the right
                    ui.label('')

                # Next or Submit button logic
                # Show "Next" if we're not at the very end (including showing Next on last static question)
                # Only show "Submit" when we're truly at the last question (after dynamic questions)
                is_last_static = (current == survey_state['static_count'] - 1 and 
                                survey_state['mode'] == 'static')
                is_truly_last = current >= len(questions) - 1
                
                if is_last_static:
                    # Last static question - show "Next" to trigger transition
                    ui.button('Next', on_click=next_page).classes(
                        'bg-blue-600 text-white hover:bg-blue-700'
                    )
                elif is_truly_last:
                    # Truly the last question (after dynamic or if no dynamic) - show "Submit"
                    ui.button(
                        'Submit',
                        on_click=lambda: submit_survey(dialog),
                    ).classes(
                        'bg-green-600 text-white hover:bg-green-700'
                    )
                else:
                    # Normal questions - show "Next"
                    ui.button('Next', on_click=next_page).classes(
                        'bg-blue-600 text-white hover:bg-blue-700'
                    )


# ─── Landing Page ────────────────────────────────────────────────
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