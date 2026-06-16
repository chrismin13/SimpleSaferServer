from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HEALTHCHECKS_TIMEOUT_SECONDS = 10


class HealthchecksPingError(RuntimeError):
    """Raised when a configured Healthchecks.io ping could not be sent."""


def normalize_healthchecks_ping_url(value) -> str:
    """Return a safe optional Healthchecks.io ping URL."""
    if value is None:
        return ""
    url = str(value).strip()
    if not url:
        return ""
    if any(character.isspace() for character in url):
        raise ValueError("Healthchecks success ping URL must not contain spaces.")
    if len(url) > 2048:
        raise ValueError("Healthchecks success ping URL is too long.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Healthchecks success ping URL must start with http:// or https://.")
    return url


def ping_healthchecks_url(url: str, *, timeout: int = HEALTHCHECKS_TIMEOUT_SECONDS) -> None:
    """Ping a Healthchecks.io URL without putting the URL in a command line."""
    normalized_url = normalize_healthchecks_ping_url(url)
    if not normalized_url:
        return

    request = Request(
        normalized_url,
        method="GET",
        headers={"User-Agent": "SimpleSaferServer cloud-backup"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            if status >= 400:
                raise HealthchecksPingError(f"Healthchecks.io returned HTTP {status}.")
    except HTTPError as exc:
        raise HealthchecksPingError(f"Healthchecks.io returned HTTP {exc.code}.") from exc
    except URLError as exc:
        # Do not include the target URL here; the path usually contains the
        # Healthchecks check UUID and can end up in service logs.
        raise HealthchecksPingError(f"Healthchecks.io request failed: {exc.reason}") from exc
