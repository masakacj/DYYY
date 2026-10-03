ARCHS = arm64 arm64e
TARGET = iphone:clang:latest:15.0

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = CJNasPatch
CJNasPatch_FILES = Tweak.xm
CJNasPatch_CFLAGS = -fobjc-arc
CJNasPatch_FRAMEWORKS = Foundation UIKit
CJNasPatch_LDFLAGS = -Wl,-undefined,dynamic_lookup

include $(THEOS_MAKE_PATH)/tweak.mk
