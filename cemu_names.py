#!/usr/bin/env python3
"""
cemu_names.py -- turn your PROVEN hash_bridge match report into Cemu load DDS.

Step 1 (your existing, working tool) -- just get the report, no --copy needed:
    py hash_bridge.py "S:\\MH3U Extract" "S:\\3ds_romfs_extract" "S:\\NGRP"
    (writes bridge_report.csv with a 'matched' row per texture)

Step 2 (this script) -- compute each Cemu hash and transcode the matched NGRP art:
    py cemu_names.py bridge_report.csv "S:\\MH3U Extract" "S:\\NGRP" "S:\\CemuLoad" ^
                     --texconv "C:\\tools\\texconv.exe"

Writes  <cemuHash>_<w>x<h>_fmt<XXXX>_mip00.dds  into CemuLoad. Drop that into
<Cemu>\\load\\textures\\ . Needs addrlib.py beside this file. Without --texconv it
only prints what it *would* build (dry run).
"""
import argparse, os, sys, csv, struct, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addrlib

TEX_BE = b"\x00XET"
FMT = {267: (0x031, "BC1_UNORM"), 268: (0x032, "BC2_UNORM"), 259: (0x01a, "R8G8B8A8_UNORM")}

def _rotl64(v, r): v &= (1 << 64) - 1; return ((v << r) | (v >> (64 - r))) & ((1 << 64) - 1)
def cemu_hash(buf):
    import numpy as np
    m = len(buf)
    if m < 256:
        u32 = np.frombuffer(buf[:m // 4 * 4], dtype='<u4'); hv = 0
        for x in u32: hv = (hv + int(x)) & 0xFFFFFFFF; hv = ((hv << 3) | (hv >> 29)) & 0xFFFFFFFF
        return hv
    u64 = np.frombuffer(buf[:m // 8 * 8], dtype='<u8'); hv = 0; step = (m // 8) // 37; idx = 0
    for _ in range(37):
        hv = (hv + int(u64[idx])) & ((1 << 64) - 1); hv = _rotl64(hv, 3); idx += step
    return (hv & 0xFFFFFFFF) ^ (hv >> 32)

def wiiu_tex_info(tex):
    if tex[:4] != TEX_BE: return None
    x = struct.unpack(">I", tex[8:12])[0]
    w = (x >> 13) & 0x1FFF; h = x & 0x1FFF
    fmt = struct.unpack(">H", tex[12:14])[0]
    if fmt not in FMT: return None, fmt
    gx2, tcf = FMT[fmt]
    try: surf = addrlib.getSurfaceInfo(gx2, w, h, 1, 1, 4, 0, 0).surfSize
    except Exception: return None, fmt
    return ("%08x" % cemu_hash(tex[16:16 + surf]), w, h, gx2, tcf), fmt

def dds_dims(path):
    try:
        d = open(path, "rb").read(20)
        return struct.unpack("<I", d[16:20])[0], struct.unpack("<I", d[12:16])[0]
    except Exception: return 0, 0

def index_pack(root):
    idx = {}
    for dp, _, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".dds"): idx[fn] = os.path.join(dp, fn)
    return idx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report"); ap.add_argument("wiiu_root")
    ap.add_argument("ngrp_pack"); ap.add_argument("out_load_dir")
    ap.add_argument("--texconv"); ap.add_argument("--no-flip", action="store_true")
    ap.add_argument("--rules", help="also write a rules.txt covering every replaced size/format")
    ap.add_argument("--manifest", help="also write a portable manifest (Cemu hash + fmt + NGRP file) so end users can convert with only NGRP")
    ap.add_argument("--title-id", default="", help="16-hex MH3U title id for the rules [Definition]")
    a = ap.parse_args()
    pack = index_pack(a.ngrp_pack)
    os.makedirs(a.out_load_dir, exist_ok=True)
    made = skipped_fmt = skipped_src = fail = 0
    groups = {}
    manifest_rows = []
    unknown_fmts = {}
    with open(a.report, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "matched": continue
            wpath = os.path.join(a.wiiu_root, row["wiiu"])
            try: tex = open(wpath, "rb").read()
            except OSError: skipped_src += 1; continue
            info, fmt = wiiu_tex_info(tex)
            if info is None:
                unknown_fmts[fmt] = unknown_fmts.get(fmt, 0) + 1; skipped_fmt += 1; continue
            ch, w, h, gx2, tcf = info
            ngrp = pack.get(row["match"]) or pack.get(os.path.basename(row.get("match", "")))
            if not ngrp: skipped_src += 1; continue
            dw, dh = dds_dims(ngrp)
            g = groups.setdefault((w, h, gx2), {}); g[(dw, dh)] = g.get((dw, dh), 0) + 1
            # filename uses the ORIGINAL Wii U size (mirrors Cemu's dump name).
            # The DDS *content* stays the upscaled NGRP size -- only the name field is original.
            out_name = "%s_%dx%d_fmt%04x_mip00.dds" % (ch, w, h, gx2)
            manifest_rows.append([ch, w, h, "%04x" % gx2, tcf, os.path.basename(ngrp)])
            if not a.texconv:
                made += 1
                if made <= 8: print("  would build %-40s <- %s" % (out_name, row["match"]))
                continue
            # write texconv output straight into out_load_dir (same drive -> rename works)
            cmd = [a.texconv, "-nologo", "-y", "-m", "0", "-f", tcf, "-o", a.out_load_dir]
            if not a.no_flip: cmd.insert(1, "-vflip")
            cmd.append(ngrp)
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                base = os.path.splitext(os.path.basename(ngrp))[0]
                produced = os.path.join(a.out_load_dir, base + ".DDS")
                if not os.path.exists(produced): produced = produced[:-4] + ".dds"
                dest = os.path.join(a.out_load_dir, out_name)
                if os.path.abspath(produced) != os.path.abspath(dest):
                    if os.path.exists(dest): os.remove(dest)
                    os.replace(produced, dest)
                made += 1
            except Exception as ex:
                fail += 1
                if fail <= 5: print("  texconv fail on %s: %s" % (row["match"], str(ex)[:80]))
    print("\n%s: %d DDS %s, %d skipped(no src), %d skipped(unknown fmt), %d texconv fails"
          % (a.out_load_dir, made, "written" if a.texconv else "would build",
             skipped_src, skipped_fmt, fail))
    if unknown_fmts:
        print("  unknown Wii U .tex formats (extend FMT map): " +
              ", ".join("fmt%d x%d" % (k, v) for k, v in unknown_fmts.items()))
    if not a.texconv:
        print("  (dry run) add --texconv \"path\\texconv.exe\" to actually build the DDS")

    if a.manifest:
        with open(a.manifest, "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f); wr.writerow(["cemu_hash","w","h","fmt","texconv_fmt","ngrp_file"])
            wr.writerows(manifest_rows)
        print("  wrote manifest (%d entries) -> %s" % (len(manifest_rows), a.manifest))
    if a.rules:
        out = ["[Definition]",
               "titleIds = " + (a.title_id or "<PUT_YOUR_16HEX_TITLE_ID_HERE>"),
               'name = "NGRP HD Textures"',
               'path = "Monster Hunter 3 Ultimate/NGRP HD"',
               "version = 7", ""]
        conflicts = 0
        for (w, h, gx2), hds in sorted(groups.items()):
            if len(hds) > 1:
                conflicts += 1
                best = max(hds.items(), key=lambda kv: kv[1])[0]
                print("  ! size conflict %dx%d fmt%04x upscales to %s -> rule uses %dx%d, the rest will stay vanilla"
                      % (w, h, gx2, sorted(hds.keys()), best[0], best[1]))
            else:
                best = next(iter(hds))
            hw, hh = best
            out += ["[TextureRedefine]", "width = %d" % w, "height = %d" % h,
                    "formats = 0x%03x" % gx2, "overwriteWidth = %d" % hw,
                    "overwriteHeight = %d" % hh, ""]
        with open(a.rules, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
        print("  wrote rules.txt (%d rules, %d conflict groups) -> %s" % (len(groups), conflicts, a.rules))
        if not a.title_id:
            print("  NOTE: set titleIds in %s (right-click the game in Cemu -> title id), or pass --title-id" % a.rules)

if __name__ == "__main__":
    main()
