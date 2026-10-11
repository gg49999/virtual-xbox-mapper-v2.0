# Bundled driver build: controller types

`driver/ViGEmBus` is the source of the ViGEmBus virtual-gamepad driver with one
addition: an Xbox target can be presented as an Xbox One or Xbox Series X|S family
controller instead of an Xbox 360 one. It is what **Settings › Virtual controller ›
Controller type** relies on. What the change involves on the driver side is described
in [ViGEmBus/XBOX-MODELS.md](ViGEmBus/XBOX-MODELS.md).

> **Status: source only.** The driver has not been compiled with the Windows Driver
> Kit, signed, or loaded on Windows. Until a build of it is installed, the app offers
> the Xbox 360 controller only. See [What has and hasn't been verified](#what-has-and-hasnt-been-verified).

## How the app uses it

- `src/controller_models.py` lists the controller types and the vendor/product ID
  each one is requested with. It is the same table as `ViGEmBus/sys/XboxModels.cpp`;
  a test keeps the two in step.
- `VirtualController` puts those IDs on the target before plugging it in. For the
  Xbox 360 type it runs exactly the code it always ran.
- **The app never requests a newer type from a driver that does not support it.**
  The stock driver hands such IDs straight to Windows, which then loads its Xbox One
  controller driver for a device speaking the Xbox 360 protocol, and the virtual
  controller is dead until it is re-created. The bundled build therefore carries the
  marker string `ViGEmBus-XboxModels-v1:max=<n>` in its version resource, and the app
  looks for it in `%SystemRoot%\System32\drivers\ViGEmBus.sys` every time it connects.
  No marker (stock driver, unreadable file, not Windows) means Xbox 360 only, and the
  other types are greyed out.
- The driver also has a machine-wide default (`ViGEmBus/tools/Set-XboxModel.ps1`,
  administrator only) that applies to every application asking for the plain Xbox 360
  IDs. The app only *reads* that setting, to show the type really in effect while
  "Xbox 360 Controller" is selected.

## Getting the build onto a machine

1. Build `driver/ViGEmBus` with Visual Studio, the Windows Driver Kit and DMF as
   described in its README. The `sdk` submodule
   ([ViGEmClient](https://github.com/nefarius/ViGEmClient)) has to be checked out into
   `driver/ViGEmBus/sdk`.
2. Sign it. A kernel driver you built yourself loads only in Windows test-signing mode
   (development machines; Secure Boot off) or with your own production signature
   obtained through Microsoft's driver signing process. The signature on the stock
   driver does not carry over.
3. Install it: put `ViGEmBus.inf`, `.sys`, `.cat` and `devcon.exe` into
   `installer/driver` and either run `Install-Driver.ps1` there from an elevated
   prompt, or compile the installer with `/DBundleModelDriver`
   (see `installer/driver/README.txt`).
4. Start the app, open **Settings**, press **Reconnect** if it was already running,
   and pick a controller type.

## What has and hasn't been verified

Verified without Windows:

- The driver's new code against the real KMDF headers, and in a user-mode model of the
  kernel calls it makes (`ViGEmBus/tests/xinputhid/run.sh`).
- The app side: `tests/test_controller_models.py` (type table, marker detection, the
  rule above, the controller and engine against a stand-in for `vgamepad`) and
  `tests/test_ui_controller_type.py` (the Settings row with real Qt widgets, offscreen).

**Not verified:** the driver has not been compiled with the WDK, loaded, or used by a
game. `Install-Driver.ps1`, the `BundleModelDriver` branch of `setup.iss`, and the
registry read of the machine-wide default have never run on Windows. Treat the first
build and install as a test, on a machine you can afford to troubleshoot.

## Licenses

- ViGEmBus: BSD 3-Clause, © Nefarius Software Solutions e.U. and contributors
  ([ViGEmBus/LICENSE](ViGEmBus/LICENSE)). The license text has to accompany binary
  redistributions; the installer copies it when the driver is bundled.
- The HID report descriptor in `ViGEmBus/sys/XinputHidPdo.cpp` comes from
  [DsHidMini](https://github.com/nefarius/DsHidMini) (BSD 3-Clause), originally
  captured by DJm00n.
- `devcon.exe`, which `Install-Driver.ps1` uses, is part of the Windows Driver Kit and
  is not included; check Microsoft's redistribution terms before shipping it.
