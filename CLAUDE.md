# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary is a Django web application — "Your intelligent daily planner." Built for the DEVKADA Hackathon.

**Core flow:** User logs in → brain-dumps tasks as free text (or uploads a screenshot) → GPT-4o parses into structured tasks → scheduling engine builds a realistic hourly plan → "Re-shuffle" button re-plans the remaining day from current time.

## Setup

```bash
# Create and activate virtual environment
python3.13 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY

# Apply migrations
python manage.py migrate

# Create a user
python manage.py createsuperuser

# Build Tailwind CSS (one-time / after template changes)
python manage.py tailwind build

# Run development server (in one terminal)
python manage.py runserver

# Run Tailwind in watch mode (in another terminal, needed for CSS hot-reload)
python manage.py tailwind start
```

## Development Commands

```bash
python manage.py runserver          # Dev server at http://127.0.0.1:8000
python manage.py tailwind start     # Tailwind watch mode (CSS hot-reload)
python manage.py tailwind build     # Build Tailwind for production
python manage.py migrate            # Apply DB migrations
python manage.py makemigrations     # Create new migration after model changes
python manage.py collectstatic      # Collect static files for production
```

## Architecture

**Entry points:**
- `config/urls.py` — URL routing (root → dashboard redirect, auth URLs, scheduler URLs)
- `config/settings.py` — Django configuration; reads from `.env` via python-dotenv
- `manage.py` — Django CLI

**Main app: `scheduler/`**
- `models.py` — `ScheduleSession` (one per user per brain-dump) + `Task` (individual scheduled item)
- `views.py` — `dashboard`, `generate_schedule` (POST), `toggle_task` (POST/AJAX), `reshuffle` (POST)
- `urls.py` — `/dashboard/`, `/generate/`, `/task/<id>/toggle/`, `/reshuffle/<session_id>/`
- `services/ai_service.py` — GPT-4o wrapper; parses raw text → structured task JSON list
- `services/ocr_service.py` — Pillow + pytesseract; image → extracted text
- `services/scheduler_service.py` — Pure-Python scheduling algorithm; fits tasks into free time slots

**Template system:**
- `templates/base.html` — base layout with Tailwind navbar (auth-aware), messages block
- `templates/registration/login.html` — standalone login page (no base inheritance)
- `templates/scheduler/dashboard.html` — main page: brain dump form + schedule timeline
- `theme/` — django-tailwind app; source: `theme/static_src/src/styles.css`

**Styling:**
- Source: `theme/static_src/src/styles.css` (Tailwind directives)
- Output: `theme/static/css/dist/styles.css` (built; must rebuild after template changes)
- `django-browser-reload` for hot-reload during development

**Task JSON schema** (what GPT outputs, what the scheduler consumes):
```json
{
  "title": "string",
  "duration_minutes": 60,
  "fixed_time": "HH:MM or null",
  "priority": "high | medium | low",
  "notes": "string"
}
```

## Environment Variables (`.env`)

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for dev, `False` for prod |
| `ALLOWED_HOSTS` | Comma-separated hosts for production |
| `OPENAI_API_KEY` | Required for AI parsing feature |

## Database

SQLite (`db.sqlite3`) for development. `psycopg2-binary` installed for a PostgreSQL migration when deploying to Railway.

## Production

Gunicorn + Whitenoise already installed. For Railway deployment:
1. Set `DEBUG=False`, `ALLOWED_HOSTS=your-domain.railway.app`
2. Set a strong `SECRET_KEY`
3. Switch `DATABASES` in settings to PostgreSQL using `DATABASE_URL`
4. Run `python manage.py collectstatic`

## Settings Notes

- `SECRET_KEY` reads from `.env` (falls back to insecure default for local dev only)
- `LOGIN_URL = '/auth/login/'`, `LOGIN_REDIRECT_URL = '/dashboard/'`
- `MEDIA_ROOT = BASE_DIR / 'media'` — uploaded images stored here
