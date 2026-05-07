import json
import re
from openai import OpenAI
from django.conf import settings

SYSTEM_PROMPT = """You are a task scheduling assistant. Parse the user's brain dump into structured tasks.

Return ONLY a valid JSON array. Each task object must have:
- "title": string — clear, concise task name
- "duration_minutes": integer — realistic estimate (15, 30, 45, 60, 90, 120, etc.)
- "fixed_time": string or null — if a specific time is mentioned (e.g., "3pm meeting" → "15:00"), else null
- "priority": "high" | "medium" | "low"
- "notes": string — any extra context, or empty string

Rules:
- If the user mentions a fixed time (e.g., "3pm", "9:30am", "at noon"), set fixed_time in 24h "HH:MM" format
- Be generous with duration estimates — most tasks take longer than expected
- Sort by priority (high first), then by fixed_time
- Do NOT include anything outside the JSON array in your response

Example output:
[
  {"title": "Team standup", "duration_minutes": 30, "fixed_time": "09:00", "priority": "high", "notes": ""},
  {"title": "Write project report", "duration_minutes": 90, "fixed_time": null, "priority": "high", "notes": ""},
  {"title": "Reply to emails", "duration_minutes": 30, "fixed_time": null, "priority": "medium", "notes": ""}
]"""


def parse_tasks_from_text(text: str) -> list[dict]:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    data = json.loads(content)

    if isinstance(data, list):
        return data
    for key in ("tasks", "items", "schedule", "result"):
        if key in data and isinstance(data[key], list):
            return data[key]

    # Fallback: find first JSON array in response
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        return json.loads(match.group())

    return []
