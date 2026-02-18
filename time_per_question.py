from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer, String
from Base import Base

class Time_Per_Question(Base):
    __tablename__ = "time_per_question"

    id = Column(Integer, primary_key=True, autoincrement=True)
    response_id = Column(Integer, ForeignKey('responses.id'), nullable=False)
    question_id = Column(String, nullable=False)
    time_spent = Column(Float, nullable=False)  # Time in seconds (can be fractional)