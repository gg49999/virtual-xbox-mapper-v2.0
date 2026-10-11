// Minimal user-mode model of the kernel/WDF/DMF surface used by XinputHidPdo.cpp and XboxModels.cpp.
// Purpose: execute the real, unmodified source files and observe their behaviour. Not a WDK replacement.
#pragma once
#include <cstdint>
#include <cstring>
#include <cassert>
#include <deque>
#include <vector>
#include <string>
typedef void VOID; typedef void* PVOID; typedef unsigned char UCHAR, *PUCHAR, BYTE, BOOLEAN; typedef char CHAR; typedef unsigned short USHORT; typedef short SHORT;
typedef unsigned int ULONG, *PULONG, DWORD; typedef int LONG; typedef int32_t NTSTATUS; typedef uintptr_t ULONG_PTR; typedef long long LONGLONG; typedef unsigned long long ULONGLONG;
typedef wchar_t WCHAR; typedef const WCHAR* PCWSTR; typedef WCHAR* PWSTR; typedef int INT;
#define TRUE 1
#define FALSE 0
#define IN
#define OUT
#define _In_
#define _Out_
#define _In_opt_
#define _Inout_
#define _IRQL_requires_max_(x)
#define _Use_decl_annotations_
#define FORCEINLINE inline
#define UNREFERENCED_PARAMETER(x) (void)(x)
#define ARRAYSIZE(a) (sizeof(a)/sizeof((a)[0]))
#define NT_SUCCESS(s) (((NTSTATUS)(s)) >= 0)
#define STATUS_SUCCESS ((NTSTATUS)0)
#define STATUS_PENDING ((NTSTATUS)0x103)
#define STATUS_UNSUCCESSFUL ((NTSTATUS)0xC0000001)
#define STATUS_NOT_IMPLEMENTED ((NTSTATUS)0xC0000002)
#define STATUS_INVALID_PARAMETER ((NTSTATUS)0xC000000D)
#define STATUS_ACCESS_DENIED ((NTSTATUS)0xC0000022)
#define STATUS_BUFFER_TOO_SMALL ((NTSTATUS)0xC0000023)
#define STATUS_OBJECT_NAME_NOT_FOUND ((NTSTATUS)0xC0000034)
#define STATUS_NOT_SUPPORTED ((NTSTATUS)0xC00000BB)
#define STATUS_INVALID_DEVICE_OBJECT_PARAMETER ((NTSTATUS)0xC0000369)
#define STATUS_NO_MORE_ENTRIES ((NTSTATUS)0x8000001A)
#define RtlCopyMemory memcpy
#define RtlCopyBytes memcpy
#define RtlZeroMemory(p,n) memset((p),0,(n))
inline size_t RtlCompareMemory(const void* a, const void* b, size_t n) { size_t i = 0; auto x = (const UCHAR*)a, y = (const UCHAR*)b; while (i < n && x[i] == y[i]) i++; return i; }
struct GUID { ULONG a; USHORT b, c; UCHAR d[8]; };
#define DEFINE_GUID(n, ...) static const GUID n = {}
#define CTL_CODE(t,f,m,a) (((t)<<16)|((a)<<14)|((f)<<2)|(m))
#define FILE_DEVICE_BUS_EXTENDER 0x2a
#define METHOD_BUFFERED 0
#define FILE_READ_DATA 1
#define FILE_WRITE_DATA 2
#define KEY_READ 0x20019
// ---- strings
struct UNICODE_STRING { USHORT Length, MaximumLength; PWSTR Buffer; }; typedef UNICODE_STRING* PUNICODE_STRING; typedef const UNICODE_STRING* PCUNICODE_STRING;
#define DECLARE_UNICODE_STRING_SIZE(n, s) WCHAR n##_buffer[s] = {0}; UNICODE_STRING n = { 0, (USHORT)((s) * sizeof(WCHAR)), n##_buffer }
#define DECLARE_CONST_UNICODE_STRING(n, s) const WCHAR n##_buffer[] = s; const UNICODE_STRING n = { sizeof(s) - sizeof(WCHAR), sizeof(s), (PWSTR)n##_buffer }
inline std::u16string U(PCUNICODE_STRING s) { return std::u16string((const char16_t*)s->Buffer, s->Length / 2); }
inline NTSTATUS RtlUnicodeStringInit(PUNICODE_STRING d, PCWSTR s) { USHORT n = 0; while (s[n]) n++; d->Buffer = (PWSTR)s; d->Length = (USHORT)(n * 2); d->MaximumLength = (USHORT)(n * 2 + 2); return STATUS_SUCCESS; }
inline NTSTATUS RtlUnicodeStringCopy(PUNICODE_STRING d, PCUNICODE_STRING s) { if (s->Length > d->MaximumLength) return STATUS_BUFFER_TOO_SMALL; memcpy(d->Buffer, s->Buffer, s->Length); d->Length = s->Length; return STATUS_SUCCESS; }
// supports exactly what the driver uses: literal text and %04X taking an unsigned value
inline NTSTATUS RtlUnicodeStringPrintf(PUNICODE_STRING d, PCWSTR f, unsigned a = 0, unsigned b = 0) { unsigned args[2] = { a, b }; int ai = 0; USHORT n = 0; USHORT max = d->MaximumLength / 2;
  for (; *f; f++) { if (f[0] == L'%' && f[1] == L'0' && f[2] == L'4' && f[3] == L'X') { static const char h[] = "0123456789ABCDEF"; unsigned v = args[ai++]; for (int s = 12; s >= 0; s -= 4) { if (n >= max) return STATUS_BUFFER_TOO_SMALL; d->Buffer[n++] = (WCHAR)h[(v >> s) & 0xF]; } f += 3; }
    else { assert(*f != L'%'); if (n >= max) return STATUS_BUFFER_TOO_SMALL; d->Buffer[n++] = *f; } } d->Length = (USHORT)(n * 2); return STATUS_SUCCESS; }
// ---- kernel objects
struct MOCK { int lockDepth = 0, lockAcquires = 0, eventSets = 0, timerStarts = 0, timerStops = 0, regOpens = 0, regCloses = 0; NTSTATUS regOpenStatus = STATUS_SUCCESS, regQueryStatus = STATUS_SUCCESS; ULONG regValue = 0;
  std::vector<std::u16string> hardwareIds, compatibleIds; bool ownerProcess = true; };
inline MOCK g;
typedef uintptr_t KSPIN_LOCK; struct KLOCK_QUEUE_HANDLE { KSPIN_LOCK* l; }; struct KEVENT { int signaled; };
inline void KeInitializeSpinLock(KSPIN_LOCK* l) { *l = 0; }
inline void KeAcquireInStackQueuedSpinLock(KSPIN_LOCK* l, KLOCK_QUEUE_HANDLE* h) { assert(*l == 0 && "recursive spin lock acquisition"); *l = 1; h->l = l; g.lockDepth++; g.lockAcquires++; }
inline void KeReleaseInStackQueuedSpinLock(KLOCK_QUEUE_HANDLE* h) { assert(*h->l == 1); *h->l = 0; g.lockDepth--; }
inline LONG KeSetEvent(KEVENT* e, LONG, BOOLEAN) { e->signaled = 1; g.eventSets++; return 0; }
inline LONG InterlockedExchange(LONG* t, LONG v) { LONG o = *t; *t = v; return o; }
struct MDL { PVOID MappedSystemVa; }; typedef MDL* PMDL;
enum { NormalPagePriority = 16 };
#define MdlMappingNoExecute 0x40000000
inline PVOID MmGetSystemAddressForMdlSafe(PMDL m, ULONG) { return m->MappedSystemVa; }
enum { PowerSystemWorking = 1, PowerSystemMaximum = 7 }; enum { PowerDeviceD0 = 1 };
// ---- USB (member names as in usb.h; validated separately against the real headers)
typedef LONG USBD_STATUS; typedef PVOID USBD_PIPE_HANDLE, USBD_INTERFACE_HANDLE; typedef int USBD_PIPE_TYPE;
#define USBD_STATUS_SUCCESS ((USBD_STATUS)0)
#define USBD_STATUS_STALL_PID ((USBD_STATUS)0xC0000004)
#define USBD_TRANSFER_DIRECTION_IN 1
#define USB_DEVICE_DESCRIPTOR_TYPE 1
#define USB_STRING_DESCRIPTOR_TYPE 3
#pragma pack(push, 1)
struct USB_DEVICE_DESCRIPTOR { UCHAR bLength, bDescriptorType; USHORT bcdUSB; UCHAR bDeviceClass, bDeviceSubClass, bDeviceProtocol, bMaxPacketSize0; USHORT idVendor, idProduct, bcdDevice; UCHAR iManufacturer, iProduct, iSerialNumber, bNumConfigurations; };
#pragma pack(pop)
typedef USB_DEVICE_DESCRIPTOR* PUSB_DEVICE_DESCRIPTOR;
struct USBD_PIPE_INFORMATION { USHORT MaximumPacketSize; UCHAR EndpointAddress, Interval; USBD_PIPE_TYPE PipeType; USBD_PIPE_HANDLE PipeHandle; ULONG MaximumTransferSize, PipeFlags; };
struct USBD_INTERFACE_INFORMATION { USHORT Length; UCHAR InterfaceNumber, AlternateSetting, Class, SubClass, Protocol, Reserved; USBD_INTERFACE_HANDLE InterfaceHandle; ULONG NumberOfPipes; USBD_PIPE_INFORMATION Pipes[2]; };
typedef USBD_INTERFACE_INFORMATION* PUSBD_INTERFACE_INFORMATION;
struct _URB_HEADER { USHORT Length, Function; USBD_STATUS Status; PVOID UsbdDeviceHandle; ULONG UsbdFlags; };
struct _URB_SELECT_CONFIGURATION { _URB_HEADER Hdr; PVOID ConfigurationDescriptor, ConfigurationHandle; USBD_INTERFACE_INFORMATION Interface; };
struct _URB_CONTROL_DESCRIPTOR_REQUEST { _URB_HEADER Hdr; ULONG TransferBufferLength; PVOID TransferBuffer; PMDL TransferBufferMDL; UCHAR Index, DescriptorType; USHORT LanguageId; };
struct _URB_BULK_OR_INTERRUPT_TRANSFER { _URB_HEADER Hdr; USBD_PIPE_HANDLE PipeHandle; ULONG TransferFlags, TransferBufferLength; PVOID TransferBuffer; PMDL TransferBufferMDL; };
struct _URB_CONTROL_VENDOR_OR_CLASS_REQUEST { _URB_HEADER Hdr; ULONG TransferFlags, TransferBufferLength; PVOID TransferBuffer; PMDL TransferBufferMDL; UCHAR Request; USHORT Value, Index; };
struct _URB_CONTROL_TRANSFER { _URB_HEADER Hdr; UCHAR SetupPacket[8]; };
struct URB { union { _URB_HEADER UrbHeader; _URB_SELECT_CONFIGURATION UrbSelectConfiguration; _URB_CONTROL_DESCRIPTOR_REQUEST UrbControlDescriptorRequest; _URB_BULK_OR_INTERRUPT_TRANSFER UrbBulkOrInterruptTransfer; _URB_CONTROL_VENDOR_OR_CLASS_REQUEST UrbControlVendorClassRequest; _URB_CONTROL_TRANSFER UrbControlTransfer; }; };
typedef URB* PURB;
// ---- WDM IRP
struct IO_STACK_LOCATION { struct { struct { PVOID Argument1; } Others; } Parameters; }; struct IRP { IO_STACK_LOCATION stack; }; typedef IRP* PIRP;
inline IO_STACK_LOCATION* IoGetCurrentIrpStackLocation(PIRP i) { return &i->stack; }
// ---- WDF
struct FakeRequest { IRP irp{}; bool completed = false; NTSTATUS status = 0; ULONG_PTR information = 0; std::vector<UCHAR> out; };
struct FakeQueue { std::deque<FakeRequest*> q; };
typedef FakeRequest* WDFREQUEST; typedef FakeQueue* WDFQUEUE; typedef struct FakeDevice* WDFDEVICE; typedef PVOID WDFOBJECT; typedef struct FakeTimer* WDFTIMER; typedef struct FakeKey* WDFKEY; typedef PVOID WDFDRIVER;
typedef struct FakeInit* PWDFDEVICE_INIT;
enum WDF_TRI_STATE { WdfFalse = 0, WdfTrue = 1, WdfUseDefault = 2 };
struct WDF_DEVICE_PNP_CAPABILITIES { WDF_TRI_STATE Removable = WdfUseDefault, SurpriseRemovalOK = WdfUseDefault, UniqueID = WdfUseDefault; };
struct WDF_DEVICE_POWER_CAPABILITIES { int DeviceState[PowerSystemMaximum] = {}; WDF_TRI_STATE WakeFromD0 = WdfUseDefault; };
typedef VOID EVT_WDF_TIMER(WDFTIMER);
struct WDF_TIMER_CONFIG { EVT_WDF_TIMER* EvtTimerFunc; LONG Period; };
struct WDF_OBJECT_ATTRIBUTES { WDFOBJECT ParentObject; };
#define WDF_NO_OBJECT_ATTRIBUTES ((WDF_OBJECT_ATTRIBUTES*)nullptr)
struct FakeTimer { EVT_WDF_TIMER* fn; WDFOBJECT parent; LONG period; bool running = false; };
inline void WDF_TIMER_CONFIG_INIT_PERIODIC(WDF_TIMER_CONFIG* c, EVT_WDF_TIMER* f, LONG p) { c->EvtTimerFunc = f; c->Period = p; }
inline void WDF_OBJECT_ATTRIBUTES_INIT(WDF_OBJECT_ATTRIBUTES* a) { a->ParentObject = nullptr; }
inline NTSTATUS WdfTimerCreate(WDF_TIMER_CONFIG* c, WDF_OBJECT_ATTRIBUTES* a, WDFTIMER* t) { assert(a->ParentObject); *t = new FakeTimer{ c->EvtTimerFunc, a->ParentObject, c->Period }; return STATUS_SUCCESS; }
inline LONGLONG WDF_REL_TIMEOUT_IN_MS(ULONGLONG ms) { return -(LONGLONG)(ms * 10000); }
inline BOOLEAN WdfTimerStart(WDFTIMER t, LONGLONG due) { assert(t && due < 0); t->running = true; g.timerStarts++; return FALSE; }
inline BOOLEAN WdfTimerStop(WDFTIMER t, BOOLEAN) { assert(t); t->running = false; g.timerStops++; return TRUE; }
inline WDFOBJECT WdfTimerGetParentObject(WDFTIMER t) { return t->parent; }
inline NTSTATUS WdfIoQueueRetrieveNextRequest(WDFQUEUE q, WDFREQUEST* r) { if (q->q.empty()) return STATUS_NO_MORE_ENTRIES; *r = q->q.front(); q->q.pop_front(); return STATUS_SUCCESS; }
inline NTSTATUS WdfRequestForwardToIoQueue(WDFREQUEST r, WDFQUEUE q) { q->q.push_back(r); return STATUS_SUCCESS; }
inline PIRP WdfRequestWdmGetIrp(WDFREQUEST r) { return &r->irp; }
inline void WdfRequestComplete(WDFREQUEST r, NTSTATUS s) { assert(!r->completed && "request completed twice"); assert(g.lockDepth == 0 && "request completed while holding a spin lock"); r->completed = true; r->status = s; }
inline void WdfRequestCompleteWithInformation(WDFREQUEST r, NTSTATUS s, ULONG_PTR i) { WdfRequestComplete(r, s); r->information = i; }
inline NTSTATUS WdfRequestRetrieveOutputBuffer(WDFREQUEST r, size_t min, PVOID* b, size_t* l) { if (r->out.size() < min) return STATUS_BUFFER_TOO_SMALL; *b = r->out.data(); if (l) *l = r->out.size(); return STATUS_SUCCESS; }
inline NTSTATUS WdfPdoInitAddHardwareID(PWDFDEVICE_INIT, PCUNICODE_STRING s) { g.hardwareIds.push_back(U(s)); return STATUS_SUCCESS; }
inline NTSTATUS WdfPdoInitAddCompatibleID(PWDFDEVICE_INIT, PCUNICODE_STRING s) { g.compatibleIds.push_back(U(s)); return STATUS_SUCCESS; }
inline WDFDRIVER WdfGetDriver() { return (WDFDRIVER)1; }
inline NTSTATUS WdfDriverOpenParametersRegistryKey(WDFDRIVER, ULONG access, WDF_OBJECT_ATTRIBUTES*, WDFKEY* k) { assert(access == KEY_READ); if (!NT_SUCCESS(g.regOpenStatus)) return g.regOpenStatus; g.regOpens++; *k = (WDFKEY)1; return STATUS_SUCCESS; }
inline NTSTATUS WdfRegistryQueryULong(WDFKEY k, PCUNICODE_STRING n, PULONG v) { assert(k && U(n) == u"XusbDefaultModel"); if (!NT_SUCCESS(g.regQueryStatus)) return g.regQueryStatus; *v = g.regValue; return STATUS_SUCCESS; }
inline void WdfRegistryClose(WDFKEY k) { assert(k); g.regCloses++; }
// ---- DMF buffer queue (fixed pool, no growth - like the driver configures it)
struct FakeBufferQueue { static const int N = 64; UCHAR data[N][128]; size_t ctx[N]; std::deque<int> freeList, queued; int fetched = 0; FakeBufferQueue() { for (int i = 0; i < N; i++) freeList.push_back(i); } };
typedef FakeBufferQueue* DMFMODULE; typedef PVOID PDMFMODULE_INIT;
inline NTSTATUS DMF_BufferQueue_Fetch(DMFMODULE m, VOID** b, VOID** c) { if (m->freeList.empty()) return STATUS_UNSUCCESSFUL; int i = m->freeList.front(); m->freeList.pop_front(); m->fetched++; *b = m->data[i]; *c = &m->ctx[i]; return STATUS_SUCCESS; }
inline int bq_index(DMFMODULE m, VOID* b) { return (int)(((UCHAR*)b - &m->data[0][0]) / 128); }
inline void DMF_BufferQueue_Enqueue(DMFMODULE m, VOID* b) { m->fetched--; m->queued.push_back(bq_index(m, b)); }
inline NTSTATUS DMF_BufferQueue_Dequeue(DMFMODULE m, VOID** b, VOID** c) { if (m->queued.empty()) return STATUS_UNSUCCESSFUL; int i = m->queued.front(); m->queued.pop_front(); m->fetched++; *b = m->data[i]; *c = &m->ctx[i]; return STATUS_SUCCESS; }
inline void DMF_BufferQueue_Reuse(DMFMODULE m, VOID* b) { m->fetched--; m->freeList.push_back(bq_index(m, b)); }
inline ULONG DMF_BufferQueue_Count(DMFMODULE m) { return (ULONG)m->queued.size(); }
// ---- tracing: accepted and discarded
enum VIGEM_TRACE_FLAGS { TRACE_XIHID }; enum { TRACE_LEVEL_WARNING = 3 };
template<typename... A> inline void TraceEvents(int, VIGEM_TRACE_FLAGS, const char*, A&&...) {}
template<typename... A> inline void TraceError(VIGEM_TRACE_FLAGS, const char*, A&&...) {}
template<typename... A> inline void TraceVerbose(VIGEM_TRACE_FLAGS, const char*, A&&...) {}
inline void FuncEntry(VIGEM_TRACE_FLAGS) {}
