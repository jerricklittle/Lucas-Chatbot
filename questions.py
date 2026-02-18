from sqlalchemy import ForeignKey, Text, Text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer
from Base import Base

class Questions(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_text = Column(Text, nullable=False)
    version = Column(Integer)
    question_type_id = Column(Integer, ForeignKey('question_types.id'))