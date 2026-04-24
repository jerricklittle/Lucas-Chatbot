"""
Import every ORM class so they attach to the shared Base.metadata in FK-safe order.

``main`` and scripts must import this (or these modules) before ``create_all`` or any
query that configures mappers. Otherwise ``Survey`` / ``QuestionBank`` reference
``users.id`` before the ``users`` table is registered → NoReferencedTableError.
"""

from user import User  # noqa: F401
from survey_models import QuestionBank, Survey, SurveyQuestion  # noqa: F401
from responses import Response  # noqa: F401
from time_per_question import Time_Per_Question  # noqa: F401
