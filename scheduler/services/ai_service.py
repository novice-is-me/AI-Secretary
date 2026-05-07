import json
import re
from datetime import date as _date
from openai import OpenAI
from django.conf import settings

SYSTEM_PROMPT_TEMPLATE = """You are a task scheduling assistant. Today is {today_str}.

Parse the user's brain dump into structured tasks.

Return ONLY a valid JSON object with a "tasks" key containing an array. Each task object must have:
- "title": string — clear, concise task name
- "duration_minutes": integer — realistic estimate (15, 30, 45, 60, 90, 120, etc.)
- "fixed_time": string or null — if a specific time is mentioned (e.g., "3pm meeting" → "15:00"), else null
- "day": string — which day this task belongs to. Use exactly one of:
  - "today" — if no specific day mentioned, or the task is for today
  - "tomorrow" — if tomorrow is mentioned
  - "Monday" | "Tuesday" | "Wednesday" | "Thursday" | "Friday" | "Saturday" | "Sunday" — for a named weekday
  - "YYYY-MM-DD" — for a specific calendar date (e.g., "May 13" → "{year}-05-13")
- "priority": "high" | "medium" | "low"
- "notes": string — any extra context (do NOT repeat day info here), or empty string

Rules:
- If the user mentions a fixed time (e.g., "3pm", "9:30am", "at noon"), set fixed_time in 24h "HH:MM" format
- If the user says a specific date like "May 13" or "the 20th", output it as "YYYY-MM-DD" using the current year unless another year is clear
- If the user says a weekday like "Tuesday" or "next Friday", use that weekday name
- Be generous with duration estimates — most tasks take longer than expected
- Do NOT include anything outside the JSON in your response

Example output (assuming today is Thursday 2026-05-07):
{{"tasks": [
  {{"title": "Team standup", "duration_minutes": 30, "fixed_time": "09:00", "day": "today", "priority": "high", "notes": ""}},
  {{"title": "Swim", "duration_minutes": 60, "fixed_time": null, "day": "2026-05-13", "priority": "medium", "notes": ""}},
  {{"title": "Dentist appointment", "duration_minutes": 60, "fixed_time": "14:00", "day": "Tuesday", "priority": "high", "notes": ""}},
  {{"title": "Clean the house", "duration_minutes": 120, "fixed_time": null, "day": "Saturday", "priority": "medium", "notes": ""}}
]}}"""


def _get_client():
    api_key = getattr(settings, 'AI_API_KEY', '') or getattr(settings, 'OPENAI_API_KEY', '')
    base_url = getattr(settings, 'AI_BASE_URL', None)
    kwargs = {'api_key': api_key}
    if base_url:
        kwargs['base_url'] = base_url
    return OpenAI(**kwargs)


def parse_tasks_from_text(text: str, today: _date | None = None) -> list[dict]:
    if today is None:
        today = _date.today()

    client = _get_client()
    model = getattr(settings, 'AI_MODEL', 'gpt-4o')

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        today_str=today.strftime('%A %Y-%m-%d'),
        year=today.year,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message.content.strip()

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
