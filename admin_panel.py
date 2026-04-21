"""
Admin Panel for Survey and Question Management
Provides CRUD operations for surveys and questions via NiceGUI interface
"""

import json
import os
from nicegui import ui
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from Base import Base
from survey_models import Survey, QuestionBank, SurveyQuestion
from authentication import is_authenticated, is_admin, get_current_user, get_current_user_role, get_current_user_id, logout_user
from dotenv import load_dotenv

load_dotenv()

# Database setup
database_url = os.getenv('DATABASE_URL')
engine = create_engine("database_url")
Session = sessionmaker(bind=engine)

# Create all tables
Base.metadata.create_all(engine)


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
        
        # Surveys table
        if surveys:
            with ui.card().classes('w-full'):
                columns = [
                    {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left'},
                    {'name': 'name', 'label': 'Name', 'field': 'name', 'align': 'left'},
                    {'name': 'version', 'label': 'Version', 'field': 'version', 'align': 'center'},
                    {'name': 'updated', 'label': 'Last Updated', 'field': 'updated', 'align': 'left'},
                    {'name': 'actions', 'label': 'Actions', 'field': 'actions', 'align': 'center'},
                ]
                
                rows = []
                for s in surveys:
                    rows.append({
                        'id': s.id,
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
                        <q-btn flat round dense icon="delete" size="sm" color="red" 
                               @click="$parent.$emit('delete', props.row.id)" />
                    </q-td>
                ''')
                table.on('edit', lambda e: ui.navigate.to(f'/admin/surveys/edit/{e.args}'))
                table.on('delete', lambda e: delete_survey(e.args))
        else:
            ui.label('No surveys yet. Click "Add" to create one.').classes('text-gray-500 text-center py-8')


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
                    randomize_enabled.value
                )).classes('bg-blue-600 text-white mt-4')
            else:
                ui.button('Update Details', on_click=lambda: update_survey_details(
                    survey_id, 
                    name_input.value, 
                    desc_input.value,
                    randomize_enabled.value
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


def create_survey_initial(name, description, randomize):
    """Create initial survey"""
    if not name.strip():
        ui.notify('Survey name is required', type='negative')
        return
    
    settings = {}
    if randomize:
        settings['randomize'] = True
    
    session = Session()
    survey = Survey(
        name=name, 
        description=description, 
        settings=settings,
        created_by=get_current_user_id()  # Set owner
    )
    session.add(survey)
    session.commit()
    survey_id = survey.id
    session.close()
    
    ui.notify(f'Survey "{name}" created!', type='positive')
    ui.navigate.to(f'/admin/surveys/edit/{survey_id}')


def update_survey_details(survey_id, name, description, randomize):
    """Update survey metadata"""
    session = Session()
    survey = session.query(Survey).filter_by(id=survey_id).first()
    survey.name = name
    survey.description = description
    
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
    if not is_admin():
        ui.navigate.to('/login?error=admin_only')
        return
    
    with ui.column().classes('w-full max-w-4xl mx-auto p-8'):
        with ui.row().classes('w-full justify-between items-center mb-8'):
            with ui.column():
                ui.label('Survey Admin Panel').classes('text-4xl font-bold')
                ui.label(f'Logged in as: {get_current_user()}').classes('text-sm text-gray-600')
            with ui.row().classes('gap-2'):
                ui.button('← Back to Survey', on_click=lambda: ui.navigate.to('/')).classes('bg-gray-500 text-white')
                ui.button('Logout', on_click=lambda: ui.navigate.to('/logout')).classes('bg-red-600 text-white')
        
        with ui.row().classes('gap-4'):
            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/surveys')):
                ui.label('📋 Surveys').classes('text-2xl font-bold')
                ui.label('Manage survey pages').classes('text-gray-600')
            
            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/questions')):
                ui.label('❓ Questions').classes('text-2xl font-bold')
                ui.label('Manage question bank').classes('text-gray-600')
            
            with ui.card().classes('w-64 p-6 cursor-pointer hover:shadow-lg').on('click', lambda: ui.navigate.to('/admin/analytics')):
                ui.label('📊 Analytics').classes('text-2xl font-bold')
                ui.label('View response insights').classes('text-gray-600')


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
    
    # Get questions in order
    survey_questions = session.query(SurveyQuestion).filter_by(survey_id=survey_id).order_by(SurveyQuestion.order).all()
    
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
            session = Session()
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
            
            session.close()


# Run the admin panel
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='Survey Admin Panel', port=8080)