from typing import List
from typing import Optional
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.dialects.postgresql import JSONB, insert


class Base(DeclarativeBase):
    pass

class responses(Base):
    __tablename__ = "responses"

    response: Mapped[JSONB] = mapped_column(JSONB)
    id: Mapped[int] = mapped_column(primary_key=True)