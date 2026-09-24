import json
import os

import pytest

from profile_manager import ProfileManager, Profile, validate_profile_name
from settings_manager import SettingsManager


def test_seed_and_crud(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "FPS.json").write_text(json.dumps({"name": "FPS", "bindings": {"A": ["space"]}}))
    pm = ProfileManager(str(tmp_path / "p"), seed_dir=str(seed))
    assert pm.list_profiles() == ["FPS"]

    pm.create("Racing")
    with pytest.raises(ValueError):
        pm.create("racing")          # case-insensitive duplicate
    with pytest.raises(ValueError):
        pm.create("bad/name")

    pm.rename("Racing", "Driving")
    assert "Driving" in pm.list_profiles() and "Racing" not in pm.list_profiles()
    pm.rename("Driving", "DRIVING")  # case-only rename keeps the file
    assert "DRIVING" in pm.list_profiles()

    pm.duplicate("FPS", "FPS 2")
    assert pm.load("FPS 2").bindings == {"A": ["space"]}
    pm.delete("FPS 2")
    assert "FPS 2" not in pm.list_profiles()


def test_cannot_delete_last(tmp_path):
    pm = ProfileManager(str(tmp_path / "p"))
    with pytest.raises(ValueError):
        pm.delete(pm.list_profiles()[0])


def test_import_sanitises_and_dedupes(tmp_path):
    pm = ProfileManager(str(tmp_path / "p"))
    src = tmp_path / "in.json"
    src.write_text(json.dumps({
        "name": "Default",
        "bindings": {"A": "space", "NOT_A_TARGET": ["x"], "B": [1, "Shift"]},
        "modes": {"A": {"mode": "turbo", "rate": 500}, "B": {"mode": "weird"}},
    }))
    p = pm.import_profile(str(src))
    assert p.name == "Default (2)"
    assert p.bindings == {"A": ["space"], "B": ["shift"]}
    assert p.modes == {"A": {"mode": "turbo", "rate": 30.0}}


def test_import_rejects_garbage(tmp_path):
    pm = ProfileManager(str(tmp_path / "p"))
    src = tmp_path / "bad.json"
    src.write_text("[1, 2, 3]")
    with pytest.raises(ValueError):
        pm.import_profile(str(src))


def test_profile_roundtrip():
    p = Profile(name="X")
    p.set_mode("A", "turbo", 12)
    p2 = Profile.from_dict(p.to_dict())
    assert p2.mode_for("A") == "turbo" and p2.turbo_rate("A") == 12


def test_name_validation():
    assert validate_profile_name("My Profile") is None
    assert validate_profile_name("  ") is not None
    assert validate_profile_name("con") is not None
    assert validate_profile_name("a" * 100) is not None


def test_settings_repair_bad_values(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "mouse": {"sensitivity_x": "high", "smoothing": 0.5},
        "appearance": {"theme": "neon"},
        "controller": {"tick_rate_hz": 250.0, "deadzone": 0.1},
        "custom": {"kept": True},
    }))
    s = SettingsManager(str(path))
    assert s.get("mouse", "sensitivity_x") == 1.0
    assert s.get("mouse", "smoothing") == 0.5
    assert s.get("appearance", "theme") == "dark"
    assert s.get("controller", "tick_rate_hz") == 250
    assert "deadzone" not in s.section("controller")
    assert s.settings["custom"] == {"kept": True}


def test_settings_corrupt_file_recovers(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    s = SettingsManager(str(path))
    assert s.get("hotkeys", "emergency_release") == "f10"
    assert os.path.exists(str(path) + ".corrupt")
