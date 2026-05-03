"""WSGI entrypoint for hosted deployments."""

from simple_safer_server.app_factory import create_app

app, socketio = create_app()
