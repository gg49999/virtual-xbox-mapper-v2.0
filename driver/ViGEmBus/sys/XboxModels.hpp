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

#include <ntddk.h>
#include <wdf.h>

//
// Presentation models for Xbox-type emulation targets.
//
// Client applications always plug in the same target type (Xbox360Wired) and
// keep using the exact same IOCTLs to feed it. What changes with the model is
// purely how the virtual device presents itself to Windows:
//
//   - XboxModel360 is the classic behaviour: an "Xbox 360 Controller for
//     Windows" speaking the XUSB protocol to XUSB22.SYS. This is the default
//     and is implemented by EmulationTargetXUSB, untouched.
//
//   - Every other model presents an Xbox One family controller the way
//     Windows itself exposes one to applications: a HID game controller that
//     XINPUTHID.SYS turns into an XInput device. This is implemented by
//     EmulationTargetXinputHid.
//
// The model is selected in one of two ways:
//
//   1. Machine wide default (applies to targets plugged in with the stock
//      045E:028E IDs, which is what every unmodified client does):
//
//        HKLM\SYSTEM\CurrentControlSet\Services\ViGEmBus\Parameters
//          XusbDefaultModel (REG_DWORD) = one of XBOX_PRESENTATION_MODEL
//
//      The value is read every time a target gets plugged in, so no reboot or
//      driver restart is required. A missing or out-of-range value means
//      XboxModel360.
//
//   2. Per target: the client sets one of the vendor/product ID pairs listed
//      in the table in XboxModels.cpp (vigem_target_set_vid/_pid) before
//      adding the target. Explicit IDs always win over the default.
//

namespace ViGEm::Bus::Targets
{
	enum XBOX_PRESENTATION_MODEL : ULONG
	{
		//
		// Xbox 360 Controller (XUSB), the stock behaviour
		//
		XboxModel360 = 0,
		//
		// Xbox One Controller, exactly as XBOXGIP.SYS exposes any wired
		// Xbox One/Series controller to applications (045E:02FF)
		//
		XboxModelOne = 1,
		//
		// Xbox One S Controller (045E:02EA)
		//
		XboxModelOneS = 2,
		//
		// Xbox Elite Wireless Controller Series 2 (045E:0B00)
		//
		XboxModelEliteSeries2 = 3,
		//
		// Xbox Series X|S Controller, USB identity (045E:0B12)
		//
		XboxModelSeries = 4,
		//
		// Xbox Series X|S Controller, Bluetooth identity (045E:0B13)
		//
		XboxModelSeriesBluetooth = 5,
		//
		// Not a model, first invalid value. When adding a model, also raise
		// the number in the "XboxModels" value of ViGEmBus.rc: that is how
		// client applications find out what this build supports.
		//
		XboxModelMax
	};

	struct XBOX_MODEL_PROFILE
	{
		//
		// The model this profile describes
		//
		XBOX_PRESENTATION_MODEL Model;

		//
		// Vendor and product ID reported by the USB device descriptor. This
		// is what applications get to see (HID attributes, XInput).
		//
		USHORT VendorId;
		USHORT ProductId;

		//
		// Product ID used in the PNP hardware ID. This is what Windows uses
		// to pick the driver for the HID child device and it has to be one
		// XINPUTHID.INF knows about.
		//
		USHORT MatchProductId;

		//
		// Bus-reported device description
		//
		PCWSTR DeviceDescription;

		//
		// USB string descriptors (manufacturer and product)
		//
		PCWSTR ManufacturerString;
		PCWSTR ProductString;
	};

	//
	// Returns the profile of a model or nullptr for XboxModel360 and for
	// values outside of the valid range.
	//
	const XBOX_MODEL_PROFILE* XboxModelLookupByModel(ULONG Model);

	//
	// Returns the profile reporting the given vendor and product ID or
	// nullptr if there is none.
	//
	const XBOX_MODEL_PROFILE* XboxModelLookupByIds(USHORT VendorId, USHORT ProductId);

	//
	// Reads the machine wide default model from the registry. Never fails,
	// falls back to XboxModel360.
	//
	_IRQL_requires_max_(PASSIVE_LEVEL)
	ULONG XboxModelQueryDefault();

	//
	// Decides how an Xbox360Wired target requested with the given IDs is
	// going to be presented. Returns nullptr if it is a classic XUSB device.
	//
	_IRQL_requires_max_(PASSIVE_LEVEL)
	const XBOX_MODEL_PROFILE* XboxModelResolve(USHORT VendorId, USHORT ProductId);
}
