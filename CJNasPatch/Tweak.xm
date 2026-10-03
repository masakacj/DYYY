#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

static IMP CJNasOriginalHandleVideoData = NULL;

static void CJNasShowLoadedToast(void) {
    dispatch_async(dispatch_get_main_queue(), ^{
        Class utils = NSClassFromString(@"DYYYUtils");
        SEL selector = NSSelectorFromString(@"showToast:");
        if (utils && [utils respondsToSelector:selector]) {
            ((void (*)(id, SEL, id))objc_msgSend)(utils, selector, @"CJNasPatch 已加载");
        }
    });
}

static void CJNasHandleVideoData(id self, SEL _cmd, NSDictionary *dataDict) {
    // 第一版保持 DYYY 原始数据处理完全不变，只验证独立补丁可稳定 hook 2.3-0#19。
    if (CJNasOriginalHandleVideoData) {
        ((void (*)(id, SEL, NSDictionary *))CJNasOriginalHandleVideoData)(self, _cmd, dataDict);
    }
}

__attribute__((constructor))
static void CJNasPatchInit(void) {
    @autoreleasepool {
        Class manager = NSClassFromString(@"DYYYManager");
        if (!manager) return;

        Class meta = object_getClass(manager);
        SEL selector = NSSelectorFromString(@"handleVideoData:");
        Method method = class_getClassMethod(manager, selector);
        if (!method) return;

        IMP current = method_getImplementation(method);
        if (current == (IMP)CJNasHandleVideoData) return;

        CJNasOriginalHandleVideoData = current;
        method_setImplementation(method, (IMP)CJNasHandleVideoData);

        NSLog(@"[CJNasPatch] hooked +[DYYYManager handleVideoData:]");
        CJNasShowLoadedToast();
    }
}
