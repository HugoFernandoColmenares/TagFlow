"""Fixtures de Qt en modo sin pantalla."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    application = QApplication.instance() or QApplication([])
    yield application
