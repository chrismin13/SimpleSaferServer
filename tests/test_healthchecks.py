from urllib.error import HTTPError, URLError

import pytest

from simple_safer_server.services.healthchecks import (
    HealthchecksPingError,
    normalize_healthchecks_ping_url,
    ping_healthchecks_url,
)


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def getcode(self):
        return self.status


def test_normalize_healthchecks_ping_url_allows_blank_optional_value():
    assert normalize_healthchecks_ping_url(None) == ""
    assert normalize_healthchecks_ping_url("  ") == ""


def test_normalize_healthchecks_ping_url_requires_http_url_without_spaces():
    with pytest.raises(ValueError, match="http:// or https://"):
        normalize_healthchecks_ping_url("ftp://example.test/check")

    with pytest.raises(ValueError, match="spaces"):
        normalize_healthchecks_ping_url("https://hc-ping.com/check with space")


def test_ping_healthchecks_url_sends_get_without_leaking_url_in_errors(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse(200)

    monkeypatch.setattr("simple_safer_server.services.healthchecks.urlopen", fake_urlopen)

    ping_healthchecks_url("https://hc-ping.com/secret-check-id")

    assert calls[0][0].full_url == "https://hc-ping.com/secret-check-id"
    assert calls[0][0].get_method() == "GET"


def test_ping_healthchecks_url_reports_http_status_without_url(monkeypatch):
    def fake_urlopen(_request, timeout):
        _ = timeout
        raise HTTPError(
            "https://hc-ping.com/secret-check-id",
            500,
            "server error",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("simple_safer_server.services.healthchecks.urlopen", fake_urlopen)

    with pytest.raises(HealthchecksPingError) as exc_info:
        ping_healthchecks_url("https://hc-ping.com/secret-check-id")

    message = str(exc_info.value)
    assert "HTTP 500" in message
    assert "secret-check-id" not in message


def test_ping_healthchecks_url_reports_network_error_without_url(monkeypatch):
    def fake_urlopen(_request, timeout):
        _ = timeout
        raise URLError("connection refused")

    monkeypatch.setattr("simple_safer_server.services.healthchecks.urlopen", fake_urlopen)

    with pytest.raises(HealthchecksPingError) as exc_info:
        ping_healthchecks_url("https://hc-ping.com/secret-check-id")

    message = str(exc_info.value)
    assert "connection refused" in message
    assert "secret-check-id" not in message
