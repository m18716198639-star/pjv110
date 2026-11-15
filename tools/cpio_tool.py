#!/usr/bin/env python3
"""newc cpio extract/pack that preserves symlinks and modes (run on Linux CI).

  python3 cpio_tool.py extract <file.cpio> <outdir>
  python3 cpio_tool.py pack    <dir> <out.cpio>
  python3 cpio_tool.py list    <file.cpio> [substr]
"""

import os
import stat
import struct
import sys


def read_cpio(path):
    data = open(path, "rb").read()
    i = 0
    while i + 110 <= len(data):
        if data[i:i + 6] != b"070701":
            i += 1
            continue
        hdr = data[i:i + 110]
        f = [int(hdr[6 + 8 * k:6 + 8 * (k + 1)], 16) for k in range(13)]
        ino, mode, uid, gid, nlink, mtime, filesize, devmaj, devmin, rdevmaj, rdevmin, namesize, _ = f
        name = data[i + 110:i + 110 + namesize - 1].decode("utf-8", "replace")
        off = (i + 110 + namesize + 3) & ~3
        blob = data[off:off + filesize]
        i = (off + filesize + 3) & ~3
        if name == "TRAILER!!!":
            break
        yield name, mode, blob


def cmd_extract(src, outdir):
    outdir = os.path.abspath(outdir)
    count = 0
    for name, mode, blob in read_cpio(src):
        rel = name.lstrip("/")
        dst = os.path.join(outdir, rel)
        fmt = stat.S_IFMT(mode)
        try:
            if fmt == stat.S_IFDIR:
                os.makedirs(dst, exist_ok=True)
            elif fmt == stat.S_IFLNK:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.lexists(dst):
                    os.unlink(dst)
                os.symlink(blob.decode("utf-8", "replace"), dst)
            elif fmt in (stat.S_IFREG, 0):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.lexists(dst):
                    os.unlink(dst)
                with open(dst, "wb") as fp:
                    fp.write(blob)
                os.chmod(dst, stat.S_IMODE(mode) or 0o644)
        except (FileExistsError, NotADirectoryError, PermissionError) as e:
            print("skip", rel, e, file=sys.stderr)
        count += 1
    print("extracted %d entries to %s" % (count, outdir))


def _entry(name, mode, blob, ino):
    name_b = name.encode() + b"\x00"
    header = b"070701" + b"".join(
        struct.pack("<8s", b"%08X" % v)
        for v in (ino, mode, 0, 0, 1, 0, len(blob), 0, 0, 0, 0, len(name_b), 0)
    )
    pad1 = b"\x00" * ((4 - (len(header) + len(name_b)) % 4) % 4)
    pad2 = b"\x00" * ((4 - len(blob) % 4) % 4)
    return header + name_b + pad1 + blob + pad2


def cmd_pack(src, out):
    src = os.path.abspath(src)
    items = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for d in dirs:
            full = os.path.join(root, d)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            if os.path.islink(full):
                items.append((rel, stat.S_IFLNK | 0o777, os.readlink(full).encode()))
            else:
                items.append((rel + "/", stat.S_IFDIR | 0o755, b""))
        for f in sorted(files):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                items.append((rel, stat.S_IFLNK | 0o777, os.readlink(full).encode()))
            else:
                with open(full, "rb") as fp:
                    blob = fp.read()
                mode = stat.S_IFREG | (0o755 if st.st_mode & 0o111 else 0o644)
                items.append((rel, mode, blob))
    items.sort(key=lambda x: x[0])
    out_b = bytearray()
    for i, (name, mode, blob) in enumerate(items, 1):
        out_b += _entry(name, mode, blob, i)
    out_b += _entry("TRAILER!!!", 0, b"", 0)
    open(out, "wb").write(out_b)
    print("packed %d entries -> %s (%d bytes)" % (len(items), out, len(out_b)))


def cmd_list(src, pat=None):
    n = 0
    for name, mode, blob in read_cpio(src):
        if pat and pat not in name:
            continue
        print("%o %9d %s" % (mode, len(blob), name))
        n += 1
    print("--", n)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    elif sys.argv[1] == "extract":
        cmd_extract(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "pack":
        cmd_pack(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "list":
        cmd_list(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print(__doc__)
