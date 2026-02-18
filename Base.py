"""
Shared declarative base for all SQLAlchemy models.
Import this Base in all your model files to ensure they share the same metadata.
"""
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass