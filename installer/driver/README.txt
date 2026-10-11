Driver package for the installer (optional)
===========================================

Put the BUILT driver package here if the installer should ship the driver
from driver\ViGEmBus (the one that lets Settings > Virtual controller >
Controller type offer the Xbox One / Xbox Series X|S controllers):

    ViGEmBus.inf
    ViGEmBus.sys
    ViGEmBus.cat
    devcon.exe        (from the Windows Driver Kit, x64)

Then compile the installer with the BundleModelDriver switch, after
building the app with installer\build_exe.bat:

    ISCC.exe /DBundleModelDriver /DMyAppVersion=<version> installer\setup.iss

Without the switch the installer behaves as before and offers the stock
ViGEmBus setup that is checked in next to setup.iss.

Nothing in this folder is produced by this repository's build scripts and
no driver binaries are checked in: the driver has to be built with Visual
Studio and the Windows Driver Kit and signed by whoever distributes it.
See driver\README.md, including what has and has not been tested.

Install-Driver.ps1 is what the installer runs. It can also be run by hand
from an elevated PowerShell prompt.
