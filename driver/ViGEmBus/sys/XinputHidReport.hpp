/*
* Virtual Gamepad Emulation Framework - Windows kernel-mode bus driver
*
* BSD 3-Clause License
*
* Copyright (c) 2018-2022, Nefarius Software Solutions e.U. and Contributors
* All rights reserved.
*
* Redistribution and use in source and binary forms, with or without
* modification, are permitted provided that the following conditions are met:
*
* 1. Redistributions of source code must retain the above copyright notice, this
*    list of conditions and the following disclaimer.
*
* 2. Redistributions in binary form must reproduce the above copyright notice,
*    this list of conditions and the following disclaimer in the documentation
*    and/or other materials provided with the distribution.
*
* 3. Neither the name of the copyright holder nor the names of its
*    contributors may be used to endorse or promote products derived from
*    this software without specific prior written permission.
*
* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
* AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
* IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
* DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
* FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
* DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
* SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
* CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
* OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
* OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/


#pragma once

//
// Report translation for the "XInput HID" presentation of Xbox targets
// (see XinputHidPdo.hpp).
//
// This header intentionally contains nothing but plain integer arithmetic on
// byte buffers. It has no dependency on WDF, DMF or the kernel so the exact
// same code can be compiled and unit-tested in user mode. The only things it
// expects from the includer are the basic Windows integer typedefs and
// XUSB_REPORT / XUSB_GAMEPAD_* from <ViGEm/Common.h>.
//
// Layout of the 17 byte input report described by the report descriptor in
// XinputHidPdo.cpp (no report ID, all multi-byte fields little-endian):
//
//   [ 0.. 1]  X   left stick,  0..65535, 32768 = centre, 0 = left
//   [ 2.. 3]  Y   left stick,  0..65535,                  0 = up
//   [ 4.. 5]  Rx  right stick, 0..65535, 32768 = centre, 0 = left
//   [ 6.. 7]  Ry  right stick, 0..65535,                  0 = up
//   [ 8.. 9]  Z   left trigger,  10 bit (0..1023) + 6 bit padding
//   [10..11]  Rz  right trigger, 10 bit (0..1023) + 6 bit padding
//   [12]      buttons 1..8:  A, B, X, Y, LB, RB, View (Back), Menu (Start)
//   [13]      buttons 9..10: left stick click, right stick click (+ padding)
//   [14]      hat switch in the low nibble: 1 = N .. 8 = NW, 0 = released
//   [15]      bit 0: System Main Menu (Xbox / Guide button)
//   [16]      battery strength
//
// Layout of the 8 byte output (rumble) report sent by XINPUTHID.SYS:
//
//   [0]  actuator enable mask
//   [1]  left trigger motor,  0..100
//   [2]  right trigger motor, 0..100
//   [3]  left (large, low frequency) motor,   0..100
//   [4]  right (small, high frequency) motor, 0..100
//   [5]  duration, [6] start delay, [7] loop count
//

namespace ViGEm::Bus::Targets::XinputHid
{
	// Size in bytes of the input report (there is no report ID)
	constexpr ULONG InputReportSize = 17;

	// Size in bytes of the output report as declared by the descriptor
	constexpr ULONG OutputReportSize = 8;

	// Number of bytes that have to be present to read both main motors
	constexpr ULONG OutputReportMinSize = 5;

	// Offsets within the output report
	constexpr ULONG OutputLargeMotorOffset = 3;
	constexpr ULONG OutputSmallMotorOffset = 4;

	// Battery strength value XINPUTHID.SYS interprets as "wired"
	constexpr UCHAR BatteryWired = 0x80;

	//
	// Converts the d-pad bits of XUSB_REPORT::wButtons into a HID hat switch
	// value. Physically impossible combinations (up + down, left + right)
	// cancel each other out instead of producing an arbitrary direction.
	//
	inline UCHAR DpadToHat(USHORT Buttons)
	{
		bool up = (Buttons & XUSB_GAMEPAD_DPAD_UP) != 0;
		bool down = (Buttons & XUSB_GAMEPAD_DPAD_DOWN) != 0;
		bool left = (Buttons & XUSB_GAMEPAD_DPAD_LEFT) != 0;
		bool right = (Buttons & XUSB_GAMEPAD_DPAD_RIGHT) != 0;

		if (up && down)
		{
			up = false;
			down = false;
		}

		if (left && right)
		{
			left = false;
			right = false;
		}

		if (up)
		{
			if (right) return 2; // NE
			if (left) return 8;  // NW
			return 1;            // N
		}

		if (down)
		{
			if (right) return 4; // SE
			if (left) return 6;  // SW
			return 5;            // S
		}

		if (right) return 3;     // E
		if (left) return 7;      // W

		return 0;                // released (outside the logical range = null)
	}

	//
	// Expands an 8 bit trigger value to the 10 bit range of the report by
	// replicating the top bits. 0 stays 0, 255 becomes 1023 and shifting the
	// result right by two always yields the original value again.
	//
	inline USHORT TriggerTo10Bit(UCHAR Value)
	{
		return static_cast<USHORT>((static_cast<USHORT>(Value) << 2) | (Value >> 6));
	}

	//
	// Signed XInput axis (-32768..32767, positive = right) to unsigned HID
	// axis (0..65535, 32768 = centre).
	//
	inline USHORT AxisToHid(SHORT Value)
	{
		return static_cast<USHORT>(static_cast<LONG>(Value) + 32768);
	}

	//
	// Same as AxisToHid but for the vertical axes: XInput reports "up" as
	// positive while HID reports "up" as the minimum value.
	//
	inline USHORT AxisToHidInverted(SHORT Value)
	{
		return static_cast<USHORT>(32767 - static_cast<LONG>(Value));
	}

	//
	// Writes a complete input report for the given XUSB report.
	// Output has to provide room for InputReportSize bytes.
	//
	inline void FromXusbReport(const XUSB_REPORT* Input, UCHAR* Output)
	{
		const USHORT buttons = Input->wButtons;

		const USHORT lx = AxisToHid(Input->sThumbLX);
		const USHORT ly = AxisToHidInverted(Input->sThumbLY);
		const USHORT rx = AxisToHid(Input->sThumbRX);
		const USHORT ry = AxisToHidInverted(Input->sThumbRY);
		const USHORT lt = TriggerTo10Bit(Input->bLeftTrigger);
		const USHORT rt = TriggerTo10Bit(Input->bRightTrigger);

		ULONG low = 0;
		ULONG high = 0;

		if (buttons & XUSB_GAMEPAD_A) low |= 0x01;
		if (buttons & XUSB_GAMEPAD_B) low |= 0x02;
		if (buttons & XUSB_GAMEPAD_X) low |= 0x04;
		if (buttons & XUSB_GAMEPAD_Y) low |= 0x08;
		if (buttons & XUSB_GAMEPAD_LEFT_SHOULDER) low |= 0x10;
		if (buttons & XUSB_GAMEPAD_RIGHT_SHOULDER) low |= 0x20;
		if (buttons & XUSB_GAMEPAD_BACK) low |= 0x40;
		if (buttons & XUSB_GAMEPAD_START) low |= 0x80;

		if (buttons & XUSB_GAMEPAD_LEFT_THUMB) high |= 0x01;
		if (buttons & XUSB_GAMEPAD_RIGHT_THUMB) high |= 0x02;

		Output[0] = static_cast<UCHAR>(lx & 0xFF);
		Output[1] = static_cast<UCHAR>(lx >> 8);
		Output[2] = static_cast<UCHAR>(ly & 0xFF);
		Output[3] = static_cast<UCHAR>(ly >> 8);
		Output[4] = static_cast<UCHAR>(rx & 0xFF);
		Output[5] = static_cast<UCHAR>(rx >> 8);
		Output[6] = static_cast<UCHAR>(ry & 0xFF);
		Output[7] = static_cast<UCHAR>(ry >> 8);
		Output[8] = static_cast<UCHAR>(lt & 0xFF);
		Output[9] = static_cast<UCHAR>((lt >> 8) & 0x03);
		Output[10] = static_cast<UCHAR>(rt & 0xFF);
		Output[11] = static_cast<UCHAR>((rt >> 8) & 0x03);
		Output[12] = static_cast<UCHAR>(low);
		Output[13] = static_cast<UCHAR>(high);
		Output[14] = DpadToHat(buttons);
		Output[15] = static_cast<UCHAR>((buttons & XUSB_GAMEPAD_GUIDE) ? 0x01 : 0x00);
		Output[16] = BatteryWired;
	}

	//
	// Converts a motor magnitude from the 0..100 range used by the output
	// report to the 0..255 range of XUSB_REQUEST_NOTIFICATION. Out of range
	// input is clamped.
	//
	inline UCHAR MotorPercentToByte(UCHAR Percent)
	{
		const ULONG value = Percent;
		const ULONG clamped = (value > 100) ? 100 : value;

		return static_cast<UCHAR>((clamped * 255 + 50) / 100);
	}
}
