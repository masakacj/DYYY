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

marker = "// DYYY_NAS_ACTION_SUPPORTED"
if marker in text:
    print("DYYY NAS action support already applied")
    raise SystemExit(0)

helper_methods = r'''
// DYYY_NAS_ACTION_SUPPORTED
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

+ (void)dyyyNasGET:(NSURL *)url completion:(void (^)(NSDictionary *json, NSHTTPURLResponse *response, NSError *error))completion {
    if (!url) {
        if (completion) {
            completion(nil, nil, [NSError errorWithDomain:@"DYYY.NAS" code:-1 userInfo:@{NSLocalizedDescriptionKey : @"NAS接口地址无效"}]);
        }
        return;
    }

    // NAS action 与已经验证可用的 API 解析请求保持同一网络实现：
    // 使用 NSURLSession.sharedSession，仅由 NSURLRequest 控制禁缓存与超时。
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:15.0];
    request.HTTPMethod = @"GET";
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"no-cache" forHTTPHeaderField:@"Cache-Control"];

    NSURLSession *session = [NSURLSession sharedSession];
    NSURLSessionDataTask *task = [session dataTaskWithRequest:request
                                           completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
                                             NSDictionary *json = nil;
                                             if (data.length > 0) {
                                                 json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
                                             }
                                             if (completion) {
                                                 completion(json, (NSHTTPURLResponse *)response, error);
                                             }
                                           }];
    [task resume];
}

+ (NSURL *)dyyyNasRequestURLForAction:(NSDictionary *)nasAction {
    NSString *endpoint = [nasAction[@"endpoint"] isKindOfClass:[NSString class]] ? nasAction[@"endpoint"] : nil;
    NSString *awemeID = nil;
    id awemeValue = nasAction[@"aweme_id"];
    if ([awemeValue isKindOfClass:[NSString class]]) {
        awemeID = awemeValue;
    } else if ([awemeValue respondsToSelector:@selector(stringValue)]) {
        awemeID = [awemeValue stringValue];
    }

    if (endpoint.length == 0 || awemeID.length == 0) {
        return nil;
    }

    NSURLComponents *components = [NSURLComponents componentsWithString:endpoint];
    if (!components) {
        return nil;
    }

    NSString *quality = [nasAction[@"quality"] isKindOfClass:[NSString class]] && [nasAction[@"quality"] length] > 0
        ? nasAction[@"quality"]
        : @"original";

    NSMutableArray<NSURLQueryItem *> *items = [NSMutableArray arrayWithArray:components.queryItems ?: @[]];
    [items addObject:[NSURLQueryItem queryItemWithName:@"source" value:@"dyyy"]];
    [items addObject:[NSURLQueryItem queryItemWithName:@"action" value:@"nas"]];
    [items addObject:[NSURLQueryItem queryItemWithName:@"aweme_id" value:awemeID]];
    [items addObject:[NSURLQueryItem queryItemWithName:@"quality" value:quality]];
    components.queryItems = items;
    return components.URL;
}

+ (void)dyyyPollNasStatusURL:(NSURL *)statusURL progressView:(DYYYToast *)progressView retryCount:(NSInteger)retryCount {
    if (!statusURL || !progressView) {
        return;
    }

    [self dyyyNasGET:statusURL
          completion:^(NSDictionary *json, NSHTTPURLResponse *response, NSError *error) {
            if (error) {
                if (retryCount < 8) {
                    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)),
                                   dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
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

            NSDictionary *payload = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : nil;
            if (response.statusCode < 200 || response.statusCode >= 300 || !payload) {
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
                NSString *message = serverError.length > 0
                    ? serverError
                    : ([state isEqualToString:@"cancelled"] ? @"任务已取消" : @"未知错误");
                dispatch_async(dispatch_get_main_queue(), ^{
                  [progressView dismiss];
                  [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
                });
                return;
            }

            NSString *statusText = nil;
            if ([state isEqualToString:@"preparing"]) {
                statusText = @"NAS 准备中…\n等待服务器创建任务";
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

            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.75 * NSEC_PER_SEC)),
                           dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
              [self dyyyPollNasStatusURL:statusURL progressView:progressView retryCount:0];
            });
          }];
}

+ (void)dyyyStartNasAction:(NSDictionary *)nasAction progressView:(DYYYToast *)progressView {
    NSURL *requestURL = [self dyyyNasRequestURLForAction:nasAction];
    if (!requestURL) {
        [progressView dismiss];
        [DYYYUtils showToast:@"NAS action 参数无效"];
        return;
    }

    NSLog(@"[DYYY][NAS] start action url=%@", requestURL.absoluteString);

    [self dyyyNasGET:requestURL
          completion:^(NSDictionary *json, NSHTTPURLResponse *response, NSError *error) {
            if (error) {
                dispatch_async(dispatch_get_main_queue(), ^{
                  [progressView dismiss];
                  [DYYYUtils showToast:[NSString stringWithFormat:@"NAS任务创建失败: %@", error.localizedDescription]];
                });
                return;
            }

            NSDictionary *payload = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : nil;
            NSString *message = [json[@"msg"] isKindOfClass:[NSString class]] ? json[@"msg"] : @"服务器返回异常";
            if (response.statusCode < 200 || response.statusCode >= 300 || !payload) {
                dispatch_async(dispatch_get_main_queue(), ^{
                  [progressView dismiss];
                  [DYYYUtils showToast:[NSString stringWithFormat:@"NAS任务创建失败: %@", message]];
                });
                return;
            }

            NSString *statusPath = [payload[@"status_url"] isKindOfClass:[NSString class]] ? payload[@"status_url"] : nil;
            NSURL *statusURL = statusPath.length > 0
                ? [[NSURL URLWithString:statusPath relativeToURL:requestURL] absoluteURL]
                : nil;

            if (!statusURL) {
                dispatch_async(dispatch_get_main_queue(), ^{
                  [progressView dismiss];
                  [DYYYUtils showToast:@"NAS任务已创建，但缺少状态地址"];
                });
                return;
            }

            [self dyyyPollNasStatusURL:statusURL progressView:progressView retryCount:0];
          }];
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
nas_action_block = r'''        NSString *nasActionName = [nasAction[@"action"] isKindOfClass:[NSString class]] ? nasAction[@"action"] : nil;
        if ([nasActionName isEqualToString:@"nas"]) {
            NSString *nasTitle = [nasAction[@"title"] isKindOfClass:[NSString class]] && [nasAction[@"title"] length] > 0
                ? nasAction[@"title"]
                : @"下载原画至NAS";
            AWEUserSheetAction *nasDownloadAction = [NSClassFromString(@"AWEUserSheetAction") actionWithTitle:nasTitle
                                                                                                      imgName:nil
                                                                                                      handler:^{
                                                                                                        DYYYToast *nasProgressView = [[DYYYToast alloc] initWithFrame:[UIScreen mainScreen].bounds];
                                                                                                        nasProgressView.userInteractionEnabled = NO;
                                                                                                        [nasProgressView setProgress:0.0f statusText:@"NAS 准备中…\n正在创建任务"];
                                                                                                        [nasProgressView show];
                                                                                                        [self dyyyStartNasAction:nasAction progressView:nasProgressView];
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
print("Added native DYYY nas_action support")
