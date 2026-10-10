#import "KwaiParseManager.h"

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

static BOOL KwaiParseIsTargetApp(void) {
    NSString *bundleID = NSBundle.mainBundle.bundleIdentifier;
    return [bundleID isEqualToString:@"com.jiangjia.gif"];
}

%hook UIViewController

- (void)viewDidAppear:(BOOL)animated {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] attachLongPressToController:self];
    }
}

%end

%hook UIPasteboard

- (void)setString:(NSString *)string {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateText:string];
    }
}

- (void)setStrings:(NSArray<NSString *> *)strings {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateItems:strings];
    }
}

- (void)setURL:(NSURL *)URL {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateText:URL.absoluteString];
    }
}

- (void)setURLs:(NSArray<NSURL *> *)URLs {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateItems:URLs];
    }
}

- (void)setItems:(NSArray<NSDictionary<NSString *, id> *> *)items {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateItems:items];
    }
}

- (void)setItems:(NSArray<NSDictionary<NSString *, id> *> *)items
         options:(NSDictionary<UIPasteboardOption, id> *)options {
    %orig;
    if (KwaiParseIsTargetApp()) {
        [[KwaiParseManager shared] handleCandidateItems:items];
    }
}

%end

%ctor {
    @autoreleasepool {
        if (!KwaiParseIsTargetApp()) return;
        %init;

        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.2 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
          [[KwaiParseManager shared] showLoadedHint];
        });

        NSLog(@"[KwaiParsePatch] loaded in %@", NSBundle.mainBundle.bundleIdentifier);
    }
}
