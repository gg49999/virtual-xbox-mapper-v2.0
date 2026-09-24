from hotkey_manager import HotkeyManager, find_duplicate


def test_combo_fires_once_and_consumes():
    fired = []
    hk = HotkeyManager(use_os_modifier_state=False)
    bad = hk.set_bindings({"cap": "f8", "open": "ctrl+alt+x", "broken": "ctrl+"},
                          {"cap": lambda: fired.append("cap"), "open": lambda: fired.append("open")})
    assert bad == ["broken"]
    assert hk.feed("f8", True) is True
    assert hk.feed("f8", True) is False       # auto-repeat
    hk.feed("f8", False)
    assert hk.feed("x", True) is False        # modifiers not held
    hk.feed("x", False)
    hk.feed("ctrl", True)
    hk.feed("alt", True)
    assert hk.feed("x", True) is True
    assert fired == ["cap", "open"]


def test_extra_modifier_blocks_plain_hotkey():
    fired = []
    hk = HotkeyManager(use_os_modifier_state=False)
    hk.set_bindings({"cap": "f8"}, {"cap": lambda: fired.append(1)})
    hk.feed("shift", True)
    assert hk.feed("f8", True) is False
    assert fired == []


def test_rebinding_replaces_old_combo():
    fired = []
    hk = HotkeyManager(use_os_modifier_state=False)
    hk.set_bindings({"cap": "f8"}, {"cap": lambda: fired.append(1)})
    hk.set_bindings({"cap": "f7"}, {"cap": lambda: fired.append(2)})
    hk.feed("f8", True)
    hk.feed("f7", True)
    assert fired == [2]


def test_find_duplicate():
    assert find_duplicate({"a": "f8", "b": "F8"}) == ("a", "b")
    assert find_duplicate({"a": "f8", "b": "f9"}) is None
