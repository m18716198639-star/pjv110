#!/usr/bin/env bash
#
# Build the OrangeFox vendor_boot image for PJV110 from the recovery.img that
# the AOSP/OrangeFox build produced.
#
#   SRC=$HOME/fox bash scripts/pack.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${SRC:-$HOME/fox}"
OUT="$ROOT/out"
PART_SIZE=67108864

rm -rf "$OUT"
mkdir -p "$OUT"

PRODUCT_OUT="$SRC/out/target/product/PJV110"
IMG=""
for CAND in recovery.img boot.img; do
    IMG="$(find "$PRODUCT_OUT" -maxdepth 1 -name "$CAND" 2>/dev/null | head -n1 || true)"
    [ -n "$IMG" ] && break
done
if [ -z "$IMG" ]; then
    IMG="$(find "$PRODUCT_OUT" -maxdepth 1 -name 'OrangeFox-*.img' 2>/dev/null | head -n1 || true)"
fi
if [ -z "$IMG" ]; then
    echo "!! no recovery/boot/OrangeFox image found under $PRODUCT_OUT"
    find "$SRC/out/target/product" -maxdepth 2 -name '*.img' 2>/dev/null | head -n 40 || true
    exit 1
fi
echo "== source image: $IMG"
ls -l "$IMG"

echo "== unpack recovery ramdisk"
python3 "$ROOT/tools/androidimg.py" unpack "$IMG" "$OUT/rec"
CPIO="$OUT/rec/ramdisk.cpio"
if [ ! -f "$CPIO" ]; then
    echo "!! ramdisk.cpio not produced"
    ls -l "$OUT/rec" || true
    exit 1
fi

echo "== extract ramdisk"
python3 "$ROOT/tools/cpio_tool.py" extract "$CPIO" "$OUT/root"

echo "== inject vendor modules and firmware from the stock vendor_boot"
tar -xzf "$ROOT/prebuilt/modules.tar.gz"      -C "$OUT/root"
tar -xzf "$ROOT/prebuilt/modules-meta.tar.gz" -C "$OUT/root"
tar -xzf "$ROOT/prebuilt/firmware.tar.gz"     -C "$OUT/root"

MODS="$OUT/root/lib/modules/modules.load.recovery"
if [ ! -f "$MODS" ]; then
    echo "!! modules.load.recovery missing after extraction"
    exit 1
fi

echo "== generate init.recovery.mt6895.rc"
python3 "$ROOT/tools/gen_init_rc.py" "$MODS" "$OUT/root/init.recovery.mt6895.rc"

# Make sure TWRP's init.rc imports our rc file even if the branch uses a
# different property for the import path.
if [ -f "$OUT/root/init.rc" ] && ! grep -q 'init.recovery.mt6895.rc' "$OUT/root/init.rc"; then
    printf '\nimport /init.recovery.mt6895.rc\n' >> "$OUT/root/init.rc"
fi

if [ ! -e "$OUT/root/init" ] && [ ! -L "$OUT/root/init" ]; then
    ln -s /system/bin/init "$OUT/root/init"
fi

# TARGET_RECOVERY_FSTAB is handled differently across branches; make sure the
# fstab is where TWRP expects it.
mkdir -p "$OUT/root/etc"
if [ ! -f "$OUT/root/etc/recovery.fstab" ]; then
    cp "$ROOT/device/oplus/PJV110/recovery.fstab" "$OUT/root/etc/recovery.fstab"
fi
mkdir -p "$OUT/root/system/etc"
if [ ! -f "$OUT/root/system/etc/recovery.fstab" ]; then
    cp "$ROOT/device/oplus/PJV110/recovery.fstab" "$OUT/root/system/etc/recovery.fstab"
fi

echo "== repack ramdisk"
python3 "$ROOT/tools/cpio_tool.py" pack "$OUT/root" "$OUT/ramdisk.cpio"

echo "== build vendor_boot image"
python3 "$ROOT/tools/mkvendor_boot.py" build \
    --ramdisk "$OUT/ramdisk.cpio" \
    --dtb "$ROOT/prebuilt/dtb.bin" \
    --cmdline "bootopt=64S3,32N2,64N2 bootconfig buildvariant=user" \
    --out "$OUT/OrangeFox-PJV110-vendor_boot.img"

SIZE=$(stat -c%s "$OUT/OrangeFox-PJV110-vendor_boot.img")
echo "== final image size: $SIZE (partition $PART_SIZE)"
if [ "$SIZE" -ge "$PART_SIZE" ]; then
    echo "!! image does not fit in vendor_boot"
    exit 1
fi

cp "$OUT/OrangeFox-PJV110-vendor_boot.img" "$ROOT/OrangeFox-PJV110-vendor_boot.img"
ls -l "$ROOT/OrangeFox-PJV110-vendor_boot.img"

# Keep OrangeFox's own boot-as-recovery image/zip as extra artifacts (not used
# for flashing on this device, but useful for reference/backup).
for f in "$PRODUCT_OUT"/OrangeFox-*.img "$PRODUCT_OUT"/OrangeFox-*.zip; do
    if [ -e "$f" ]; then
        cp -f "$f" "$ROOT/" && echo "copied $(basename "$f")"
    fi
done
