#!/usr/bin/env python3
"""
Deterministic NGRP -> MH3U Wii U texture bridge (hash-based, EXACT)
==================================================================
Replaces the fuzzy content matcher with an exact, identity-based mapping.

How it works
------------
The 3DS and Wii U versions of MH3U share the same arc structure and the
same internal texture paths. NGRP's filenames embed the hash Citra
computes from the 3DS texture data. So:

    Wii U texture  --(same internal path)-->  3DS texture
                   --(Citra CityHash64 of mip0)-->  NGRP file

Every link is exact. No pixel comparison, so nothing lands in the wrong
place, and duplicate art is handled for free (identical data -> identical
hash -> same replacement).

The hash was reverse-engineered and verified against a known pair:
CityHash64 over the mip0 bytes of the 3DS .tex reproduces the hash in the
NGRP filename exactly. The 3DS rTexture layout is a 0x10-byte header plus
a mipCount-entry u32 offset table, so mip0's size is read directly from
the table (format-independent).

Inputs
------
  wiiu_root : your Wii U extraction (folder 2) - .tex files at arc paths,
              e.g. ...\\f_face003.arc\\player\\mod\\f\\face003\\f_face003_BM.tex
  threeds   : your 3DS romfs dump - a tree of .arc files (little-endian
              MTFramework). Loose .tex files are also accepted.
  pack_root : the NGRP pack (.dds files named tex1_WxH_HASH_fmt_mip0)

Usage
-----
    pip install -U cityhash pillow
    py hash_bridge.py <wiiu_root> <threeds> <pack_root>
    py hash_bridge.py <wiiu_root> <threeds> <pack_root> --copy <staging> --clean

Report (bridge_report.csv) lists every Wii U texture, its internal path,
the 3DS hash, and the matched NGRP file (or why not). --copy stages the
matched replacements (flipped, alpha-transplanted, format-tagged) exactly
like the old matcher, so the rest of your pipeline is unchanged.
"""

import argparse
import csv
import os
import re
import struct
import sys
import zlib

import cityhash

ARC_MAGIC = b"ARC\x00"       # 3DS (little-endian) MTFramework
TEX_MAGIC = b"TEX\x00"       # 3DS rTexture
WIIU_TEX_MAGIC = b"\x00XET"  # Wii U rTexture (big-endian container)
PACK_RE = re.compile(r"tex1_\d+x\d+_([0-9A-Fa-f]{16})_\d+_mip0\.(?:dds|png)$", re.IGNORECASE)
WIIU_TAGS = {267: "DXT1", 268: "DXT5", 259: "RGBA8"}


# ----------------------------------------------------------------------
# 3DS texture hashing
# ----------------------------------------------------------------------

def tex_mip0_hash(tex):
    """CityHash64 of mip0, the value Citra puts in the dump filename.
    Returns (hash_hex_upper, width, height) or (None, 0, 0)."""
    if len(tex) < 0x14 or tex[:4] != TEX_MAGIC:
        return None, 0, 0
    packed = struct.unpack("<I", tex[8:12])[0]
    mip_count = packed & 0x3F
    width = (packed >> 6) & 0x1FFF
    height = (packed >> 19) & 0x1FFF
    if mip_count < 1:
        return None, width, height
    header_size = 0x10 + mip_count * 4
    if len(tex) < header_size:
        return None, width, height
    offsets = [struct.unpack("<I", tex[0x10 + i * 4:0x14 + i * 4])[0] for i in range(mip_count)]
    data = tex[header_size:]
    mip0 = data[offsets[0]:offsets[1]] if mip_count > 1 else data[offsets[0]:]
    h = cityhash.CityHash64(mip0)
    return "%016X" % h, width, height


def parse_arc_le(buf):
    """Yield (internal_name, decompressed_bytes) for every entry."""
    if buf[:4] != ARC_MAGIC:
        return
    count = struct.unpack("<H", buf[6:8])[0]
    for i in range(count):
        off = 0xC + i * 0x50
        raw = buf[off:off + 0x50]
        if len(raw) < 0x50:
            break
        name = raw[:64].split(b"\x00")[0].decode("ascii", "replace")
        _type, zsize, _sizefield, offset = struct.unpack("<IIII", raw[64:80])
        blob = buf[offset:offset + zsize]
        try:
            data = zlib.decompress(blob)
        except zlib.error:
            continue
        yield name, data


def norm_key(path_no_ext):
    """Normalize an internal texture path to a comparison key."""
    return path_no_ext.replace("\\", "/").lower().lstrip("/")


def build_3ds_hashmap(threeds_root, arc_scope=False):
    """Walk the 3DS romfs/arcs and loose .tex; return {key: (hash, w, h)}
    plus collision examples (same key, different hash across arcs)."""
    hashmap = {}
    collisions = []
    n_arc = n_tex = 0
    for dirpath, _dirs, files in os.walk(threeds_root):
        for fn in files:
            full = os.path.join(dirpath, fn)
            low = fn.lower()
            if low.endswith(".arc"):
                n_arc += 1
                try:
                    buf = open(full, "rb").read()
                except OSError:
                    continue
                arc_base = os.path.splitext(fn)[0].lower()
                for name, data in parse_arc_le(buf):
                    if data[:4] != TEX_MAGIC:
                        continue
                    h, w, ht = tex_mip0_hash(data)
                    if h is None:
                        continue
                    ipath = norm_key(os.path.splitext(name)[0])
                    key = (arc_base + "|" + ipath) if arc_scope else ipath
                    prev = hashmap.get(key)
                    if prev and prev[0] != h:
                        if len(collisions) < 20:
                            collisions.append((key, prev[0], h))
                    else:
                        hashmap[key] = (h, w, ht)
            elif low.endswith(".tex"):
                n_tex += 1
                try:
                    data = open(full, "rb").read()
                except OSError:
                    continue
                if data[:4] != TEX_MAGIC:
                    continue
                h, w, ht = tex_mip0_hash(data)
                if h is None:
                    continue
                rel = os.path.relpath(full, threeds_root)
                key = internal_key_from_relpath(rel)
                prev = hashmap.get(key)
                if prev and prev[0] != h:
                    collisions.append(key)
                else:
                    hashmap[key] = (h, w, ht)
    print("  3DS: parsed %d arc(s), %d loose tex -> %d unique textures%s"
          % (n_arc, n_tex, len(hashmap),
             (", %d collisions" % len(collisions)) if collisions else ""))
    return hashmap, collisions


def index_pack(pack_root):
    """{HASH_UPPER: filepath} for mip0 pack files."""
    idx = {}
    dup = 0
    for dirpath, _dirs, files in os.walk(pack_root):
        for fn in files:
            m = PACK_RE.search(fn)
            if not m:
                continue
            h = m.group(1).upper()
            if h in idx:
                dup += 1
            idx[h] = os.path.join(dirpath, fn)
    print("  pack: %d mip0 textures indexed by hash%s"
          % (len(idx), (" (%d duplicate hashes)" % dup) if dup else ""))
    return idx


# ----------------------------------------------------------------------
# path helpers for the Wii U side
# ----------------------------------------------------------------------

def classify_alpha(alpha_arr):
    """Given a WxHx? array's alpha channel (uint8 2D), decide how to treat it.
    Returns (mode, reason). Mirrors the measurements that diagnosed the
    plank-edge feathering bug:
      - almost entirely opaque            -> 'opaque'
      - opaque + transparency at borders  -> 'wiiu-hard' (crisp mask)
      - large genuine translucent regions -> 'wiiu' (smooth)
    """
    import numpy as np
    a = alpha_arr.astype(np.float32)
    frac_opaque = float((a >= 250).mean())
    frac_transp = float((a <= 5).mean())
    frac_mid    = float(((a > 5) & (a < 250)).mean())
    if frac_opaque >= 0.98:
        return "opaque", "%.0f%% opaque" % (frac_opaque * 100)
    # is the transparency concentrated at the borders? (edge mask)
    h, w = a.shape
    if min(h, w) >= 16:
        b = max(2, min(h, w) // 16)
        border = np.concatenate([a[:b].ravel(), a[-b:].ravel(), a[:, :b].ravel(), a[:, -b:].ravel()])
        center = a[h//4:3*h//4, w//4:3*w//4].ravel()
        edge_biased = border.mean() < center.mean() - 30
    else:
        edge_biased = False
    # mostly opaque with limited mid-range and edge-biased transparency = hard mask
    if frac_opaque >= 0.55 and frac_mid <= 0.35 and (edge_biased or frac_transp <= 0.35):
        return "wiiu-hard", "mask: %.0f%% opaque, transp at edges" % (frac_opaque * 100)
    return "wiiu", "translucent: %.0f%% mid, %.0f%% transp" % (frac_mid * 100, frac_transp * 100)


def apply_alpha(im, mode, wpng_path):
    """Apply the chosen alpha mode to NGRP image `im` in place-ish; returns
    (image, applied_bool). `im` is RGBA (already flipped to Wii U orientation)."""
    from PIL import Image
    if mode == "opaque":
        im.putalpha(255)
        return im, True
    if mode == "ngrp":
        return im, True  # keep pack alpha
    if wpng_path is None:
        return im, False  # can't read Wii U alpha
    resample = Image.NEAREST if mode == "wiiu-hard" else Image.BICUBIC
    with Image.open(wpng_path) as wpng:
        a = wpng.convert("RGBA").split()[3].resize(im.size, resample)
    im.putalpha(a)
    return im, True


def find_wiiu_png(tex_path):
    stem = os.path.splitext(tex_path)[0]
    for c in [stem + ".png"] + [stem + "-" + t + ".png"
                                for t in ("DXT5", "DXT1", "RGBA8", "dxt5", "dxt1", "rgba8")]:
        if os.path.isfile(c):
            return c
    return None


def internal_key_from_relpath(rel, arc_scope=False):
    """From a Wii U extraction relative path, take the part after the
    last '.arc' segment (the internal arc path), drop the extension and
    any -DXTn/-RGBA8 tag, and normalize. With arc_scope, prefix the arc
    basename so identically-named internal paths in different arcs stay
    distinct."""
    parts = rel.replace("\\", "/").split("/")
    arc_i = max((i for i, p in enumerate(parts) if p.lower().endswith(".arc")), default=-1)
    inner = parts[arc_i + 1:] if arc_i >= 0 else parts
    stem = os.path.splitext("/".join(inner))[0]
    stem = re.sub(r"[-_](dxt[15]|rgba8)$", "", stem, flags=re.IGNORECASE)
    ipath = norm_key(stem)
    if arc_scope and arc_i >= 0:
        arc_base = os.path.splitext(parts[arc_i])[0].lower()
        return arc_base + "|" + ipath
    return ipath


def wiiu_tex_tag(tex_path):
    try:
        with open(tex_path, "rb") as f:
            hdr = f.read(16)
    except OSError:
        return None
    if len(hdr) < 16 or hdr[:4] != WIIU_TEX_MAGIC:
        return None
    return WIIU_TAGS.get(struct.unpack(">H", hdr[12:14])[0])


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Exact hash-based NGRP->WiiU texture bridge")
    ap.add_argument("wiiu_root", help="Wii U extraction (folder with .tex at arc paths)")
    ap.add_argument("threeds", help="3DS romfs dump (tree of .arc files) or loose .tex")
    ap.add_argument("pack_root", help="NGRP pack (.dds named by hash)")
    ap.add_argument("--copy", metavar="STAGING", help="stage matched replacements here")
    ap.add_argument("--copy-from", metavar="DIR", help="take files from DIR instead of pack_root")
    ap.add_argument("--flip", choices=["always", "never"], default="always",
                    help="NGRP files are vertically flipped vs your exports (default: always)")
    ap.add_argument("--alpha", choices=["wiiu", "wiiu-hard", "ngrp", "opaque", "auto"],
                    default="opaque",
                    help="alpha source per texture. auto (DEFAULT) picks per-texture using "
                         "the original's alpha profile: opaque textures -> opaque, hard-edged "
                         "masks -> wiiu-hard (nearest-neighbour, crisp edges), genuine "
                         "transparency -> wiiu (bicubic). Force one with: opaque, wiiu-hard "
                         "(crisp mask), wiiu (smooth), ngrp (keep pack alpha). DEFAULT is "
                         "opaque: stage clean HD colour only - real alpha is restored later "
                         "by fix_pack_alpha.py at the DDS stage. Prevents the original-showing-"
                         "through merge.")
    ap.add_argument("--alpha-report", default=None,
                    help="write a CSV of each texture's chosen alpha mode and why")
    ap.add_argument("--arc-scope", action="store_true",
                    help="include the arc name in the match key (use if the collision "
                         "report shows many different textures sharing an internal path)")
    ap.add_argument("--sample", type=int, default=0, metavar="N",
                    help="print N example mappings for spot-checking, then continue")
    ap.add_argument("--clean", action="store_true", help="wipe staging before copying")
    ap.add_argument("--exclude", action="append", default=[], metavar="SEGMENT",
                    help="skip any Wii U texture whose path contains this folder segment "
                         "(repeatable). Example: --exclude stage  skips all stage textures, "
                         "which the game cannot load at changed resolutions.")
    ap.add_argument("--report", default="bridge_report.csv")
    args = ap.parse_args()

    for label, p in (("wiiu_root", args.wiiu_root), ("threeds", args.threeds),
                     ("pack_root", args.pack_root)):
        if not os.path.isdir(p):
            sys.exit("Missing %s: %s" % (label, p))

    print("Indexing NGRP pack...")
    pack = index_pack(args.pack_root)
    print("Hashing 3DS textures...")
    hashmap, collisions = build_3ds_hashmap(args.threeds, arc_scope=args.arc_scope)
    if not pack or not hashmap:
        sys.exit("Nothing to bridge (empty pack or no 3DS textures found).")

    print("Resolving Wii U textures...")
    rows = []
    n = 0
    for dirpath, _dirs, files in os.walk(args.wiiu_root):
        for fn in files:
            if not fn.lower().endswith(".tex"):
                continue
            n += 1
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, args.wiiu_root)
            if args.exclude:
                segs = [s.lower() for s in rel.replace("\\", "/").split("/")]
                if any(x.lower() in segs for x in args.exclude):
                    continue
            key = internal_key_from_relpath(rel, arc_scope=args.arc_scope)
            row = {"wiiu": rel, "internal": key}
            hit = hashmap.get(key)
            if hit is None:
                row.update(status="no_3ds_source", hash="", match="")
                rows.append(row)
                continue
            h, w, ht = hit
            row["hash"] = h
            row["dims"] = "%dx%d" % (w, ht)
            pf = pack.get(h)
            if pf is None:
                row.update(status="not_in_pack", match="")
            else:
                row.update(status="matched", match=os.path.basename(pf), match_path=pf)
            rows.append(row)

    fields = ["wiiu", "internal", "hash", "dims", "status", "match"]
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        wtr.writeheader()
        for r in rows:
            wtr.writerow(r)

    from collections import Counter
    tally = Counter(r["status"] for r in rows)
    print("\n%d Wii U textures: %d matched, %d not in pack, %d no 3DS source  ->  %s"
          % (len(rows), tally["matched"], tally["not_in_pack"], tally["no_3ds_source"], args.report))
    if collisions:
        print("  WARNING: internal-path collisions detected (same path, different 3DS content).")
        print("           These cause WRONG PLACEMENT. Re-run with --arc-scope to fix. Examples:")
        for key, h1, h2 in collisions[:5]:
            print("             %s : %s vs %s" % (key, h1, h2))

    if args.sample:
        import random
        matched_rows = [r for r in rows if r.get("status") == "matched"]
        print("\n  sample mappings (spot-check these in-game):")
        for r in random.sample(matched_rows, min(args.sample, len(matched_rows))):
            print("    %s\n      -> %s  (hash %s)" % (r["wiiu"], r["match"], r["hash"]))

    if not args.copy:
        print("Add --copy STAGING (and --clean) to stage the matched replacements.")
        return

    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        sys.exit("Staging needs Pillow + numpy: pip install -U pillow numpy")

    if args.clean and os.path.isdir(args.copy):
        import shutil
        print("Cleaning %s ..." % args.copy)
        shutil.rmtree(args.copy)
    os.makedirs(args.copy, exist_ok=True)

    src_root = args.copy_from if args.copy_from else args.pack_root
    copied = alpha_fixed = alpha_missing = 0
    alpha_modes_used = {}
    alpha_report_rows = [] if args.alpha_report else None
    for r in rows:
        if r.get("status") != "matched":
            continue
        pf = r["match_path"]
        if args.copy_from:
            cand = os.path.join(src_root, os.path.relpath(pf, args.pack_root))
            if os.path.isfile(cand):
                pf = cand
            else:
                base = os.path.splitext(cand)[0]
                pf = next((base + e for e in (".dds", ".png") if os.path.isfile(base + e)), pf)

        wiiu_tex = os.path.join(args.wiiu_root, r["wiiu"])
        tag = wiiu_tex_tag(wiiu_tex)
        stem = os.path.splitext(r["wiiu"])[0]
        stem = re.sub(r"[-_](dxt[15]|rgba8)$", "", stem, flags=re.IGNORECASE)
        out_path = os.path.join(args.copy, stem + (("-" + tag) if tag else "") + ".png")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        try:
            im = Image.open(pf).convert("RGBA")
        except Exception as e:
            print("  ! can't read %s: %s" % (pf, e))
            continue
        if args.flip == "always":
            im = im.transpose(Image.FLIP_TOP_BOTTOM)

        wpng_path = find_wiiu_png(wiiu_tex)

        # decide the alpha mode for this texture
        if args.alpha == "auto":
            if wpng_path is not None:
                try:
                    with Image.open(wpng_path) as wpng:
                        wa = np.asarray(wpng.convert("RGBA"))[:, :, 3]
                    mode, reason = classify_alpha(wa)
                except Exception:
                    mode, reason = "opaque", "wiiu png unreadable -> opaque"
            else:
                mode, reason = "opaque", "no wiiu png -> opaque"
        else:
            mode, reason = args.alpha, "forced"

        im, applied = apply_alpha(im, mode, wpng_path)
        if mode in ("wiiu", "wiiu-hard"):
            if applied:
                alpha_fixed += 1
            else:
                alpha_missing += 1
        alpha_modes_used[mode] = alpha_modes_used.get(mode, 0) + 1
        if alpha_report_rows is not None:
            alpha_report_rows.append({"wiiu": r["wiiu"], "alpha_mode": mode, "reason": reason})

        im.save(out_path)
        copied += 1

    print("Copied %d replacements into %s (%d with original alpha transplanted)"
          % (copied, args.copy, alpha_fixed))
    if alpha_modes_used:
        print("  alpha modes chosen: " + ", ".join("%s=%d" % (k, v)
              for k, v in sorted(alpha_modes_used.items())))
    if alpha_report_rows is not None:
        with open(args.alpha_report, "w", newline="", encoding="utf-8") as f:
            wtr = csv.DictWriter(f, fieldnames=["wiiu", "alpha_mode", "reason"])
            wtr.writeheader()
            for row in alpha_report_rows:
                wtr.writerow(row)
        print("  alpha-mode report: %s" % args.alpha_report)
    if args.alpha == "wiiu" and alpha_missing:
        print("  WARNING: %d textures had NO original Wii U PNG found next to their .tex, so the"
              % alpha_missing)
        print("           pack's alpha was kept for those (this is the bug that caused wrong")
        print("           transparency). Make sure folder 2 has the exported PNGs beside each .tex.")


if __name__ == "__main__":
    main()
