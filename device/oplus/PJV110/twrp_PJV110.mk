#
# OPPO Reno12 (PJV110) — product definition for OrangeFox/TWRP
#

DEVICE_PATH := device/oplus/PJV110

$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit.mk)

# Branch-safe minimal base: embedded.mk exists on some manifests, base.mk on others.
ifeq ($(wildcard $(SRC_TARGET_DIR)/product/embedded.mk),)
$(call inherit-product, $(SRC_TARGET_DIR)/product/base.mk)
else
$(call inherit-product, $(SRC_TARGET_DIR)/product/embedded.mk)
endif

ifneq ($(wildcard $(SRC_TARGET_DIR)/product/languages_full.mk),)
$(call inherit-product, $(SRC_TARGET_DIR)/product/languages_full.mk)
endif

$(call inherit-product, $(DEVICE_PATH)/device.mk)

PRODUCT_NAME := twrp_PJV110
PRODUCT_DEVICE := PJV110
PRODUCT_BRAND := OPPO
PRODUCT_MODEL := PJV110
PRODUCT_MANUFACTURER := OPPO
PRODUCT_RELEASE_NAME := PJV110

PRODUCT_BUILD_PROP_OVERRIDES += \
    PRODUCT_NAME=PJV110 \
    TARGET_DEVICE=PJV110
