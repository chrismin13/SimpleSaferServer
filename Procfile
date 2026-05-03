web: gunicorn --worker-class gthread --threads ${WEB_THREADS:-4} -w 1 --bind 0.0.0.0:$PORT simple_safer_server.wsgi:app
