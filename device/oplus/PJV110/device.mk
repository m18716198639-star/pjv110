LOCAL_PATH := device/oplus/PJV110

PRODUCT_PROPERTY_OVERRIDES += \
    ro.hardware=mt6895 \
    ro.board.platform=mt6895 \
    ro.product.device=PJV110

# Nothing else is copied here on purpose: kernel modules, firmware and the
# generated init.recovery.mt6895.rc are injected after the build by
# scripts/pack.sh (they come from prebuilt/*.tar.gz, extracted from the stock
# vendor_boot ramdisk of this exact ROM).
