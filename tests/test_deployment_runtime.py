import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REMOVED_SOCKET_RUNTIME_PACKAGES = {
    "eventlet",
    "flask-socketio",
    "python-engineio",
    "python-socketio",
}


def _dependency_name(requirement: str) -> str:
    return re.split(r"[<>=!~;\\[]", requirement, maxsplit=1)[0].strip().lower()


def test_runtime_dependencies_do_not_include_socketio_or_eventlet_packages():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = {
        _dependency_name(requirement) for requirement in pyproject["project"]["dependencies"]
    }

    lockfile = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_packages = {package["name"].lower() for package in lockfile["package"]}

    # Socket.IO is not used by the app today, so these packages only add deploy risk.
    assert runtime_dependencies.isdisjoint(REMOVED_SOCKET_RUNTIME_PACKAGES)
    assert locked_packages.isdisjoint(REMOVED_SOCKET_RUNTIME_PACKAGES)


def test_deployment_commands_use_threaded_gunicorn_wsgi_entrypoint():
    railway_command = json.loads((REPO_ROOT / "railway.json").read_text(encoding="utf-8"))[
        "deploy"
    ]["startCommand"]
    nixpacks_command = tomllib.loads((REPO_ROOT / "nixpacks.toml").read_text(encoding="utf-8"))[
        "start"
    ]["cmd"]
    procfile_command = (REPO_ROOT / "Procfile").read_text(encoding="utf-8").strip()
    systemd_unit = (REPO_ROOT / "simple_safer_server_web.service").read_text(encoding="utf-8")

    commands = [railway_command, nixpacks_command, procfile_command, systemd_unit]

    for command in commands:
        assert "eventlet" not in command.lower()
        assert "--worker-class gthread" in command
        assert "simple_safer_server.wsgi:app" in command


def test_app_and_frontend_do_not_use_socketio():
    searchable_paths = [
        *Path(REPO_ROOT / "simple_safer_server").rglob("*"),
        *Path(REPO_ROOT / "static").rglob("*"),
        *Path(REPO_ROOT / "templates").rglob("*"),
    ]
    searchable_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in searchable_paths
        if path.is_file() and path.suffix in {".html", ".js", ".py"}
    ).lower()

    # If real-time browser updates are added later, choose a supported runtime path with it.
    assert "flask_socketio" not in searchable_text
    assert "socketio" not in searchable_text
    assert "socket.io" not in searchable_text
