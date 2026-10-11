#!/bin/sh
# User-mode tests for the Xbox One/Series (XInput HID) presentation.
# Needs g++ (C++17) and python3; runs on Linux, WSL or macOS. No WDK required.
#
# The sources in sys/ are copied unmodified and compiled against a small model
# of the kernel/WDF/DMF calls they make (mock/fakekernel.h).
set -e
cd "$(dirname "$0")"
SDK="${VIGEM_SDK_INCLUDE:-../../sdk/include}"
if [ ! -f "$SDK/ViGEm/Common.h" ]; then
	echo "ViGEm SDK headers not found in $SDK." >&2
	echo "Run 'git submodule update --init' or point VIGEM_SDK_INCLUDE at ViGEmClient/include." >&2
	exit 1
fi
rm -rf build && mkdir -p build/ViGEm/km
cp mock/* build/
cp ../../sys/XinputHidPdo.cpp ../../sys/XinputHidPdo.hpp ../../sys/XboxModels.cpp ../../sys/XboxModels.hpp ../../sys/XinputHidReport.hpp build/
cp "$SDK/ViGEm/Common.h" build/ViGEm/ && cp "$SDK/ViGEm/km/BusShared.h" build/ViGEm/km/
SAN="${SANITIZE--fsanitize=address,undefined -fno-sanitize-recover=all}"
g++ -std=c++17 -Wall -Wextra -Wconversion -Werror -I ../../sys report_dump.cpp -o build/report_dump
python3 test_report_layout.py build/report_dump
g++ -std=c++17 -fshort-wchar -Wall -Wextra -Wno-unused-parameter $SAN -g -I build build/test.cpp build/XinputHidPdo.cpp build/XboxModels.cpp -o build/test
build/test
