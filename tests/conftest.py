import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_appdata(tmp_path, monkeypatch):
    """Keep every test away from the real %APPDATA%."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    yield tmp_path


@pytest.fixture(scope="session")
def app():
    """One QApplication for the whole test session (Qt dislikes re-creating it)."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication
    instance = QApplication.instance() or QApplication([])
    yield instance
