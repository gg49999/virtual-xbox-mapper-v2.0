import keycodes


class _Key:
    def __init__(self, vk=None, char=None, name=None):
        self.vk, self.char, self.name = vk, char, name


def test_vk_normalisation_ignores_modifier_chars():
    # Ctrl+W on Windows reports char '\x17' but vk 0x57.
    assert keycodes.from_pynput_key(_Key(vk=0x57, char="\x17")) == "w"
    # Shift+1 reports '!' but vk 0x31.
    assert keycodes.from_pynput_key(_Key(vk=0x31, char="!")) == "1"


def test_char_fallback_unshifts():
    assert keycodes.from_pynput_key(_Key(char="!"), prefer_vk=False) == "1"
    assert keycodes.from_pynput_key(_Key(char="W"), prefer_vk=False) == "w"


def test_special_key_aliases():
    assert keycodes.from_pynput_key(_Key(name="shift_r")) == "shift"
    assert keycodes.from_pynput_key(_Key(name="ctrl_l")) == "ctrl"
    assert keycodes.from_pynput_key(_Key(name="f8")) == "f8"


def test_buttons_and_wheel():
    assert keycodes.from_pynput_button(_Key(name="x2")) == "mouse_x2"
    assert keycodes.wheel_codes(0, 1) == ["wheel_up"]
    assert keycodes.wheel_codes(-1, -1) == ["wheel_down", "wheel_left"]


def test_combo_parsing():
    assert keycodes.parse_combo("ctrl+alt+x") == (frozenset({"ctrl", "alt"}), "x")
    assert keycodes.parse_combo("F8") == (frozenset(), "f8")
    assert keycodes.parse_combo("ctrl+alt") is None
    assert keycodes.parse_combo("ctrl+nonsense") is None
    assert keycodes.format_combo(["alt", "ctrl"], "x") == "ctrl+alt+x"
    assert keycodes.combo_display("ctrl+alt+right") == "Ctrl + Alt + Right"


def test_display_names():
    assert keycodes.display_name("mouse_left") == "Left Click"
    assert keycodes.display_name("num5") == "Num 5"
    assert keycodes.short_name("mouse_right") == "RMB"
    assert keycodes.display_name("q") == "Q"
