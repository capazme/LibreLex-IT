# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""LibreLex-IT LibreOffice extension (stdlib + UNO only)."""
__version__ = "0.1.0"
PROTOCOL_VERSION = 1          # must equal librelex_core.PROTOCOL_VERSION
EXTENSION_ID = "org.librelex.extension"
IMPLEMENTATION_NAME = "org.librelex.extension.PanelFactory"


class DocumentActionError(Exception):
    """A document action failed; reported to the core as doc_result ok=false.

    Defined here, in the only module every part of the extension already imports, so that
    ``document.py`` (UNO) and ``session.py`` (no UNO) share one class: ``session`` checks it
    with ``isinstance`` to send the adapter's plain Italian message to the core unchanged.
    """
