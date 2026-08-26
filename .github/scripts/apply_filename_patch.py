#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager_h = root / "DYYYManager.h"
manager_m = root / "DYYYManager.m"
longpress = root / "DYYYLongPressPanel.xm"

for p in (manager_h, manager_m, longpress):
    if not p.exists():
        raise SystemExit(f"Missing required file: {p}")

def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Patch point not found: {label}")
    return text.replace(old, new, 1)

h = manager_h.read_text(encoding="utf-8")
decl = '+ (void)setDownloadAwemeModel:(AWEAwemeModel *)awemeModel;'
if decl not in h:
    h = replace_once(h, "+ (instancetype)shared;", "+ (instancetype)shared;\n\n/** 设置当前作品，供下载文件命名使用 */\n" + decl, "manager header")
manager_h.write_text(h, encoding="utf-8")

m = manager_m.read_text(encoding="utf-8")
prop = '@property(nonatomic, strong) NSMutableDictionary<NSString *, NSString *> *desiredFilenameMap;'
if prop not in m:
    m = replace_once(m,
        '@property(nonatomic, strong) NSMutableDictionary<NSString *, NSString *> *filePathToDownloadID;',
        '@property(nonatomic, strong) NSMutableDictionary<NSString *, NSString *> *filePathToDownloadID;\n' + prop,
        "filename map property")

if '_desiredFilenameMap = [NSMutableDictionary dictionary];' not in m:
    m = replace_once(m,
        '_filePathToDownloadID = [NSMutableDictionary dictionary];',
        '_filePathToDownloadID = [NSMutableDictionary dictionary];\n        _desiredFilenameMap = [NSMutableDictionary dictionary];',
        "filename map init")

if "DYYYFilenamePatchHelpers" not in m:
    helpers = r'''@implementation DYYYManager

#pragma mark - DYYYFilenamePatchHelpers

static AWEAwemeModel *sDYYYDownloadAwemeModel = nil;
static NSString *sDYYYDownloadStem = nil;
static NSInteger sDYYYLiveSequence = 0;

+ (void)setDownloadAwemeModel:(AWEAwemeModel *)awemeModel {
    sDYYYDownloadAwemeModel = awemeModel;
    sDYYYDownloadStem = [self dyyy_downloadStemForAweme:awemeModel];
    sDYYYLiveSequence = 0;
}

+ (NSString *)dyyy_safeFilenamePart:(NSString *)value fallback:(NSString *)fallback {
    NSString *result = [value isKindOfClass:[NSString class]] ? value : @"";
    result = [result stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
    if (result.length == 0) result = fallback ?: @"unknown";
    NSCharacterSet *illegal = [NSCharacterSet characterSetWithCharactersInString:@"/\\:*?\"<>|\n\r\t"];
    result = [[result componentsSeparatedByCharactersInSet:illegal] componentsJoinedByString:@"_"];
    while ([result containsString:@"__"]) {
        result = [result stringByReplacingOccurrencesOfString:@"__" withString:@"_"];
    }
    if (result.length > 80) result = [result substringToIndex:80];
    return result.length ? result : (fallback ?: @"unknown");
}

+ (NSString *)dyyy_downloadStemForAweme:(AWEAwemeModel *)awemeModel {
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

+ (NSString *)dyyy_defaultExtensionForMediaType:(MediaType)mediaType {
    switch (mediaType) {
        case MediaTypeVideo: return @"mp4";
        case MediaTypeAudio: return @"mp3";
        case MediaTypeHeic: return @"heic";
        case MediaTypeImage:
        default: return @"jpg";
    }
}

+ (NSString *)dyyy_filenameForMediaType:(MediaType)mediaType index:(NSInteger)index {
    NSString *stem = sDYYYDownloadStem;
    if (stem.length == 0) {
        stem = [self dyyy_downloadStemForAweme:sDYYYDownloadAwemeModel];
    }
    if (index > 0) stem = [stem stringByAppendingFormat:@"_%02ld", (long)index];
    return [stem stringByAppendingPathExtension:[self dyyy_defaultExtensionForMediaType:mediaType]];
}
'''
    m = replace_once(m, "@implementation DYYYManager\n", helpers, "helper insertion")

single_old = '''      NSString *downloadID = [NSUUID UUID].UUIDString;
      [[DYYYManager shared].progressViews setObject:progressView forKey:downloadID];'''
single_new = '''      NSString *downloadID = [NSUUID UUID].UUIDString;
      [[DYYYManager shared].progressViews setObject:progressView forKey:downloadID];

      NSString *desiredFilename = [self dyyy_filenameForMediaType:mediaType index:0];
      if (desiredFilename.length > 0) {
          [DYYYManager shared].desiredFilenameMap[downloadID] = desiredFilename;
      }'''
if single_new not in m:
    m = replace_once(m, single_old, single_new, "single filename")

bulk_marker = '''          NSString *downloadID = [NSUUID UUID].UUIDString;
          [[DYYYManager shared] associateDownload:downloadID withBatchID:batchID];'''
if 'dyyyBatchIndex' not in m:
    replacement = '''          NSString *downloadID = [NSUUID UUID].UUIDString;
          [[DYYYManager shared] associateDownload:downloadID withBatchID:batchID];
          NSInteger dyyyBatchIndex = [imageURLs indexOfObject:urlString] + 1;
          NSString *desiredFilename = [self dyyy_filenameForMediaType:MediaTypeImage index:dyyyBatchIndex];
          if (desiredFilename.length > 0) {
              [DYYYManager shared].desiredFilenameMap[downloadID] = desiredFilename;
          }'''
    m = replace_once(m, bulk_marker, replacement, "batch image filename")

delegate_old = '''    // 处理下载的文件
    NSString *fileName = [downloadTask.originalRequest.URL lastPathComponent];'''
delegate_new = '''    // 处理下载的文件
    NSString *fileName = self.desiredFilenameMap[downloadIDForTask];
    if (fileName.length == 0) {
        fileName = [downloadTask.originalRequest.URL lastPathComponent];
    }'''
if delegate_new not in m:
    m = replace_once(m, delegate_old, delegate_new, "delegate filename")

photos_old = '''      [[PHPhotoLibrary sharedPhotoLibrary]
          performChanges:^{
            if (mediaType == MediaTypeVideo) {
                [PHAssetChangeRequest creationRequestForAssetFromVideoAtFileURL:mediaURL];
            } else {
                UIImage *image = [UIImage imageWithContentsOfFile:mediaURL.path];
                if (image) {
                    [PHAssetChangeRequest creationRequestForAssetFromImage:image];
                }
            }
          }
          completionHandler:^(BOOL success, NSError *_Nullable error) {'''
photos_new = '''      [[PHPhotoLibrary sharedPhotoLibrary]
          performChanges:^{
            PHAssetCreationRequest *request = [PHAssetCreationRequest creationRequestForAsset];
            PHAssetResourceCreationOptions *options = [[PHAssetResourceCreationOptions alloc] init];
            options.originalFilename = mediaURL.lastPathComponent;
            PHAssetResourceType resourceType = (mediaType == MediaTypeVideo) ? PHAssetResourceTypeVideo : PHAssetResourceTypePhoto;
            [request addResourceWithType:resourceType fileURL:mediaURL options:options];
          }
          completionHandler:^(BOOL success, NSError *_Nullable error) {'''
if photos_new not in m:
    m = replace_once(m, photos_old, photos_new, "photo library original filename")

heic_old = '''          [[PHPhotoLibrary sharedPhotoLibrary]
              performChanges:^{
                UIImage *image = [UIImage imageWithContentsOfFile:mediaURL.path];
                if (image) {
                    [PHAssetChangeRequest creationRequestForAssetFromImage:image];
                }
              }
              completionHandler:^(BOOL success, NSError *_Nullable error) {'''
heic_new = '''          [[PHPhotoLibrary sharedPhotoLibrary]
              performChanges:^{
                PHAssetCreationRequest *request = [PHAssetCreationRequest creationRequestForAsset];
                PHAssetResourceCreationOptions *options = [[PHAssetResourceCreationOptions alloc] init];
                options.originalFilename = mediaURL.lastPathComponent;
                [request addResourceWithType:PHAssetResourceTypePhoto fileURL:mediaURL options:options];
              }
              completionHandler:^(BOOL success, NSError *_Nullable error) {'''
if heic_new not in m:
    m = replace_once(m, heic_old, heic_new, "heic original filename")

lp_old = '''    NSString *uniqueID = [NSUUID UUID].UUIDString;
    NSString *imagePath = [livePhotoPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.heic", uniqueID]];
    NSString *videoPath = [livePhotoPath stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.mp4", uniqueID]];'''
lp_new = '''    NSString *uniqueID = [NSUUID UUID].UUIDString;
    NSInteger liveIndex = ++sDYYYLiveSequence;
    NSString *liveStem = sDYYYDownloadStem;
    if (liveStem.length == 0) {
        liveStem = [self dyyy_downloadStemForAweme:sDYYYDownloadAwemeModel];
    }
    if (liveStem.length == 0) liveStem = uniqueID;
    liveStem = [liveStem stringByAppendingFormat:@"_%02ld", (long)liveIndex];
    NSString *imagePath = [livePhotoPath stringByAppendingPathComponent:[liveStem stringByAppendingPathExtension:@"heic"]];
    NSString *videoPath = [livePhotoPath stringByAppendingPathComponent:[liveStem stringByAppendingPathExtension:@"mp4"]];'''
if lp_new not in m:
    m = replace_once(m, lp_old, lp_new, "live photo temp names")

manager_m.write_text(m, encoding="utf-8")

lp = longpress.read_text(encoding="utf-8")
old_aweme = 'AWEAwemeModel *awemeModel = self.awemeModel;'
new_aweme = '''AWEAwemeModel *awemeModel = self.awemeModel;
          [DYYYManager setDownloadAwemeModel:awemeModel];'''
if "[DYYYManager setDownloadAwemeModel:awemeModel];" not in lp:
    lp = lp.replace(old_aweme, new_aweme)
api_old = '''        apiDownload.action = ^{
          NSString *shareLink = [self.awemeModel valueForKey:@"shareURL"];'''
api_new = '''        apiDownload.action = ^{
          // 接口解析是异步链路，先在点击瞬间冻结作者/抖音号/发布时间命名上下文
          [DYYYManager setDownloadAwemeModel:self.awemeModel];
          NSString *shareLink = [self.awemeModel valueForKey:@"shareURL"];'''
if api_new not in lp:
    lp = replace_once(lp, api_old, api_new, "api context")
longpress.write_text(lp, encoding="utf-8")

print("Applied DYYY filename patch")
print("Single: 作者名字_抖音号_yyyyMMdd_HHmm.ext")
print("Batch : 作者名字_抖音号_yyyyMMdd_HHmm_01.ext")
