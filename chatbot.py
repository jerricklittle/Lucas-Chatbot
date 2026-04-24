from openai import AsyncOpenAI
import os

# Default instructor/decision rules (used in admin UI when adaptive is enabled and as AI fallback when prompt_text is empty).
DEFAULT_ADAPTIVE_PROMPT_TEXT = """
You are an instructor collecting constructive, actionable feedback to improve a course.

Given the student's response, decide whether asking follow-up questions would provide
meaningful additional insight beyond what was already said.

Decision rules:
- Request follow-up questions if ANY of the following are true:
    1. The student's answer is vague, generic, or lacks specifics
       (e.g. "it was fine", "I didn't like it", "could be better").
    2. The student mentions a problem, frustration, or negative experience
       but does not explain why or give an example.
    3. The student references something specific (a topic, assignment, or
       interaction) but does not elaborate on the impact or why it mattered.
    4. The student's answer suggests a tradeoff or tension worth exploring.
- Do NOT generate follow-ups for responses that are already detailed,
  concrete, and self-contained (the student has already explained what
  happened and why it mattered).

Generation rules:
- Generate at most 2 follow-up questions per student response.
- If the student was vague or negative without detail, the first follow-up
  should gently ask them to give a specific example or describe a moment
  that stands out.
- Follow-up questions must be open-ended and encourage reflection or
  concrete examples.
- Do NOT repeat, restate, or closely paraphrase the original question or
  the student's answer.
- Each follow-up question should explore a new angle or clarify an
  implication of the response.
""".strip()

# Fixed JSON contract (always appended to the system message).
ADAPTIVE_FOLLOWUP_OUTPUT_SPEC = """
Output rules:
- If follow-up questions are needed, set "needs_followup" to true.
- If no follow-up questions are needed, set "needs_followup" to false and
  return an empty list for "followup_questions".
- Respond ONLY with valid JSON. Do not include explanations, commentary,
  or formatting outside the JSON.

Return JSON in exactly the following format:

{
  "needs_followup": true,
  "followup_questions": [
    {
      "id": "followup_1",
      "prompt": "Can you describe a specific example of when this happened?",
      "source_question_id": "q1"
    },
    {
      "id": "followup_2",
      "prompt": "How did this impact your learning experience?",
      "source_question_id": "q1"
    }
  ]
}
""".strip()

# Full legacy system prompt (default instructor text + output spec).
adaptive_prompt = f"{DEFAULT_ADAPTIVE_PROMPT_TEXT}\n\n{ADAPTIVE_FOLLOWUP_OUTPUT_SPEC}"

FOLLOWUP_SYSTEM_PREAMBLE = """You help analyze open-ended survey responses and propose optional follow-up questions.
Each numbered response below begins with an "Instructor context" section. Apply that guidance only when deciding whether follow-ups are needed for that specific response, and when phrasing follow-up questions for that response.
""".strip()


def _effective_prompt_text(response: dict) -> str:
    raw = response.get("prompt_text")
    if raw is None:
        return DEFAULT_ADAPTIVE_PROMPT_TEXT
    text = str(raw).strip()
    return text if text else DEFAULT_ADAPTIVE_PROMPT_TEXT


async def analyze_all_responses_for_survey(text_responses):
    """
    Analyzes multiple student text responses at once and generates
    follow-up questions for all of them in a single GPT call.

    Args:
        text_responses: List of dicts with keys: question_id, text, prompt,
            and optional prompt_text (instructor instructions for the model;
            empty or missing uses DEFAULT_ADAPTIVE_PROMPT_TEXT).

    Returns:
        JSON string with needs_followup and followup_questions array
    """
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_content = f"{FOLLOWUP_SYSTEM_PREAMBLE}\n\n{ADAPTIVE_FOLLOWUP_OUTPUT_SPEC}"

    combined_text = "The student provided the following responses:\n\n"

    for i, response in enumerate(text_responses, 1):
        instructor = _effective_prompt_text(response)
        combined_text += f"Response {i}:\n"
        combined_text += f"Instructor context (for this response only):\n{instructor}\n\n"
        combined_text += f"Original Question: {response['prompt']}\n"
        combined_text += f"Question ID: {response['question_id']}\n"
        combined_text += f"Student Answer: {response['text']}\n\n"

    combined_text += (
        "\nBased on ALL of the above responses, generate follow-up questions where appropriate. "
        "Respect each response's Instructor context only for that response. "
        "Include the source_question_id field in each follow-up to indicate which response it's addressing."
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": combined_text},
        ],
        temperature=0.2,
    )

    raw_response = response.choices[0].message.content
    cleaned_response = raw_response.strip()
    if cleaned_response.startswith("```json"):
        cleaned_response = cleaned_response[7:]
    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response[3:]
    if cleaned_response.endswith("```"):
        cleaned_response = cleaned_response[:-3]

    return cleaned_response.strip()
