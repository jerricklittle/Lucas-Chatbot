from sqlalchemy import DateTime, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer

class Base(DeclarativeBase):
    pass

class Time_Per_Question(Base):
    __tablename__ = "time_per_question"

    id: Column[Integer] = Column[Integer](Integer, primary_key=True, autoincrement=True)
    response_id = Column(Integer, ForeignKey('responses.id'), nullable=False)
    question_id = Column(Integer, nullable=False)
    time_spent = Column(DateTime, nullable=False)