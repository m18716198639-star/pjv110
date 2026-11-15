#!/usr/bin/env python3
"""Minimal Android boot / vendor_boot image parser (stdlib only).

Usage:
  python androidimg.py info   <img> [...]
  python androidimg.py unpack <img> <outdir>
"""

import os
import struct
import sys
import gzip
import zlib

PAGE = 4096


# ---------------------------------------------------------------- lz4
def lz4_block_decompress(src):
    dst = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        dst += src[i:i + lit_len]
        i += lit_len
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("lz4: zero offset")
        match_len = token & 0x0F
        if match_len == 15:
            while True:
                b = src[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        match_len += 4
        start = len(dst) - offset
        if start < 0:
            raise ValueError("lz4: bad offset")
        for k in range(match_len):
            dst.append(dst[start + k])
    return bytes(dst)


def lz4_legacy_decompress(data):
    if data[:4] != b"\x02\x21\x4c\x18":
        raise ValueError("not lz4 legacy")
    out = bytearray()
    i = 4
    n = len(data)
    while i + 4 <= n:
        size = struct.unpack_from("<I", data, i)[0]
        i += 4
        if size == 0 or i + size > n:
            break
        out += lz4_block_decompress(data[i:i + size])
        i += size
    return bytes(out)


def lz4_frame_decompress(data):
    if data[:4] != b"\x04\x22\x4d\x18":
        raise ValueError("not lz4 frame")
    i = 4
    flg = data[i]
    i += 1
    bd = data[i]
    i += 1
    if flg & 0x08:  # content size
        i += 8
    if flg & 0x01:  # dict id
        i += 4
    i += 1  # header checksum
    out = bytearray()
    while i + 4 <= len(data):
        size = struct.unpack_from("<I", data, i)[0]
        i += 4
        if size == 0:
            break
        uncompressed = bool(size & 0x80000000)
        size &= 0x7FFFFFFF
        block = data[i:i + size]
        i += size
        if uncompressed:
            out += block
        else:
            out += lz4_block_decompress(block)
        if flg & 0x10:  # block checksum
            i += 4
    return bytes(out)


def decompress(data):
    if data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    if data[:4] == b"\x04\x22\x4d\x18":
        return lz4_frame_decompress(data)
    if data[:4] == b"\x02\x21\x4c\x18":
        return lz4_legacy_decompress(data)
    if data[:6] == b"\xfd7zXZ\x00":
        import lzma
        return lzma.decompress(data)
    if data[:4] == b"\x28\xb5\x2f\xfd":
        import shutil
        import subprocess
        exe = shutil.which("zstd")
        if not exe:
            raise ValueError("zstd compressed ramdisk but no zstd binary")
        return subprocess.run([exe, "-d", "-c"], input=data,
                              stdout=subprocess.PIPE, check=True).stdout
    return data


# ---------------------------------------------------------------- cpio
def cpio_entries(data):
    i = 0
    n = len(data)
    while i + 110 <= n:
        if data[i:i + 6] != b"070701":
            # skip padding
            if data[i] == 0:
                i += 1
                continue
            raise ValueError("bad cpio magic at %d" % i)
        hdr = data[i:i + 110]
        fields = [int(hdr[6 + 8 * k:6 + 8 * (k + 1)], 16) for k in range(13)]
        filesize = fields[6]
        namesize = fields[11]
        name_start = i + 110
        name = data[name_start:name_start + namesize - 1].decode("utf-8", "replace")
        off = name_start + namesize
        off = (off + 3) & ~3
        filedata = data[off:off + filesize]
        off = (off + filesize + 3) & ~3
        yield name, filedata
        i = off
        if name == "TRAILER!!!":
            break


# ---------------------------------------------------------------- boot
def parse_boot(data):
    if data[:8] != b"ANDROID!":
        return None
    ver = struct.unpack_from("<I", data, 40)[0]
    if ver in (0, 1, 2):
        kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr = \
            struct.unpack_from("<6I", data, 8)
        tags_addr, page_size, header_version, os_version = \
            struct.unpack_from("<4I", data, 32)
        cmdline = data[64:64 + 512].split(b"\x00")[0].decode("utf-8", "replace")
        return {
            "type": "boot", "version": ver, "kernel_size": kernel_size,
            "ramdisk_size": ramdisk_size, "page_size": page_size,
            "os_version": os_version, "cmdline": cmdline,
            "kernel_off": page_size, "ramdisk_off": page_size * (1 + (kernel_size + page_size - 1) // page_size),
        }
    # v3 / v4
    kernel_size, ramdisk_size, os_version, header_size = struct.unpack_from("<4I", data, 8)
    header_version = struct.unpack_from("<I", data, 40)[0]
    cmdline = data[44:44 + 1536].split(b"\x00")[0].decode("utf-8", "replace")
    page = PAGE
    return {
        "type": "boot", "version": header_version, "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size, "page_size": page, "os_version": os_version,
        "cmdline": cmdline, "kernel_off": page,
        "ramdisk_off": page * (1 + (kernel_size + page - 1) // page),
    }


def parse_vendor_boot(data):
    if data[:8] != b"VNDRBOOT":
        return None
    ver, page, kernel_addr, ramdisk_addr, vendor_ramdisk_size = struct.unpack_from("<5I", data, 8)
    cmdline = data[28:28 + 2048].split(b"\x00")[0].decode("utf-8", "replace")
    tags_addr = struct.unpack_from("<I", data, 28 + 2048)[0]
    name = data[28 + 2048 + 4:28 + 2048 + 4 + 16].split(b"\x00")[0].decode("utf-8", "replace")
    header_size, dtb_size = struct.unpack_from("<2I", data, 28 + 2048 + 4 + 16)
    dtb_addr = struct.unpack_from("<Q", data, 28 + 2048 + 4 + 16 + 8)[0]
    info = {
        "type": "vendor_boot", "version": ver, "page_size": page,
        "vendor_ramdisk_size": vendor_ramdisk_size, "dtb_size": dtb_size,
        "name": name, "cmdline": cmdline, "header_size": header_size,
    }
    frags = []
    if ver >= 4:
        table_size, entry_num, entry_size, bootconfig_size = struct.unpack_from("<4I", data, header_size - 16)
        info.update(table_size=table_size, entry_num=entry_num,
                    entry_size=entry_size, bootconfig_size=bootconfig_size)
        ramdisk_off = page
        dtb_off = ramdisk_off + ((vendor_ramdisk_size + page - 1) // page) * page
        table_off = dtb_off + ((dtb_size + page - 1) // page) * page
        for k in range(entry_num):
            base = table_off + k * entry_size
            rsize, roff, rtype = struct.unpack_from("<3I", data, base)
            rname = data[base + 12:base + 44].split(b"\x00")[0].decode("utf-8", "replace")
            frags.append({"size": rsize, "offset": roff, "type": rtype, "name": rname,
                          "abs": table_off + roff if roff < table_off else roff})
        info["table_off"] = table_off
        info["fragments"] = frags
    return info


def redump(path, outdir):
    data = open(path, "rb").read()
    info = parse_vendor_boot(data) or parse_boot(data)
    if info is None:
        print("not an android image:", path)
        return 1
    print_info(path, info)
    os.makedirs(outdir, exist_ok=True)
    if info["type"] == "boot":
        rd = data[info["ramdisk_off"]:info["ramdisk_off"] + info["ramdisk_size"]]
        open(os.path.join(outdir, "ramdisk.img"), "wb").write(rd)
        try:
            raw = decompress(rd)
            open(os.path.join(outdir, "ramdisk.cpio"), "wb").write(raw)
            print("  ramdisk decompressed -> ramdisk.cpio (%d bytes)" % len(raw))
        except Exception as e:
            print("  ramdisk decompress failed:", e)
    else:
        page = info["page_size"]
        vrd = data[page:page + info["vendor_ramdisk_size"]]
        if info["version"] >= 4 and info["fragments"]:
            # ramdisk blob offset 0 is start of vendor_ramdisk area
            for f in info["fragments"]:
                blob = data[page + f["offset"]: page + f["offset"] + f["size"]]
                fn = os.path.join(outdir, "frag_%s.img" % f["name"].replace(" ", "_"))
                open(fn, "wb").write(blob)
                print("  fragment %-16s type=%d size=%d -> %s" % (f["name"], f["type"], f["size"], fn))
                try:
                    raw = decompress(blob)
                    open(fn + ".cpio", "wb").write(raw)
                    print("    decompressed %d" % len(raw))
                except Exception as e:
                    print("    decompress failed: %s (head=%s)" % (e, blob[:4].hex()))
        else:
            open(os.path.join(outdir, "vendor_ramdisk.img"), "wb").write(vrd)
            print("  vendor_ramdisk head=%s" % vrd[:4].hex())
            try:
                raw = decompress(vrd)
                open(os.path.join(outdir, "vendor_ramdisk.cpio"), "wb").write(raw)
                print("  vendor_ramdisk decompressed -> vendor_ramdisk.cpio (%d bytes)" % len(raw))
            except Exception as e:
                print("  decompress failed:", e)
    return 0


def print_info(path, info):
    print("== %s ==" % path)
    for k, v in info.items():
        if k == "fragments":
            continue
        if isinstance(v, str) and len(v) > 120:
            v = v[:120] + "..."
        print("  %-20s %s" % (k, v))
    for f in info.get("fragments", []):
        print("  fragment %-12s type=%d size=%-10d off=%d rel" % (f["name"], f["type"], f["size"], f["offset"]))


def cmd_ls(path, pattern=None):
    data = open(path, "rb").read()
    count = 0
    for name, filedata in cpio_entries(data):
        if pattern and pattern not in name:
            continue
        kind = "d" if name.endswith("/") else "f"
        print("%s %9d  %s" % (kind, len(filedata), name))
        count += 1
    print("-- %d entries --" % count)


def cmd_extract(path, outdir):
    data = open(path, "rb").read()
    outdir = os.path.abspath(outdir)
    for name, filedata in cpio_entries(data):
        if name in ("TRAILER!!!",):
            continue
        rel = name.lstrip("/").replace("..", "__")
        dst = os.path.join(outdir, rel)
        if name.endswith("/"):
            try:
                os.makedirs(dst, exist_ok=True)
            except (FileExistsError, NotADirectoryError):
                pass
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fp:
                fp.write(filedata)
        except (FileExistsError, NotADirectoryError, IsADirectoryError, PermissionError):
            pass
    print("extracted to", outdir)


def cmd_cat(path, want):
    data = open(path, "rb").read()
    for name, filedata in cpio_entries(data):
        if name.lstrip("/") == want.lstrip("/"):
            sys.stdout.buffer.write(filedata)
            return
    print("not found:", want, file=sys.stderr)


def main():
    cmd = sys.argv[1]
    if cmd == "info":
        for p in sys.argv[2:]:
            data = open(p, "rb").read()
            info = parse_vendor_boot(data) or parse_boot(data)
            if info:
                print_info(p, info)
            else:
                print("== %s ==\n  not an android boot image (head=%s)" % (p, data[:16].hex()))
                print("  head=%r" % data[:16])
    elif cmd == "unpack":
        sys.exit(redump(sys.argv[2], sys.argv[3]))
    elif cmd == "ls":
        cmd_ls(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "extract":
        cmd_extract(sys.argv[2], sys.argv[3])
    elif cmd == "cat":
        cmd_cat(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
