# Presenting Xbox targets as a more recent controller

Out of the box every Xbox target of this driver shows up as an **Xbox 360 Controller for Windows**. This build adds the option to present the very same target as an **Xbox One / Xbox Series X|S** family controller instead.

Nothing changes for client applications. They keep creating an `Xbox360Wired` target and keep feeding it with the same calls (`vigem_target_x360_update` and friends); only the way the virtual device introduces itself to Windows is different. With no configuration at all the driver behaves exactly like the original.

> **Status: not yet built with the WDK and not yet run on Windows.** See [What has and hasn't been verified](#what-has-and-hasnt-been-verified) before relying on it.

## Models

| Value | Name | Reports as (VID:PID) | Notes |
|---|---|---|---|
| 0 | `Xbox360` | 045E:028E | The original behaviour (XUSB, `xusb22.sys`). Default. |
| 1 | `XboxOne` | 045E:02FF | What Windows itself reports to applications for *any* wired Xbox One family controller. The most conservative modern choice. |
| 2 | `XboxOneS` | 045E:02EA | Xbox One S controller. |
| 3 | `XboxEliteSeries2` | 045E:0B00 | Elite Series 2. The paddles don't exist on the virtual device. |
| 4 | `XboxSeries` | 045E:0B12 | Xbox Series X\|S controller, USB identity. |
| 5 | `XboxSeriesBluetooth` | 045E:0B13 | Xbox Series X\|S controller, Bluetooth identity and product name. |

Software that names controllers by their IDs (Steam, SDL based games, ...) is expected to pick up the corresponding name and button glyphs. Start with `XboxOne` or `XboxSeries`; the other rows only differ in the product ID and the product string.

## Selecting a model

### For everything on the machine

```powershell
# elevated PowerShell
.\tools\Set-XboxModel.ps1 XboxSeries     # change
.\tools\Set-XboxModel.ps1                # show the current setting
.\tools\Set-XboxModel.ps1 Xbox360        # back to the original behaviour
```

The script writes a single registry value:

```
HKLM\SYSTEM\CurrentControlSet\Services\ViGEmBus\Parameters
    XusbDefaultModel (REG_DWORD) = <value from the table>
```

The driver reads it each time a controller is plugged in, so there is no reboot and no driver restart; just restart the application that creates the controller. The setting applies to every application that creates an Xbox 360 target without asking for particular IDs, which is practically all of them. A missing or unknown value means `Xbox360`.

### For a single controller

A client can ask for a model by setting its IDs before adding the target. Explicit IDs win over the machine wide setting.

```c
PVIGEM_TARGET pad = vigem_target_x360_alloc();
vigem_target_set_vid(pad, 0x045E);
vigem_target_set_pid(pad, 0x0B12);   /* Xbox Series X|S */
vigem_target_add(client, pad);
```

With Python's `vgamepad` the IDs have to be set between allocating and adding the target, which a small subclass takes care of:

```python
import vgamepad as vg
import vgamepad.win.vigem_client as vcli

class VXboxSeriesGamepad(vg.VX360Gamepad):
    def target_alloc(self):
        target = vcli.vigem_target_x360_alloc()
        vcli.vigem_target_set_vid(target, 0x045E)
        vcli.vigem_target_set_pid(target, 0x0B12)
        return target

pad = VXboxSeriesGamepad()   # used exactly like vg.VX360Gamepad()
```

IDs that aren't in the table keep working the way they always did (an XUSB device reporting those IDs).

**Only ask a driver for these IDs if it supports them.** The original driver passes the IDs of a newer Xbox controller straight on to Windows, which then loads the wrong driver and leaves the virtual controller dead. A build with model support says so in its version resource: the driver file (`%SystemRoot%\System32\drivers\ViGEmBus.sys`) contains the UTF-16 string `ViGEmBus-XboxModels-v1:max=5`, the number being the highest model value it knows. Clients should look for that string first and stay with the Xbox 360 IDs when it is missing.

## How it works

Asking the classic target for the IDs of a newer controller does not work, and that is not a ViGEm limitation: Windows claims the USB IDs of first-party Xbox One and Series controllers for its own Xbox One controller driver (`dc1-controller.inf`), which expects a device speaking the GIP protocol, not the Xbox 360 one.

A real Xbox One or Series controller looks like this to Windows:

```
USB\VID_045E&PID_0B12                 Xbox Controller              (dc1-controller / xboxgip, GIP protocol)
 └─ USB\VID_045E&PID_02FF&IG_00       USB Input Device             (hidusb)
     └─ HID\VID_045E&PID_02FF&IG_00   XINPUT compatible HID device (xinputhid)
```

Games, Steam, XInput, DirectInput and Windows.Gaming.Input only ever deal with the lower two entries. The modern models make the bus enumerate exactly that middle device: a plain USB HID game controller with the hardware ID `USB\VID_045E&PID_02FF&IG_00` and the report descriptor of the Xbox One HID device. Windows loads `hidusb.sys` for it, the HID child inherits the `HID\VID_045E&PID_02FF&IG_00` ID, `xinputhid.inf` matches that, and Microsoft's own `xinputhid.sys` provides XInput on top. No vendor protocol is emulated and no additional driver is involved.

The hardware ID always carries product ID 02FF because that is the entry `xinputhid.inf` has had since the early Windows 10 releases, while several of the newer product IDs are missing from it. The product ID from the table is what the device descriptor (and therefore the HID attributes and XInput) report.

Inside the driver:

| File | Purpose |
|---|---|
| `sys/XboxModels.hpp/.cpp` | The model table, the registry lookup and the decision which presentation a plug-in request gets. |
| `sys/XinputHidPdo.hpp/.cpp` | The new device (`EmulationTargetXinputHid`). USB/HID plumbing modelled on the existing DualShock 4 target. |
| `sys/XinputHidReport.hpp` | Translation between `XUSB_REPORT` and the 17 byte HID input report, and of the rumble report. Pure arithmetic, shared with the tests. |
| `sys/busenum.cpp` | Creates the new device when a model other than `Xbox360` applies. |
| `sys/EmulationTargetPDO.hpp`, `sys/XusbPdo.hpp`, `sys/Queue.cpp` | The user index query became a virtual call, since two classes now report the `Xbox360Wired` type. |
| `sys/trace.h` | New trace flag `TRACE_XIHID` (appended, existing flags keep their bit). |

## Differences to the Xbox 360 presentation

- **XInput user index and LED number are unknown.** The classic target learns its player slot from the LED command `xusb22.sys` sends; `xinputhid.sys` has no equivalent. `vigem_target_x360_get_user_index` returns `VIGEM_ERROR_XUSB_USERINDEX_OUT_OF_RANGE` and the `LedNumber` passed to rumble notifications is always 255.
- **Rumble arrives with 1% resolution.** `xinputhid.sys` sends motor strengths as 0-100; they are scaled back to 0-255 for the notification callback. Trigger rumble motors are ignored.
- **The Guide button is reported** (`XUSB_GAMEPAD_GUIDE`). There is no Share button, `XUSB_REPORT` has no bit for it.
- **`vigem_target_add` returns immediately** instead of waiting for Windows to finish bringing the device up. Reports submitted in the meantime are not lost; the latest state is delivered as soon as the HID stack asks. The very first time a model is used Windows installs its inbox HID drivers for the new device, which can take a few seconds.
- Reports are only sent to Windows when something changed.

The device shares its start-up and shutdown handling with the DualShock 4 target. Whatever requires re-plugging a virtual DualShock 4 (possibly sleep and resume, this has not been examined) will require it here as well.

## Checking the result on Windows

1. Select a model and start the application that creates the controller.
2. Device Manager, *View > Devices by connection*: below the virtual gamepad bus there should be a **USB Input Device** with an **XINPUT compatible HID device** below it. Its hardware IDs (Details tab) include `HID\VID_045E&PID_02FF&IG_00`.
3. `joy.cpl` lists **Controller (Xbox One For Windows)** (or **Xbox Wireless Controller** for model 5) and reacts to input.
4. An XInput application sees exactly one controller.

If the child device shows up as *HID-compliant game controller* instead, `xinputhid.inf` did not match and XInput will not see the device. If anything looks wrong, `.\tools\Set-XboxModel.ps1 Xbox360` restores the original behaviour without touching the driver.

## Building and loading

Build as described in the [README](README.md) (Visual Studio, WDK, DMF, and the `sdk` submodule). The two new source files are already part of `sys/ViGEmBus.vcxproj`.

A driver built from these sources is a different binary than the one Nefarius Software Solutions signed. To load it you either need Windows in test-signing mode with a test certificate (development machines only; this requires Secure Boot to be off) or your own production signature via Microsoft's driver attestation signing. The original driver has to be removed first, both use the same service name and device interface.

## What has and hasn't been verified

Done, without Windows:

- The new and the modified source files pass a compiler syntax and type check against the real KMDF 1.15 headers and the mingw-w64 DDK headers (GCC, with stand-ins for DMF and the WPP generated trace headers). Unmodified files of the original driver pass the same check, so the setup is meaningful.
- `tests/xinputhid/run.sh` runs the unmodified sources in user mode against a model of the kernel calls they make, with AddressSanitizer and UBSan: model selection, hardware IDs, all descriptors including truncated and MDL-backed requests, delivery of input reports (immediately, by timer, into undersized buffers), rumble notifications with and without a waiting client, and a few abuse cases.
- The report translation is checked by decoding every generated report through the actual report descriptor with an independent parser.
- The report descriptor is byte-identical in two projects that use it with `xinputhid.sys` on real machines (DsHidMini and HIDMaestro).

Not done:

- The driver has **not been compiled with MSVC and the WDK**. Expect to fix the odd warning.
- It has **not been loaded on Windows**. That `hidusb.sys` and `xinputhid.sys` accept the device is derived from how the DualShock 4 target of this driver and the two projects above work, not from a test run.
- `tools/Set-XboxModel.ps1` has not been executed.

## Credits

- HID report descriptor: [DsHidMini](https://github.com/nefarius/DsHidMini) (BSD-3-Clause, Benjamin Höglinger-Stelzer), originally captured by [DJm00n](https://gist.github.com/DJm00n/07e1b7bb21643725e53b16f45e0e7022).
- The hardware ID technique for binding `xinputhid.sys` is documented by DsHidMini and by [HIDMaestro](https://github.com/hifihedgehog/HIDMaestro) (MIT).
