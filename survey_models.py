from sqlalchemy import String, Text, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.orm import relationship
from datetime import datetime
from Base import Base

class Survey(Base):
    """Survey model - represents a complete survey with metadata"""
    __tablename__ = "surveys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # Survey name
    description = Column(Text, nullable=True)
    # Rich HTML (e.g. from ui.editor): instructions, informed consent summary, links — shown before questions.
    participant_landing_html = Column(Text, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)  # Who owns this survey
    settings = Column(JSONB, nullable=True)  # Store survey settings like allowBack, etc.
    # Naive UTC: first moment the survey accepts responses; None = no start restriction.
    opens_at = Column(DateTime, nullable=True)
    # Naive UTC: last moment responses are accepted; None = no end restriction.
    closes_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to survey_questions (junction table)
    survey_questions = relationship("SurveyQuestion", back_populates="survey", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Survey(id={self.id}, name='{self.name}', version={self.version})>"


class QuestionBank(Base):
    """Question Bank - reusable questions that can be added to multiple surveys"""
    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)  # Short name/identifier for the question
    question_text = Column(Text, nullable=False)  # The actual question text/prompt
    question_type = Column(String(50), nullable=False)  # 'likert', 'boolean', 'text'
    version = Column(Integer, default=1)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)  # Who created this question
    config = Column(JSONB, nullable=False)  # Store type-specific config (options, labels, char limits, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to survey_questions
    survey_questions = relationship("SurveyQuestion", back_populates="question")
    
    def __repr__(self):
        return f"<QuestionBank(id={self.id}, name='{self.name}', type='{self.question_type}')>"


class SurveyQuestion(Base):
    """Junction table - links surveys to questions with ordering"""
    __tablename__ = "survey_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('question_bank.id'), nullable=False)
    order = Column(Integer, nullable=False)  # Order of question in survey
    is_adaptive = Column(Boolean, default=False)  # Whether this question triggers follow-ups
    
    # Relationships
    survey = relationship("Survey", back_populates="survey_questions")
    question = relationship("QuestionBank", back_populates="survey_questions")
    
    def __repr__(self):
        return f"<SurveyQuestion(survey_id={self.survey_id}, question_id={self.question_id}, order={self.order})>"


# Example config structures for different question types:
"""
LIKERT CONFIG:
{
    "scale": {
        "labels": {
            "1": "Strongly Disagree",
            "2": "Disagree", 
            "3": "Neutral",
            "4": "Agree",
            "5": "Strongly Agree"
        }
    }
}

BOOLEAN CONFIG:
{
    "options": {
        "trueLabel": "Yes",
        "falseLabel": "No"
    }
}

TEXT CONFIG:
{
    "text": {
        "placeholder": "Enter your response...",
        "charLimit": 1000
    }
}
"""