import json
from nicegui import ui
from datetime import datetime

from sqlalchemy import MetaData, create_engine, insert
from chatbot import analyze_response_for_survey
from dotenv import load_dotenv
from responses import responses
import uuid

submission: dict = {
      "type": "string",
      "minLength": 1
    }

data = json.dumps(submission, indent=2)
    # print(json.dumps(submission, indent=2))
engine = create_engine("postgresql://postgres:postgres@localhost:5432/sai_db")
meta_data = MetaData()
meta_data.reflect(bind = engine)
responses_table = meta_data.tables["responses"]
insert_statement = insert(responses_table).values(data = data)
connection = engine.connect()
connection.execute(insert_statement)
connection.commit()