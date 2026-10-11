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
#include "XinputHidPdo.hpp"
#include "trace.h"
#include "XinputHidPdo.tmh"
#define NTSTRSAFE_LIB
#include <ntstrsafe.h>


using ViGEm::Bus::Targets::EmulationTargetXinputHid;
namespace XinputHid = ViGEm::Bus::Targets::XinputHid;

namespace
{
	//
	// HID class requests and report types
	//
	constexpr UCHAR HidRequestGetReport = 0x01;
	constexpr UCHAR HidRequestSetReport = 0x09;
	constexpr UCHAR HidReportTypeInput = 0x01;
	constexpr UCHAR HidReportTypeOutput = 0x02;

	//
	// HID class descriptor types
	//
	constexpr UCHAR HidDescriptorTypeHid = 0x21;
	constexpr UCHAR HidDescriptorTypeReport = 0x22;

	//
	// Endpoint addresses and the opaque pipe handles handed to HIDUSB.SYS
	//
	constexpr UCHAR EndpointIn = 0x84;
	constexpr UCHAR EndpointOut = 0x03;
	constexpr ULONG_PTR PipeHandleIn = 0xFFFF0084;
	constexpr ULONG_PTR PipeHandleOut = 0xFFFF0003;
	constexpr ULONG_PTR InterfaceHandle = 0xFFFF0000;

	//
	// Size of the configuration descriptor (configuration, one interface,
	// HID class descriptor, two endpoints)
	//
	constexpr ULONG ConfigurationDescriptorSize = 0x0029;

	//
	// Smallest valid URB_FUNCTION_SELECT_CONFIGURATION for one interface with
	// two pipes. Same layout as the DualShock 4 target.
	//
#if defined(_X86_)
	constexpr USHORT SelectConfigurationUrbSize = 0x0050;
#else
	constexpr USHORT SelectConfigurationUrbSize = 0x0070;
#endif

	//
	// bcdDevice
	//
	constexpr USHORT DeviceRevision = 0x0100;

	//
	// Interval in milliseconds at which reports that couldn't be delivered
	// immediately are retried
	//
	constexpr LONG QueueFlushPeriod = 0x05;

	//
	// Longest string (in characters) that fits into a USB string descriptor
	//
	constexpr ULONG MaxStringDescriptorChars = 126;

	//
	// Size of a rumble record stored in the notification buffer queue
	//
	constexpr size_t RumbleRecordSize = 2;

	//
	// HID report descriptor of the device XBOXGIP.SYS creates for an Xbox One
	// family controller, the layout XINPUTHID.SYS has been written for.
	//
	// Taken from DsHidMini (https://github.com/nefarius/DsHidMini, BSD-3-Clause,
	// Copyright (c) Benjamin Hoeglinger-Stelzer), which has been using it with
	// XINPUTHID.SYS for its "XInput" mode. Originally captured by DJm00n:
	// https://gist.github.com/DJm00n/07e1b7bb21643725e53b16f45e0e7022
	//
	// One input report of 17 bytes and one output report of 8 bytes, no
	// report IDs. See XinputHidReport.hpp for the layout of both.
	//
	const UCHAR HidReportDescriptor[] =
	{
		0x05, 0x01,        // Usage Page (Generic Desktop Ctrls)
		0x09, 0x05,        // Usage (Game Pad)
		0xA1, 0x01,        // Collection (Application)
		0xA1, 0x00,        //   Collection (Physical)
		0x09, 0x30,        //     Usage (X)
		0x09, 0x31,        //     Usage (Y)
		0x15, 0x00,        //     Logical Minimum (0)
		0x27, 0xFF, 0xFF, 0x00, 0x00,  //     Logical Maximum (65534)
		0x95, 0x02,        //     Report Count (2)
		0x75, 0x10,        //     Report Size (16)
		0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0xC0,              //   End Collection
		0xA1, 0x00,        //   Collection (Physical)
		0x09, 0x33,        //     Usage (Rx)
		0x09, 0x34,        //     Usage (Ry)
		0x15, 0x00,        //     Logical Minimum (0)
		0x27, 0xFF, 0xFF, 0x00, 0x00,  //     Logical Maximum (65534)
		0x95, 0x02,        //     Report Count (2)
		0x75, 0x10,        //     Report Size (16)
		0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0xC0,              //   End Collection
		0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
		0x09, 0x32,        //   Usage (Z)
		0x15, 0x00,        //   Logical Minimum (0)
		0x26, 0xFF, 0x03,  //   Logical Maximum (1023)
		0x95, 0x01,        //   Report Count (1)
		0x75, 0x0A,        //   Report Size (10)
		0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x15, 0x00,        //   Logical Minimum (0)
		0x25, 0x00,        //   Logical Maximum (0)
		0x75, 0x06,        //   Report Size (6)
		0x95, 0x01,        //   Report Count (1)
		0x81, 0x03,        //   Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
		0x09, 0x35,        //   Usage (Rz)
		0x15, 0x00,        //   Logical Minimum (0)
		0x26, 0xFF, 0x03,  //   Logical Maximum (1023)
		0x95, 0x01,        //   Report Count (1)
		0x75, 0x0A,        //   Report Size (10)
		0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x15, 0x00,        //   Logical Minimum (0)
		0x25, 0x00,        //   Logical Maximum (0)
		0x75, 0x06,        //   Report Size (6)
		0x95, 0x01,        //   Report Count (1)
		0x81, 0x03,        //   Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x05, 0x09,        //   Usage Page (Button)
		0x19, 0x01,        //   Usage Minimum (0x01)
		0x29, 0x0A,        //   Usage Maximum (0x0A)
		0x95, 0x0A,        //   Report Count (10)
		0x75, 0x01,        //   Report Size (1)
		0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x15, 0x00,        //   Logical Minimum (0)
		0x25, 0x00,        //   Logical Maximum (0)
		0x75, 0x06,        //   Report Size (6)
		0x95, 0x01,        //   Report Count (1)
		0x81, 0x03,        //   Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
		0x09, 0x39,        //   Usage (Hat switch)
		0x15, 0x01,        //   Logical Minimum (1)
		0x25, 0x08,        //   Logical Maximum (8)
		0x35, 0x00,        //   Physical Minimum (0)
		0x46, 0x3B, 0x01,  //   Physical Maximum (315)
		0x66, 0x14, 0x00,  //   Unit (System: English Rotation, Length: Centimeter)
		0x75, 0x04,        //   Report Size (4)
		0x95, 0x01,        //   Report Count (1)
		0x81, 0x42,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,Null State)
		0x75, 0x04,        //   Report Size (4)
		0x95, 0x01,        //   Report Count (1)
		0x15, 0x00,        //   Logical Minimum (0)
		0x25, 0x00,        //   Logical Maximum (0)
		0x35, 0x00,        //   Physical Minimum (0)
		0x45, 0x00,        //   Physical Maximum (0)
		0x65, 0x00,        //   Unit (None)
		0x81, 0x03,        //   Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0xA1, 0x02,        //   Collection (Logical)
		0x05, 0x0F,        //     Usage Page (PID Page)
		0x09, 0x97,        //     Usage (0x97)
		0x15, 0x00,        //     Logical Minimum (0)
		0x25, 0x01,        //     Logical Maximum (1)
		0x75, 0x04,        //     Report Size (4)
		0x95, 0x01,        //     Report Count (1)
		0x91, 0x02,        //     Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0x15, 0x00,        //     Logical Minimum (0)
		0x25, 0x00,        //     Logical Maximum (0)
		0x91, 0x03,        //     Output (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0x09, 0x70,        //     Usage (0x70)
		0x15, 0x00,        //     Logical Minimum (0)
		0x25, 0x64,        //     Logical Maximum (100)
		0x75, 0x08,        //     Report Size (8)
		0x95, 0x04,        //     Report Count (4)
		0x91, 0x02,        //     Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0x09, 0x50,        //     Usage (0x50)
		0x66, 0x01, 0x10,  //     Unit (System: SI Linear, Time: Seconds)
		0x55, 0x0E,        //     Unit Exponent (-2)
		0x26, 0xFF, 0x00,  //     Logical Maximum (255)
		0x95, 0x01,        //     Report Count (1)
		0x91, 0x02,        //     Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0x09, 0xA7,        //     Usage (0xA7)
		0x91, 0x02,        //     Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0x65, 0x00,        //     Unit (None)
		0x55, 0x00,        //     Unit Exponent (0)
		0x09, 0x7C,        //     Usage (0x7C)
		0x91, 0x02,        //     Output (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position,Non-volatile)
		0xC0,              //   End Collection
		0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
		0x09, 0x80,        //   Usage (Sys Control)
		0xA1, 0x00,        //   Collection (Physical)
		0x09, 0x85,        //     Usage (Sys Main Menu)
		0x15, 0x00,        //     Logical Minimum (0)
		0x25, 0x01,        //     Logical Maximum (1)
		0x95, 0x01,        //     Report Count (1)
		0x75, 0x01,        //     Report Size (1)
		0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0x15, 0x00,        //     Logical Minimum (0)
		0x25, 0x00,        //     Logical Maximum (0)
		0x75, 0x07,        //     Report Size (7)
		0x95, 0x01,        //     Report Count (1)
		0x81, 0x03,        //     Input (Const,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0xC0,              //   End Collection
		0x05, 0x06,        //   Usage Page (Generic Dev Ctrls)
		0x09, 0x20,        //   Usage (Battery Strength)
		0x15, 0x00,        //   Logical Minimum (0)
		0x26, 0xFF, 0x00,  //   Logical Maximum (255)
		0x75, 0x08,        //   Report Size (8)
		0x95, 0x01,        //   Report Count (1)
		0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
		0xC0,              // End Collection
	};

	//
	// HID class descriptor, also embedded in the configuration descriptor
	//
	const UCHAR HidDescriptor[] =
	{
		0x09,        // bLength
		0x21,        // bDescriptorType (HID)
		0x11, 0x01,  // bcdHID 1.11
		0x00,        // bCountryCode
		0x01,        // bNumDescriptors
		0x22,        // bDescriptorType[0] (Report)
		static_cast<UCHAR>(sizeof(HidReportDescriptor) & 0xFF),        // wDescriptorLength[0]
		static_cast<UCHAR>((sizeof(HidReportDescriptor) >> 8) & 0xFF)
	};

	//
	// Supported string descriptor language: American English
	//
	const UCHAR LanguageIdDescriptor[] =
	{
		0x04, 0x03, 0x09, 0x04
	};

	static_assert(sizeof(HidReportDescriptor) == 262, "Unexpected HID report descriptor size");
	static_assert(sizeof(HidDescriptor) == 9, "Unexpected HID descriptor size");

	//
	// Returns a system address for a transfer buffer that has been supplied
	// either directly or as MDL, or nullptr if there is none.
	//
	PUCHAR MapTransferBuffer(PVOID Buffer, PMDL Mdl)
	{
		if (Buffer != nullptr)
		{
			return static_cast<PUCHAR>(Buffer);
		}

		if (Mdl != nullptr)
		{
			return static_cast<PUCHAR>(MmGetSystemAddressForMdlSafe(
				Mdl,
				NormalPagePriority | MdlMappingNoExecute
			));
		}

		return nullptr;
	}

	//
	// Answers a GET_DESCRIPTOR request the way a device does: as much of the
	// descriptor as fits into the buffer gets transferred, the length of the
	// request is updated to the amount of bytes actually returned.
	//
	NTSTATUS CopyDescriptor(struct _URB_CONTROL_DESCRIPTOR_REQUEST* pRequest, const UCHAR* Descriptor, ULONG DescriptorLength)
	{
		const PUCHAR buffer = MapTransferBuffer(pRequest->TransferBuffer, pRequest->TransferBufferMDL);

		if (buffer == nullptr)
		{
			pRequest->TransferBufferLength = 0;
			return STATUS_INVALID_PARAMETER;
		}

		const ULONG length = (pRequest->TransferBufferLength < DescriptorLength)
			? pRequest->TransferBufferLength
			: DescriptorLength;

		RtlCopyMemory(buffer, Descriptor, length);
		pRequest->TransferBufferLength = length;

		return STATUS_SUCCESS;
	}

	//
	// Answers a GET_DESCRIPTOR request for a string descriptor
	//
	NTSTATUS CopyStringDescriptor(struct _URB_CONTROL_DESCRIPTOR_REQUEST* pRequest, PCWSTR String)
	{
		UCHAR descriptor[2 + (MaxStringDescriptorChars * sizeof(WCHAR))];
		ULONG chars = 0;

		if (String == nullptr)
		{
			pRequest->TransferBufferLength = 0;
			return STATUS_INVALID_PARAMETER;
		}

		RtlZeroMemory(descriptor, sizeof(descriptor));

		while (chars < MaxStringDescriptorChars && String[chars] != L'\0')
		{
			descriptor[2 + (chars * 2)] = static_cast<UCHAR>(String[chars] & 0xFF);
			descriptor[3 + (chars * 2)] = static_cast<UCHAR>((String[chars] >> 8) & 0xFF);
			chars++;
		}

		descriptor[0] = static_cast<UCHAR>(2 + (chars * 2)); // bLength
		descriptor[1] = USB_STRING_DESCRIPTOR_TYPE;          // bDescriptorType

		return CopyDescriptor(pRequest, descriptor, descriptor[0]);
	}
}

EmulationTargetXinputHid::EmulationTargetXinputHid(ULONG Serial, LONG SessionId, const XBOX_MODEL_PROFILE* Profile)
	: EmulationTargetPDO(Serial, SessionId, Profile->VendorId, Profile->ProductId),
	_Profile(Profile)
{
	//
	// Towards client applications this is an Xbox 360 target like any other,
	// which is what makes all the IOCTL_XUSB_* requests find this object.
	//
	this->_TargetType = Xbox360Wired;
	this->_UsbConfigurationDescriptionSize = ConfigurationDescriptorSize;

	//
	// Set PNP Capabilities
	//
	// Removable makes Windows assign the device a container of its own (like
	// the Xbox 360 target), so it shows up as a separate device instead of
	// being lumped together with the computer itself.
	//
	this->_PnpCapabilities.Removable = WdfTrue;
	this->_PnpCapabilities.SurpriseRemovalOK = WdfTrue;
	this->_PnpCapabilities.UniqueID = WdfTrue;

	//
	// Set Power Capabilities (same as the other HID target)
	//
	this->_PowerCapabilities.DeviceState[PowerSystemWorking] = PowerDeviceD0;
	this->_PowerCapabilities.WakeFromD0 = WdfTrue;

	KeInitializeSpinLock(&this->_ReportLock);

	//
	// Start out with everything released and both sticks centered
	//
	XUSB_REPORT neutral;
	RtlZeroMemory(&neutral, sizeof(XUSB_REPORT));
	XinputHid::FromXusbReport(&neutral, this->_Report);

	//
	// Unlike the other targets this one can take report updates at any time:
	// the most recent one is kept and handed to the HID stack as soon as it
	// starts asking. Windows may also need considerably longer than the one
	// second the bus is willing to wait when it has to install the HID
	// drivers for this device for the very first time. So tell the client
	// library right away that it is good to go, instead of failing the
	// plugin request while the device is in fact coming up just fine.
	//
	KeSetEvent(&this->_PdoBootNotificationEvent, 0, FALSE);
}

NTSTATUS EmulationTargetXinputHid::PdoPrepareDevice(PWDFDEVICE_INIT DeviceInit,
	PUNICODE_STRING DeviceId, PUNICODE_STRING DeviceDescription)
{
	NTSTATUS status;
	DECLARE_UNICODE_STRING_SIZE(buffer, _maxHardwareIdLength);
	DECLARE_CONST_UNICODE_STRING(compatibleId1, L"USB\\Class_03&SubClass_00&Prot_00");
	DECLARE_CONST_UNICODE_STRING(compatibleId2, L"USB\\Class_03&SubClass_00");
	DECLARE_CONST_UNICODE_STRING(compatibleId3, L"USB\\Class_03");

	// prepare device description
	status = RtlUnicodeStringInit(DeviceDescription, this->_Profile->DeviceDescription);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"RtlUnicodeStringInit failed with status %!STATUS!",
			status);
		return status;
	}

	//
	// Set hardware ID
	//
	// This is the one thing everything else hinges on. The HID class driver
	// derives the IDs of the HID child device from this string, turning it
	// into HID\VID_045E&PID_02FF&IG_00, which
	//
	//   - is the ID XINPUTHID.INF matches, so XINPUTHID.SYS gets loaded and
	//     provides XInput for this device, and
	//   - carries the "IG_" marker by which software tells XInput devices
	//     apart from plain HID game controllers.
	//
	// It deliberately is not one of the plain USB\VID_045E&PID_xxxx IDs of a
	// physical controller: those are claimed by the Xbox One controller
	// driver (DC1-CONTROLLER.INF), which expects a device speaking GIP.
	//
	status = RtlUnicodeStringPrintf(
		&buffer,
		L"USB\\VID_%04X&PID_%04X&IG_00",
		this->_Profile->VendorId,
		this->_Profile->MatchProductId
	);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"RtlUnicodeStringPrintf failed with status %!STATUS!",
			status);
		return status;
	}

	status = WdfPdoInitAddHardwareID(DeviceInit, &buffer);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"WdfPdoInitAddHardwareID failed with status %!STATUS!",
			status);
		return status;
	}

	status = RtlUnicodeStringCopy(DeviceId, &buffer);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"RtlUnicodeStringCopy failed with status %!STATUS!",
			status);
		return status;
	}

	//
	// Set compatible IDs (generic USB HID device, loads HIDUSB.SYS)
	//
	status = WdfPdoInitAddCompatibleID(DeviceInit, &compatibleId1);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"WdfPdoInitAddCompatibleID (#01) failed with status %!STATUS!",
			status);
		return status;
	}

	status = WdfPdoInitAddCompatibleID(DeviceInit, &compatibleId2);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"WdfPdoInitAddCompatibleID (#02) failed with status %!STATUS!",
			status);
		return status;
	}

	status = WdfPdoInitAddCompatibleID(DeviceInit, &compatibleId3);
	if (!NT_SUCCESS(status))
	{
		TraceError(
			TRACE_XIHID,
			"WdfPdoInitAddCompatibleID (#03) failed with status %!STATUS!",
			status);
		return status;
	}

	return STATUS_SUCCESS;
}

NTSTATUS EmulationTargetXinputHid::PdoPrepareHardware()
{
	//
	// Whatever the current state is, the HID stack hasn't seen it yet
	//
	InterlockedExchange(&this->_ReportDirty, 1);

	// Start pending IRP queue flush timer
	WdfTimerStart(this->_PendingUsbInRequestsTimer, WDF_REL_TIMEOUT_IN_MS(static_cast<ULONGLONG>(QueueFlushPeriod)));

	return STATUS_SUCCESS;
}

NTSTATUS EmulationTargetXinputHid::PdoInitContext()
{
	NTSTATUS status;

	TraceVerbose(TRACE_XIHID, "Initializing XInput HID context...");

	// Initialize periodic timer
	WDF_TIMER_CONFIG timerConfig;
	WDF_TIMER_CONFIG_INIT_PERIODIC(
		&timerConfig,
		PendingUsbRequestsTimerFunc,
		QueueFlushPeriod
	);

	// Timer object attributes
	WDF_OBJECT_ATTRIBUTES timerAttribs;
	WDF_OBJECT_ATTRIBUTES_INIT(&timerAttribs);

	// PDO is parent
	timerAttribs.ParentObject = this->_PdoDevice;

	// Create timer
	if (!NT_SUCCESS(status = WdfTimerCreate(
		&timerConfig,
		&timerAttribs,
		&this->_PendingUsbInRequestsTimer
	)))
	{
		TraceError(
			TRACE_XIHID,
			"WdfTimerCreate failed with status %!STATUS!",
			status);
	}

	return status;
}

VOID EmulationTargetXinputHid::GetConfigurationDescriptorType(PUCHAR Buffer, ULONG Length)
{
	const UCHAR descriptor[ConfigurationDescriptorSize] =
	{
		0x09,        // bLength
		0x02,        // bDescriptorType (Configuration)
		0x29, 0x00,  // wTotalLength 41
		0x01,        // bNumInterfaces 1
		0x01,        // bConfigurationValue
		0x00,        // iConfiguration (String Index)
		0xC0,        // bmAttributes Self Powered
		0xFA,        // bMaxPower 500mA

		0x09,        // bLength
		0x04,        // bDescriptorType (Interface)
		0x00,        // bInterfaceNumber 0
		0x00,        // bAlternateSetting
		0x02,        // bNumEndpoints 2
		0x03,        // bInterfaceClass (HID)
		0x00,        // bInterfaceSubClass
		0x00,        // bInterfaceProtocol
		0x00,        // iInterface (String Index)

		HidDescriptor[0], HidDescriptor[1], HidDescriptor[2],
		HidDescriptor[3], HidDescriptor[4], HidDescriptor[5],
		HidDescriptor[6], HidDescriptor[7], HidDescriptor[8],

		0x07,        // bLength
		0x05,        // bDescriptorType (Endpoint)
		EndpointIn,  // bEndpointAddress (IN/D2H)
		0x03,        // bmAttributes (Interrupt)
		0x40, 0x00,  // wMaxPacketSize 64
		0x05,        // bInterval 5 (unit depends on device speed)

		0x07,        // bLength
		0x05,        // bDescriptorType (Endpoint)
		EndpointOut, // bEndpointAddress (OUT/H2D)
		0x03,        // bmAttributes (Interrupt)
		0x40, 0x00,  // wMaxPacketSize 64
		0x05         // bInterval 5 (unit depends on device speed)

		// 41 bytes
	};

	RtlCopyMemory(Buffer, descriptor, (Length < sizeof(descriptor)) ? Length : sizeof(descriptor));
}

NTSTATUS EmulationTargetXinputHid::UsbGetDeviceDescriptorType(PUSB_DEVICE_DESCRIPTOR pDescriptor)
{
	pDescriptor->bLength = 0x12;
	pDescriptor->bDescriptorType = USB_DEVICE_DESCRIPTOR_TYPE;
	pDescriptor->bcdUSB = 0x0200; // USB v2.0
	pDescriptor->bDeviceClass = 0x00; // per Interface
	pDescriptor->bDeviceSubClass = 0x00;
	pDescriptor->bDeviceProtocol = 0x00;
	pDescriptor->bMaxPacketSize0 = 0x40;
	pDescriptor->idVendor = this->_VendorId;
	pDescriptor->idProduct = this->_ProductId;
	pDescriptor->bcdDevice = DeviceRevision;
	pDescriptor->iManufacturer = 0x01;
	pDescriptor->iProduct = 0x02;
	pDescriptor->iSerialNumber = 0x00;
	pDescriptor->bNumConfigurations = 0x01;

	return STATUS_SUCCESS;
}

NTSTATUS EmulationTargetXinputHid::SelectConfiguration(PURB Urb)
{
	if (Urb->UrbHeader.Length < SelectConfigurationUrbSize)
	{
		TraceEvents(TRACE_LEVEL_WARNING,
			TRACE_XIHID,
			">> >> >> URB_FUNCTION_SELECT_CONFIGURATION: Invalid ConfigurationDescriptor");
		return STATUS_INVALID_PARAMETER;
	}

	PUSBD_INTERFACE_INFORMATION pInfo = &Urb->UrbSelectConfiguration.Interface;

	TraceVerbose(
		TRACE_XIHID,
		">> >> >> URB_FUNCTION_SELECT_CONFIGURATION: Length %d, Interface %d, Alternate %d, Pipes %d",
		static_cast<int>(pInfo->Length),
		static_cast<int>(pInfo->InterfaceNumber),
		static_cast<int>(pInfo->AlternateSetting),
		pInfo->NumberOfPipes);

	pInfo->Class = 0x03; // HID
	pInfo->SubClass = 0x00;
	pInfo->Protocol = 0x00;

	pInfo->InterfaceHandle = reinterpret_cast<USBD_INTERFACE_HANDLE>(InterfaceHandle);

	pInfo->Pipes[0].MaximumTransferSize = 0x00400000;
	pInfo->Pipes[0].MaximumPacketSize = 0x40;
	pInfo->Pipes[0].EndpointAddress = EndpointIn;
	pInfo->Pipes[0].Interval = 0x05;
	pInfo->Pipes[0].PipeType = static_cast<USBD_PIPE_TYPE>(0x03);
	pInfo->Pipes[0].PipeHandle = reinterpret_cast<USBD_PIPE_HANDLE>(PipeHandleIn);
	pInfo->Pipes[0].PipeFlags = 0x00;

	pInfo->Pipes[1].MaximumTransferSize = 0x00400000;
	pInfo->Pipes[1].MaximumPacketSize = 0x40;
	pInfo->Pipes[1].EndpointAddress = EndpointOut;
	pInfo->Pipes[1].Interval = 0x05;
	pInfo->Pipes[1].PipeType = static_cast<USBD_PIPE_TYPE>(0x03);
	pInfo->Pipes[1].PipeHandle = reinterpret_cast<USBD_PIPE_HANDLE>(PipeHandleOut);
	pInfo->Pipes[1].PipeFlags = 0x00;

	return STATUS_SUCCESS;
}

void EmulationTargetXinputHid::AbortPipe()
{
	// Higher driver shutting down, emptying PDOs queues
	WdfTimerStop(this->_PendingUsbInRequestsTimer, FALSE);
}

NTSTATUS EmulationTargetXinputHid::UsbClassInterface(PURB Urb)
{
	struct _URB_CONTROL_VENDOR_OR_CLASS_REQUEST* pRequest = &Urb->UrbControlVendorClassRequest;

	const UCHAR reportType = static_cast<UCHAR>((pRequest->Value >> 8) & 0xFF);
	const PUCHAR buffer = MapTransferBuffer(pRequest->TransferBuffer, pRequest->TransferBufferMDL);

	TraceVerbose(
		TRACE_XIHID,
		">> >> >> URB_FUNCTION_CLASS_INTERFACE: TransferFlags = 0x%X, Request = 0x%X, Value = 0x%X, Index = 0x%X, BufLen = %d",
		pRequest->TransferFlags,
		pRequest->Request,
		pRequest->Value,
		pRequest->Index,
		pRequest->TransferBufferLength);

	switch (pRequest->Request)
	{
	case HidRequestGetReport:

		//
		// The current state of the controller on demand
		//
		if (reportType == HidReportTypeInput && buffer != nullptr)
		{
			KLOCK_QUEUE_HANDLE lock;
			const ULONG length = (pRequest->TransferBufferLength < XinputHid::InputReportSize)
				? pRequest->TransferBufferLength
				: XinputHid::InputReportSize;

			KeAcquireInStackQueuedSpinLock(&this->_ReportLock, &lock);
			RtlCopyMemory(buffer, this->_Report, length);
			KeReleaseInStackQueuedSpinLock(&lock);

			pRequest->TransferBufferLength = length;

			return STATUS_SUCCESS;
		}

		//
		// The descriptor declares neither feature nor readable output reports
		//
		pRequest->TransferBufferLength = 0;
		Urb->UrbHeader.Status = USBD_STATUS_STALL_PID;

		return STATUS_UNSUCCESSFUL;

	case HidRequestSetReport:

		//
		// Rumble request that didn't take the interrupt OUT endpoint
		//
		if (reportType == HidReportTypeOutput && buffer != nullptr)
		{
			this->HandleOutputReport(buffer, pRequest->TransferBufferLength);
		}

		return STATUS_SUCCESS;

	default:

		//
		// SET_IDLE, SET_PROTOCOL and friends: nothing to do but to agree.
		// Requests expecting data back get none.
		//
		if (pRequest->TransferFlags & USBD_TRANSFER_DIRECTION_IN)
		{
			pRequest->TransferBufferLength = 0;
		}

		return STATUS_SUCCESS;
	}
}

NTSTATUS EmulationTargetXinputHid::UsbGetDescriptorFromInterface(PURB Urb)
{
	struct _URB_CONTROL_DESCRIPTOR_REQUEST* pRequest = &Urb->UrbControlDescriptorRequest;

	TraceVerbose(
		TRACE_XIHID,
		">> >> >> _URB_CONTROL_DESCRIPTOR_REQUEST: Type 0x%X, Buffer Length %d",
		pRequest->DescriptorType,
		pRequest->TransferBufferLength);

	switch (pRequest->DescriptorType)
	{
	case HidDescriptorTypeReport:
		return CopyDescriptor(pRequest, HidReportDescriptor, sizeof(HidReportDescriptor));
	case HidDescriptorTypeHid:
		return CopyDescriptor(pRequest, HidDescriptor, sizeof(HidDescriptor));
	default:
		pRequest->TransferBufferLength = 0;
		return STATUS_INVALID_PARAMETER;
	}
}

NTSTATUS EmulationTargetXinputHid::UsbSelectInterface(PURB Urb)
{
	UNREFERENCED_PARAMETER(Urb);

	return STATUS_NOT_IMPLEMENTED;
}

NTSTATUS EmulationTargetXinputHid::UsbGetStringDescriptorType(PURB Urb)
{
	struct _URB_CONTROL_DESCRIPTOR_REQUEST* pRequest = &Urb->UrbControlDescriptorRequest;

	TraceVerbose(
		TRACE_XIHID,
		"Index = %d",
		pRequest->Index);

	switch (pRequest->Index)
	{
	case 0:
		return CopyDescriptor(pRequest, LanguageIdDescriptor, sizeof(LanguageIdDescriptor));
	case 1:
		return CopyStringDescriptor(pRequest, this->_Profile->ManufacturerString);
	case 2:
		return CopyStringDescriptor(pRequest, this->_Profile->ProductString);
	default:
		//
		// The device descriptor doesn't refer to any other string
		//
		pRequest->TransferBufferLength = 0;
		Urb->UrbHeader.Status = USBD_STATUS_STALL_PID;

		return STATUS_UNSUCCESSFUL;
	}
}

NTSTATUS EmulationTargetXinputHid::UsbBulkOrInterruptTransfer(_URB_BULK_OR_INTERRUPT_TRANSFER* pTransfer, WDFREQUEST Request)
{
	// Data coming FROM us TO higher driver
	if (pTransfer->TransferFlags & USBD_TRANSFER_DIRECTION_IN)
	{
		if (pTransfer->PipeHandle != reinterpret_cast<USBD_PIPE_HANDLE>(PipeHandleIn))
		{
			return STATUS_INVALID_PARAMETER;
		}

		TraceVerbose(
			TRACE_XIHID,
			">> >> >> Incoming request, queuing...");

		/* This request is sent periodically and relies on data the "feeder"
		   has to supply, so we queue this request and return with STATUS_PENDING.
		   The request gets completed as soon as the "feeder" sent an update. */
		const NTSTATUS status = WdfRequestForwardToIoQueue(Request, this->_PendingUsbInRequests);

		return (NT_SUCCESS(status)) ? STATUS_PENDING : status;
	}

	// Data coming FROM the higher driver TO us
	TraceVerbose(
		TRACE_XIHID,
		">> >> >> URB_FUNCTION_BULK_OR_INTERRUPT_TRANSFER: Handle %p, Flags %X, Length %d",
		pTransfer->PipeHandle,
		pTransfer->TransferFlags,
		pTransfer->TransferBufferLength);

	const PUCHAR buffer = MapTransferBuffer(pTransfer->TransferBuffer, pTransfer->TransferBufferMDL);

	if (buffer != nullptr)
	{
		this->HandleOutputReport(buffer, pTransfer->TransferBufferLength);
	}

	return STATUS_SUCCESS;
}

NTSTATUS EmulationTargetXinputHid::UsbControlTransfer(PURB Urb)
{
	NTSTATUS status;

	switch (Urb->UrbControlTransfer.SetupPacket[6])
	{
	case 0x14:
		//
		// This is some weird USB 1.0 condition and _must fail_
		// 
		Urb->UrbControlTransfer.Hdr.Status = USBD_STATUS_STALL_PID;
		status = STATUS_UNSUCCESSFUL;
		break;
	case 0x08:
		//
		// This is some weird USB 1.0 condition and _must fail_
		// 
		Urb->UrbControlTransfer.Hdr.Status = USBD_STATUS_STALL_PID;
		status = STATUS_UNSUCCESSFUL;
		break;
	default:
		status = STATUS_SUCCESS;
		break;
	}

	return status;
}

NTSTATUS EmulationTargetXinputHid::SubmitReportImpl(PVOID NewReport)
{
	UCHAR report[XinputHid::InputReportSize];
	KLOCK_QUEUE_HANDLE lock;
	BOOLEAN changed;

	//
	// Translate what the client sent into the report format of this device
	//
	XinputHid::FromXusbReport(&static_cast<PXUSB_SUBMIT_REPORT>(NewReport)->Report, report);

	KeAcquireInStackQueuedSpinLock(&this->_ReportLock, &lock);

	changed = (RtlCompareMemory(this->_Report, report, sizeof(report)) != sizeof(report));

	if (changed)
	{
		RtlCopyMemory(this->_Report, report, sizeof(report));
	}

	KeReleaseInStackQueuedSpinLock(&lock);

	// Don't waste pending IRP if input hasn't changed
	if (!changed)
	{
		return STATUS_SUCCESS;
	}

	//
	// Hand the new state over right away if the HID stack is waiting for
	// one, otherwise leave it to the timer. Either way it is never lost.
	//
	if (!this->CompletePendingInputRequest())
	{
		InterlockedExchange(&this->_ReportDirty, 1);
	}

	return STATUS_SUCCESS;
}

NTSTATUS EmulationTargetXinputHid::XusbGetUserIndex(PULONG UserIndex) const
{
	if (!this->IsOwnerProcess())
		return STATUS_ACCESS_DENIED;

	if (!UserIndex)
		return STATUS_INVALID_PARAMETER;

	//
	// The classic target learns its XInput slot from the LED command
	// XUSB22.SYS sends. Nothing of that sort exists here: XINPUTHID.SYS keeps
	// the slot assignment to itself. Report "not assigned" just like the
	// classic target does when it is outside of the four XInput slots.
	//
	return STATUS_INVALID_DEVICE_OBJECT_PARAMETER;
}

bool EmulationTargetXinputHid::CompletePendingInputRequest()
{
	WDFREQUEST usbRequest;

	// Get pending USB request
	if (!NT_SUCCESS(WdfIoQueueRetrieveNextRequest(this->_PendingUsbInRequests, &usbRequest)))
	{
		return false;
	}

	// Get pending IRP
	const auto pendingIrp = WdfRequestWdmGetIrp(usbRequest);

	const auto irpStack = IoGetCurrentIrpStackLocation(pendingIrp);

	// Get USB request block
	const auto urb = static_cast<PURB>(irpStack->Parameters.Others.Argument1);

	const auto pTransfer = &urb->UrbBulkOrInterruptTransfer;

	// Get transfer buffer
	const PUCHAR buffer = MapTransferBuffer(pTransfer->TransferBuffer, pTransfer->TransferBufferMDL);

	// Never write more than the requester made room for
	ULONG length = (pTransfer->TransferBufferLength < XinputHid::InputReportSize)
		? pTransfer->TransferBufferLength
		: XinputHid::InputReportSize;

	if (buffer != nullptr)
	{
		KLOCK_QUEUE_HANDLE lock;

		// Copy cached report to transfer buffer
		KeAcquireInStackQueuedSpinLock(&this->_ReportLock, &lock);
		RtlCopyMemory(buffer, this->_Report, length);
		KeReleaseInStackQueuedSpinLock(&lock);
	}
	else
	{
		length = 0;
	}

	// Set buffer length to the amount of bytes transferred
	pTransfer->TransferBufferLength = length;
	urb->UrbHeader.Status = USBD_STATUS_SUCCESS;

	// Complete pending request
	WdfRequestComplete(usbRequest, STATUS_SUCCESS);

	return true;
}

void EmulationTargetXinputHid::FillNotification(PXUSB_REQUEST_NOTIFICATION Notify, UCHAR LargeMotor, UCHAR SmallMotor) const
{
	Notify->Size = sizeof(XUSB_REQUEST_NOTIFICATION);
	Notify->SerialNo = this->_SerialNo;
	Notify->LargeMotor = LargeMotor;
	Notify->SmallMotor = SmallMotor;
	// The XInput slot is not known to this target, same value the classic
	// target reports until it has been assigned one
	Notify->LedNumber = 0xFF;
}

void EmulationTargetXinputHid::HandleOutputReport(const UCHAR* Buffer, ULONG Length)
{
	NTSTATUS status;
	WDFREQUEST notifyRequest;

	if (Length < XinputHid::OutputReportMinSize)
	{
		TraceVerbose(
			TRACE_XIHID,
			"Ignoring output report of %d bytes",
			Length);
		return;
	}

	// Extract rumble (vibration) information
	const UCHAR largeMotor = XinputHid::MotorPercentToByte(Buffer[XinputHid::OutputLargeMotorOffset]);
	const UCHAR smallMotor = XinputHid::MotorPercentToByte(Buffer[XinputHid::OutputSmallMotorOffset]);

	TraceVerbose(
		TRACE_XIHID,
		"-- Rumble: large motor %d, small motor %d",
		largeMotor,
		smallMotor);

	if (NT_SUCCESS(WdfIoQueueRetrieveNextRequest(
		this->_PendingNotificationRequests,
		&notifyRequest
	)))
	{
		PXUSB_REQUEST_NOTIFICATION notify = nullptr;

		status = WdfRequestRetrieveOutputBuffer(
			notifyRequest,
			sizeof(XUSB_REQUEST_NOTIFICATION),
			reinterpret_cast<PVOID*>(&notify),
			nullptr
		);

		if (NT_SUCCESS(status))
		{
			// Assign values to output buffer
			this->FillNotification(notify, largeMotor, smallMotor);

			WdfRequestCompleteWithInformation(notifyRequest, status, notify->Size);
		}
		else
		{
			TraceError(
				TRACE_XIHID,
				"WdfRequestRetrieveOutputBuffer failed with status %!STATUS!",
				status);

			WdfRequestComplete(notifyRequest, status);
		}
	}
	else
	{
		//
		// Nobody is waiting right now, keep it for the next request
		//
		PVOID clientBuffer, contextBuffer;

		if (NT_SUCCESS(DMF_BufferQueue_Fetch(
			this->_UsbInterruptOutBufferQueue,
			&clientBuffer,
			&contextBuffer
		)))
		{
			static_cast<PUCHAR>(clientBuffer)[0] = largeMotor;
			static_cast<PUCHAR>(clientBuffer)[1] = smallMotor;

			*static_cast<size_t*>(contextBuffer) = RumbleRecordSize;

			DMF_BufferQueue_Enqueue(this->_UsbInterruptOutBufferQueue, clientBuffer);
		}
	}
}

void EmulationTargetXinputHid::ProcessPendingNotification(WDFQUEUE Queue)
{
	NTSTATUS status;
	WDFREQUEST request;
	PVOID clientBuffer, contextBuffer;
	PXUSB_REQUEST_NOTIFICATION notify = nullptr;

	FuncEntry(TRACE_XIHID);

	//
	// Loop through and drain all queued requests until buffer is empty
	// 
	while (NT_SUCCESS(WdfIoQueueRetrieveNextRequest(Queue, &request)))
	{
		status = DMF_BufferQueue_Dequeue(
			this->_UsbInterruptOutBufferQueue,
			&clientBuffer,
			&contextBuffer
		);

		//
		// Shouldn't happen, but if so, error out
		// 
		if (!NT_SUCCESS(status))
		{
			//
			// Don't requeue request as we may be out of order now
			// 
			WdfRequestComplete(request, status);
			continue;
		}

		status = WdfRequestRetrieveOutputBuffer(
			request,
			sizeof(XUSB_REQUEST_NOTIFICATION),
			reinterpret_cast<PVOID*>(&notify),
			nullptr
		);

		if (NT_SUCCESS(status))
		{
			this->FillNotification(
				notify,
				static_cast<PUCHAR>(clientBuffer)[0],
				static_cast<PUCHAR>(clientBuffer)[1]
			);

			WdfRequestCompleteWithInformation(request, status, notify->Size);
		}
		else
		{
			WdfRequestComplete(request, status);
		}

		DMF_BufferQueue_Reuse(this->_UsbInterruptOutBufferQueue, clientBuffer);

		//
		// If no more buffer to process, exit loop and await next callback
		// 
		if (DMF_BufferQueue_Count(this->_UsbInterruptOutBufferQueue) == 0)
		{
			break;
		}
	}

	TraceVerbose(TRACE_XIHID, "%!FUNC! Exit");
}

VOID EmulationTargetXinputHid::PendingUsbRequestsTimerFunc(
	_In_ WDFTIMER Timer
)
{
	const auto ctx = static_cast<EmulationTargetXinputHid*>(Core::EmulationTargetPdoGetContext(
		WdfTimerGetParentObject(Timer))->Target);

	//
	// Nothing to do unless there is a report the HID stack hasn't received.
	// If it still isn't asking for one, try again on the next tick.
	//
	if (InterlockedExchange(&ctx->_ReportDirty, 0) != 0)
	{
		if (!ctx->CompletePendingInputRequest())
		{
			InterlockedExchange(&ctx->_ReportDirty, 1);
		}
	}
}

VOID EmulationTargetXinputHid::DmfDeviceModulesAdd(_In_ PDMFMODULE_INIT DmfModuleInit)
{
	UNREFERENCED_PARAMETER(DmfModuleInit);
}
