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

#include "EmulationTargetPDO.hpp"
#include "XboxModels.hpp"
#include <ViGEm/km/BusShared.h>
#include "XinputHidReport.hpp"

namespace ViGEm::Bus::Targets
{
	//
	// Xbox One family controller presented the way Windows exposes the real
	// thing to applications.
	//
	// A physical Xbox One/Series controller on USB is driven by XBOXGIP.SYS,
	// which creates a child device with the ID USB\VID_045E&PID_02FF&IG_00.
	// That child is an ordinary USB HID device (HIDUSB.SYS) whose HID
	// collection is matched by XINPUTHID.INF, and XINPUTHID.SYS on top of it
	// provides XInput. Games, Steam, SDL, Windows.Gaming.Input and so on only
	// ever talk to that part of the device tree.
	//
	// This target is exactly that child device: a USB HID game controller
	// carrying the report descriptor XINPUTHID.SYS expects. Everything above
	// it is stock Microsoft software, there is no vendor specific protocol
	// to emulate.
	//
	// Towards client applications it is indistinguishable from the classic
	// Xbox 360 target (EmulationTargetXUSB): it reports Xbox360Wired as its
	// type, accepts IOCTL_XUSB_SUBMIT_REPORT and answers
	// IOCTL_XUSB_REQUEST_NOTIFICATION, so existing feeders work unmodified.
	//
	class EmulationTargetXinputHid : public Core::EmulationTargetPDO
	{
	public:
		EmulationTargetXinputHid(ULONG Serial, LONG SessionId, const XBOX_MODEL_PROFILE* Profile);

		NTSTATUS PdoPrepareDevice(PWDFDEVICE_INIT DeviceInit,
			PUNICODE_STRING DeviceId,
			PUNICODE_STRING DeviceDescription) override;

		NTSTATUS PdoPrepareHardware() override;

		NTSTATUS PdoInitContext() override;

		VOID GetConfigurationDescriptorType(PUCHAR Buffer, ULONG Length) override;

		NTSTATUS UsbGetDeviceDescriptorType(PUSB_DEVICE_DESCRIPTOR pDescriptor) override;

		NTSTATUS SelectConfiguration(PURB Urb) override;

		void AbortPipe() override;

		NTSTATUS UsbClassInterface(PURB Urb) override;

		NTSTATUS UsbGetDescriptorFromInterface(PURB Urb) override;

		NTSTATUS UsbSelectInterface(PURB Urb) override;

		NTSTATUS UsbGetStringDescriptorType(PURB Urb) override;

		NTSTATUS UsbBulkOrInterruptTransfer(_URB_BULK_OR_INTERRUPT_TRANSFER* pTransfer, WDFREQUEST Request) override;

		NTSTATUS UsbControlTransfer(PURB Urb) override;

		NTSTATUS SubmitReportImpl(PVOID NewReport) override;

		NTSTATUS XusbGetUserIndex(PULONG UserIndex) const override;

	protected:
		void ProcessPendingNotification(WDFQUEUE Queue) override;

		void DmfDeviceModulesAdd(_In_ PDMFMODULE_INIT DmfModuleInit) override;

	private:
		static EVT_WDF_TIMER PendingUsbRequestsTimerFunc;

		//
		// Completes one pending interrupt IN transfer with the current input
		// report. Returns false if no transfer was pending.
		//
		bool CompletePendingInputRequest();

		//
		// Processes an output (rumble) report sent by the HID stack
		//
		void HandleOutputReport(const UCHAR* Buffer, ULONG Length);

		//
		// Populates a notification for the client library
		//
		void FillNotification(PXUSB_REQUEST_NOTIFICATION Notify, UCHAR LargeMotor, UCHAR SmallMotor) const;

		//
		// The model this device presents itself as (never null, static storage)
		//
		const XBOX_MODEL_PROFILE* _Profile;

		//
		// Current HID input report
		//
		UCHAR _Report[XinputHid::InputReportSize];

		//
		// Protects _Report
		//
		KSPIN_LOCK _ReportLock;

		//
		// Non-zero if _Report has content the HID stack hasn't received yet
		//
		LONG _ReportDirty{};

		//
		// Timer delivering reports that couldn't be handed over right away
		//
		WDFTIMER _PendingUsbInRequestsTimer{};
	};
}
