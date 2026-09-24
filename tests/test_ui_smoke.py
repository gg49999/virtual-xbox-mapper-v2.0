"""End-to-end smoke tests for the Qt UI (runs headless via QT_QPA_PLATFORM=offscreen)."""
import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt, QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402




@pytest.fixture
def window(app, tmp_path):
    from settings_manager import SettingsManager
    from profile_manager import ProfileManager
    from engine import Engine
    from ui.main_window import MainWindow

    settings = SettingsManager(str(tmp_path / "settings.json"))
    profiles = ProfileManager(str(tmp_path / "profiles"))
    engine = Engine(settings, profiles)
    win = MainWindow(engine)
    engine.start()
    win.sync_from_engine()
    win.resize(1200, 800)
    win.show()
    yield win
    win.quit_app()


def test_every_page_renders(window):
    for key in ("mapping", "tuning", "test", "profiles", "settings", "about"):
        window.go_to(key)
        window._refresh_live()
        assert window.current_page() is window._pages[key]
        assert not window.grab().isNull()


def test_theme_switch_and_compact_nav(window):
    window.settings.set("appearance", "theme", "light")
    window.apply_theme()
    window.resize(900, 620)
    QApplication.processEvents()
    assert window.nav.buttons["mapping"].compact
    window.settings.set("appearance", "diagram_style", "photo")
    window.apply_diagram_style()
    assert not window.grab().isNull()


def test_binding_dialog_captures_key(window):
    from ui.binding_dialog import BindingDialog
    dlg = BindingDialog("A", lambda code: ["B"] if code == "space" else [], parent=window)

    def press():
        QTest.keyClick(dlg, Qt.Key.Key_Space)
        assert dlg.box.code == "space"
        assert dlg.conflict_area.isVisible()
        QTest.keyClick(dlg, Qt.Key.Key_Return)

    QTimer.singleShot(50, press)
    assert dlg.exec()
    assert dlg.result_code == "space" and dlg.replace_conflicts


def test_binding_edit_updates_engine(window):
    engine = window.engine
    page = window._pages["mapping"]
    page.select_target("X")
    engine.profile.bind("X", "g")
    engine.bindings_edited()
    assert "g" in engine.profile.inputs_for("X")
    page.remove_input("X", "g")
    assert "g" not in engine.profile.inputs_for("X")
    reloaded = engine.profiles.load(engine.profile.name)
    assert "g" not in reloaded.inputs_for("X")


def test_emulation_toggle_and_capture_guard(window):
    engine = window.engine
    engine.set_emulation(False)
    assert not window.emulation_toggle.isChecked()
    engine.set_capture(True)          # refused while emulation is off
    assert not engine.captured
    engine.set_emulation(True)
    assert window.emulation_toggle.isChecked()
