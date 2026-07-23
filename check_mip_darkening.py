#!/usr/bin/env python3
"""
check_mip_darkening.py -- find DDS files whose mip chain is darkened.

A correct box-filter mip chain preserves the average colour at every level. Textures with
heavy transparency, converted without texconv's -sepalpha, get their lower mips dragged dark
by transparent texels -- which renders as black/noisy at distance while looking fine up close.

    py check_mip_darkening.py "C:\\CemuLoad"

Reports any file whose deeper mips deviate strongly from level 0's mean brightness.
"""
import sys, os, struct

def levels(path):
    d = open(path, "rb").read()
    if len(d) < 128 or d[:4] != b'DDS ': return None
    h, w = struct.unpack("<I", d[12:16])[0], struct.unpack("<I", d[16:20])[0]
    mips = max(1, struct.unpack("<I", d[28:32])[0])
    fourcc = d[84:88]
    bpb = {b'DXT1': 8, b'ATI1': 8, b'BC4U': 8}.get(fourcc, 16)
    if fourcc not in (b'DXT1', b'DXT3', b'DXT5', b'ATI1', b'ATI2', b'BC4U', b'BC5U'): return None
    off, W, H, out = 128, w, h, []
    for lvl in range(mips):
        bw, bh = max(1, (W + 3) // 4), max(1, (H + 3) // 4)
        sz = bw * bh * bpb
        if off + sz > len(d): break
        blk, tot, n = d[off:off + sz], 0, 0
        cofs = 8 if bpb == 16 else 0          # BC2/BC3 colour starts at byte 8
        for b in range(0, sz, bpb):
            c0, c1 = struct.unpack("<HH", blk[b + cofs:b + cofs + 4])
            for c in (c0, c1):
                tot += (((c >> 11) & 0x1f) << 3) + (((c >> 5) & 0x3f) << 2) + ((c & 0x1f) << 3)
                n += 3
        out.append((lvl, W, H, tot / max(1, n)))
        off += sz; W = max(1, W >> 1); H = max(1, H >> 1)
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    root = sys.argv[1]
    bad = scanned = 0
    for dp, _, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".dds"): continue
            p = os.path.join(dp, fn)
            lv = levels(p)
            if not lv or len(lv) < 3: continue
            scanned += 1
            base = lv[0][3]
            if base < 8: continue                      # near-black base: ratio meaningless
            worst, wl = 1.0, 0
            for lvl, W, H, m in lv[1:]:
                if W < 4 or H < 4: continue            # tiny levels are noisy
                r = m / base
                if r < worst: worst, wl = r, lvl
            if worst < 0.6:                            # >40% darker than base
                bad += 1
                print("  %-52s base=%5.1f  level %d = %5.1f  (%.0f%% of base)"
                      % (fn, base, wl, worst * base, worst * 100))
    print("\nscanned %d DDS, %d with darkened mips" % (scanned, bad))
    if bad:
        print("Re-convert with texconv's -sepalpha (the updated scripts do this automatically).")

if __name__ == "__main__":
    main()
