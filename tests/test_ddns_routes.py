from pathlib import Path
from tempfile import mkdtemp
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from simple_safer_server.core.module_lifecycle import apply_module
from simple_safer_server.modules.ddns.module import create_module as create_ddns_module
from simple_safer_server.modules.ddns.routes import ddns


def _tool_path(name):
    if name == "update-ca-certificates":
        return "/usr/sbin/update-ca-certificates"
    return None


def _app_with_services(services):
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    app.extensions["simple_safer_server"] = services
    app.context_processor(
        lambda: {
            "browser_title": lambda page_name: page_name,
            "runtime_mode": "fake" if services.runtime.is_fake else "prod",
            "sidebar_nav_items": [],
            "default_mount_point": "/media/backup",
            "is_admin": True,
        }
    )
    app.add_url_rule("/logout", "logout", lambda: "logout")
    app.register_blueprint(ddns)
    return app


def _admin_post(app, path, json):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.post(path, json=json)


def _services(*, fake=True):
    return SimpleNamespace(
        runtime=SimpleNamespace(
            data_dir=Path(mkdtemp(prefix="sss-ddns-test-")),
            is_fake=fake,
        ),
        ddns_service=MagicMock(),
    )


def _admin_get(app, path):
    client = app.test_client()
    with client.session_transaction() as session:
        session["username"] = "admin"
    with patch(
        "simple_safer_server.services.user_manager.UserManager",
        return_value=SimpleNamespace(is_admin=lambda username: username == "admin"),
    ):
        return client.get(path)


def test_ddns_page_renders_module_owned_help():
    app = _app_with_services(_services(fake=True))

    response = _admin_get(app, "/ddns")

    assert response.status_code == 200
    assert b"<wa-callout" in response.data
    assert b"module-help-band" in response.data
    assert b"DDNS keeps a hostname pointed at the server" in response.data
    assert b"DDNS stores provider settings in SSS config" in response.data
    assert b"Valid DDNS credentials can update live DNS records" in response.data
    assert b'data-module-help-key="duckdns_domain"' in response.data
    assert b"Enter only the DuckDNS subdomain" in response.data
    assert b'data-module-help-key="cloudflare_proxy"' in response.data
    assert b"Leave proxying off for normal DNS" in response.data
    assert b'id="ddns-copy"' in response.data
    assert b"Connection error while loading DDNS configuration." in response.data
    assert b"Run DDNS Checks" in response.data


def test_ddns_page_hides_fake_mode_warning_outside_fake_mode():
    app = _app_with_services(_services(fake=False))

    response = _admin_get(app, "/ddns")

    assert response.status_code == 200
    assert b"module-help-band" in response.data
    assert b"Valid DDNS credentials can update live DNS records" not in response.data


def test_ddns_config_write_requires_module_apply():
    app = _app_with_services(_services())

    response = _admin_post(app, "/api/ddns/config", {"duckdns": {"enabled": False}})

    assert response.status_code == 409
    assert response.get_json()["type"].endswith("#module-setup-required")


def test_ddns_config_write_uses_service_after_module_apply():
    services = _services()
    services.ddns_service.save_config.return_value = "DDNS configuration saved."
    with patch("simple_safer_server.core.module_checks.shutil.which", _tool_path):
        apply_module(create_ddns_module(), services.runtime)
    app = _app_with_services(services)

    response = _admin_post(app, "/api/ddns/config", {"duckdns": {"enabled": False}})

    assert response.status_code == 200
    services.ddns_service.save_config.assert_called_once_with({"duckdns": {"enabled": False}})
