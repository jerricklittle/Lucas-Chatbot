from sqlalchemy import Text
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer

class Base(DeclarativeBase):
    pass

class QuestionTypes(Base):
    __tablename__ = "question_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_type = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)