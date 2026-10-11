#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cstdlib>
typedef unsigned char UCHAR; typedef unsigned short USHORT; typedef short SHORT; typedef unsigned int ULONG; typedef int LONG; typedef UCHAR BYTE;
// identical to ViGEm/Common.h
typedef enum _XUSB_BUTTON { XUSB_GAMEPAD_DPAD_UP=0x0001, XUSB_GAMEPAD_DPAD_DOWN=0x0002, XUSB_GAMEPAD_DPAD_LEFT=0x0004, XUSB_GAMEPAD_DPAD_RIGHT=0x0008,
 XUSB_GAMEPAD_START=0x0010, XUSB_GAMEPAD_BACK=0x0020, XUSB_GAMEPAD_LEFT_THUMB=0x0040, XUSB_GAMEPAD_RIGHT_THUMB=0x0080, XUSB_GAMEPAD_LEFT_SHOULDER=0x0100,
 XUSB_GAMEPAD_RIGHT_SHOULDER=0x0200, XUSB_GAMEPAD_GUIDE=0x0400, XUSB_GAMEPAD_A=0x1000, XUSB_GAMEPAD_B=0x2000, XUSB_GAMEPAD_X=0x4000, XUSB_GAMEPAD_Y=0x8000 } XUSB_BUTTON;
typedef struct _XUSB_REPORT { USHORT wButtons; BYTE bLeftTrigger; BYTE bRightTrigger; SHORT sThumbLX; SHORT sThumbLY; SHORT sThumbRX; SHORT sThumbRY; } XUSB_REPORT;
#include "XinputHidReport.hpp"
using namespace ViGEm::Bus::Targets::XinputHid;
int main(int argc, char** argv) {
  if (argc == 2 && !strcmp(argv[1], "misc")) {
    for (int b = 0; b < 16; b++) printf("hat %d %d\n", b, DpadToHat((USHORT)b));
    for (int v = 0; v < 256; v++) printf("trig %d %d\n", v, TriggerTo10Bit((UCHAR)v));
    for (int v = 0; v < 256; v++) printf("motor %d %d\n", v, MotorPercentToByte((UCHAR)v));
    return 0;
  }
  XUSB_REPORT r; memset(&r, 0, sizeof r);
  r.wButtons=(USHORT)strtoul(argv[1],0,0); r.bLeftTrigger=(BYTE)atoi(argv[2]); r.bRightTrigger=(BYTE)atoi(argv[3]);
  r.sThumbLX=(SHORT)atoi(argv[4]); r.sThumbLY=(SHORT)atoi(argv[5]); r.sThumbRX=(SHORT)atoi(argv[6]); r.sThumbRY=(SHORT)atoi(argv[7]);
  UCHAR out[InputReportSize + 4]; memset(out, 0xAA, sizeof out);
  FromXusbReport(&r, out);
  for (unsigned i = 0; i < sizeof out; i++) printf("%02x", out[i]);
  printf("\n"); return 0;
}
