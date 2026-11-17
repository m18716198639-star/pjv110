LOCAL_PATH := device/oplus/PJV110

PRODUCT_PROPERTY_OVERRIDES += \
    ro.hardware=mt6895 \
    ro.board.platform=mt6895 \
    ro.product.device=PJV110

# Android 16 release configs (ap2a/bp2a) ship CrashRecovery as an APEX.  A
# minimal recovery product that inherits base.mk must declare its
# system-server jar, otherwise soong aborts while generating the ninja file:
#   prebuilt_com.android.crashrecovery-systemserverclasspath-fragment:
#   [service-crashrecovery] in contents must also be declared in
#   PRODUCT_APEX_SYSTEM_SERVER_JARS
PRODUCT_APEX_SYSTEM_SERVER_JARS += com.android.crashrecovery:service-crashrecovery

# Nothing else is copied here on purpose: kernel modules, firmware and the
# generated init.recovery.mt6895.rc are injected after the build by
# scripts/pack.sh (they come from prebuilt/*.tar.gz, extracted from the stock
# vendor_boot ramdisk of this exact ROM).
