#Monster Hunter 3 Ultimate .TEX [Wii U] - ".TEX" Loader
#By Zaramot, header decoding fixes + format support v1.2
#Special thanks: Chrrox
#
#v1.1: proper bitfield header decode (mips:6|width:13|height:13), GX2
#      pitch alignment for small textures, graceful skip of unknown
#      formats, stale temp-file cleanup.
#v1.2: added format 259 (0x103) = uncompressed RGBA8, used by UI sheets
#      (st_menu_*) and some material maps (*_GSM_HQ). Size math is now
#      generic across block-compressed and per-pixel formats.

from inc_noesis import *
import subprocess
import struct
import os

def registerNoesisTypes():
    handle = noesis.register("Monster Hunter 3 Ultimate Texture [Wii U]", ".tex")
    noesis.setHandlerTypeCheck(handle, texCheckType)
    noesis.setHandlerLoadRGBA(handle, texLoadDDS)
    noesis.logPopup()
    return 1

def texCheckType(data):
    bs = NoeBitStream(data, NOE_BIGENDIAN)
    fileMagic = bs.readUInt()
    if fileMagic == 0x584554:
        return 1
    print("Fatal Error: Unknown file magic: " + str(hex(fileMagic)) + " expected 0x584554!")
    return 0

#TexInd -> (label, GX2 surface format, element size in px (4 = BC block, 1 = per pixel), bytes per element, gtx alignment field)
TEX_FORMATS = {
    267: ("DXT1/BC1", 0x31, 4, 8,  4096),
    268: ("DXT5/BC3", 0x33, 4, 16, 8192),
    259: ("RGBA8",    0x1A, 1, 4,  8192),
}

def texLoadDDS(data, texList):
    bs = NoeBitStream(data, NOE_BIGENDIAN)
    ddsName = rapi.getLocalFileName(rapi.getInputName())

    bs.seek(0x8, NOESEEK_ABS)
    dims = bs.readUInt()
    mipCount = (dims >> 26) & 0x3F
    Width = (dims >> 13) & 0x1FFF
    Height = dims & 0x1FFF

    bs.seek(0xC, NOESEEK_ABS)
    TexInd = bs.readUShort()

    print("%s: %dx%d, %d mips, format %d" % (ddsName, Width, Height, mipCount, TexInd))

    if Width == 0 or Height == 0:
        print("WARNING: bad dimensions in " + ddsName + " - skipped")
        return 0

    if TexInd not in TEX_FORMATS:
        print("WARNING: unhandled pixel format %d (0x%X) in %s (%dx%d) - skipped. "
              "Send this file to whoever maintains the plugin." % (TexInd, TexInd, ddsName, Width, Height))
        return 0

    fmtName, gtxType, elemDiv, elemBytes, gtxAlign = TEX_FORMATS[TexInd]

    #GX2 2D-tiled mip 0: pitch padded to >= 32 elements, height to >= 16
    #element rows (elements = 4x4 blocks for BC formats, pixels otherwise).
    elemW = (Width + elemDiv - 1) // elemDiv
    elemH = (Height + elemDiv - 1) // elemDiv
    ddsSize = max(elemW, 32) * max(elemH, 16) * elemBytes
    ddsSize = (ddsSize + 1023) & ~1023

    bs.seek(0x10, NOESEEK_ABS)
    remaining = len(data) - 0x10
    if ddsSize > remaining:
        ddsSize = remaining
    ddsData = bs.readBytes(ddsSize)

    gtxFmtReg = (gtxType << 26) | 0x3FF

    gtxTex = (b'\x47\x66\x78\x32\x00\x00\x00\x20\x00\x00\x00\x06\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x42\x4C\x4B\x7B\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x0A\x00\x00\x00\x9C\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01')
    gtxTex += struct.pack(">I", Width)
    gtxTex += struct.pack(">I", Height)
    gtxTex += (b'\x00\x00\x00\x01\x00\x00\x00\x01')
    gtxTex += struct.pack(">I", gtxType)
    gtxTex += (b'\x00\x00\x00\x00\x00\x00\x00\x01')
    gtxTex += struct.pack(">I", ddsSize)
    gtxTex += (b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x0D\x00\x00')
    gtxTex += struct.pack(">II", gtxAlign, 256)
    gtxTex += (b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x01\x00\x01\x02\x03\x1F\xF8\x7F\x21')
    gtxTex += struct.pack(">I", gtxFmtReg)
    gtxTex += (b'\x06\x88\x84\x00\x00\x00\x00\x00\x80\x00\x00\x10\x42\x4C\x4B\x7B\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x0B')
    gtxTex += struct.pack(">I", ddsSize)
    gtxTex += (b'\x00\x00\x00\x00\x00\x00\x00\x00')
    gtxTex += ddsData
    gtxTex += (b'\x42\x4C\x4B\x7B\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x01\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')

    dstFilePath = noesis.getScenesPath() + ddsName + ".gtx"
    dstDDSPath = dstFilePath + ".dds"

    for stale in (dstFilePath, dstDDSPath):
        try:
            os.remove(stale)
        except OSError:
            pass

    newfile = open(dstFilePath, 'wb')
    newfile.write(gtxTex)
    newfile.close()

    try:
        subprocess.Popen([noesis.getScenesPath() + 'TexConv2.bat', dstFilePath]).wait()
        texData = rapi.loadIntoByteArray(dstDDSPath)
        texture = rapi.loadTexByHandler(texData, ".dds")
        if texture is None:
            raise ValueError("dds handler returned nothing")
    except Exception as e:
        print("WARNING: TexConv2 conversion failed for %s (%dx%d, format %d %s): %s - skipped"
              % (ddsName, Width, Height, TexInd, fmtName, repr(e)))
        return 0

    texture.name = ddsName
    texList.append(texture)
    return 1
