from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, String
from Base import Base

class Response(Base):
    __tablename__ = "responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    survey_id = Column(Integer, ForeignKey('surveys.id'), nullable=True)
    response = Column(JSONB, nullable=False) 
    uuid = Column(String, unique=True, nullable=False)
    sid = Column(String, nullable=True)