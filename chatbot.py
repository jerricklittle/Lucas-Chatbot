from openai import OpenAI
import os


import os

adaptive_prompt = """
You are helping design a survey.

Given a student's open-ended response, decide whether follow-up questions
would help clarify or deepen their response.

Rules:
- Generate at most 2 follow-up questions
- Questions must be open-ended
- Questions must be neutral and non-judgmental
- Do NOT repeat the original question
- Do NOT teach or explain anything

Respond ONLY with valid JSON:

{
  "needs_followup": true | false,
  "followup_questions": [
    {
      "id": "string",
      "prompt": "string"
    }
  ]
}
"""
# system_prompt = (
#     "You are a helpful teaching assistant for an Introductory Biology course. "
#     "Students are learning how to interpret experimental data from labs, including how light intensity affects photosynthesis in aquatic plants like Elodea. "
#     "Your job is to help students who feel unsure about how to start their lab assignments. "
#     "You should guide them in forming scientific claims and justifying those claims using lab data, without giving them the answer. "
#     "Use the Feynman Technique: ask the student to explain what they understand in their own words, help them identify gaps, and encourage revision and reflection. "
#     "Stay conversational and supportive, like a peer or lab partner who helps them think it through. "
#     "Never write their answer for them — just help them gain confidence in starting or refining their own ideas."
# )

def ask_chatbot(prompt, system_role=adaptive_prompt):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(model="gpt-4o",
    messages=[
        {"role": "system", "content": system_role},
        {"role": "user", "content": prompt}
    ],
    temperature=0.7)
    return response.choices[0].message.content

def analyze_response_for_survey(text):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": adaptive_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content