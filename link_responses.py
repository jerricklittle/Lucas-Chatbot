"""
Link existing responses to imported surveys
Run this to connect your test responses to the database surveys
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from survey_models import Survey
from responses import Response

engine = create_engine("postgresql://postgres:postgres@localhost/sai_db")
Session = sessionmaker(bind=engine)

session = Session()

# Find the imported surveys
surveys = session.query(Survey).filter(Survey.created_by == None).all()

print("📊 Found imported surveys:")
for s in surveys:
    print(f"  ID {s.id}: {s.name}")

print("\n🔍 Checking existing responses...")
responses = session.query(Response).all()
print(f"  Found {len(responses)} responses")

if len(responses) == 0:
    print("\n❌ No responses to link!")
    session.close()
    exit()

if len(surveys) == 0:
    print("\n❌ No imported surveys found! Run import_surveys.py first.")
    session.close()
    exit()

# Ask which survey to link to (default to first one - probably course survey)
print(f"\n❓ Which survey were these responses for?")
for idx, s in enumerate(surveys, 1):
    print(f"  {idx}. {s.name}")

choice = input(f"\nEnter number (default 1): ").strip() or "1"
survey_id = surveys[int(choice) - 1].id

print(f"\n🔗 Linking {len(responses)} responses to survey ID {survey_id}...")

# Update all responses
for response in responses:
    response.survey_id = survey_id

session.commit()
session.close()

print(f"✅ Done! All responses now linked to survey ID {survey_id}")
print("🎉 Check your analytics page!")