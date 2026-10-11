"""The "Controller type" row on the Settings page, with real Qt widgets
(offscreen) and `fake_driver` standing in for vgamepad and the driver."""
import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from controller_models import MODELS  # noqa: E402


@pytest.fixture
def open_window(app, tmp_path, fake_driver):
    from settings_manager import SettingsManager
    from profile_manager import ProfileManager
    from engine import Engine
    from ui.main_window import MainWindow

    windows = []

    def make():
        settings = SettingsManager(str(tmp_path / "settings.json"))
        engine = Engine(settings, ProfileManager(str(tmp_path / "profiles")))
        win = MainWindow(engine)
        windows.append(win)
        engine.start()
        win.sync_from_engine()
        win.resize(1200, 800)
        win.show()
        win.go_to("settings")
        QApplication.processEvents()
        return win, win._pages["settings"]

    yield make
    for win in windows:
        win.quit_app()
        # Several tests here open more than one window. Destroy them for real,
        # or every later test in the session pays for the widgets left behind.
        win.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def _choose(combo, model_id):
    """What clicking an entry of the combo box does."""
    index = combo.findData(model_id)
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    QApplication.processEvents()


def _enabled(combo):
    return [combo.model().item(i).isEnabled() for i in range(combo.count())]


def test_selecting_a_type_saves_applies_and_shows_it(open_window, fake_driver):
    fake_driver.driver["max"] = 5
    win, page = open_window()
    combo = page.model_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [m.label for m in MODELS]
    assert all(_enabled(combo)) and combo.currentData() == "xbox360"
    assert page.status_msg.text() == "Windows sees an Xbox 360 Controller."

    _choose(combo, "xbox_series")
    assert win.settings.get("controller", "model") == "xbox_series"
    assert [p[3] for p in fake_driver.plugs()] == [0x028E, 0x0B12] and win.engine.connected
    assert combo.currentData() == "xbox_series"
    assert page.status_msg.text() == "Windows sees an Xbox Series X|S Controller."
    assert "Xbox Series X|S Controller" in page.model_note.text()
    assert "Xbox Series X|S Controller" in win.status_pill.toolTip()
    assert "Controller type: Xbox Series X|S Controller" in win._pages["about"].diagnostics()
    assert not win.grab().isNull()

    _choose(combo, "xbox_series")                 # same entry again: no re-plug
    assert len(fake_driver.plugs()) == 2


def test_saved_type_is_shown_and_used_on_the_next_start(open_window, fake_driver):
    fake_driver.driver["max"] = 5
    _, page = open_window()
    _choose(page.model_combo, "xbox_one")

    win, page = open_window()                     # same settings file
    assert fake_driver.plugs()[-1] == ("plug", "_ModelGamepad", 0x045E, 0x02FF)
    assert page.model_combo.currentData() == "xbox_one"
    assert page.status_msg.text() == "Windows sees an Xbox One Controller."


def test_newer_types_are_disabled_with_the_stock_driver(open_window, fake_driver):
    win, page = open_window()
    combo = page.model_combo
    assert combo.currentData() == "xbox360"
    assert _enabled(combo) == [True] + [False] * (len(MODELS) - 1)
    assert all(combo.itemText(i).endswith("not available") for i in range(1, combo.count()))
    assert "can only present an Xbox 360" in page.model_note.text()

    page._set_model("xbox_series")                # cannot be forced through either
    assert win.settings.get("controller", "model") == "xbox360" and len(fake_driver.plugs()) == 1
    assert not win.grab().isNull()


def test_types_become_available_after_installing_the_driver_and_reconnecting(open_window, fake_driver):
    _, page = open_window()
    assert _enabled(page.model_combo)[1:] == [False] * (len(MODELS) - 1)
    fake_driver.driver["max"] = 5                 # the user installs the bundled driver...
    page._reconnect()                             # ...and presses Reconnect
    QApplication.processEvents()
    assert all(_enabled(page.model_combo))
    _choose(page.model_combo, "xbox_series")
    assert fake_driver.plugs()[-1][3] == 0x0B12


def test_saved_type_the_driver_no_longer_supports(open_window, fake_driver):
    fake_driver.driver["max"] = 5
    _, page = open_window()
    _choose(page.model_combo, "xbox_series")

    fake_driver.driver["max"] = 0                 # back on the stock driver
    win, page = open_window()
    assert fake_driver.plugs()[-1] == ("plug", "VX360Gamepad", 0x045E, 0x028E)
    assert page.model_combo.currentData() == "xbox360"
    text = page.model_note.text()
    assert "can only present an Xbox 360" in text and "Xbox Series X|S Controller" in text
    assert page.status_msg.text() == "Windows sees an Xbox 360 Controller."


def test_failure_to_recreate_the_controller_is_shown(open_window, fake_driver):
    fake_driver.driver["max"] = 5
    win, page = open_window()
    fake_driver.fail = True
    _choose(page.model_combo, "xbox_one_s")
    assert not win.engine.connected
    assert win.settings.get("controller", "model") == "xbox_one_s"
    assert page.status_pill._text == "Not connected"
    fake_driver.fail = False
    page._reconnect()
    assert win.engine.connected and fake_driver.plugs()[-1][3] == 0x02EA
