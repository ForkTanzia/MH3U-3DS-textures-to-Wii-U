# MH3U 3DS Textures to Wii U

Convert MH3U 3DS textures, like **NGRP** HD texture pack (by **raccu**, made for the *3DS* version of Monster
Hunter 3 Ultimate) into textures the **Wii U** version can load through
[Cemu-Fork-Tanzia](https://github.com/ForkTanzia/Cemu-Fork-Tanzia-Texture-Loading-). While you can convert
any MH3U 3DS Texture pack, this guide is targeted at NGRP by raccu.

> **Not affiliated with or endorsed by NGRP/raccu, Cemu, or Nintendo.**
> This repository contains **only conversion scripts** — no game files and no NGRP art.
> You must download NGRP yourself from its official source. This keeps the original work
> in the hands of its author: you get NGRP from raccu, and this tool just re-targets it.
> This also does not convert the UI as the 3DS and Wii U Ui layouts are very different.

---

## What you need
- **Python 3** — https://www.python.org/downloads/ (tick "Add Python to PATH" on install)
- **texconv.exe** — https://github.com/microsoft/DirectXTex/releases (the texture converter)
- **The NGRP pack** — https://www.raccu.com/releases/runtime/mh3u-3g (download the DDS texture pack)
- **HD UI/Ultrawide UI** - https://gamebanana.com/mods/695684 (currently a work in progress, will be updated as I continue my work on it)
- Python libraries: `pip install -r requirements.txt`

Two ways to use this, depending on what you have.

---

## Section 1 — Quick convert (recommended, easiest)

Use this if you **just want the textures**. You need **only NGRP** — no 3DS, no Wii U
extraction. It works from a prebuilt **manifest** (provided in Releases) that already knows
each texture's Cemu hash, format, and which NGRP file it maps to.

1. Download the latest releasse from this repo's **Releases**.
2. Download the **NGRP pack** from its official source.
3. Run:
   ```
   py convert_from_manifest.py manifest.csv "C:\[Your extracted NGRP Folder]" "C:\[Your Converted Folder Path]" --texconv "C:\[Your texconv.exe path]"
   ```
   (Leave off `--texconv` first for a dry run that just lists what it would build.)
4. Copy everything from `"C:\[Your Converted Folder Path]"` into your Cemu Fork Tanzia's `load\textures\` folder.
5. Launch the game — textures load automatically.

**Important:** the manifest is tied to the **NGRP version it was built against** [In this case 1.2.1.1]. If
`convert_from_manifest.py` reports files "missing from your NGRP," your NGRP version differs —
use the matching version, grab an updated manifest, or use Section 2 to regenerate.

---

## Section 2 — Full pipeline (from scratch / when NGRP updates)

Use this if NGRP has been **updated**, or you want to build the mapping yourself. This
requires extracting textures from **both** the Wii U and 3DS versions of the game you own.

You need:
- Your **Wii U** MH3U texture extraction (the `.tex` files from the game's `.arc` archives)
- Your **3DS** MH3U romfs extraction
- The **NGRP** pack

Setup:
1. Grab a Wii U game extraction tool like "Uwizard" and extract the files. The Extracted folder should include the ".arc" files we need.

2. Grab quickbms from their website and find a "dmc4.bms" and put it in the same folder as quickbms.exe

3. Make a ".bat" file in the base quickbms and write the script below and replace the file paths with your own, and run the file.
   ```
   quickbms.exe -d -o -. -F "{}.arc" dmc4.bms "C:\[your .arcs folder]" "C:\[Your Extract folder]"
   ```
4. After it finishes you should be left with a bunch of extracted .arc folders.

5. On your 3DS Emulator dump romfs on your MH3U

Steps:
1. Build the match report (Wii U texture → 3DS CityHash → NGRP file):
   ```
   py hash_bridge.py "C:\[Your extracted Wii U .arcs folder]" "C:\[Your MH3U Dumped romfs folder" "C:\[Your NGRP folder]"
   ```
   This writes `bridge_report.csv`.
2. Convert, and (optionally) regenerate the portable manifest + rules:
   ```
   py cemu_names.py bridge_report.csv "C:\[Your extracted Wii U .arcs folder]" "C:\[Your NGRP folder]" "C:\[Your output folder]" ^
      --texconv "C:\[Your texconv.exe path]" --manifest "C:\[path of where your manifest.csv generated"
   ```
3. Once it finishes, copy the contents of `C:\[Your output folder]` into your Cemu's `load\textures\`.

The `--manifest` file it produces is exactly what Section 1 users need — so if you update the
pack, share the new `manifest.csv`. To make things simple I would recommend keeping all the scripts and folders in one folder.

Optionally if you wish to convert the raw .tex files into PNG you can do it via Noesis with the "fmt_MonsterHunter_TEX.py" plugin I provided

1. Download and install noesis.

2. In Noesis's "plugins/python" folder paste the "fmt_MonsterHunter_TEX.py" file.

3. You can now view and export the .tex files via noesis.

4. If you wish to batch convert all the .tex files to png you can make a ".bat" file with the content below and run it:

@echo off
set NOESIS=C:\[Your Noesis.exe]

for /r "C:\[Your extracted Wii U .arcs folder]" %%f in (*.tex) do "%NOESIS%" ?cmode "%%f" "%%~dpnf.png"
pause

---

## Options
- `--no-flip` — NGRP textures are vertically flipped by default (matching NGRP's `flip_png_files`).
  If textures appear upside-down in game, re-run with `--no-flip`.
- Formats: BC1/BC2 and RGBA8 are handled. If the tool reports "unknown fmt," open an issue with
  the format number and it can be added.

## How it works (short version)
Cemu-Fork-Tanzia matches custom textures by the emulator's own texture content hash. These
scripts reproduce that hash offline from the Wii U texture data, bridge each Wii U texture to
its NGRP counterpart (via the shared internal name → 3DS CityHash that NGRP filenames use),
and transcode the NGRP art into Cemu's expected format and naming. Full technical write-up is
in the fork's repository.

## Video Demo featuring custom textures (Click)
[![Custom Texture Demo](https://img.youtube.com/vi/nntnY9l1PAI/maxresdefault.jpg)](https://www.youtube.com/watch?v=nntnY9l1PAI)

## Credits
- **NGRP** HD texture project by **raccu** — the source art. Download it from its official page.
- **Cemu** by the Cemu project (MPL-2.0).

## Support
The fork and all tools are free to download and build. If it's been useful, you can
optionally support my work:

[![Support me on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/H8L623H70U)

## License
MIT (these scripts only). NGRP assets are **not** covered by this license and are **not**
included — they belong to raccu.
