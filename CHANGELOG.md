# Changelog

## 2.0.1

Fixes the Windows installer, which could install the original 1.x interface
instead of the 2.0 one.

### Fixed
- The repository contained an old 1.x build in `build/dist` (plus a prebuilt
  `VirtualXboxMapper-Setup-1.0.0.exe`) and a duplicate 1.x source tree in
  `VirtualXboxMapper/`. Compiling `installer/setup.iss` packaged that stale build,
  so Windows installs showed the old UI. All three have been removed.
- `setup.iss` now refuses to compile unless `build\dist\VirtualXboxMapper\VirtualXboxMapper.exe`
  exists **and** its version resource matches the installer version, so a stale build
  can never be shipped again.
- Upgrades clean out the previous install first (`[InstallDelete]` removes the old
  `_internal` runtime, exe, bundled config/profiles, and the 1.x Start-menu folder),
  and a running copy of the app is closed before files are replaced.

### Changed
- The version is defined once, in `src/app_info.py`. The PyInstaller spec generates the
  exe's version resource from it, and `build_exe.bat` and CI pass it to Inno Setup
  (`/DMyAppVersion=...`, read with `tools/app_version.py`).

## 2.0.0

A ground-up redesign of the interface plus a rewrite of the input engine.

### New
- **Windows 11–style interface**:
  - navigation pane with Mapping, Tuning, Live test, Profiles, Settings, and About pages
  - command bar with controller status, emulation switch, and capture/release buttons
  - status bar
  - in-app notifications with Undo
  - dark, light, and system themes with six accent colors
  - dark title bar on Windows
- Responsive layout: the navigation collapses to icons on narrow windows, panels scroll,
  and diagram labels compress or fall back to hover when space is tight.
- New controller diagram:
  - a 2.5D, true-perspective controller (camera tilted 24° above the front) with
    a solid body, raised buttons and upright stick caps, drawn in code (`ui/controller_art.py`), with
    proportions traced from a real controller: carbon-black finish in dark mode and
    robot-white in light mode, soft shadows, bevel and rim lighting, textured stick
    caps and triggers, a faceted hybrid D-pad, glossy face buttons with coloured
    letters, and live pressed/stick/trigger states
  - photo mode, re-calibrated so the controls line up
  - custom-photo mode with a calibration wizard
  - collision-free binding labels, hover tooltips, and clickable labels
- Per-control **Toggle** and **Turbo** behaviors.
- **Walk** and **Precision aim** modifier inputs.
- Mouse buttons 4 and 5, and mouse-wheel up, down, left, and right, can be bound.
- Xbox (Guide) button binding.
- Mouse aim:
  - velocity-based, so it no longer depends on the polling rate
  - radial shaping, so diagonals keep their direction
  - anti-deadzone, precision scale, and an *Aggressive* curve
  - live response-curve preview
  - the mouse can drive the left stick or nothing at all
- Raw Input mouse capture with cursor clipping and optional hiding. Capture is released
  automatically when you switch windows.
- Tuning is saved per profile. The FPS profile now has its own sensitivity, and a new
  Racing example profile is included.
- Trigger pull strength per trigger.
- Round (circular) stick output for diagonal keys.
- Engine runs on a dedicated high-resolution timing thread, with a selectable rate of
  60–1000 Hz.
- The Live test page shows stick pads with trails, trigger meters, and **rumble from the
  game**, plus an input log.
- Binding dialog:
  - inline conflict resolution (move the key, or keep it on both controls)
  - hotkey clash warning
  - Esc to cancel, Enter to confirm
- Hotkey recorder in Settings with duplicate detection. The "show window" and
  next/previous profile hotkeys now work.
- On-screen overlay and optional tray notifications for hotkey actions.
- Tray menu with emulation and capture toggles, emergency release, and a profile switcher.
  The tray icon reflects the current state.
- Only one instance runs at a time; a second launch focuses the running window.
- `--minimized`, `--debug`, and `--version` command-line options.
- About page with shortcuts, getting-started steps, and copyable diagnostics.

### Fixed
- **W/S and vertical mouse movement were inverted.** Up now pushes the stick up.
- Qt widgets were updated from pynput listener threads, which could crash or freeze the
  app. All cross-thread updates now go through queued Qt signals.
- The binding dialog recorded the click on its own **Cancel** button as a *Left Click*
  binding. Its background listener thread also never exited.
- Changing a hotkey left the old one active; both fired.
- Saved mouse and keyboard tuning wasn't applied at startup.
- Switching from a profile with custom sensitivity kept that sensitivity.
- Holding two keys bound to the same button released the button when either key
  was let go.
- Ctrl+letter and Shift+number were recorded as control characters or symbols, which
  caused bindings that never released.
- Mouse capture centered the cursor using window-relative coordinates, which is wrong on
  most setups.
- Creating or renaming a profile could silently overwrite an existing one. A case-only
  rename deleted the profile on Windows.
- Importing a malformed profile could crash the app later. Imports are now validated and
  sanitized.
- The shipped FPS profile bound Q to both Y and LB.
- Start with Windows pointed at `python.exe` without the script when run from source.
- Dead settings (stick deadzone, trigger threshold, vibration) did nothing; they were removed.
- Corrupt `settings.json` files are backed up and replaced instead of being silently ignored.
- Exceptions on background threads are now logged and reported.

### Packaging
- PyInstaller spec with relative paths, a Windows version resource, and a generated
  multi-size icon.
- Inno Setup script:
  - installs ViGEmBus only when it's missing
  - supports silent installs
  - requires Windows 10 or later on x64
  - cleans up the startup entry on uninstall
- One-step `installer\build_exe.bat` that tests, builds, and packages.
- GitHub Actions CI runs tests on Windows and Linux. Tagged builds produce the installer.
- 46 automated tests, covering the engine, profiles, settings, hotkeys, and headless UI
  smoke tests.
