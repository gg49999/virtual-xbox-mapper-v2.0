#include <cstdio>
#define private public
#define protected public
#include "XinputHidPdo.hpp"
#undef private
#undef protected
using namespace ViGEm::Bus::Targets;
using ViGEm::Bus::Core::EMULATION_TARGET_PDO_CONTEXT;
static int checks = 0;
#define CHECK(c) do { checks++; if (!(c)) { printf("FAILED line %d: %s\n", __LINE__, #c); return 1; } } while (0)
static const UCHAR Expected[] = {
#include "expected_descriptor.inc"
};
struct Rig {
  FakeQueue in, notify; FakeBufferQueue bq; EMULATION_TARGET_PDO_CONTEXT ctx{}; EmulationTargetXinputHid* t;
  Rig(const XBOX_MODEL_PROFILE* p, ULONG serial = 1) { t = new EmulationTargetXinputHid(serial, 100, p); ctx.Target = t;
    t->_PdoDevice = (WDFDEVICE)&ctx; t->_PendingUsbInRequests = &in; t->_PendingNotificationRequests = &notify; t->_UsbInterruptOutBufferQueue = &bq; }
  ~Rig() { delete t->_PendingUsbInRequestsTimer; delete t; }
  void tick() { t->_PendingUsbInRequestsTimer->fn(t->_PendingUsbInRequestsTimer); }
};
struct InReq { FakeRequest req; URB urb{}; UCHAR buf[64]; MDL mdl{};
  InReq(ULONG len = 17, bool useMdl = false, ULONG_PTR pipe = 0xFFFF0084) { memset(buf, 0xEE, sizeof buf); auto& x = urb.UrbBulkOrInterruptTransfer; x.PipeHandle = (PVOID)pipe; x.TransferFlags = USBD_TRANSFER_DIRECTION_IN; x.TransferBufferLength = len;
    if (useMdl) { mdl.MappedSystemVa = buf; x.TransferBufferMDL = &mdl; } else x.TransferBuffer = buf; req.irp.stack.Parameters.Others.Argument1 = &urb; urb.UrbHeader.Status = (USBD_STATUS)0x12345678; } };
static NTSTATUS sendOut(Rig& r, const UCHAR* d, ULONG n) { FakeRequest req; URB u{}; UCHAR b[64]; memcpy(b, d, n); auto& x = u.UrbBulkOrInterruptTransfer; x.PipeHandle = (PVOID)(ULONG_PTR)0xFFFF0003; x.TransferBufferLength = n; x.TransferBuffer = b; return r.t->UsbBulkOrInterruptTransfer(&x, &req); }
static NTSTATUS submit(Rig& r, USHORT w, BYTE lt = 0, BYTE rt = 0, SHORT lx = 0, SHORT ly = 0, SHORT rx = 0, SHORT ry = 0) { XUSB_SUBMIT_REPORT s; XUSB_SUBMIT_REPORT_INIT(&s, 1); s.Report.wButtons = w; s.Report.bLeftTrigger = lt; s.Report.bRightTrigger = rt; s.Report.sThumbLX = lx; s.Report.sThumbLY = ly; s.Report.sThumbRX = rx; s.Report.sThumbRY = ry; return r.t->SubmitReportImpl(&s); }
static NTSTATUS getDesc(Rig& r, bool string, UCHAR typeOrIndex, UCHAR* buf, ULONG& len, bool useMdl = false) { URB u{}; MDL m{ buf }; auto& q = u.UrbControlDescriptorRequest; q.TransferBufferLength = len; if (useMdl) q.TransferBufferMDL = &m; else q.TransferBuffer = buf;
  NTSTATUS s; if (string) { q.Index = typeOrIndex; q.DescriptorType = 3; s = r.t->UsbGetStringDescriptorType(&u); } else { q.DescriptorType = typeOrIndex; s = r.t->UsbGetDescriptorFromInterface(&u); } len = q.TransferBufferLength; return s; }
static NTSTATUS classReq(Rig& r, UCHAR request, UCHAR type, bool in, UCHAR* buf, ULONG& len, USBD_STATUS* usbd = nullptr) { URB u{}; auto& q = u.UrbControlVendorClassRequest; q.Request = request; q.Value = (USHORT)(type << 8); q.TransferFlags = in ? USBD_TRANSFER_DIRECTION_IN : 0; q.TransferBufferLength = len; q.TransferBuffer = buf; NTSTATUS s = r.t->UsbClassInterface(&u); len = q.TransferBufferLength; if (usbd) *usbd = u.UrbHeader.Status; return s; }
static const UCHAR Neutral[17] = { 0x00,0x80, 0xFF,0x7F, 0x00,0x80, 0xFF,0x7F, 0,0, 0,0, 0,0, 0, 0, 0x80 };

int main() {
  // ---------- model selection ----------
  CHECK(XboxModelLookupByModel(XboxModel360) == nullptr && XboxModelLookupByModel(XboxModelMax) == nullptr && XboxModelLookupByModel(0xFFFFFFFF) == nullptr);
  for (ULONG m = XboxModelOne; m < XboxModelMax; m++) { auto p = XboxModelLookupByModel(m); CHECK(p && p->Model == m && p->VendorId == 0x045E && p->MatchProductId == 0x02FF && XboxModelLookupByIds(p->VendorId, p->ProductId) == p); }
  CHECK(XboxModelLookupByModel(XboxModelSeries)->ProductId == 0x0B12 && XboxModelLookupByModel(XboxModelSeriesBluetooth)->ProductId == 0x0B13 && XboxModelLookupByModel(XboxModelOneS)->ProductId == 0x02EA && XboxModelLookupByModel(XboxModelEliteSeries2)->ProductId == 0x0B00 && XboxModelLookupByModel(XboxModelOne)->ProductId == 0x02FF);
  g.regValue = 0;  CHECK(XboxModelResolve(0x045E, 0x028E) == nullptr && XboxModelResolve(0, 0) == nullptr);        // nothing configured: classic
  g.regValue = 4;  CHECK(XboxModelResolve(0x045E, 0x028E) == XboxModelLookupByModel(XboxModelSeries) && XboxModelResolve(0, 0) == XboxModelLookupByModel(XboxModelSeries) && XboxModelResolve(0x045E, 0) == XboxModelLookupByModel(XboxModelSeries));
  CHECK(XboxModelResolve(0x045E, 0x0B13) == XboxModelLookupByModel(XboxModelSeriesBluetooth));                      // explicit IDs win over the default
  CHECK(XboxModelResolve(0x046D, 0xC21F) == nullptr && XboxModelResolve(0x045E, 0x0719) == nullptr);                // unknown IDs stay classic
  g.regValue = 6;  CHECK(XboxModelResolve(0x045E, 0x028E) == nullptr); g.regValue = 0xFFFFFFFF; CHECK(XboxModelResolve(0x045E, 0x028E) == nullptr);   // out of range: classic
  g.regValue = 0;  CHECK(XboxModelResolve(0x045E, 0x02FF) == XboxModelLookupByModel(XboxModelOne));                 // explicit modern IDs work without any registry setting
  g.regValue = 2; g.regQueryStatus = STATUS_OBJECT_NAME_NOT_FOUND; CHECK(XboxModelResolve(0x045E, 0x028E) == nullptr); g.regQueryStatus = STATUS_SUCCESS;
  CHECK(g.regOpens > 0 && g.regOpens == g.regCloses);                                                               // key always closed
  { int o = g.regOpens; g.regOpenStatus = STATUS_UNSUCCESSFUL; CHECK(XboxModelResolve(0x045E, 0x028E) == nullptr && g.regOpens == o && g.regCloses == o); g.regOpenStatus = STATUS_SUCCESS; }
  { int o = g.regOpens; XboxModelResolve(0x045E, 0x0B12); CHECK(g.regOpens == o); }                                 // explicit IDs never touch the registry

  for (ULONG m = XboxModelOne; m < XboxModelMax; m++) {
    const XBOX_MODEL_PROFILE* p = XboxModelLookupByModel(m); g.hardwareIds.clear(); g.compatibleIds.clear(); int ev = g.eventSets;
    Rig r(p); auto t = r.t;
    // ---------- construction / identity ----------
    CHECK(g.eventSets == ev + 1 && t->_PdoBootNotificationEvent.signaled == 1);
    CHECK(t->_TargetType == Xbox360Wired && t->_UsbConfigurationDescriptionSize == 41 && t->_VendorId == p->VendorId && t->_ProductId == p->ProductId);
    CHECK(t->_PnpCapabilities.Removable == WdfTrue && t->_PnpCapabilities.SurpriseRemovalOK == WdfTrue && t->_PnpCapabilities.UniqueID == WdfTrue);
    WCHAR idBuf[80] = { 0 }; UNICODE_STRING id = { 0, sizeof idBuf, idBuf }, desc{};
    CHECK(t->PdoPrepareDevice(nullptr, &id, &desc) == STATUS_SUCCESS);
    CHECK(g.hardwareIds.size() == 1 && g.hardwareIds[0] == u"USB\\VID_045E&PID_02FF&IG_00" && U(&id) == u"USB\\VID_045E&PID_02FF&IG_00");
    CHECK(g.compatibleIds.size() == 3 && g.compatibleIds[0] == u"USB\\Class_03&SubClass_00&Prot_00" && g.compatibleIds[1] == u"USB\\Class_03&SubClass_00" && g.compatibleIds[2] == u"USB\\Class_03");
    CHECK(U(&desc) == std::u16string((const char16_t*)p->DeviceDescription) && U(&desc).rfind(u"Virtual Xbox ", 0) == 0);
    USB_DEVICE_DESCRIPTOR dd{}; CHECK(t->UsbGetDeviceDescriptorType(&dd) == STATUS_SUCCESS && dd.bLength == 18 && dd.idVendor == p->VendorId && dd.idProduct == p->ProductId && dd.bDeviceClass == 0 && dd.iManufacturer == 1 && dd.iProduct == 2 && dd.iSerialNumber == 0 && dd.bNumConfigurations == 1);
    // ---------- configuration descriptor ----------
    UCHAR cfg[64]; memset(cfg, 0xEE, sizeof cfg); t->GetConfigurationDescriptorType(cfg, 9); CHECK(cfg[0] == 9 && cfg[1] == 2 && cfg[2] == 41 && cfg[3] == 0 && cfg[9] == 0xEE);
    t->GetConfigurationDescriptorType(cfg, 41); CHECK(cfg[41] == 0xEE);
    { ULONG off = 0; int ifaces = 0, eps = 0, hid = 0; while (off < 41) { UCHAR l = cfg[off], ty = cfg[off + 1]; CHECK(l >= 2 && off + l <= 41);
        if (ty == 4) { ifaces++; CHECK(cfg[off + 4] == 2 && cfg[off + 5] == 3 && cfg[off + 6] == 0 && cfg[off + 7] == 0); }
        if (ty == 0x21) { hid++; CHECK(l == 9 && cfg[off + 5] == 1 && cfg[off + 6] == 0x22 && (cfg[off + 7] | (cfg[off + 8] << 8)) == 262); }
        if (ty == 5) { eps++; CHECK(l == 7 && cfg[off + 3] == 3 && (cfg[off + 2] == 0x84 || cfg[off + 2] == 0x03) && cfg[off + 4] == 0x40); }
        off += l; } CHECK(off == 41 && ifaces == 1 && eps == 2 && hid == 1 && cfg[4] == 1); }
    { URB u{}; u.UrbHeader.Length = 0x70; CHECK(t->SelectConfiguration(&u) == STATUS_SUCCESS); auto& i = u.UrbSelectConfiguration.Interface; CHECK(i.Class == 3 && i.Pipes[0].EndpointAddress == 0x84 && i.Pipes[0].PipeHandle == (PVOID)(ULONG_PTR)0xFFFF0084 && i.Pipes[1].EndpointAddress == 0x03 && i.Pipes[1].PipeHandle == (PVOID)(ULONG_PTR)0xFFFF0003 && i.Pipes[0].PipeType == 3);
      URB s{}; s.UrbHeader.Length = 0x6F; CHECK(t->SelectConfiguration(&s) == STATUS_INVALID_PARAMETER); }
    // ---------- HID descriptors ----------
    UCHAR big[400]; ULONG len;
    memset(big, 0xEE, sizeof big); len = 262 + 64; CHECK(getDesc(r, false, 0x22, big, len) == STATUS_SUCCESS && len == 262 && sizeof Expected == 262 && !memcmp(big, Expected, 262) && big[262] == 0xEE);
    memset(big, 0xEE, sizeof big); len = 262;      CHECK(getDesc(r, false, 0x22, big, len, true) == STATUS_SUCCESS && len == 262 && !memcmp(big, Expected, 262) && big[262] == 0xEE);   // MDL supplied buffer
    memset(big, 0xEE, sizeof big); len = 100;      CHECK(getDesc(r, false, 0x22, big, len) == STATUS_SUCCESS && len == 100 && !memcmp(big, Expected, 100) && big[100] == 0xEE);         // short buffer: truncated, no overrun
    memset(big, 0xEE, sizeof big); len = 64;       CHECK(getDesc(r, false, 0x21, big, len) == STATUS_SUCCESS && len == 9 && big[0] == 9 && big[1] == 0x21 && (big[7] | (big[8] << 8)) == 262 && big[9] == 0xEE);
    len = 64; CHECK(!NT_SUCCESS(getDesc(r, false, 0x23, big, len)) && len == 0);
    { URB u{}; u.UrbControlDescriptorRequest.DescriptorType = 0x22; u.UrbControlDescriptorRequest.TransferBufferLength = 262; CHECK(!NT_SUCCESS(t->UsbGetDescriptorFromInterface(&u)) && u.UrbControlDescriptorRequest.TransferBufferLength == 0); }   // no buffer at all
    // ---------- string descriptors ----------
    memset(big, 0xEE, sizeof big); len = 255; CHECK(getDesc(r, true, 0, big, len) == STATUS_SUCCESS && len == 4 && big[0] == 4 && big[1] == 3 && big[2] == 9 && big[3] == 4 && big[4] == 0xEE);
    for (int idx = 1; idx <= 2; idx++) { std::u16string want((const char16_t*)(idx == 1 ? p->ManufacturerString : p->ProductString)); ULONG full = (ULONG)(2 + want.size() * 2);
      memset(big, 0xEE, sizeof big); len = 4;   CHECK(getDesc(r, true, (UCHAR)idx, big, len) == STATUS_SUCCESS && len == 4 && big[0] == full && big[1] == 3 && big[4] == 0xEE);          // length probe
      memset(big, 0xEE, sizeof big); len = 255; CHECK(getDesc(r, true, (UCHAR)idx, big, len) == STATUS_SUCCESS && len == full && big[0] == full && big[1] == 3 && big[full] == 0xEE);
      CHECK(std::u16string((const char16_t*)(big + 2), want.size()) == want); }
    len = 255; CHECK(!NT_SUCCESS(getDesc(r, true, 3, big, len)) && len == 0);
    // ---------- input reports ----------
    CHECK(t->PdoInitContext() == STATUS_SUCCESS && t->_PendingUsbInRequestsTimer && t->_PendingUsbInRequestsTimer->period == 5 && !t->_PendingUsbInRequestsTimer->running);
    CHECK(submit(r, XUSB_GAMEPAD_A) == STATUS_SUCCESS);                                           // client is allowed to feed before the HID stack is up...
    int ts = g.timerStarts; CHECK(t->PdoPrepareHardware() == STATUS_SUCCESS && g.timerStarts == ts + 1 && t->_PendingUsbInRequestsTimer->running);
    r.tick(); CHECK(r.in.q.empty());                                                              // nobody asking yet: nothing happens
    InReq a; CHECK(t->UsbBulkOrInterruptTransfer(&a.urb.UrbBulkOrInterruptTransfer, &a.req) == STATUS_PENDING && r.in.q.size() == 1 && !a.req.completed);
    r.tick(); CHECK(a.req.completed && a.req.status == STATUS_SUCCESS && a.urb.UrbBulkOrInterruptTransfer.TransferBufferLength == 17 && a.urb.UrbHeader.Status == USBD_STATUS_SUCCESS);
    CHECK(a.buf[12] == 0x01 && a.buf[17] == 0xEE && !memcmp(a.buf, Neutral, 12));               // ...and that state is the first thing delivered
    InReq b, c; t->UsbBulkOrInterruptTransfer(&b.urb.UrbBulkOrInterruptTransfer, &b.req); t->UsbBulkOrInterruptTransfer(&c.urb.UrbBulkOrInterruptTransfer, &c.req);
    r.tick(); r.tick(); CHECK(!b.req.completed && !c.req.completed);                              // no change: requests stay pending, no chatter
    CHECK(submit(r, XUSB_GAMEPAD_A) == STATUS_SUCCESS && !b.req.completed);                       // identical report: still nothing
    CHECK(submit(r, 0, 255, 0, 32767, 32767) == STATUS_SUCCESS && b.req.completed && !c.req.completed);   // change: delivered immediately, one request per report
    CHECK(b.urb.UrbBulkOrInterruptTransfer.TransferBufferLength == 17 && b.buf[0] == 0xFF && b.buf[1] == 0xFF && b.buf[2] == 0 && b.buf[3] == 0 && b.buf[8] == 0xFF && b.buf[9] == 0x03 && b.buf[12] == 0 && b.buf[16] == 0x80 && b.buf[17] == 0xEE);
    CHECK(submit(r, XUSB_GAMEPAD_GUIDE | XUSB_GAMEPAD_DPAD_LEFT) == STATUS_SUCCESS && c.req.completed && c.buf[15] == 1 && c.buf[14] == 7);
    CHECK(submit(r, XUSB_GAMEPAD_B) == STATUS_SUCCESS && submit(r, XUSB_GAMEPAD_Y) == STATUS_SUCCESS);   // two changes with nobody listening: latest one is kept
    r.tick(); InReq d(17, true); t->UsbBulkOrInterruptTransfer(&d.urb.UrbBulkOrInterruptTransfer, &d.req); CHECK(!d.req.completed);
    r.tick(); CHECK(d.req.completed && d.buf[12] == 0x08 && d.urb.UrbBulkOrInterruptTransfer.TransferBufferLength == 17);       // delivered by the timer, into an MDL buffer
    InReq e(8); t->UsbBulkOrInterruptTransfer(&e.urb.UrbBulkOrInterruptTransfer, &e.req); CHECK(submit(r, 0) == STATUS_SUCCESS && e.req.completed && e.urb.UrbBulkOrInterruptTransfer.TransferBufferLength == 8 && e.buf[8] == 0xEE);   // undersized buffer: no overrun
    InReq f(17); f.urb.UrbBulkOrInterruptTransfer.TransferBuffer = nullptr; t->UsbBulkOrInterruptTransfer(&f.urb.UrbBulkOrInterruptTransfer, &f.req); CHECK(submit(r, XUSB_GAMEPAD_X) == STATUS_SUCCESS && f.req.completed && f.urb.UrbBulkOrInterruptTransfer.TransferBufferLength == 0);   // no buffer: no write
    InReq w(17, false, 0xFFFF0081); CHECK(t->UsbBulkOrInterruptTransfer(&w.urb.UrbBulkOrInterruptTransfer, &w.req) == STATUS_INVALID_PARAMETER && r.in.q.empty());
    { UCHAR rep[32]; memset(rep, 0xEE, sizeof rep); ULONG l = 32; CHECK(classReq(r, 0x01, 0x01, true, rep, l) == STATUS_SUCCESS && l == 17 && rep[12] == 0x04 && rep[17] == 0xEE);   // GET_REPORT(Input) = current state
      l = 32; USBD_STATUS us = 0; CHECK(!NT_SUCCESS(classReq(r, 0x01, 0x03, true, rep, l, &us)) && l == 0 && us == USBD_STATUS_STALL_PID);                                          // no feature reports
      l = 0;  CHECK(classReq(r, 0x0A, 0, false, nullptr, l) == STATUS_SUCCESS);                                                                                                    // SET_IDLE
      l = 8;  CHECK(classReq(r, 0x02, 0, true, rep, l) == STATUS_SUCCESS && l == 0); }                                                                                             // GET_IDLE: no data
    // ---------- rumble ----------
    const UCHAR rum[8] = { 0x0F, 0, 0, 100, 50, 0xFF, 0, 0xEB };
    FakeRequest n1; n1.out.resize(sizeof(XUSB_REQUEST_NOTIFICATION)); r.notify.q.push_back(&n1);
    CHECK(sendOut(r, rum, 8) == STATUS_SUCCESS && n1.completed && n1.status == STATUS_SUCCESS && n1.information == sizeof(XUSB_REQUEST_NOTIFICATION));
    { auto x = (PXUSB_REQUEST_NOTIFICATION)n1.out.data(); CHECK(x->Size == sizeof(XUSB_REQUEST_NOTIFICATION) && x->SerialNo == 1 && x->LargeMotor == 255 && x->SmallMotor == 128 && x->LedNumber == 0xFF); }
    const UCHAR off[8] = { 0x0F, 0, 0, 0, 0, 0xFF, 0, 0xEB }, q25[8] = { 0x0F, 0, 0, 25, 200, 0, 0, 0 };
    CHECK(sendOut(r, q25, 8) == STATUS_SUCCESS && r.bq.queued.size() == 1 && r.bq.fetched == 0);  // nobody waiting: buffered
    { UCHAR o[8]; memcpy(o, off, 8); ULONG l = 8; CHECK(classReq(r, 0x09, 0x02, false, o, l) == STATUS_SUCCESS && r.bq.queued.size() == 2); }      // SET_REPORT(Output) takes the same path
    FakeRequest n2; n2.out.resize(sizeof(XUSB_REQUEST_NOTIFICATION)); FakeQueue arriving; arriving.q.push_back(&n2); t->ProcessPendingNotification(&arriving);
    { auto x = (PXUSB_REQUEST_NOTIFICATION)n2.out.data(); CHECK(n2.completed && x->LargeMotor == 64 && x->SmallMotor == 255 && x->SerialNo == 1 && r.bq.queued.size() == 1 && r.bq.fetched == 0); }   // oldest first, 200% clamped
    FakeRequest n3; n3.out.resize(sizeof(XUSB_REQUEST_NOTIFICATION)); arriving.q.push_back(&n3); t->ProcessPendingNotification(&arriving);
    { auto x = (PXUSB_REQUEST_NOTIFICATION)n3.out.data(); CHECK(n3.completed && x->LargeMotor == 0 && x->SmallMotor == 0 && r.bq.queued.empty() && r.bq.freeList.size() == 64); }
    FakeRequest tiny; tiny.out.resize(4); r.notify.q.push_back(&tiny); CHECK(sendOut(r, rum, 8) == STATUS_SUCCESS && tiny.completed && !NT_SUCCESS(tiny.status));   // malformed listener request is failed, not leaked
    CHECK(sendOut(r, rum, 3) == STATUS_SUCCESS && r.bq.queued.empty());                           // runt report ignored
    for (int i = 0; i < 200; i++) CHECK(sendOut(r, rum, 8) == STATUS_SUCCESS);                    // flood without a listener: bounded, nothing leaks
    CHECK(r.bq.queued.size() == 64 && r.bq.freeList.empty() && r.bq.fetched == 0);
    // ---------- misc ----------
    ULONG ui = 77; CHECK(t->XusbGetUserIndex(&ui) == STATUS_INVALID_DEVICE_OBJECT_PARAMETER && ui == 77 && t->XusbGetUserIndex(nullptr) == STATUS_INVALID_PARAMETER);
    g.ownerProcess = false; CHECK(t->XusbGetUserIndex(&ui) == STATUS_ACCESS_DENIED); g.ownerProcess = true;
    { URB u{}; u.UrbControlTransfer.SetupPacket[6] = 0x14; CHECK(!NT_SUCCESS(t->UsbControlTransfer(&u))); URB v{}; CHECK(t->UsbControlTransfer(&v) == STATUS_SUCCESS); CHECK(t->UsbSelectInterface(&v) == STATUS_NOT_IMPLEMENTED); }
    int st = g.timerStops; t->AbortPipe(); CHECK(g.timerStops == st + 1 && !t->_PendingUsbInRequestsTimer->running);
    CHECK(g.lockDepth == 0 && g.lockAcquires > 0);
  }
  printf("%d checks passed across %d models\n", checks, (int)XboxModelMax - 1);
  return 0;
}
