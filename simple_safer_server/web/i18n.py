from __future__ import annotations


def gettext(message: str) -> str:
    """Return UI text through a gettext-shaped function.

    English is the only shipped language for now. Keeping this tiny shim lets
    templates and Python code use the normal gettext call shape without adding
    Babel catalogs, compile steps, or a JavaScript translation build.
    """
    return message
