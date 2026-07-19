#!/usr/bin/env python3
"""
convert_from_manifest.py -- the EASY path (no Wii U extraction, no 3DS needed).

Takes a prebuilt manifest (Cemu hash + format + which NGRP file) and your copy of the
NGRP pack, and writes Cemu-ready DDS. Use this if you just want the textures and were
given a manifest.csv.

    py convert_from_manifest.py manifest.csv "C:\\NGRP" "C:\\CemuLoad" --texconv "C:\\texconv.exe"

Then drop everything in CemuLoad into  <Cemu>\\load\\textures\\ .

Notes:
- The manifest is tied to a specific NGRP version. If NGRP has updated, regenerate the
  manifest with the full pipeline (see the README) or ask for an updated manifest.
- Get texconv from: https://github.com/microsoft/DirectXTex/releases
"""
import argparse, os, csv, subprocess

def index_pack(root):
    idx = {}
    for dp, _, files in os.walk(root):
        for fn in files:
            if fn.lower().endswith(".dds"):
                idx[fn] = os.path.join(dp, fn)
    return idx

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest"); ap.add_argument("ngrp_pack"); ap.add_argument("out_load_dir")
    ap.add_argument("--texconv"); ap.add_argument("--no-flip", action="store_true")
    a = ap.parse_args()
    pack = index_pack(a.ngrp_pack)
    os.makedirs(a.out_load_dir, exist_ok=True)
    made = miss = fail = 0
    with open(a.manifest, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ch, w, h = row["cemu_hash"], int(row["w"]), int(row["h"])
            gx2, tcf, ngrp_file = row["fmt"], row["texconv_fmt"], row["ngrp_file"]
            src = pack.get(ngrp_file) or pack.get(os.path.basename(ngrp_file))
            if not src:
                miss += 1
                if miss <= 8: print("  missing in your NGRP copy: %s" % ngrp_file)
                continue
            out_name = "%s_%dx%d_fmt%s_mip00.dds" % (ch, w, h, gx2)
            if not a.texconv:
                made += 1
                if made <= 8: print("  would build %-42s <- %s" % (out_name, ngrp_file))
                continue
            cmd = [a.texconv, "-nologo", "-y", "-m", "0", "-f", tcf, "-o", a.out_load_dir]
            if not a.no_flip: cmd.insert(1, "-vflip")
            cmd.append(src)
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                base = os.path.splitext(os.path.basename(src))[0]
                produced = os.path.join(a.out_load_dir, base + ".DDS")
                if not os.path.exists(produced): produced = produced[:-4] + ".dds"
                dest = os.path.join(a.out_load_dir, out_name)
                if os.path.abspath(produced) != os.path.abspath(dest):
                    if os.path.exists(dest): os.remove(dest)
                    os.replace(produced, dest)
                made += 1
            except Exception as ex:
                fail += 1
                if fail <= 5: print("  texconv fail on %s: %s" % (ngrp_file, str(ex)[:80]))
    print("\n%s: %d DDS %s, %d missing from your NGRP, %d texconv fails"
          % (a.out_load_dir, made, "written" if a.texconv else "would build", miss, fail))
    if not a.texconv:
        print("  (dry run) add --texconv \"path\\texconv.exe\" to actually build the DDS")
    if miss:
        print("  Missing files usually mean your NGRP version differs from the manifest's. "
              "Use the matching NGRP version, or regenerate via the full pipeline.")

if __name__ == "__main__":
    main()
