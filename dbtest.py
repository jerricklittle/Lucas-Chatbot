import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from responses import Base, Response

database_url = os.getenv('DATABASE_URL')
engine = create_engine("database_url")
Session = sessionmaker(bind=engine)
session = Session()

Base.metadata.create_all(engine)

response_data = {'a': 1, 'b': 'foo', 'c': [1, 1, 2, 3, 5, 8, 13]}
response = Response(response=response_data)

# Insert it into the database
session.add(response)
session.commit()
