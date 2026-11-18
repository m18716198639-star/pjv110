#
# OrangeFox / TWRP board configuration
# Device : OPPO Reno12 (PJV110 / PLJ110, mt6895 / Dimensity 8250)
# ROM    : ColorOS 17 (Android 17 userspace, GKI 6.12 kernel)
#
# Recovery does NOT live in a recovery partition on this device: it is packed
# into the vendor_boot ramdisk (A/B, no recovery partition).  We build a normal
# recovery.img here only to obtain the OrangeFox ramdisk, then repack it into a
# vendor_boot image with tools/mkvendor_boot.py (see scripts/pack.sh).
#

DEVICE_PATH := device/oplus/PJV110

# ------------------------------------------------------------------ platform
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-2a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_ABI2 :=
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RECOVERY := generic
TARGET_SUPPORTS_64_BIT_APPS := true

TARGET_BOARD_PLATFORM := mt6895
TARGET_BOOTLOADER_BOARD_NAME := mt6895
TARGET_OTA_ASSERT_DEVICE := PJV110,PLJ110,OP5E17L1

# ------------------------------------------------------------------ kernel
TARGET_PREBUILT_KERNEL := $(DEVICE_PATH)/prebuilt/kernel
BOARD_KERNEL_IMAGE_NAME := Image
BOARD_KERNEL_CMDLINE := bootopt=64S3,32N2,64N2 buildvariant=user
BOARD_KERNEL_BASE := 0x40000000
BOARD_KERNEL_PAGESIZE := 4096
# The recovery.img built here is only used as a container for the OrangeFox
# ramdisk (it gets repacked into vendor_boot afterwards), so keep the legacy
# header version that every TWRP branch handles.
BOARD_BOOT_HEADER_VERSION := 2
BOARD_MKBOOTIMG_ARGS += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS += --pagesize $(BOARD_KERNEL_PAGESIZE)

# ------------------------------------------------------------------ partitions
BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_DTBOIMG_PARTITION_SIZE := 8388608

BOARD_SUPER_PARTITION_SIZE := 15678308352
BOARD_SUPER_PARTITION_GROUPS := oplus_dynamic_partitions
BOARD_OPLUS_DYNAMIC_PARTITIONS_PARTITION_LIST := \
    system system_ext product vendor odm vendor_dlkm odm_dlkm system_dlkm \
    my_product my_stock my_heytap my_carrier my_company my_engineering \
    my_manifest my_preload my_region my_bigball
BOARD_OPLUS_DYNAMIC_PARTITIONS_SIZE := 15674114048
BOARD_USES_METADATA_PARTITION := true

# The device is A/B without a dedicated recovery partition, but the classic
# recovery.img code path in the build system is gated on
# BOARD_RECOVERYIMAGE_PARTITION_SIZE.  We only use that image as a container
# for the OrangeFox ramdisk, which scripts/pack.sh then repacks into
# vendor_boot (the partition this bootloader actually uses for recovery).
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 67108864

# ------------------------------------------------------------------ recovery
TARGET_RECOVERY_FSTAB := $(DEVICE_PATH)/recovery.fstab
TARGET_RECOVERY_PIXEL_FORMAT := RGBX_8888
TARGET_USES_MKE2FS := true
TARGET_RECOVERY_DEVICE_MODULES :=

TW_THEME := portrait_hdpi
TW_SCREEN_BLANK_ON_BOOT := true
TW_MAX_BRIGHTNESS := 2047
TW_DEFAULT_BRIGHTNESS := 1024
TW_HAS_MTP := true
TW_EXCLUDE_DEFAULT_USB_INIT := true
TW_EXTRA_LANGUAGES := true
TW_DEFAULT_LANGUAGE := zh_CN
TW_INPUT_BLACKLIST := "hbtp_vm"
TW_USE_TOOLBOX := true
TW_INCLUDE_FASTBOOTD := true
TW_INCLUDE_FUSE_EXFAT := true
TW_INCLUDE_FUSE_NTFS := true

# No /data decryption: the device uses f2fs + metadata encryption and a
# vendor keymaster (Trustonic) that recovery cannot talk to yet.
TW_INCLUDE_CRYPTO := false
TW_INCLUDE_CRYPTO_FBE := false
TW_INCLUDE_FBE_METADATA_DECRYPT := false

# ------------------------------------------------------------------ OrangeFox
OF_SCREEN_H := 2400
OF_STATUS_H := 99
OF_STATUS_INDENT_LEFT := 48
OF_STATUS_INDENT_RIGHT := 48
OF_HIDE_NOTCH := 1
OF_CLOCK_POS := 1
OF_ALLOW_DISABLE_NAVBAR := 0
OF_DISABLE_OTA_MENU := 1
OF_NO_TREBLE_CHECK := 1
OF_SKIP_MULTIUSER_FOLDERS_BACKUP := 1
OF_QUICK_BACKUP_LIST := "/boot;"
