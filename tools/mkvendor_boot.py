#!/usr/bin/env python3
"""Repack an Android vendor_boot (header v4) image with a new vendor ramdisk.

Why: PJV110 has no recovery partition; recovery lives in vendor_boot.  We build
OrangeFox/TWRP ramdisks elsewhere and repack them into the stock vendor_boot
header + dtb here, instead of relying on AOSP's vendor_boot build target.

Commands:
  info      <stock.img>
  roundtrip <stock.img> <out.img>     # rebuild from the stock ramdisk, then verify
  repack    <stock.img> <ramdisk.cpio> <out.img>
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from androidimg import parse_vendor_boot, decompress, cpio_entries  # noqa: E402

PAGE = 4096


# ------------------------------------------------------------------ lz4 compressor
def lz4_compress_block(src):
    """Greedy LZ4 block compressor. Returns a valid LZ4 block."""
    n = len(src)
    out = bytearray()
    table = {}
    anchor = 0
    i = 0
    limit = n - 4
    while i < limit:
        seq = src[i] | (src[i + 1] << 8) | (src[i + 2] << 16) | (src[i + 3] << 24)
        prev = table.get(seq, -1)
        table[seq] = i
        if prev < 0 or i - prev > 0xFFFF:
            i += 1
            continue
        # extend match
        m = 4
        while i + m < n and src[prev + m] == src[i + m]:
            m += 1
        lit_len = i - anchor
        token = (lit_len if lit_len < 15 else 15) << 4
        match_code = m - 4
        token |= match_code if match_code < 15 else 15
        out.append(token)
        if lit_len >= 15:
            left = lit_len - 15
            while left >= 255:
                out.append(255)
                left -= 255
            out.append(left)
        out += src[anchor:i]
        off = i - prev
        out.append(off & 0xFF)
        out.append(off >> 8)
        if match_code >= 15:
            left = match_code - 15
            while left >= 255:
                out.append(255)
                left -= 255
            out.append(left)
        i += m
        anchor = i
        if i < limit:
            table[src[i - 2] | (src[i - 1] << 8)] = i - 2  # cheap extra coverage
    # trailing literals
    lit_len = n - anchor
    token = (lit_len if lit_len < 15 else 15) << 4
    out.append(token)
    if lit_len >= 15:
        left = lit_len - 15
        while left >= 255:
            out.append(255)
            left -= 255
        out.append(left)
    out += src[anchor:]
    return bytes(out)


def lz4_legacy_compress(data, block_size=8 * 1024 * 1024):
    out = bytearray(b"\x02\x21\x4c\x18")
    for off in range(0, len(data), block_size):
        chunk = data[off:off + block_size]
        comp = lz4_compress_block(chunk)
        out += struct.pack("<I", len(comp))
        out += comp
    return bytes(out)


# ------------------------------------------------------------------ cpio
def cpio_pack(entries, pad_to=0):
    """entries: iterable of (name, mode, data). name ending in '/' => dir entry."""
    out = bytearray()
    ino = 1
    for name, mode, data in entries:
        name_b = name.encode("utf-8")
        if not name_b.endswith(b"\x00"):
            name_b += b"\x00"
        header = b"070701" + b"".join(
            struct.pack("<8s", b"%08X" % v)
            for v in (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name_b), 0)
        )
        out += header
        out += name_b
        out += b"\x00" * ((4 - (len(header) + len(name_b)) % 4) % 4)
        out += data
        out += b"\x00" * ((4 - len(data) % 4) % 4)
        ino += 1
    # trailer
    name_b = b"TRAILER!!!\x00"
    header = b"070701" + b"".join(
        struct.pack("<8s", b"%08X" % v)
        for v in (0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(name_b), 0)
    )
    out += header + name_b
    out += b"\x00" * ((4 - (len(header) + len(name_b)) % 4) % 4)
    if pad_to:
        out += b"\x00" * ((pad_to - len(out) % pad_to) % pad_to)
    return bytes(out)


def cpio_read_full(path):
    """Return list of (name, mode, data) from a newc cpio (dirs => data b'')."""
    data = open(path, "rb").read()
    entries = []
    i = 0
    while i + 110 <= len(data):
        if data[i:i + 6] != b"070701":
            i += 1
            continue
        hdr = data[i:i + 110]
        f = [int(hdr[6 + 8 * k:6 + 8 * (k + 1)], 16) for k in range(13)]
        mode, filesize, namesize = f[1], f[6], f[11]
        name = data[i + 110:i + 110 + namesize - 1].decode("utf-8", "replace")
        off = (i + 110 + namesize + 3) & ~3
        filedata = data[off:off + filesize] if not name.endswith("/") else b""
        i = (off + filesize + 3) & ~3
        if name == "TRAILER!!!":
            break
        entries.append((name, mode, filedata))
    return entries


# ------------------------------------------------------------------ vendor_boot
class VendorBoot:
    def __init__(self, path):
        self.path = path
        self.raw = open(path, "rb").read()
        h = parse_vendor_boot(self.raw)
        if not h:
            raise ValueError("not a vendor_boot image")
        self.h = h
        self.page = h["page_size"]
        self.ramdisk = self.raw[self.page:self.page + h["vendor_ramdisk_size"]]
        dtb_off = self.page + self._pages(h["vendor_ramdisk_size"]) * self.page
        self.dtb = self.raw[dtb_off:dtb_off + h["dtb_size"]]
        self.bootconfig = b""

    def _pages(self, size):
        return (size + self.page - 1) // self.page

    def build(self, ramdisk, dtb=None, bootconfig=None):
        dtb = self.dtb if dtb is None else dtb
        bc = self.bootconfig if bootconfig is None else bootconfig
        h = bytearray(self.h["header_size"])
        # magic .. vendor_ramdisk_size
        struct.pack_into("<8s5I", h, 0, b"VNDRBOOT", 4, self.page,
                         0x40000000, 0x66F00000, len(ramdisk))
        cmdline = self.h["cmdline"].encode()[:2048]
        h[28:28 + len(cmdline)] = cmdline
        struct.pack_into("<I", h, 28 + 2048, 0x47C80000)          # tags_addr
        struct.pack_into("<2I", h, 28 + 2048 + 4 + 16, 2128, len(dtb))
        struct.pack_into("<Q", h, 28 + 2048 + 4 + 16 + 8, 0x47C80000)
        if len(h) >= 2128:
            struct.pack_into("<4I", h, 2112, 0, 0, 0, len(bc))
        out = bytearray()
        out += h
        out += b"\x00" * (self._pages(len(h)) * self.page - len(h))
        out += ramdisk
        out += b"\x00" * (self._pages(len(ramdisk)) * self.page - len(ramdisk))
        out += dtb
        out += b"\x00" * (self._pages(len(dtb)) * self.page - len(dtb))
        out += bc
        out += b"\x00" * (self._pages(len(bc)) * self.page - len(bc))
        return bytes(out)


def cmd_info(path):
    v = VendorBoot(path)
    print("header version", v.h["version"], "page", v.page)
    print("ramdisk", len(v.ramdisk), "dtb", len(v.dtb), "cmdline", v.h["cmdline"])
    print("total", len(v.raw))


def cmd_roundtrip(stock, out):
    v = VendorBoot(stock)
    raw_cpio = decompress(v.ramdisk)
    entries = cpio_read_full_bytes(raw_cpio, v.ramdisk)
    print("stock entries:", len(entries), "ramdisk cpio:", len(raw_cpio))
    packed = cpio_pack(entries, pad_to=0)
    comp = lz4_legacy_compress(packed)
    print("repacked cpio:", len(packed), "lz4:", len(comp), "orig lz4:", len(v.ramdisk))
    img = v.build(comp)
    open(out, "wb").write(img)
    print("wrote", out, len(img), "bytes (partition 64MB)")
    # verify round trip
    v2 = VendorBoot(out)
    raw2 = decompress(v2.ramdisk)
    e2 = cpio_read_full_bytes(raw2, None)
    a = [(n, len(d)) for n, m, d in entries]
    b = [(n, len(d)) for n, m, d in e2]
    print("verify entries:", "OK" if a == b else "MISMATCH (%d vs %d)" % (len(a), len(b)))
    print("verify dtb:", "OK" if v2.dtb == v.dtb else "MISMATCH")
    print("verify cmdline:", "OK" if v2.h["cmdline"] == v.h["cmdline"] else "MISMATCH")


def cpio_read_full_bytes(raw_cpio, _):
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp.cpio")
    open(tmp, "wb").write(raw_cpio)
    try:
        return cpio_read_full(tmp)
    finally:
        os.remove(tmp)


def cmd_repack(stock, ramdisk_cpio, out, compress_mode="lz4"):
    v = VendorBoot(stock)
    raw = open(ramdisk_cpio, "rb").read()
    if raw[:6] == b"070701":
        packed = raw
    else:
        raise SystemExit("ramdisk must be an uncompressed newc cpio")
    comp = lz4_legacy_compress(packed) if compress_mode == "lz4" else zlib.compress(packed, 9)
    img = v.build(comp)
    open(out, "wb").write(img)
    print("wrote %s: cpio=%d %s=%d image=%d" % (out, len(packed), compress_mode, len(comp), len(img)))


def build_from_scratch(ramdisk_cpio, dtb, cmdline, out, compress="lz4"):
    """Create a vendor_boot v4 image from a raw newc cpio + dtb + cmdline."""
    page = 4096
    comp = lz4_legacy_compress(ramdisk_cpio) if compress == "lz4" else zlib.compress(ramdisk_cpio, 9)
    hdr = bytearray(2128)
    struct.pack_into("<8s5I", hdr, 0, b"VNDRBOOT", 4, page, 0x40000000, 0x66F00000, len(comp))
    cb = cmdline.encode()[:2047]
    hdr[28:28 + len(cb)] = cb
    struct.pack_into("<I", hdr, 28 + 2048, 0x47C80000)          # tags_addr
    struct.pack_into("<2I", hdr, 28 + 2048 + 4 + 16, 2128, len(dtb))
    struct.pack_into("<Q", hdr, 28 + 2048 + 4 + 16 + 8, 0x47C80000)
    struct.pack_into("<4I", hdr, 2112, 0, 0, 0, 0)
    out_b = bytearray(hdr)
    out_b += b"\x00" * (page - len(hdr) % page if len(hdr) % page else 0)
    out_b += comp
    out_b += b"\x00" * ((page - len(comp) % page) % page)
    out_b += dtb
    out_b += b"\x00" * ((page - len(dtb) % page) % page)
    open(out, "wb").write(out_b)
    print("wrote %s: ramdisk cpio=%d %s=%d dtb=%d image=%d (partition 64MB)"
          % (out, len(ramdisk_cpio), compress, len(comp), len(dtb), len(out_b)))


def build_boot_v2(kernel, ramdisk_comp, cmdline, out, page=4096):
    """Create a classic boot/recovery image (header v2): kernel + compressed ramdisk."""
    hdr = bytearray(page)
    struct.pack_into("<8s6I", hdr, 0, b"ANDROID!",
                     len(kernel), 0x00008000, len(ramdisk_comp), 0x01000000, 0, 0)
    # tags_addr, page_size, header_version(2), os_version
    struct.pack_into("<4I", hdr, 32, 0x00000100, page, 2, 0)
    cb = cmdline.encode()[:511]
    hdr[64:64 + len(cb)] = cb
    # header v2 extra fields
    struct.pack_into("<Q", hdr, 1608, 0)      # recovery_dtbo_size
    struct.pack_into("<Q", hdr, 1616, 0)      # recovery_dtbo_offset
    struct.pack_into("<I", hdr, 1624, 1628)   # header_size
    out_b = bytearray(hdr)
    out_b += kernel
    out_b += b"\x00" * ((page - len(kernel) % page) % page)
    out_b += ramdisk_comp
    out_b += b"\x00" * ((page - len(ramdisk_comp) % page) % page)
    open(out, "wb").write(out_b)
    print("wrote %s: kernel=%d ramdisk=%d image=%d"
          % (out, len(kernel), len(ramdisk_comp), len(out_b)))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "info":
        cmd_info(sys.argv[2])
    elif cmd == "roundtrip":
        cmd_roundtrip(sys.argv[2], sys.argv[3])
    elif cmd == "repack":
        cmd_repack(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "mkboot":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--kernel", required=True)
        ap.add_argument("--ramdisk", required=True, help="uncompressed newc cpio")
        ap.add_argument("--cmdline", default="bootopt=64S3,32N2,64N2 bootconfig buildvariant=user")
        ap.add_argument("--out", required=True)
        a = ap.parse_args(sys.argv[2:])
        comp = lz4_legacy_compress(open(a.ramdisk, "rb").read())
        build_boot_v2(open(a.kernel, "rb").read(), comp, a.cmdline, a.out)
    elif cmd == "build":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--ramdisk", required=True)
        ap.add_argument("--dtb", required=True)
        ap.add_argument("--cmdline", default="bootopt=64S3,32N2,64N2 buildvariant=user")
        ap.add_argument("--out", required=True)
        ap.add_argument("--gzip", action="store_true")
        a = ap.parse_args(sys.argv[2:])
        build_from_scratch(open(a.ramdisk, "rb").read(), open(a.dtb, "rb").read(),
                           a.cmdline, a.out, "gzip" if a.gzip else "lz4")
    else:
        print(__doc__)
