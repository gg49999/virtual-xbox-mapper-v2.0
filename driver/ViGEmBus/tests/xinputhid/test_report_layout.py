#!/usr/bin/env python3
"""Checks the report translation in sys/XinputHidReport.hpp against the HID
report descriptor in sys/XinputHidPdo.cpp.

The descriptor is parsed with a small, independent HID item parser. Every
generated input report is then decoded through the field positions the parser
found, so the test does not share any layout assumptions with the code under
test. Usage: test_report_layout.py <path to report_dump binary>
"""
import os, random, re, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
dump = sys.argv[1]
src = open(os.path.join(here, '..', '..', 'sys', 'XinputHidPdo.cpp')).read()
body = src[src.index('const UCHAR HidReportDescriptor[] ='):]
body = body[:body.index('};')]
d = []
for line in body.splitlines():
    d += [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', line.split('//')[0])]
assert len(d) == 262, len(d)

fields = {}
g = dict(page=0, size=0, count=0)
usages, umin, umax, bit, outbits, depth, i = [], None, None, 0, 0, 0, 0
while i < len(d):
    b = d[i]; n = b & 3; n = 4 if n == 3 else n; tag = b & 0xFC
    val = int.from_bytes(bytes(d[i + 1:i + 1 + n]), 'little'); i += 1 + n
    if tag == 0x04: g['page'] = val
    elif tag == 0x74: g['size'] = val
    elif tag == 0x94: g['count'] = val
    elif tag == 0x84: raise SystemExit('descriptor unexpectedly uses report IDs')
    elif tag == 0x08: usages.append(val)
    elif tag == 0x18: umin = val
    elif tag == 0x28: umax = val
    elif tag in (0x80, 0x90):
        if tag == 0x80:
            if not (val & 1):
                us = usages if usages else list(range(umin, umax + 1))
                for k in range(g['count']):
                    fields[(g['page'], us[k] if k < len(us) else us[-1])] = (bit + k * g['size'], g['size'])
            bit += g['size'] * g['count']
        else:
            outbits += g['size'] * g['count']
        usages, umin, umax = [], None, None
    elif tag == 0xA0: depth += 1; usages, umin, umax = [], None, None
    elif tag == 0xC0: depth -= 1; usages, umin, umax = [], None, None
assert depth == 0 and bit == 17 * 8 and outbits == 8 * 8, (depth, bit, outbits)

def get(buf, key):
    off, size = fields[key]
    return (int.from_bytes(buf, 'little') >> off) & ((1 << size) - 1)

GD, BTN, GDC = 1, 9, 6
BUTTONS = {0x1000: 1, 0x2000: 2, 0x4000: 3, 0x8000: 4, 0x0100: 5, 0x0200: 6, 0x0020: 7, 0x0010: 8, 0x0040: 9, 0x0080: 10}
HAT = {(1, 0, 0, 0): 1, (1, 0, 0, 1): 2, (0, 0, 0, 1): 3, (0, 1, 0, 1): 4, (0, 1, 0, 0): 5, (0, 1, 1, 0): 6, (0, 0, 1, 0): 7, (1, 0, 1, 0): 8}

def run(*a):
    return bytes.fromhex(subprocess.check_output([dump] + [str(x) for x in a]).decode().strip())

def check(w, lt, rt, lx, ly, rx, ry):
    raw = run(w, lt, rt, lx, ly, rx, ry)
    assert raw[17:] == b'\xaa' * 4, 'wrote past the end of the report'
    buf = raw[:17]
    assert get(buf, (GD, 0x30)) == lx + 32768 and get(buf, (GD, 0x33)) == rx + 32768
    assert get(buf, (GD, 0x31)) == 32767 - ly and get(buf, (GD, 0x34)) == 32767 - ry
    assert get(buf, (GD, 0x32)) >> 2 == lt and get(buf, (GD, 0x35)) >> 2 == rt
    for mask, index in BUTTONS.items():
        assert get(buf, (BTN, index)) == (1 if w & mask else 0), (hex(w), index)
    assert get(buf, (GD, 0x85)) == (1 if w & 0x0400 else 0)
    assert get(buf, (GDC, 0x20)) == 0x80
    u, dn, l, r = bool(w & 1), bool(w & 2), bool(w & 4), bool(w & 8)
    if u and dn: u = dn = False
    if l and r: l = r = False
    assert get(buf, (GD, 0x39)) == HAT.get((u, dn, l, r), 0), hex(w)
    v = 0
    for key, (off, size) in fields.items():
        v |= get(buf, key) << off
    assert v.to_bytes(17, 'little') == buf, 'padding bits are not zero'

count = 0
for w in [0] + [1 << b for b in range(16)] + list(range(16)) + [0xFFFF, 0xF7FF]:
    check(w, 0, 0, 0, 0, 0, 0); count += 1
for v in (0, 1, 63, 64, 127, 128, 254, 255):
    check(0, v, 255 - v, 0, 0, 0, 0); count += 1
for v in (-32768, -32767, -1, 0, 1, 32766, 32767):
    check(0, 0, 0, v, v, -1 - v, -1 - v); count += 1
random.seed(1)
for _ in range(1500):
    check(random.getrandbits(16), random.randrange(256), random.randrange(256), *[random.randint(-32768, 32767) for _ in range(4)]); count += 1

misc = subprocess.check_output([dump, 'misc']).decode().split('\n')
trig = {int(l.split()[1]): int(l.split()[2]) for l in misc if l.startswith('trig')}
assert trig[0] == 0 and trig[255] == 1023 and all(trig[v] >> 2 == v for v in range(256))
motor = {int(l.split()[1]): int(l.split()[2]) for l in misc if l.startswith('motor')}
assert motor[0] == 0 and motor[50] == 128 and all(motor[v] == 255 for v in range(100, 256)) and all(motor[v] <= motor[v + 1] for v in range(255))
print('%d reports decoded through the descriptor, all fields correct' % count)
