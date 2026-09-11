# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""UNO component entry point of LibreLex-IT: registers the sidebar panel factory.

LibreOffice's pythonloader executes this file; the sibling package ``librelex_ext``
holds the real code. The package directory is put on sys.path explicitly because
the loader's own sys.path handling differs between versions.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import unohelper  # noqa: E402

from librelex_ext import IMPLEMENTATION_NAME  # noqa: E402
from librelex_ext.panel import PanelFactory  # noqa: E402

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    PanelFactory, IMPLEMENTATION_NAME, ("com.sun.star.ui.UIElementFactory",))
