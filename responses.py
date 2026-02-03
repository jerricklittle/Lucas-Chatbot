from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import Column
from sqlalchemy.types import Integer

class Base(DeclarativeBase):
    pass

class Response(Base):
    __tablename__ = "responses"

    id: Column[Integer] = Column[Integer](Integer, primary_key=True)
    response: Column[JSONB] = Column[JSONB](JSONB)