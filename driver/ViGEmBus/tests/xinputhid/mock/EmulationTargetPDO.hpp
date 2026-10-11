// Stand-in for the base class: same member names and virtual interface as sys/EmulationTargetPDO.hpp
#pragma once
#include "fakekernel.h"
#include <ViGEm/Common.h>
namespace ViGEm::Bus::Core {
  class EmulationTargetPDO {
  public:
    EmulationTargetPDO(ULONG Serial, LONG SessionId, USHORT VendorId, USHORT ProductId) : _SerialNo(Serial), _SessionId(SessionId), _VendorId(VendorId), _ProductId(ProductId) { _PdoBootNotificationEvent.signaled = 0; }
    virtual ~EmulationTargetPDO() = default;
    virtual NTSTATUS PdoPrepareDevice(PWDFDEVICE_INIT, PUNICODE_STRING, PUNICODE_STRING) = 0;
    virtual NTSTATUS PdoPrepareHardware() = 0;
    virtual NTSTATUS PdoInitContext() = 0;
    virtual NTSTATUS UsbGetDeviceDescriptorType(PUSB_DEVICE_DESCRIPTOR) = 0;
    virtual NTSTATUS UsbClassInterface(PURB) = 0;
    virtual NTSTATUS UsbGetDescriptorFromInterface(PURB) = 0;
    virtual NTSTATUS UsbSelectInterface(PURB) = 0;
    virtual NTSTATUS UsbGetStringDescriptorType(PURB) = 0;
    virtual NTSTATUS UsbBulkOrInterruptTransfer(struct _URB_BULK_OR_INTERRUPT_TRANSFER*, WDFREQUEST) = 0;
    virtual NTSTATUS UsbControlTransfer(PURB) = 0;
    bool IsOwnerProcess() const { return g.ownerProcess; }
    virtual NTSTATUS XusbGetUserIndex(PULONG UserIndex) const { UNREFERENCED_PARAMETER(UserIndex); return STATUS_NOT_SUPPORTED; }
    // exposed for the test
    virtual VOID GetConfigurationDescriptorType(PUCHAR, ULONG) = 0;
    virtual NTSTATUS SelectConfiguration(PURB) = 0;
    virtual void AbortPipe() = 0;
    virtual NTSTATUS SubmitReportImpl(PVOID) = 0;
    virtual VOID ProcessPendingNotification(WDFQUEUE) = 0;
    virtual void DmfDeviceModulesAdd(PDMFMODULE_INIT) = 0;
    static const ULONG _maxHardwareIdLength = 0xFF;
    WDF_DEVICE_PNP_CAPABILITIES _PnpCapabilities; WDF_DEVICE_POWER_CAPABILITIES _PowerCapabilities;
    ULONG _SerialNo{}; LONG _SessionId{}; VIGEM_TARGET_TYPE _TargetType; USHORT _VendorId{}; USHORT _ProductId{};
    WDFQUEUE _PendingUsbInRequests{}; WDFQUEUE _PendingNotificationRequests{}; WDFDEVICE _PdoDevice{}; ULONG _UsbConfigurationDescriptionSize{}; KEVENT _PdoBootNotificationEvent; DMFMODULE _UsbInterruptOutBufferQueue{};
  };
  struct EMULATION_TARGET_PDO_CONTEXT { EmulationTargetPDO* Target; };
  inline EMULATION_TARGET_PDO_CONTEXT* EmulationTargetPdoGetContext(WDFOBJECT o) { return (EMULATION_TARGET_PDO_CONTEXT*)o; }
}
