web: python manage.py migrate --run-syncdb && python manage.py collectstatic --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT
