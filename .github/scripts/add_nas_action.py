#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
if not manager.exists():
    raise SystemExit(f"Missing required file: {manager}")

text = manager.read_text(encoding="utf-8")

signature = '+ (void)handleVideoData:(NSDictionary *)dataDict downloadStem:(NSString *)downloadStem {'
if signature not in text:
    raise RuntimeError("Expected patched handleVideoData:downloadStem: signature; run bind_api_quality_context.py first")

marker = "// DYYY_NAS_PROGRESS_SUPPORTED"
if marker in text:
    print("DYYY NAS action patch already applied")
    raise SystemExit(0)

helper_methods = r'''
// DYYY_NAS_PROGRESS_SUPPORTED
+ (NSString *)dyyyNasFormatBytes:(double)bytes {
    if (bytes <= 0) {
        return @"0 B";
    }

    NSArray<NSString *> *units = @[@"B", @"KB", @"MB", @"GB"];
    double value = bytes;
    NSUInteger unitIndex = 0;
    while (value >= 1024.0 && unitIndex + 1 < units.count) {
        value /= 1024.0;
        unitIndex += 1;
    }

    if (unitIndex == 0) {
        return [NSString stringWithFormat:@"%.0f %@", value, units[unitIndex]];
    }
    return [NSString stringWithFormat:@"%.1f %@", value, units[unitIndex]];
}

+ (void)dyyyStartNasRequestURL:(NSURL *)nasURL progressView:(DYYYToast *)progressView retryCount:(NSInteger)retryCount {
    if (!nasURL || !progressView) {
        return;
    }

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:nasURL
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:15.0];
    request.HTTPMethod = @"GET";
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"no-cache" forHTTPHeaderField:@"Cache-Control"];

    NSLog(@"[DYYY][NAS] start request retry=%ld url=%@", (long)retryCount, nasURL.absoluteString);

    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request
                                                               completionHandler:^(NSData *responseData, NSURLResponse *response, NSError *error) {
                                                                 if (error) {
                                                                     NSLog(@"[DYYY][NAS] request error retry=%ld error=%@", (long)retryCount, error);
                                                                     if (retryCount < 2) {
                                                                         dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.6 * NSEC_PER_SEC)), dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
                                                                           [self dyyyStartNasRequestURL:nasURL progressView:progressView retryCount:retryCount + 1];
                                                                         });
                                                                     } else {
                                                                         dispatch_async(dispatch_get_main_queue(), ^{
                                                                           [progressView dismiss];
                                                                           [DYYYUtils showToast:[NSString stringWithFormat:@"NAS请求失败: %@", error.localizedDescription]];
                                                                         });
                                                                     }
                                                                     return;
                                                                 }

                                                                 NSHTTPURLResponse *httpResponse = (NSHTTPURLResponse *)response;
                                                                 NSDictionary *responseJSON = responseData.length > 0
                                                                     ? [NSJSONSerialization JSONObjectWithData:responseData options:0 error:nil]
                                                                     : nil;
                                                                 NSDictionary *payload = [responseJSON[@"data"] isKindOfClass:[NSDictionary class]] ? responseJSON[@"data"] : nil;
                                                                 NSString *message = [responseJSON[@"msg"] isKindOfClass:[NSString class]] ? responseJSON[@"msg"] : @"NAS服务器返回异常";
                                                                 NSLog(@"[DYYY][NAS] response status=%ld message=%@", (long)httpResponse.statusCode, message);

                                                                 if (httpResponse.statusCode < 200 || httpResponse.statusCode >= 300) {
                                                                     dispatch_async(dispatch_get_main_queue(), ^{
                                                                       [progressView dismiss];
                                                                       [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
                                                                     });
                                                                     return;
                                                                 }

                                                                 NSString *statusURLString = [payload[@"status_url_absolute"] isKindOfClass:[NSString class]]
                                                                     ? payload[@"status_url_absolute"]
                                                                     : nil;
                                                                 if (statusURLString.length == 0 && [payload[@"status_url"] isKindOfClass:[NSString class]]) {
                                                                     statusURLString = payload[@"status_url"];
                                                                 }

                                                                 NSURL *statusURL = nil;
                                                                 if (statusURLString.length > 0) {
                                                                     NSURL *candidate = [NSURL URLWithString:statusURLString];
                                                                     statusURL = candidate.scheme.length > 0 ? candidate : [[NSURL URLWithString:statusURLString relativeToURL:nasURL] absoluteURL];
                                                                 }
                                                                 if (statusURL) {
                                                                     [self dyyyPollNasStatusURL:statusURL progressView:progressView retryCount:0];
                                                                     return;
                                                                 }

                                                                 // 兼容旧版 resolver 的同步返回。
                                                                 NSInteger responseCode = [responseJSON[@"code"] integerValue];
                                                                 if (responseCode == 202) {
                                                                     dispatch_async(dispatch_get_main_queue(), ^{
                                                                       [progressView dismiss];
                                                                       [DYYYUtils showToast:@"NAS任务已创建，但服务器未返回状态地址"];
                                                                     });
                                                                     return;
                                                                 }

                                                                 dispatch_async(dispatch_get_main_queue(), ^{
                                                                   [progressView setProgress:1.0f statusText:message.length > 0 ? message : @"已保存至 NAS"];
                                                                   progressView.allowSuccessAnimation = YES;
                                                                   [progressView dismiss];
                                                                 });
                                                               }];
    [task resume];
}

+ (void)dyyyPollNasStatusURL:(NSURL *)statusURL progressView:(DYYYToast *)progressView retryCount:(NSInteger)retryCount {
    if (!statusURL || !progressView) {
        return;
    }

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:statusURL
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:15.0];
    request.HTTPMethod = @"GET";
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"no-cache" forHTTPHeaderField:@"Cache-Control"];

    NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request
                                                               completionHandler:^(NSData *responseData, NSURLResponse *response, NSError *error) {
                                         if (error) {
                                             if (retryCount < 8) {
                                                 dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)), dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
                                                   [self dyyyPollNasStatusURL:statusURL progressView:progressView retryCount:retryCount + 1];
                                                 });
                                             } else {
                                                 dispatch_async(dispatch_get_main_queue(), ^{
                                                   [progressView dismiss];
                                                   [DYYYUtils showToast:[NSString stringWithFormat:@"NAS进度查询失败: %@", error.localizedDescription]];
                                                 });
                                             }
                                             return;
                                         }

                                         NSHTTPURLResponse *httpResponse = (NSHTTPURLResponse *)response;
                                         NSDictionary *json = responseData.length > 0
                                             ? [NSJSONSerialization JSONObjectWithData:responseData options:0 error:nil]
                                             : nil;
                                         NSDictionary *payload = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : nil;

                                         if (httpResponse.statusCode < 200 || httpResponse.statusCode >= 300 || !payload) {
                                             NSString *message = [json[@"msg"] isKindOfClass:[NSString class]] ? json[@"msg"] : @"服务器返回异常";
                                             dispatch_async(dispatch_get_main_queue(), ^{
                                               [progressView dismiss];
                                               [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
                                             });
                                             return;
                                         }

                                         NSString *state = [payload[@"state"] isKindOfClass:[NSString class]] ? payload[@"state"] : @"";
                                         double downloaded = [payload[@"downloaded_bytes"] doubleValue];
                                         double total = [payload[@"total_bytes"] doubleValue];
                                         double speed = [payload[@"speed_bps"] doubleValue];
                                         float progress = [payload[@"progress"] floatValue];
                                         if (total > 0) {
                                             progress = (float)MIN(1.0, downloaded / total);
                                         }

                                         if ([state isEqualToString:@"completed"]) {
                                             NSString *filename = [payload[@"filename"] isKindOfClass:[NSString class]] ? payload[@"filename"] : @"";
                                             NSString *detail = filename.length > 0
                                                 ? [NSString stringWithFormat:@"已保存至 NAS\n%@", filename]
                                                 : @"已保存至 NAS";
                                             dispatch_async(dispatch_get_main_queue(), ^{
                                               [progressView setProgress:1.0f statusText:detail];
                                               progressView.allowSuccessAnimation = YES;
                                               [progressView dismiss];
                                             });
                                             return;
                                         }

                                         if ([state isEqualToString:@"failed"] || [state isEqualToString:@"cancelled"]) {
                                             NSString *serverError = [payload[@"error"] isKindOfClass:[NSString class]] ? payload[@"error"] : nil;
                                             NSString *message = serverError.length > 0 ? serverError : ([state isEqualToString:@"cancelled"] ? @"任务已取消" : @"未知错误");
                                             dispatch_async(dispatch_get_main_queue(), ^{
                                               [progressView dismiss];
                                               [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
                                             });
                                             return;
                                         }

                                         NSString *statusText = nil;
                                         if ([state isEqualToString:@"preparing"]) {
                                             statusText = @"NAS 准备中…\n等待服务器解析资源";
                                         } else if (total > 0) {
                                             NSInteger percentage = (NSInteger)lrintf(progress * 100.0f);
                                             statusText = [NSString stringWithFormat:@"NAS %ld%% · %@/s\n%@ / %@",
                                                           (long)percentage,
                                                           [self dyyyNasFormatBytes:speed],
                                                           [self dyyyNasFormatBytes:downloaded],
                                                           [self dyyyNasFormatBytes:total]];
                                         } else {
                                             statusText = [NSString stringWithFormat:@"NAS 下载中 · %@/s\n已下载 %@",
                                                           [self dyyyNasFormatBytes:speed],
                                                           [self dyyyNasFormatBytes:downloaded]];
                                         }

                                         dispatch_async(dispatch_get_main_queue(), ^{
                                           [progressView setProgress:progress statusText:statusText];
                                         });

                                         dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.75 * NSEC_PER_SEC)), dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
                                           [self dyyyPollNasStatusURL:statusURL progressView:progressView retryCount:0];
                                         });
                                       }];
    [task resume];
}
'''

text = text.replace(signature, helper_methods + "\n" + signature, 1)

video_list_decl = '''    NSArray *videoList = dataDict[@"video_list"];
'''
video_list_new = '''    NSArray *videoList = dataDict[@"video_list"];
    NSDictionary *nasAction = [dataDict[@"nas_action"] isKindOfClass:[NSDictionary class]] ? dataDict[@"nas_action"] : nil;
'''
if video_list_decl not in text:
    raise RuntimeError("video_list declaration patch point not found")
text = text.replace(video_list_decl, video_list_new, 1)

action_insert_point = '''        if (actions.count > 0) {
            [actionSheet setActions:actions];
            [actionSheet show];
            return;
        }
'''
nas_action_block = r'''        // DYYY_NAS_PROGRESS_ACTION
        NSString *nasURLString = [nasAction[@"url"] isKindOfClass:[NSString class]] ? nasAction[@"url"] : nil;
        if (nasURLString.length > 0) {
            NSString *nasTitle = [nasAction[@"title"] isKindOfClass:[NSString class]] && [nasAction[@"title"] length] > 0 ? nasAction[@"title"] : @"下载至NAS";
            AWEUserSheetAction *nasDownloadAction = [NSClassFromString(@"AWEUserSheetAction") actionWithTitle:nasTitle
                                                                                                      imgName:nil
                                                                                                      handler:^{
                                                                                                        NSURL *nasURL = [NSURL URLWithString:nasURLString];
                                                                                                        if (!nasURL) {
                                                                                                            [DYYYUtils showToast:@"NAS接口地址无效"];
                                                                                                            return;
                                                                                                        }

                                                                                                        DYYYToast *nasProgressView = [[DYYYToast alloc] initWithFrame:[UIScreen mainScreen].bounds];
                                                                                                        nasProgressView.userInteractionEnabled = NO;
                                                                                                        [nasProgressView setProgress:0.0f statusText:@"NAS 准备中…\n正在创建下载任务"];
                                                                                                        [self dyyyStartNasRequestURL:nasURL progressView:nasProgressView retryCount:0];
                                                                                                        [nasProgressView show];
                                                                                                      }];
            [actions addObject:nasDownloadAction];
        }

        if (actions.count > 0) {
            [actionSheet setActions:actions];
            [actionSheet show];
            return;
        }
'''
if action_insert_point not in text:
    raise RuntimeError("video_list action sheet patch point not found")
text = text.replace(action_insert_point, nas_action_block, 1)

manager.write_text(text, encoding="utf-8")
print("Added DYYY nas_action support to video_list action sheet")
