ARCHS = arm64 arm64e
TARGET = iphone:clang:latest:15.0

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = KwaiParsePatch
KwaiParsePatch_FILES = Tweak.xm KwaiParseManager.m KwaiParseHUD.m
KwaiParsePatch_CFLAGS = -fobjc-arc
KwaiParsePatch_FRAMEWORKS = Foundation UIKit Photos QuartzCore
KwaiParsePatch_LDFLAGS = -Wl,-undefined,dynamic_lookup

include $(THEOS_MAKE_PATH)/tweak.mk
