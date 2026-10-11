# Virtual Xbox Mapper

Turn your keyboard and mouse into a real, Windows-recognized Xbox 360
controller. It's built so that games streamed through **Xbox Cloud Gaming**,
and any other XInput-only game, become playable without a physical gamepad.

```
Keyboard + Mouse ─▶ Mapping engine ─▶ Virtual Xbox 360 controller (ViGEmBus) ─▶ Windows ─▶ Game / Cloud Gaming
```

Virtual Xbox Mapper is **not** a key remapper. It creates an actual virtual controller at the
driver level. Windows, browsers, and games see it the same way they see a wired Xbox
controller.

---

## Features

**Mapping**
- An interactive controller diagram: click any control to edit it. Binding labels are
  laid out around the controller so they never overlap.
- Bind any number of keys, mouse buttons (including Mouse 4 and 5), or mouse-wheel
  directions to every button, stick direction, trigger, and the Xbox button.
- Each control can be set to **Hold**, **Toggle** (for example auto-run or sprint lock),
  or **Turbo** (2–30 presses per second).
- The binding dialog detects conflicts. You can move a key or keep it on both controls
  in a single step, and it warns you when a key is also a hotkey.
- Searchable list of all controls. Removing a binding can be undone.
- Modifier inputs: **Walk** scales the left stick down while held. **Precision aim** lowers
  mouse sensitivity while held.

**Mouse aim**
- Mouse speed drives the stick. Because the input is velocity-based, the feel doesn't
  change with your mouse's polling rate.
- Raw Input capture: the cursor is parked and hidden, and deltas are read straight from
  the device.
- Separate or linked X/Y sensitivity.
- Four response curves, with a live preview graph.
- Smoothing, acceleration, deadzone, and **anti-deadzone** (skips past the game's own
  stick deadzone).
- Maximum output, axis inversion, and a direct 1:1 mode.
- The mouse can drive the right stick, the left stick, or nothing (for example, in racing
  games).

**Keyboard movement**
- Analog ramping with adjustable ramp-up and ramp-down times, ramp shape, and stick strength.
- Round (circular) stick output, so W+D doesn't exceed a real stick's range.

**Profiles**
- Each profile carries its own bindings, behaviors, and tuning.
- Create, duplicate, rename, import, export, reset, and delete profiles. Each profile can
  have a description.
- Three example profiles are included: Default, FPS, and Racing.
- Switch profiles from the tray menu or with hotkeys while you play.

**Safety and convenience**
- Global hotkeys, all configurable:
  - capture or release the mouse
  - turn emulation on or off
  - **emergency release** (clears every input)
  - show the window
  - switch to the next or previous profile
- Mouse capture is released automatically when you Alt+Tab away. The cursor is always
  restored, even after a crash.
- An on-screen overlay confirms hotkey actions while a game has focus.
- Runs in the notification area. Optionally starts with Windows.
- Only one instance runs at a time. Launching the app again brings up the existing window.

**Live test**
- Shows what the virtual controller reports to Windows in real time:
  - sticks, with a movement trail
  - trigger percentages
  - pressed buttons
  - rumble requested by the game
- An input log shows each key or mouse press and which control it drove.
- Opens Windows' own *Game Controllers* panel.

**Interface**
- A modern Windows 11–style interface with dark, light, and system themes, and six
  accent colors.
- Responsive layout: the navigation collapses to icons on narrow windows, and the
  binding labels fall back gracefully when space is short.
- In-app notifications with Undo, keyboard navigation (Ctrl+1…6), and a dark title bar.
- The controller is a high-detail, near-photoreal render drawn in code, in the style of the
  Xbox Accessories app. It's carbon black in dark mode and robot white in light mode, and
  every press, stick movement, and trigger pull shows live. You can switch to the bundled
  photo, or to **your own photo** after a quick click-to-calibrate wizard.

---

## Requirements

- Windows 10 or 11, 64-bit.
- The [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases) driver. The installer
  offers to install it for you.
- Python 3.10 or later, only if you run from source.

## Installation

### Installer (recommended)
1. Run `VirtualXboxMapper-Setup-<version>.exe`.
2. Keep **Install the ViGEmBus virtual controller driver** ticked if the option is shown.
   It only appears when the driver is missing.
3. Launch **Virtual Xbox Mapper** from the Start menu.

### From source
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src\main.py
```
`pip install vgamepad` opens the ViGEmBus installer if the driver is missing.

Command-line options:
- `--minimized`: start in the tray.
- `--debug`: verbose logging.
- `--version`: print the version and exit.

---

## Quick start

1. The top bar should show **Controller connected**. If it doesn't, click **Get ViGEmBus**
   in the banner, install the driver, then click **Reconnect**.
2. Open **Live test** and press W, Space, or a mouse button. The on-screen controller reacts.
3. Start your game (or [xbox.com/play](https://www.xbox.com/play)). Then press **F8** to
   capture the mouse, and mouse movement becomes right-stick aiming.
4. Press **F8** again to release the mouse. Press **F10** at any time to release *everything*.

## Controller type

**Settings › Virtual controller › Controller type** selects what the virtual controller
presents itself as to Windows and games:

| Controller type | Needs |
|---|---|
| Xbox 360 Controller (default) | any ViGEmBus driver |
| Xbox One Controller | the driver build in `driver/ViGEmBus` |
| Xbox One S Controller | the driver build in `driver/ViGEmBus` |
| Xbox Elite Series 2 Controller | the driver build in `driver/ViGEmBus` |
| Xbox Series X\|S Controller | the driver build in `driver/ViGEmBus` |
| Xbox Series X\|S Controller (Bluetooth identity) | the driver build in `driver/ViGEmBus` |

Your bindings and profiles are the same for every type. Only the controller's identity
changes, which is what decides the name and button glyphs that games and Steam show.
Changing the type unplugs the virtual controller and plugs it back in, so a running game
sees a controller swap.

Types the installed driver can't present are listed but greyed out. The stock ViGEmBus
driver only knows the Xbox 360 controller, and the app checks the installed driver before
offering anything else, because asking the stock driver for a newer controller leaves the
virtual controller dead. The driver build in `driver/ViGEmBus` has to be compiled and
signed before it can be installed, and **it has not been run on a real machine yet**. See
[driver/README.md](driver/README.md).

## Default hotkeys

| Action | Default |
|---|---|
| Capture / release mouse | F8 |
| Turn emulation on / off | F9 |
| Emergency release (all inputs + mouse) | F10 |
| Show the window | Ctrl + Alt + X |
| Next / previous profile | Ctrl + Alt + → / ← |

To change them, go to **Settings › Hotkeys**. Click a shortcut, then press the new
combination; Backspace clears it.

In-app shortcuts:

| Shortcut | Action |
|---|---|
| Ctrl + 1 … 6 | Switch page |
| Ctrl + , | Open Settings |
| F1 | Open About |
| Ctrl + Q | Exit |

---

## Tuning tips

- **Aim feels sluggish when you move the mouse slowly:** raise *Anti-deadzone* on the
  Tuning page until slow movement starts turning the camera. Most games apply their own
  stick deadzone.
- **Aim feels jittery:** raise *Smoothing* a little, or choose the *Smooth* curve.
- **Flicks don't turn far enough:** raise *Acceleration* or *Maximum output*, or use
  *Aggressive*.
- **Movement feels floaty:** lower the keyboard *Ramp up* and *Ramp down* times, or turn
  off *Analog ramping*.
- **The mouse is stuck on one window:** press F8 or F10. Alt+Tab also releases the mouse
  when *Release when switching windows* is on.

## Troubleshooting

**"Controller not connected"**
: The ViGEmBus driver isn't installed or isn't running. Install it from the
  [releases page](https://github.com/nefarius/ViGEmBus/releases), reboot if asked, then
  click **Reconnect**.

**Keys aren't detected in a game running as administrator**
: Windows blocks input hooks from non-elevated apps. Run Virtual Xbox Mapper as
  administrator too.

**Aim doesn't respond while the mouse is captured**
: Turn off **Settings › Mouse capture › Use Raw Input** and try again. Please also report
  the problem, with diagnostics from **About › Copy diagnostics**.

**A button seems stuck**
: Press the emergency-release hotkey (F10). It clears every button, stick, and trigger.

**Where are my settings, profiles, and logs?**
: Settings and profiles are in `%APPDATA%\VirtualXboxMapper`, and logs are in
  `%LOCALAPPDATA%\VirtualXboxMapper\logs`. Both folders can be opened from
  **Settings › Troubleshooting**.

## Uninstalling

Use **Settings › Apps › Virtual Xbox Mapper › Uninstall**. The ViGEmBus driver stays
installed because other software may use it. You can remove it separately from the same
list.

---

## Building

```bat
installer\build_exe.bat
```
This script does the following:
1. Installs the dependencies.
2. Runs the tests.
3. Builds `build\dist\VirtualXboxMapper\` with PyInstaller.
4. If [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed, compiles
   `build\installer_output\VirtualXboxMapper-Setup-<version>.exe`.

To release a new version, bump `APP_VERSION` in `src/app_info.py`. That is the only
place: the exe's version resource and the installer version are generated from it.

`setup.iss` refuses to compile if `build\dist` holds no build, or a build whose version
doesn't match. This stops an old build from being packaged by mistake. Always build the
installer with `build_exe.bat`, and don't distribute an installer you compiled before 2.0.1.

Run the tests on any OS:
```bash
pip install PyQt6 pynput pytest
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
```

## Project structure

```
src/
  main.py                 Entry point: single instance, crash handling, startup
  engine.py               Owns the pipeline; bridges background threads to the UI via Qt signals
  input_manager.py        Global keyboard/mouse listeners (pynput) and mouse capture
  win_input.py            Windows Raw Input, cursor clipping/hiding
  hotkey_manager.py       Global hotkeys on the shared input stream
  mapping_manager.py      Input → controller logic (hold/toggle/turbo, sticks, modifiers)
  mouse_controller.py     Mouse velocity → stick shaping
  keyboard_controller.py  Key → analog ramping
  virtual_controller.py   ViGEmBus / vgamepad backend
  controller_models.py    Controller types and detection of what the installed driver supports
  keycodes.py             Canonical key names shared by every capture path
  profile_manager.py      Profile model, validation and storage
  settings_manager.py     App settings with defaults, validation and migration
  startup.py              Start-with-Windows registration
  paths.py, logger.py, app_info.py
  ui/
    main_window.py        App shell: navigation, command bar, tray, toasts
    pages/                Mapping, Tuning, Live test, Profiles, Settings, About
    controller_diagram.py Interactive controller diagram with binding callouts
    controller_art.py     High-detail controller renderer (carbon / robot-white finishes)
    binding_dialog.py     "Press a key" capture with conflict handling
    calibration_dialog.py Click-to-calibrate for custom controller photos
    widgets.py            Fluent-style widget kit
    theme.py, icons.py, osd.py, qt_keys.py
profiles/                 Example profiles copied to the user folder on first run
config/default_settings.json  First-run defaults (packagers can customise)
driver/                   Source of the driver build that adds the newer controller types (see driver/README.md)
installer/                PyInstaller spec, build script, Inno Setup script, ViGEmBus setup
  driver/                 Drop-in folder and install script for the built driver package
tests/                    Unit tests + headless UI smoke tests
```

## License

MIT. See [LICENSE](LICENSE). Xbox is a trademark of Microsoft Corporation. This project is
not affiliated with or endorsed by Microsoft.
