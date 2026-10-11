"""Controller type selection: the model table, detection of what the
installed driver supports, the rule that newer models are never requested
from a driver that doesn't know them, and the controller/engine behaviour.

The virtual-controller driver itself is not involved: `fake_driver` (see
conftest.py) stands in for vgamepad and for the installed driver."""
import os
import re
import sys

import pytest

import controller_models as cm
import virtual_controller
from settings_manager import DEFAULT_SETTINGS, SettingsManager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER_DIR = os.path.join(ROOT, "driver", "ViGEmBus")
ALL_IDS = tuple(m.id for m in cm.MODELS)


def _driver_binary(max_model=None, padding=4096):
    """Bytes shaped like a driver file: arbitrary content around a UTF-16
    version-resource string, the way the marker really appears."""
    body = os.urandom(padding).replace(b"V\x00i\x00G\x00", b"X\x00x\x00x\x00")
    if max_model is None:
        return body + "ProductVersion\0\0001.22.0.0\0".encode("utf-16-le") + body
    key = "XboxModels\0".encode("utf-16-le") + b"\x00\x00"
    return body + key + f"{cm.DRIVER_MARKER}{max_model}\0".encode("utf-16-le") + body


# ---- the table -----------------------------------------------------------------

def test_model_table_is_consistent():
    assert len(set(ALL_IDS)) == len(ALL_IDS)
    assert cm.MODELS[0].id == cm.DEFAULT_MODEL_ID and cm.MODELS[0].driver_model == 0
    assert [m.driver_model for m in cm.MODELS] == list(range(len(cm.MODELS)))
    assert len({(m.vendor_id, m.product_id) for m in cm.MODELS}) == len(cm.MODELS)
    assert all(m.label and m.short_label and m.summary for m in cm.MODELS)
    assert cm.DEFAULT_MODEL_ID == DEFAULT_SETTINGS["controller"]["model"]


def test_unknown_model_ids_fall_back_to_default():
    assert cm.get_model("xbox_series").product_id == 0x0B12
    for bad in ("", "playstation", None, 4, ["xbox_series"]):
        assert cm.get_model(bad).id == cm.DEFAULT_MODEL_ID


@pytest.mark.skipif(not os.path.isdir(DRIVER_DIR), reason="bundled driver sources not present")
def test_model_table_matches_bundled_driver_sources():
    def read(name):
        with open(os.path.join(DRIVER_DIR, "sys", name), encoding="utf-8") as f:
            return f.read()

    hpp, cpp, rc = read("XboxModels.hpp"), read("XboxModels.cpp"), read("ViGEmBus.rc")
    enum = {name: int(value) for name, value in re.findall(r"\b(XboxModel\w+) = (\d+)", hpp)}
    assert enum["XboxModel360"] == 0
    rows = re.findall(r"Targets::(XboxModel\w+),\s*MicrosoftVendorId,\s*(0x[0-9A-Fa-f]+),", cpp)
    driver_table = {enum[name]: int(pid, 16) for name, pid in rows}
    assert "constexpr USHORT MicrosoftVendorId = 0x045E;" in cpp

    app_table = {m.driver_model: m.product_id for m in cm.MODELS if m.driver_model}
    assert driver_table == app_table
    assert all(m.vendor_id == 0x045E for m in cm.MODELS)

    marker = re.search(re.escape(cm.DRIVER_MARKER) + r"(\d+)", rc)
    assert marker, "the driver's version resource must carry the model marker"
    assert int(marker.group(1)) == max(enum.values()) == max(app_table)


# ---- driver detection ------------------------------------------------------------

def test_marker_parsing():
    assert cm.parse_driver_marker(_driver_binary(5)) == 5
    assert cm.parse_driver_marker(_driver_binary(12)) == 12
    assert cm.parse_driver_marker(_driver_binary(None)) == 0          # stock driver
    assert cm.parse_driver_marker(b"") == 0
    assert cm.parse_driver_marker(cm.DRIVER_MARKER.encode("utf-16-le")) == 0            # cut off after the marker
    assert cm.parse_driver_marker((cm.DRIVER_MARKER + "x5").encode("utf-16-le")) == 0   # not a number
    assert cm.parse_driver_marker((cm.DRIVER_MARKER + "5").encode("ascii")) == 0        # wrong encoding
    assert cm.parse_driver_marker((cm.DRIVER_MARKER + "123456").encode("utf-16-le")) == 1234


def test_read_driver_max_model(tmp_path):
    stock, capable, future = tmp_path / "stock.sys", tmp_path / "capable.sys", tmp_path / "future.sys"
    stock.write_bytes(_driver_binary(None))
    capable.write_bytes(_driver_binary(5))
    future.write_bytes(_driver_binary(42))
    missing = str(tmp_path / "missing.sys")

    assert cm.read_driver_max_model([str(stock)]) == 0
    assert cm.read_driver_max_model([str(capable)]) == 5
    assert cm.read_driver_max_model([missing]) == 0
    assert cm.read_driver_max_model([missing, str(capable)]) == 5       # second location is tried
    assert cm.read_driver_max_model([str(stock), str(capable)]) == 0    # first file found is the installed one
    assert cm.read_driver_max_model([str(future)]) == 5                 # never more than this app knows
    assert cm.read_driver_max_model([str(tmp_path)]) == 0               # a directory, not a file
    assert cm.read_driver_max_model([]) == 0


def test_stock_driver_installer_shipped_with_the_app_has_no_marker():
    """The stock ViGEmBus setup bundled in installer/ must never be mistaken
    for the build with model support."""
    for name in os.listdir(os.path.join(ROOT, "installer")):
        if name.lower().startswith("vigembus") and name.lower().endswith(".exe"):
            with open(os.path.join(ROOT, "installer", name), "rb") as f:
                assert cm.parse_driver_marker(f.read()) == 0


def test_driver_file_candidates_follow_system_root(monkeypatch):
    monkeypatch.setenv("SystemRoot", os.path.join("X:", "Win"))
    first, second = cm.driver_file_candidates()
    assert first.endswith(os.path.join("System32", "drivers", "ViGEmBus.sys")) and first.startswith("X:")
    assert second.endswith(os.path.join("Sysnative", "drivers", "ViGEmBus.sys"))


def test_default_model_read_is_harmless_off_windows():
    if not sys.platform.startswith("win"):
        assert cm.read_driver_default_model() == 0


# ---- the gate ----------------------------------------------------------------------

def test_supported_models_depend_on_driver():
    assert cm.supported_model_ids(0) == ("xbox360",)
    assert cm.supported_model_ids(1) == ("xbox360", "xbox_one")
    assert cm.supported_model_ids(5) == ALL_IDS
    assert cm.supported_model_ids(-3) == ("xbox360",)


def test_newer_models_are_never_requested_from_a_driver_without_support():
    for model in cm.MODELS:
        assert cm.resolve_request(model.id, 0).id == "xbox360"
        assert cm.resolve_request(model.id, 5).id == model.id
    assert cm.resolve_request("xbox_series", 3).id == "xbox360"   # driver knows some models, not this one
    assert cm.resolve_request("nonsense", 5).id == "xbox360"


def test_effective_model():
    assert cm.effective_model("xbox_series", 5, 0).id == "xbox_series"
    assert cm.effective_model("xbox_series", 0, 0).id == "xbox360"
    assert cm.effective_model("xbox360", 5, 0).id == "xbox360"
    assert cm.effective_model("xbox360", 5, 4).id == "xbox_series"       # driver-wide default replaces Xbox 360
    assert cm.effective_model("xbox_one", 5, 4).id == "xbox_one"         # explicit choice wins over it
    assert cm.effective_model("xbox360", 0, 4).id == "xbox360"           # stock driver ignores the registry value
    assert cm.effective_model("xbox360", 5, 99).id == "xbox360"          # out of range default is ignored
    assert cm.effective_model("xbox_series", 3, 2).id == "xbox_one_s"    # unsupported choice falls back like Xbox 360


# ---- settings -----------------------------------------------------------------------

def test_settings_default_migration_and_validation(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"controller": {"tick_rate_hz": 250}}', encoding="utf-8")   # file from before the option
    settings = SettingsManager(str(path))
    assert settings.get("controller", "model") == "xbox360"
    assert settings.get("controller", "tick_rate_hz") == 250
    settings.set("controller", "model", "xbox_series")
    assert SettingsManager(str(path)).get("controller", "model") == "xbox_series"

    path.write_text('{"controller": {"model": "dreamcast"}}', encoding="utf-8")  # hand-edited nonsense
    assert SettingsManager(str(path)).get("controller", "model") == "xbox360"
    path.write_text('{"controller": {"model": 4}}', encoding="utf-8")
    assert SettingsManager(str(path)).get("controller", "model") == "xbox360"


def test_packaged_default_settings_include_the_model():
    import json
    with open(os.path.join(ROOT, "config", "default_settings.json"), encoding="utf-8") as f:
        assert json.load(f)["controller"]["model"] == cm.DEFAULT_MODEL_ID


# ---- VirtualController ----------------------------------------------------------------

def test_without_vgamepad_only_xbox360_is_offered():
    vc = virtual_controller.VirtualController()
    if not virtual_controller.VGAMEPAD_AVAILABLE:
        vc.set_model("xbox_series")
        assert vc.supported_models == ("xbox360",) and vc.model == "xbox360"
        assert vc.requested_model == "xbox_series"


def test_stock_driver_only_ever_gets_xbox360_ids(fake_driver):
    vc = virtual_controller.VirtualController()
    vc.set_model("xbox_series")
    assert vc.supported_models == ("xbox360",) and vc.model == "xbox360"
    vc.connect()
    assert fake_driver.plugs() == [("plug", "VX360Gamepad", 0x045E, 0x028E)]
    assert not [e for e in fake_driver.events if e[0].startswith("set_")]
    assert vc.model == "xbox360" and vc.requested_model == "xbox_series"
    vc.disconnect()


def test_capable_driver_gets_the_model_ids_before_plugging_in(fake_driver):
    fake_driver.driver["max"] = 5
    vc = virtual_controller.VirtualController()
    vc.set_model("xbox_series")
    assert vc.supported_models == ALL_IDS
    vc.connect()
    assert fake_driver.events[:3] == [
        ("set_vid", 0x045E), ("set_pid", 0x0B12), ("plug", "_ModelGamepad", 0x045E, 0x0B12),
    ]
    assert vc.is_connected and vc.model == "xbox_series"
    vc.set_button(virtual_controller.ControllerButton.A, True)
    assert fake_driver.events[-1] == ("update",)
    vc.disconnect()
    assert ("unplug", 0x0B12) in fake_driver.events and not vc.is_connected


def test_every_model_is_requested_with_its_own_ids(fake_driver):
    fake_driver.driver["max"] = 5
    for model in cm.MODELS:
        vc = virtual_controller.VirtualController()
        vc.set_model(model.id)
        vc.connect()
        assert fake_driver.plugs()[-1][2:] == (model.vendor_id, model.product_id)
        assert vc.model == model.id
        vc.disconnect()


def test_xbox360_takes_the_original_code_path_even_on_a_capable_driver(fake_driver):
    fake_driver.driver["max"] = 5
    vc = virtual_controller.VirtualController()
    vc.connect()
    assert fake_driver.events[0] == ("plug", "VX360Gamepad", 0x045E, 0x028E)
    assert vc.model == "xbox360"
    vc.disconnect()


def test_driver_wide_default_is_reported_when_xbox360_is_selected(fake_driver):
    fake_driver.driver.update(max=5, default=4)
    vc = virtual_controller.VirtualController()
    assert vc.model == "xbox_series" and vc.presents("xbox_one") == "xbox_one"
    vc.connect()
    assert fake_driver.plugs() == [("plug", "VX360Gamepad", 0x045E, 0x028E)]   # still asks for "no preference"
    assert vc.model == "xbox_series"
    vc.disconnect()


def test_driver_is_re_examined_on_every_connect(fake_driver):
    vc = virtual_controller.VirtualController()
    vc.set_model("xbox_one")
    vc.connect()
    assert vc.model == "xbox360"
    vc.disconnect()
    fake_driver.driver["max"] = 5               # the bundled driver got installed, then "Reconnect"
    vc.connect()
    assert fake_driver.plugs()[-1] == ("plug", "_ModelGamepad", 0x045E, 0x02FF)
    assert vc.model == "xbox_one"
    vc.disconnect()


def test_failed_connect_is_reported_and_leaves_controller_disconnected(fake_driver):
    fake_driver.driver["max"] = 5
    fake_driver.fail = True
    vc = virtual_controller.VirtualController()
    vc.set_model("xbox_series")
    with pytest.raises(virtual_controller.VirtualControllerError):
        vc.connect()
    assert not vc.is_connected and vc.last_error and vc.model == "xbox_series"
    fake_driver.fail = False
    vc.connect()
    assert vc.is_connected
    vc.disconnect()


def test_models_unavailable_without_low_level_bindings(fake_driver, monkeypatch):
    monkeypatch.setattr(virtual_controller, "_vcli", None)
    fake_driver.driver["max"] = 5
    vc = virtual_controller.VirtualController()
    vc.set_model("xbox_series")
    assert vc.supported_models == ("xbox360",)
    vc.connect()
    assert fake_driver.plugs() == [("plug", "VX360Gamepad", 0x045E, 0x028E)]
    vc.disconnect()


# ---- Engine -------------------------------------------------------------------------------

@pytest.fixture
def make_engine(app, tmp_path, fake_driver):
    from engine import Engine
    from profile_manager import ProfileManager

    engines = []

    def make(model=None):
        settings = SettingsManager(str(tmp_path / "settings.json"))
        if model:
            settings.set("controller", "model", model)
        engine = Engine(settings, ProfileManager(str(tmp_path / "profiles")))
        engines.append(engine)
        engine.messages = []
        engine.connection_changed.connect(lambda ok, text: engine.messages.append((ok, text)))
        engine.start()
        return engine

    yield make
    for engine in engines:
        engine.shutdown()


def test_engine_applies_a_new_type_by_replugging(make_engine, fake_driver):
    fake_driver.driver["max"] = 5
    engine = make_engine()
    assert fake_driver.plugs() == [("plug", "VX360Gamepad", 0x045E, 0x028E)]
    assert engine.messages[-1] == (True, "Virtual Xbox 360 Controller connected.")

    assert engine.set_controller_model("xbox_series")
    assert [p[3] for p in fake_driver.plugs()] == [0x028E, 0x0B12]
    assert fake_driver.events.index(("unplug", 0x028E)) < fake_driver.events.index(fake_driver.plugs()[1])
    assert engine.connected and engine.controller.model == "xbox_series"
    assert engine.settings.get("controller", "model") == "xbox_series"
    assert engine.messages[-1] == (True, "Virtual Xbox Series X|S Controller connected.")

    assert engine.set_controller_model("xbox_series")          # same choice again: no pointless re-plug
    assert len(fake_driver.plugs()) == 2


def test_engine_uses_the_saved_type_for_the_first_connection(make_engine, fake_driver):
    fake_driver.driver["max"] = 5
    engine = make_engine(model="xbox_one_s")
    assert fake_driver.plugs() == [("plug", "_ModelGamepad", 0x045E, 0x02EA)]
    assert engine.controller.model == "xbox_one_s"


def test_engine_refuses_types_the_driver_cannot_present(make_engine, fake_driver):
    engine = make_engine()
    assert not engine.set_controller_model("xbox_series")
    assert engine.settings.get("controller", "model") == "xbox360"
    assert len(fake_driver.plugs()) == 1 and engine.connected


def test_engine_keeps_the_choice_when_recreating_the_controller_fails(make_engine, fake_driver):
    fake_driver.driver["max"] = 5
    engine = make_engine()
    fake_driver.fail = True
    assert not engine.set_controller_model("xbox_one")
    assert not engine.connected and engine.messages[-1][0] is False
    assert engine.settings.get("controller", "model") == "xbox_one"
    fake_driver.fail = False
    assert engine.reconnect_controller()
    assert fake_driver.plugs()[-1][3] == 0x02FF and engine.controller.model == "xbox_one"


def test_engine_does_not_replug_when_windows_would_see_the_same_controller(make_engine, fake_driver):
    fake_driver.driver.update(max=5, default=4)                 # driver-wide default: Xbox Series
    engine = make_engine()
    assert engine.controller.model == "xbox_series" and len(fake_driver.plugs()) == 1
    assert engine.set_controller_model("xbox_series")           # what it already is
    assert len(fake_driver.plugs()) == 1
    assert engine.settings.get("controller", "model") == "xbox_series"
    assert engine.controller.requested_model == "xbox_series"


def test_resetting_settings_goes_back_to_xbox360(make_engine, fake_driver):
    fake_driver.driver["max"] = 5
    engine = make_engine(model="xbox_series")
    engine.settings.reset_to_default()
    engine.apply_controller_settings()                          # what "Reset all settings" does
    assert [p[3] for p in fake_driver.plugs()] == [0x0B12, 0x028E]
    assert engine.controller.model == "xbox360"
