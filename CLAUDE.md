# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Secretary is a Django web application — "Your intelligent daily planner." It is a hackathon project currently in early scaffolding stage, with navigation stubs for Dashboard, Schedule, and Auth but no business logic implemented yet.

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

# Build Tailwind CSS for production
python manage.py tailwind build

# Collect static files for production
python manage.py collectstatic
```

There is no `requirements.txt` — dependencies live in `venv/`. To regenerate: `pip freeze > requirements.txt`.

## Architecture

**Entry points:**
- `config/urls.py` — all URL routing; the home view is currently defined inline here
- `config/settings.py` — Django configuration (SQLite, DEBUG=True, hardcoded SECRET_KEY — not production-ready)
- `manage.py` — Django CLI

**Template system:**
- `templates/base.html` — base layout with Tailwind-styled navbar (Dashboard, Schedule, Logout stubs)
- `templates/home.html` — homepage placeholder; extends base

**Styling:**
- `theme/` is a Django app dedicated to Tailwind CSS via `django-tailwind`
- Source: `theme/static_src/src/styles.css` (Tailwind directives)
- Output: `theme/static/css/dist/styles.css` (built/minified)
- `django-browser-reload` is installed for hot-reload during development

**Database:** SQLite (`db.sqlite3`) for development; `psycopg2-binary` is installed for a planned PostgreSQL migration.

**Production stack:** Gunicorn (WSGI server) + Whitenoise (static files) are already installed.

## Settings Notes

- `SECRET_KEY` is hardcoded in `config/settings.py` — move to `.env` before any deployment
- `ALLOWED_HOSTS = []` must be populated before deployment
- `INTERNAL_IPS = ['127.0.0.1']` enables `django-browser-reload` locally
- `TAILWIND_APP_NAME = 'theme'` ties the theme app to the tailwind management commands
