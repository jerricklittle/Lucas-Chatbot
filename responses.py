from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer
from Base import Base

class Response(Base):
    __tablename__ = "responses"

    id: Column[Integer] = Column[Integer](Integer, primary_key=True)
    response: Column[JSONB] = Column[JSONB](JSONB) 
    uuid = Column(String, unique=True, nullable=False)