import json
import re
from openai import OpenAI
from django.conf import settings

SYSTEM_PROMPT = """You are a task scheduling assistant. Parse the user's brain dump into structured tasks.

Return ONLY a valid JSON object with a "tasks" key containing an array. Each task object must have:
- "title": string — clear, concise task name
- "duration_minutes": integer — realistic estimate (15, 30, 45, 60, 90, 120, etc.)
- "fixed_time": string or null — if a specific time is mentioned (e.g., "3pm meeting" → "15:00"), else null
- "priority": "high" | "medium" | "low"
- "notes": string — any extra context, or empty string

Rules:
- If the user mentions a fixed time (e.g., "3pm", "9:30am", "at noon"), set fixed_time in 24h "HH:MM" format
- Be generous with duration estimates — most tasks take longer than expected
- Do NOT include anything outside the JSON in your response

Example output:
{"tasks": [
  {"title": "Team standup", "duration_minutes": 30, "fixed_time": "09:00", "priority": "high", "notes": ""},
  {"title": "Write project report", "duration_minutes": 90, "fixed_time": null, "priority": "high", "notes": ""},
  {"title": "Reply to emails", "duration_minutes": 30, "fixed_time": null, "priority": "medium", "notes": ""}
]}"""


def _get_client():
    api_key = getattr(settings, 'AI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    base_url = getattr(settings, 'AI_BASE_URL', None)
    kwargs = {'api_key': api_key}
    if base_url:
        kwargs['base_url'] = base_url
    return OpenAI(**kwargs)


def parse_tasks_from_text(text: str) -> list[dict]:
    client = _get_client()
    model = getattr(settings, 'AI_MODEL', 'gpt-4o')

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if content.startswith('```'):
        content = re.sub(r'^```[a-z]*\n?', '', content)
        content = re.sub(r'\n?```$', '', content)

    data = json.loads(content)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('tasks', 'items', 'schedule', 'result'):
            if key in data and isinstance(data[key], list):
                return data[key]

    return []
