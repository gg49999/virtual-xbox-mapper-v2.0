# Tests for the Xbox One/Series presentation

`./run.sh` builds and runs two user-mode tests (g++ with C++17 and python3; Linux, WSL or macOS, no WDK):

- `test_report_layout.py` decodes generated input reports through the report descriptor in `sys/XinputHidPdo.cpp`.
- `mock/test.cpp` runs `sys/XinputHidPdo.cpp` and `sys/XboxModels.cpp`, unmodified, against `mock/fakekernel.h`, a small model of the kernel, WDF and DMF calls those files make.

The ViGEm SDK headers are taken from `sdk/include` (`git submodule update --init`) or from the directory named by `VIGEM_SDK_INCLUDE`.

These tests exercise the logic of the new target. They do not replace building with the WDK or testing on Windows.
