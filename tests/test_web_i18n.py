from simple_safer_server.web.i18n import gettext


def test_gettext_returns_english_text_without_catalogs():
    assert gettext("Storage is ready.") == "Storage is ready."
