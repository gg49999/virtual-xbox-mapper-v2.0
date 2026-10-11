"""
controller_models
Which controller the virtual device presents itself as to Windows and
games ("Xbox 360 Controller", "Xbox Series X|S Controller", ...).

The mapping engine does not care about any of this: every model takes
the exact same ControllerState. Only the identity of the virtual device
changes, which is what decides the controller name and button glyphs
that games, Steam and Windows show.

How a model gets selected (see driver/README.md):

  * The stock virtual-gamepad driver only knows the Xbox 360
    presentation. Asking it for the USB IDs of a newer Xbox controller
    does NOT work - Windows then loads its Xbox One controller driver
    for a device that speaks the Xbox 360 protocol, and the virtual
    controller is dead until it is re-created.

  * The driver build bundled in driver/ViGEmBus adds further
    presentations. A client selects one by setting the vendor/product
    ID of that model on the target before plugging it in.

Because of the first point this module never lets a newer model be
requested unless the installed driver is known to support it. The
bundled driver identifies itself with a marker string in its version
resource (driver/ViGEmBus/sys/ViGEmBus.rc), which `read_driver_max_model()`
looks for in
the installed driver file.

This module is pure Python with no Windows-only imports at module
level, so it can be imported and tested anywhere.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass

from logger import get_logger

log = get_logger("ControllerModels")


@dataclass(frozen=True)
class ControllerModel:
    """One way the virtual controller can present itself."""
    id: str             # stable identifier, stored in settings.json
    label: str          # shown in the Settings dialog
    short_label: str    # shown in the window header
    vendor_id: int      # USB vendor ID the model is requested with
    product_id: int     # USB product ID the model is requested with
    driver_model: int   # XBOX_PRESENTATION_MODEL in driver/ViGEmBus/sys/XboxModels.hpp
    summary: str        # one-line explanation for the Settings dialog


# Keep in sync with the table in driver/ViGEmBus/sys/XboxModels.cpp;
# tests/test_controller_models.py cross-checks the two.
MODELS: tuple[ControllerModel, ...] = (
    ControllerModel(
        "xbox360", "Xbox 360 Controller", "Xbox 360 Controller",
        0x045E, 0x028E, 0,
        "The classic presentation. Works with every version of the driver.",
    ),
    ControllerModel(
        "xbox_one", "Xbox One Controller", "Xbox One Controller",
        0x045E, 0x02FF, 1,
        "What Windows reports for any wired Xbox One family controller.",
    ),
    ControllerModel(
        "xbox_one_s", "Xbox One S Controller", "Xbox One S Controller",
        0x045E, 0x02EA, 2,
        "Xbox One S controller.",
    ),
    ControllerModel(
        "xbox_elite_2", "Xbox Elite Series 2 Controller", "Xbox Elite Series 2 Controller",
        0x045E, 0x0B00, 3,
        "Elite Series 2. Its paddles do not exist on the virtual controller.",
    ),
    ControllerModel(
        "xbox_series", "Xbox Series X|S Controller", "Xbox Series X|S Controller",
        0x045E, 0x0B12, 4,
        "Current Xbox controller, USB identity.",
    ),
    ControllerModel(
        "xbox_series_bt", "Xbox Series X|S Controller (Bluetooth identity)", "Xbox Series X|S Controller",
        0x045E, 0x0B13, 5,
        "Current Xbox controller with the IDs and name it uses over Bluetooth.",
    ),
)

DEFAULT_MODEL_ID = "xbox360"

_BY_ID = {m.id: m for m in MODELS}
_BY_DRIVER_MODEL = {m.driver_model: m for m in MODELS}

# The bundled driver carries "<marker><highest supported driver_model>" as
# a string in its version resource. Version resources are stored as
# UTF-16, which is how the file is searched.
DRIVER_MARKER = "ViGEmBus-XboxModels-v1:max="
DRIVER_FILE_NAME = "ViGEmBus.sys"
_DRIVER_FILE_SIZE_LIMIT = 16 * 1024 * 1024

DRIVER_PARAMETERS_KEY = r"SYSTEM\CurrentControlSet\Services\ViGEmBus\Parameters"
DRIVER_DEFAULT_MODEL_VALUE = "XusbDefaultModel"


def default_model() -> ControllerModel:
    return _BY_ID[DEFAULT_MODEL_ID]


def get_model(model_id: object) -> ControllerModel:
    """Look a model up by its settings identifier. Anything unknown
    (hand-edited or newer settings file) falls back to the default
    rather than raising, like the other settings do."""
    if isinstance(model_id, str) and model_id in _BY_ID:
        return _BY_ID[model_id]
    if model_id is not None:
        log.warning("Unknown controller model %r in settings; using %s.", model_id, DEFAULT_MODEL_ID)
    return default_model()


def model_for_driver_value(value: int) -> ControllerModel | None:
    return _BY_DRIVER_MODEL.get(value)


def supported_model_ids(driver_max_model: int) -> tuple[str, ...]:
    """Models a driver reporting `driver_max_model` can present. The
    Xbox 360 presentation is always available."""
    return tuple(m.id for m in MODELS if m.driver_model == 0 or m.driver_model <= driver_max_model)


def resolve_request(requested_id: object, driver_max_model: int) -> ControllerModel:
    """The model whose IDs may actually be sent to the driver: the
    requested one if the installed driver supports it, otherwise the
    Xbox 360 one. This is the safety gate described at the top of this
    module - never bypass it."""
    model = get_model(requested_id)
    if model.id in supported_model_ids(driver_max_model):
        return model
    return default_model()


def effective_model(
    requested_id: object, driver_max_model: int, driver_default_model: int
) -> ControllerModel:
    """What the virtual controller ends up being presented as.

    Asking for the Xbox 360 IDs means "no preference" to the driver, so
    a machine-wide default configured there (tools/Set-XboxModel.ps1)
    applies in that case."""
    sent = resolve_request(requested_id, driver_max_model)
    if sent.driver_model != 0:
        return sent
    if 0 < driver_default_model <= driver_max_model:
        return model_for_driver_value(driver_default_model) or sent
    return sent


# ---- Detecting what the installed driver supports ---------------------------

def parse_driver_marker(data: bytes) -> int:
    """Return the highest model number announced by the marker in a
    driver binary, or 0 if the marker is absent or malformed (which is
    the case for the stock driver)."""
    needle = DRIVER_MARKER.encode("utf-16-le")
    pos = data.find(needle)
    if pos < 0:
        return 0
    pos += len(needle)
    digits = ""
    while len(digits) < 4 and pos + 1 < len(data):
        low, high = data[pos], data[pos + 1]
        if high != 0 or not (0x30 <= low <= 0x39):
            break
        digits += chr(low)
        pos += 2
    if not digits:
        return 0
    return int(digits)


def driver_file_candidates() -> tuple[str, ...]:
    """Where the driver binary lives. `Sysnative` covers a 32-bit
    Python on 64-bit Windows, where System32 is redirected."""
    root = os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    return (
        os.path.join(root, "System32", "drivers", DRIVER_FILE_NAME),
        os.path.join(root, "Sysnative", "drivers", DRIVER_FILE_NAME),
    )


def read_driver_max_model(paths: Iterable[str] | None = None) -> int:
    """Highest model the installed driver supports; 0 means "Xbox 360
    only" and is also the answer whenever the driver file can't be
    found or read. Erring towards 0 is deliberate: see the safety note
    at the top of this module."""
    for path in (paths if paths is not None else driver_file_candidates()):
        try:
            if not os.path.isfile(path) or os.path.getsize(path) > _DRIVER_FILE_SIZE_LIMIT:
                continue
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            log.debug("Could not read driver file %s: %s", path, exc)
            continue
        value = parse_driver_marker(data)
        highest = max(m.driver_model for m in MODELS)
        return min(value, highest)
    return 0


def read_driver_default_model() -> int:
    """The machine-wide default model configured for the driver, or 0
    if there is none (or it can't be read, or this isn't Windows).
    Read-only; changing it requires administrator rights and is done
    with driver/ViGEmBus/tools/Set-XboxModel.ps1, not by this app."""
    if not sys.platform.startswith("win"):
        return 0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, DRIVER_PARAMETERS_KEY) as key:
            value, value_type = winreg.QueryValueEx(key, DRIVER_DEFAULT_MODEL_VALUE)
        if value_type == winreg.REG_DWORD and isinstance(value, int):
            return value
    except OSError:
        pass
    except Exception as exc:  # never let a diagnostics read break connecting
        log.debug("Could not read the driver's default model: %s", exc)
    return 0
