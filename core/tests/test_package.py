# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import librelex_core


def test_version_and_protocol():
    assert librelex_core.__version__ == "0.1.0"
    assert librelex_core.PROTOCOL_VERSION == 1
