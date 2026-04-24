"""
Import default surveys from JSON files into the database
Run this once to populate the database with your existing surveys
"""

import json
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from Base import Base
from survey_models import Survey, QuestionBank, SurveyQuestion
from user import User  # Import User so Base knows about users table

# Database setup
database_url = os.getenv('DATABASE_URL')
engine = create_engine(database_url)
Session = sessionmaker(bind=engine)

# Create all tables (including users if not exists)
Base.metadata.create_all(engine)

def import_survey_from_json(filepath):
    """Import a survey from JSON file into database"""
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    session = Session()
    
    # Create the survey
    survey = Survey(
        name=data.get('title', 'Imported Survey'),
        description=data.get('description', ''),
        created_by=None,  # NULL = default/global survey
        settings=data.get('settings', {}),
        is_active=True
    )
    session.add(survey)
    session.flush()  # Get survey.id
    
    print(f"✅ Created survey: {survey.name} (ID: {survey.id})")
    
    # Import questions
    for idx, q_data in enumerate(data.get('questions', []), 1):
        
        # Build config based on question type
        config = {}
        q_type = q_data.get('type', 'text')
        
        if q_type == 'likert':
            config = {
                'scale': {
                    'labels': q_data.get('scale', {}).get('labels', {})
                }
            }
        elif q_type == 'boolean':
            # Extract true/false labels if present
            config = {
                'options': {
                    'trueLabel': 'Yes',
                    'falseLabel': 'No'
                }
            }
        elif q_type == 'text':
            text_config = q_data.get('text', {})
            config = {
                'text': {
                    'placeholder': text_config.get('placeholder', 'Enter your response...'),
                    'charLimit': text_config.get('maxLength', 1000)
                }
            }
        elif q_type == 'multi':
            config = {
                'options': q_data.get('options', ['Option 1', 'Option 2'])
            }

        if q_data.get('tags'):
            config['tags'] = q_data['tags']

        # Create question in bank
        question = QuestionBank(
            name=q_data.get('id', f'q_{idx}'),
            question_text=q_data.get('prompt', 'Question text'),
            question_type=q_type,
            created_by=None,  # NULL = default/global question
            config=config,
            version=q_data.get('version', 1)
        )
        session.add(question)
        session.flush()  # Get question.id
        
        # Link question to survey
        survey_question = SurveyQuestion(
            survey_id=survey.id,
            question_id=question.id,
            order=idx,
            is_adaptive=q_data.get('adaptive', False)
        )
        session.add(survey_question)
        
        print(f"   ✅ Added question {idx}: {question.name}")
    
    # Save survey name before closing session
    survey_name = survey.name
    
    session.commit()
    session.close()
    
    print(f"✨ Import complete! Survey '{survey_name}' is now in the database.\n")


if __name__ == '__main__':
    print("🚀 Importing default surveys...\n")
    
    # Import both surveys
    import_survey_from_json('course_survey_embedded.json')
    import_survey_from_json('faculty_sai_sentiment.json')
    
    print("✅ All done! Default surveys are now available to all admins.")