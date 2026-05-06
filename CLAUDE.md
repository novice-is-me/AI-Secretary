# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary is a Django web application — "Your intelligent daily planner." Users type or photograph their tasks, the backend parses them into structured items with priority and duration, then generates a time-blocked schedule. The current AI pipeline is mock-based (regex + optional OCR), with no external LLM integration yet.

## Development Commands

```bash
# Activate virtual environment (Windows)
venv\Scripts\activate

# Run development server
python manage.py runserver

# Run Tailwind CSS in watch mode (required for CSS changes to take effect)
python manage.py tailwind start

# Apply database migrations
python manage.py migrate

# Run all tests
python manage.py test

# Run a single test class or method
python manage.py test core.tests.AuthFlowTests
python manage.py test core.tests.MockAIPipelineTests.test_parse_text_returns_tasks

# Build Tailwind CSS for production
python manage.py tailwind build
```

`requirements.txt` exists but is incomplete — gunicorn, whitenoise, psycopg2-binary, and django-browser-reload are installed in `venv/` but not listed. Regenerate with `pip freeze > requirements.txt` if needed.

## Architecture

**URL routing** splits across two files:
- `config/urls.py` — page views: `/`, `/login/`, `/logout/`, `/register/`, `/huddle/`, `/timeline/`, `/profile/`
- `core/urls.py` — API endpoints: `/parse-text/`, `/upload-image/`, `/generate-schedule/`

All view logic lives in `core/views.py`. Auth uses Django's built-in `User` model with a `UserProfile` OneToOneField extension.

**Data model** (`core/models.py`):
- `UserProfile.parsed_tasks` — JSONField storing task dicts `{id, title, priority, priority_key, duration_minutes, time}`
- `UserProfile.schedule` — JSONField storing schedule items (same shape plus `start_time`, `end_time`)
- `UserProfile.avatar_data` — base64-encoded profile image stored directly in the DB

**AI pipeline** (all in `core/views.py`, no external API calls):
1. `parse_text` — regex keyword matching for priority, duration, and time hints; splits on newlines/semicolons
2. `upload_image` — pytesseract OCR if available, else returns hardcoded fallback text
3. `generate_schedule` — sorts tasks (pinned explicit times first, then high→medium→low priority), allocates consecutive blocks with 10-min breaks, persists to `UserProfile`

**Template system:**
- `templates/base_auth.html` — base layout; loads Tailwind CSS and Google Fonts (Plus Jakarta Sans, Material Symbols); all page templates extend this
- `templates/components/` — reusable partials (navbars, buttons, cards, orb, timeline items)
- `base.html` and `home.html` are legacy and not actively used

**JavaScript:** All JS is inline in templates (no separate `.js` files, no framework). `huddle.html` stores chat history in `localStorage` under key `sanctuary_huddle_messages` and calls the three API endpoints via `fetch` with CSRF token from cookie.

**Styling:**
- `theme/` is a Django app dedicated to Tailwind CSS via `django-tailwind`
- Source: `theme/static_src/src/styles.css`
- Output: `theme/static/css/dist/styles.css` (built/minified)
- `django-browser-reload` provides hot-reload in development

**Settings notes:**
- `SECRET_KEY` is hardcoded — move to `.env` before deployment
- `ALLOWED_HOSTS = []` — must be populated before deployment
- `LOGIN_REDIRECT_URL = '/huddle/'`, `LOGOUT_REDIRECT_URL = '/'`
