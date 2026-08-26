#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
if not manager.exists():
    raise SystemExit(f"Missing required file: {manager}")

text = manager.read_text(encoding="utf-8")

old = r'''+ (NSString *)dyyy_downloadStemForAweme:(AWEAwemeModel *)awemeModel {
    id author = nil;
    @try { author = [awemeModel valueForKey:@"author"]; } @catch (__unused NSException *e) {}
    NSString *nickname = nil;
    NSString *douyinID = nil;
    @try { nickname = [author valueForKey:@"nickname"]; } @catch (__unused NSException *e) {}
    @try { douyinID = [author valueForKey:@"shortID"]; } @catch (__unused NSException *e) {}
    if (douyinID.length == 0) { @try { douyinID = [author valueForKey:@"uniqueID"]; } @catch (__unused NSException *e) {} }
    if (douyinID.length == 0) { @try { douyinID = [author valueForKey:@"uid"]; } @catch (__unused NSException *e) {} }
    nickname = [self dyyy_safeFilenamePart:nickname fallback:@"unknown"];
    douyinID = [self dyyy_safeFilenamePart:douyinID fallback:@"unknown"];
    NSTimeInterval timestamp = 0;
    @try {
        id rawCreateTime = [awemeModel valueForKey:@"createTime"];
        if ([rawCreateTime respondsToSelector:@selector(doubleValue)]) timestamp = [rawCreateTime doubleValue];
    } @catch (__unused NSException *e) {}
    if (timestamp > 100000000000.0) timestamp /= 1000.0;
    NSDate *date = timestamp > 0 ? [NSDate dateWithTimeIntervalSince1970:timestamp] : [NSDate date];
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateFormat = @"yyyyMMdd_HHmm";
    formatter.locale = [NSLocale localeWithLocaleIdentifier:@"zh_CN"];
    formatter.timeZone = [NSTimeZone localTimeZone];
    return [NSString stringWithFormat:@"%@_%@_%@", nickname, douyinID, [formatter stringFromDate:date]];
}
'''

new = r'''+ (id)dyyy_safeValueForObject:(id)obj key:(NSString *)key {
    if (!obj || key.length == 0) return nil;
    @try {
        return [obj valueForKey:key];
    } @catch (__unused NSException *e) {
        return nil;
    }
}

+ (BOOL)dyyy_awemeHasUsableAuthor:(id)candidate {
    id author = [self dyyy_safeValueForObject:candidate key:@"author"];
    if (!author) return NO;
    NSString *nickname = [self dyyy_safeValueForObject:author key:@"nickname"];
    NSString *shortID = [self dyyy_safeValueForObject:author key:@"shortID"];
    NSString *uniqueID = [self dyyy_safeValueForObject:author key:@"uniqueID"];
    NSString *uid = [self dyyy_safeValueForObject:author key:@"uid"];
    return nickname.length > 0 || shortID.length > 0 || uniqueID.length > 0 || uid.length > 0;
}

+ (BOOL)dyyy_aweme:(id)candidate matchesSource:(id)source {
    if (!candidate || !source) return NO;

    NSString *sourceItemID = [self dyyy_safeValueForObject:source key:@"itemID"];
    NSString *candidateItemID = [self dyyy_safeValueForObject:candidate key:@"itemID"];
    if (sourceItemID.length > 0 && candidateItemID.length > 0) {
        return [sourceItemID isEqualToString:candidateItemID];
    }

    NSString *sourceShareURL = [self dyyy_safeValueForObject:source key:@"shareURL"];
    NSString *candidateShareURL = [self dyyy_safeValueForObject:candidate key:@"shareURL"];
    if (sourceShareURL.length > 0 && candidateShareURL.length > 0) {
        return [sourceShareURL isEqualToString:candidateShareURL];
    }

    return candidate == source;
}

+ (id)dyyy_resolveFullAweme:(AWEAwemeModel *)awemeModel {
    if ([self dyyy_awemeHasUsableAuthor:awemeModel]) return awemeModel;

    id currentAweme = [self dyyy_safeValueForObject:awemeModel key:@"currentAweme"];
    if ([self dyyy_awemeHasUsableAuthor:currentAweme] &&
        ([self dyyy_aweme:currentAweme matchesSource:awemeModel] || awemeModel == currentAweme)) {
        return currentAweme;
    }

    for (NSString *key in @[@"aweme", @"awemeModel", @"model", @"item", @"rawAweme"]) {
        id nested = [self dyyy_safeValueForObject:awemeModel key:key];
        if ([self dyyy_awemeHasUsableAuthor:nested] &&
            [self dyyy_aweme:nested matchesSource:awemeModel]) {
            return nested;
        }
    }

    UIWindow *window = nil;
    for (UIWindow *candidateWindow in [UIApplication sharedApplication].windows) {
        if (!candidateWindow.hidden && candidateWindow.alpha > 0.0 && candidateWindow.windowLevel == UIWindowLevelNormal) {
            window = candidateWindow;
            break;
        }
    }
    UIViewController *root = window.rootViewController;
    if (!root) return awemeModel;

    NSMutableArray<UIViewController *> *queue = [NSMutableArray arrayWithObject:root];
    NSMutableSet<NSValue *> *visited = [NSMutableSet set];
    while (queue.count > 0) {
        UIViewController *vc = queue.firstObject;
        [queue removeObjectAtIndex:0];
        NSValue *ptr = [NSValue valueWithNonretainedObject:vc];
        if ([visited containsObject:ptr]) continue;
        [visited addObject:ptr];

        id candidate = [self dyyy_safeValueForObject:vc key:@"model"];
        if ([self dyyy_awemeHasUsableAuthor:candidate] &&
            [self dyyy_aweme:candidate matchesSource:awemeModel]) {
            return candidate;
        }

        if (vc.presentedViewController) [queue addObject:vc.presentedViewController];
        if ([vc isKindOfClass:[UINavigationController class]]) {
            UIViewController *visible = ((UINavigationController *)vc).visibleViewController;
            if (visible) [queue addObject:visible];
        }
        if ([vc isKindOfClass:[UITabBarController class]]) {
            UIViewController *selected = ((UITabBarController *)vc).selectedViewController;
            if (selected) [queue addObject:selected];
        }
        for (UIViewController *child in vc.childViewControllers) {
            if (child) [queue addObject:child];
        }
    }

    return awemeModel;
}

+ (NSString *)dyyy_downloadStemForAweme:(AWEAwemeModel *)awemeModel {
    id effectiveAweme = [self dyyy_resolveFullAweme:awemeModel];
    id author = [self dyyy_safeValueForObject:effectiveAweme key:@"author"];

    NSString *nickname = [self dyyy_safeValueForObject:author key:@"nickname"];
    NSString *douyinID = [self dyyy_safeValueForObject:author key:@"shortID"];
    if (douyinID.length == 0) douyinID = [self dyyy_safeValueForObject:author key:@"uniqueID"];
    if (douyinID.length == 0) douyinID = [self dyyy_safeValueForObject:author key:@"uid"];

    nickname = [self dyyy_safeFilenamePart:nickname fallback:@"unknown"];
    douyinID = [self dyyy_safeFilenamePart:douyinID fallback:@"unknown"];

    NSTimeInterval timestamp = 0;
    id rawCreateTime = [self dyyy_safeValueForObject:effectiveAweme key:@"createTime"];
    if ([rawCreateTime respondsToSelector:@selector(doubleValue)]) timestamp = [rawCreateTime doubleValue];
    if (timestamp <= 0 && effectiveAweme != awemeModel) {
        rawCreateTime = [self dyyy_safeValueForObject:awemeModel key:@"createTime"];
        if ([rawCreateTime respondsToSelector:@selector(doubleValue)]) timestamp = [rawCreateTime doubleValue];
    }

    if (timestamp > 100000000000.0) timestamp /= 1000.0;
    NSDate *date = timestamp > 0 ? [NSDate dateWithTimeIntervalSince1970:timestamp] : [NSDate date];
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateFormat = @"yyyyMMdd_HHmm";
    formatter.locale = [NSLocale localeWithLocaleIdentifier:@"zh_CN"];
    formatter.timeZone = [NSTimeZone localTimeZone];

    return [NSString stringWithFormat:@"%@_%@_%@", nickname, douyinID, [formatter stringFromDate:date]];
}
'''

if new not in text:
    if old not in text:
        raise RuntimeError("dyyy_downloadStemForAweme patch point not found")
    text = text.replace(old, new, 1)

manager.write_text(text, encoding="utf-8")
print("Applied current-aweme identity-matched metadata resolver")
