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



#include "Driver.h"
#include "XboxModels.hpp"

namespace
{
	constexpr USHORT MicrosoftVendorId = 0x045E;

	//
	// Product ID of the Xbox 360 Controller. ViGEmClient always sends this
	// (together with the Microsoft vendor ID) unless the application asked
	// for something else, so it means "no preference".
	//
	constexpr USHORT Xbox360ProductId = 0x028E;

	//
	// Product ID XBOXGIP.SYS uses for the HID device it creates for every
	// wired Xbox One family controller, no matter the actual model. It has
	// been part of XINPUTHID.INF from the very beginning, which makes it the
	// safest ID to get the HID child device bound to XINPUTHID.SYS.
	//
	constexpr USHORT XboxGipHidProductId = 0x02FF;

	//
	// Name of the registry value below the Parameters key of the service
	//
	DECLARE_CONST_UNICODE_STRING(DefaultModelValueName, L"XusbDefaultModel");

	//
	// The wired controllers carry the product string XBOXGIP.SYS reports for
	// its HID device, which is the name Windows shows for the real thing in
	// the game controllers control panel.
	//
	const ViGEm::Bus::Targets::XBOX_MODEL_PROFILE Profiles[] =
	{
		{
			ViGEm::Bus::Targets::XboxModelOne,
			MicrosoftVendorId, 0x02FF, XboxGipHidProductId,
			L"Virtual Xbox One Controller",
			L"Microsoft",
			L"Controller (Xbox One For Windows)"
		},
		{
			ViGEm::Bus::Targets::XboxModelOneS,
			MicrosoftVendorId, 0x02EA, XboxGipHidProductId,
			L"Virtual Xbox One S Controller",
			L"Microsoft",
			L"Controller (Xbox One For Windows)"
		},
		{
			ViGEm::Bus::Targets::XboxModelEliteSeries2,
			MicrosoftVendorId, 0x0B00, XboxGipHidProductId,
			L"Virtual Xbox Elite Series 2 Controller",
			L"Microsoft",
			L"Controller (Xbox One For Windows)"
		},
		{
			ViGEm::Bus::Targets::XboxModelSeries,
			MicrosoftVendorId, 0x0B12, XboxGipHidProductId,
			L"Virtual Xbox Series X|S Controller",
			L"Microsoft",
			L"Controller (Xbox One For Windows)"
		},
		{
			ViGEm::Bus::Targets::XboxModelSeriesBluetooth,
			MicrosoftVendorId, 0x0B13, XboxGipHidProductId,
			L"Virtual Xbox Series X|S Controller",
			L"Microsoft",
			L"Xbox Wireless Controller"
		},
	};
}

const ViGEm::Bus::Targets::XBOX_MODEL_PROFILE* ViGEm::Bus::Targets::XboxModelLookupByModel(ULONG Model)
{
	for (ULONG i = 0; i < ARRAYSIZE(Profiles); i++)
	{
		if (static_cast<ULONG>(Profiles[i].Model) == Model)
		{
			return &Profiles[i];
		}
	}

	return nullptr;
}

const ViGEm::Bus::Targets::XBOX_MODEL_PROFILE* ViGEm::Bus::Targets::XboxModelLookupByIds(
	USHORT VendorId, USHORT ProductId)
{
	for (ULONG i = 0; i < ARRAYSIZE(Profiles); i++)
	{
		if (Profiles[i].VendorId == VendorId && Profiles[i].ProductId == ProductId)
		{
			return &Profiles[i];
		}
	}

	return nullptr;
}

_Use_decl_annotations_
ULONG ViGEm::Bus::Targets::XboxModelQueryDefault()
{
	WDFKEY key = nullptr;
	ULONG value = XboxModel360;

	NTSTATUS status = WdfDriverOpenParametersRegistryKey(
		WdfGetDriver(),
		KEY_READ,
		WDF_NO_OBJECT_ATTRIBUTES,
		&key
	);
	if (!NT_SUCCESS(status))
	{
		return XboxModel360;
	}

	status = WdfRegistryQueryULong(key, &DefaultModelValueName, &value);

	WdfRegistryClose(key);

	//
	// Value missing, of the wrong type or not a model we know: stock behaviour
	//
	if (!NT_SUCCESS(status) || value >= XboxModelMax)
	{
		return XboxModel360;
	}

	return value;
}

_Use_decl_annotations_
const ViGEm::Bus::Targets::XBOX_MODEL_PROFILE* ViGEm::Bus::Targets::XboxModelResolve(
	USHORT VendorId, USHORT ProductId)
{
	const bool noPreference =
		(VendorId == 0 || ProductId == 0)
		|| (VendorId == MicrosoftVendorId && ProductId == Xbox360ProductId);

	if (noPreference)
	{
		return XboxModelLookupByModel(XboxModelQueryDefault());
	}

	//
	// IDs of a model we know get that model, everything else (third party
	// XInput controllers and so on) remains a classic XUSB device reporting
	// the IDs the client asked for.
	//
	return XboxModelLookupByIds(VendorId, ProductId);
}
