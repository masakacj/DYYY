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

marker = "// DYYY_REMOTE_ACTION_RUNTIME_SUPPORTED"
if marker in text:
    print("DYYY remote action runtime already applied")
    raise SystemExit(0)

helpers = r'''
// DYYY_REMOTE_ACTION_RUNTIME_SUPPORTED
+ (NSString *)dyyyRuntimeFormatBytes:(double)bytes {
    if (bytes <= 0) return @"0 B";
    NSArray<NSString *> *units = @[@"B", @"KB", @"MB", @"GB"];
    double value = bytes;
    NSUInteger unitIndex = 0;
    while (value >= 1024.0 && unitIndex + 1 < units.count) {
        value /= 1024.0;
        unitIndex += 1;
    }
    return unitIndex == 0
        ? [NSString stringWithFormat:@"%.0f %@", value, units[unitIndex]]
        : [NSString stringWithFormat:@"%.1f %@", value, units[unitIndex]];
}

+ (NSDictionary *)dyyyRuntimeJSONObjectFromData:(NSData *)data {
    if (data.length == 0) return nil;
    id object = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    return [object isKindOfClass:[NSDictionary class]] ? object : nil;
}

+ (void)dyyyRuntimeSendRequest:(NSURLRequest *)request
                     transport:(NSString *)transport
                    completion:(void (^)(NSDictionary *json, NSHTTPURLResponse *response, NSError *error))completion {
    if (!request.URL) {
        if (completion) {
            completion(nil, nil, [NSError errorWithDomain:@"DYYY.Runtime"
                                                      code:-1
                                                  userInfo:@{NSLocalizedDescriptionKey : @"远程动作地址无效"}]);
        }
        return;
    }

    NSString *mode = [transport lowercaseString];
    if ([mode isEqualToString:@"nsurlsession"]) {
        NSURLSessionDataTask *task = [[NSURLSession sharedSession] dataTaskWithRequest:request
                                                                    completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
          if (completion) {
              completion([self dyyyRuntimeJSONObjectFromData:data], (NSHTTPURLResponse *)response, error);
          }
        }];
        [task resume];
        return;
    }

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    [NSURLConnection sendAsynchronousRequest:request
                                       queue:[NSOperationQueue mainQueue]
                           completionHandler:^(NSURLResponse *response, NSData *data, NSError *error) {
      if (completion) {
          completion([self dyyyRuntimeJSONObjectFromData:data], (NSHTTPURLResponse *)response, error);
      }
    }];
#pragma clang diagnostic pop
}

+ (NSMutableURLRequest *)dyyyRuntimeRequestFromSpec:(NSDictionary *)spec
                                          requestID:(NSString *)requestID
                                        urlOverride:(NSURL *)urlOverride {
    if (![spec isKindOfClass:[NSDictionary class]]) return nil;

    NSString *urlString = [spec[@"url"] isKindOfClass:[NSString class]] ? spec[@"url"] : nil;
    NSURL *url = urlOverride ?: (urlString.length > 0 ? [NSURL URLWithString:urlString] : nil);
    if (!url) return nil;

    NSString *ridQuery = [spec[@"request_id_query"] isKindOfClass:[NSString class]] ? spec[@"request_id_query"] : nil;
    if (requestID.length > 0 && ridQuery.length > 0) {
        NSURLComponents *components = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO];
        if (components) {
            NSMutableArray<NSURLQueryItem *> *items = [NSMutableArray arrayWithArray:components.queryItems ?: @[]];
            [items addObject:[NSURLQueryItem queryItemWithName:ridQuery value:requestID]];
            components.queryItems = items;
            if (components.URL) url = components.URL;
        }
    }

    NSTimeInterval timeout = [spec[@"timeout_ms"] doubleValue] / 1000.0;
    if (timeout <= 0) timeout = 10.0;

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:timeout];

    NSString *method = [spec[@"method"] isKindOfClass:[NSString class]] ? [spec[@"method"] uppercaseString] : @"GET";
    request.HTTPMethod = [method isEqualToString:@"POST"] ? @"POST" : @"GET";

    NSDictionary *headers = [spec[@"headers"] isKindOfClass:[NSDictionary class]] ? spec[@"headers"] : nil;
    for (id key in headers) {
        id value = headers[key];
        if ([key isKindOfClass:[NSString class]] && [value isKindOfClass:[NSString class]]) {
            [request setValue:value forHTTPHeaderField:key];
        }
    }

    NSString *ridHeader = [spec[@"request_id_header"] isKindOfClass:[NSString class]] ? spec[@"request_id_header"] : nil;
    if (requestID.length > 0 && ridHeader.length > 0) {
        [request setValue:requestID forHTTPHeaderField:ridHeader];
    }

    NSDictionary *body = [spec[@"body"] isKindOfClass:[NSDictionary class]] ? spec[@"body"] : nil;
    if ([request.HTTPMethod isEqualToString:@"POST"] && body) {
        NSData *bodyData = [NSJSONSerialization dataWithJSONObject:body options:0 error:nil];
        if (bodyData) {
            request.HTTPBody = bodyData;
            if (![request valueForHTTPHeaderField:@"Content-Type"]) {
                [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
            }
        }
    }

    return request;
}

+ (void)dyyyRuntimePollStatusURL:(NSURL *)statusURL
                         pollSpec:(NSDictionary *)pollSpec
                        requestID:(NSString *)requestID
                     progressView:(DYYYToast *)progressView
                       retryCount:(NSInteger)retryCount {
    if (!statusURL || ![pollSpec isKindOfClass:[NSDictionary class]] || !progressView) return;

    NSMutableURLRequest *request = [self dyyyRuntimeRequestFromSpec:pollSpec requestID:requestID urlOverride:statusURL];
    if (!request) return;

    NSString *transport = [pollSpec[@"transport"] isKindOfClass:[NSString class]] ? pollSpec[@"transport"] : @"nsurlconnection";
    [self dyyyRuntimeSendRequest:request transport:transport completion:^(NSDictionary *json, NSHTTPURLResponse *response, NSError *error) {
      if (error) {
          if (retryCount < 8) {
              double interval = [pollSpec[@"interval_ms"] doubleValue] / 1000.0;
              if (interval <= 0) interval = 0.75;
              dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(interval * NSEC_PER_SEC)),
                             dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
                [self dyyyRuntimePollStatusURL:statusURL
                                      pollSpec:pollSpec
                                     requestID:requestID
                                  progressView:progressView
                                    retryCount:retryCount + 1];
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
      if (total > 0) progress = (float)MIN(1.0, downloaded / total);

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
          NSString *message = serverError.length > 0 ? serverError : @"任务失败";
          dispatch_async(dispatch_get_main_queue(), ^{
            [progressView dismiss];
            [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
          });
          return;
      }

      NSString *statusText = nil;
      if ([state isEqualToString:@"preparing"]) {
          statusText = @"NAS 准备中…\n服务器正在准备下载";
      } else if (total > 0) {
          NSInteger percentage = (NSInteger)lrintf(progress * 100.0f);
          statusText = [NSString stringWithFormat:@"NAS %ld%% · %@/s\n%@ / %@",
                        (long)percentage,
                        [self dyyyRuntimeFormatBytes:speed],
                        [self dyyyRuntimeFormatBytes:downloaded],
                        [self dyyyRuntimeFormatBytes:total]];
      } else {
          statusText = [NSString stringWithFormat:@"NAS 下载中 · %@/s\n已下载 %@",
                        [self dyyyRuntimeFormatBytes:speed],
                        [self dyyyRuntimeFormatBytes:downloaded]];
      }

      dispatch_async(dispatch_get_main_queue(), ^{
        [progressView setProgress:progress statusText:statusText];
      });

      double interval = [pollSpec[@"interval_ms"] doubleValue] / 1000.0;
      if (interval <= 0) interval = 0.75;
      dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(interval * NSEC_PER_SEC)),
                     dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        [self dyyyRuntimePollStatusURL:statusURL
                              pollSpec:pollSpec
                             requestID:requestID
                          progressView:progressView
                            retryCount:0];
      });
    }];
}

+ (void)dyyyExecuteRuntimeAction:(NSDictionary *)runtimeAction progressView:(DYYYToast *)progressView {
    NSDictionary *requestSpec = [runtimeAction[@"request"] isKindOfClass:[NSDictionary class]] ? runtimeAction[@"request"] : nil;
    NSDictionary *pollSpec = [runtimeAction[@"poll"] isKindOfClass:[NSDictionary class]] ? runtimeAction[@"poll"] : nil;
    if (!requestSpec || !pollSpec) {
        [progressView dismiss];
        [DYYYUtils showToast:@"远程动作配置不完整"];
        return;
    }

    NSString *requestID = [NSUUID UUID].UUIDString;
    NSString *shortID = requestID.length > 8 ? [requestID substringFromIndex:requestID.length - 8] : requestID;
    NSString *version = [runtimeAction[@"runtime_version"] isKindOfClass:[NSString class]] ? runtimeAction[@"runtime_version"] : @"runtime";
    [progressView setProgress:0.0f statusText:[NSString stringWithFormat:@"%@\n请求 ID %@", version, shortID ?: @"-"]];

    NSMutableURLRequest *request = [self dyyyRuntimeRequestFromSpec:requestSpec requestID:requestID urlOverride:nil];
    if (!request) {
        [progressView dismiss];
        [DYYYUtils showToast:@"无法构造远程动作请求"];
        return;
    }

    NSString *transport = [requestSpec[@"transport"] isKindOfClass:[NSString class]] ? requestSpec[@"transport"] : @"nsurlconnection";
    NSLog(@"[DYYY][Runtime] version=%@ transport=%@ request_id=%@ url=%@", version, transport, requestID, request.URL.absoluteString);

    [self dyyyRuntimeSendRequest:request transport:transport completion:^(NSDictionary *json, NSHTTPURLResponse *response, NSError *error) {
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

      NSString *statusURLString = [payload[@"status_url_absolute"] isKindOfClass:[NSString class]] ? payload[@"status_url_absolute"] : nil;
      NSURL *statusURL = statusURLString.length > 0 ? [NSURL URLWithString:statusURLString] : nil;
      if (!statusURL) {
          NSString *statusPath = [payload[@"status_url"] isKindOfClass:[NSString class]] ? payload[@"status_url"] : nil;
          statusURL = statusPath.length > 0 ? [[NSURL URLWithString:statusPath relativeToURL:request.URL] absoluteURL] : nil;
      }

      if (!statusURL) {
          dispatch_async(dispatch_get_main_queue(), ^{
            [progressView dismiss];
            [DYYYUtils showToast:@"任务已创建，但服务器未返回状态地址"];
          });
          return;
      }

      [self dyyyRuntimePollStatusURL:statusURL
                            pollSpec:pollSpec
                           requestID:requestID
                        progressView:progressView
                          retryCount:0];
    }];
}

+ (void)dyyyStartRemoteAction:(NSDictionary *)action progressView:(DYYYToast *)progressView {
    NSDictionary *embeddedRuntime = [action[@"runtime"] isKindOfClass:[NSDictionary class]] ? action[@"runtime"] : nil;
    if (embeddedRuntime) {
        [progressView setProgress:0.0f statusText:@"使用当前解析返回的热更配置…"];
        [self dyyyExecuteRuntimeAction:embeddedRuntime progressView:progressView];
        return;
    }

    // 兼容旧 resolver：没有内嵌 runtime 时才额外获取一次配置。
    NSString *runtimeURLString = [action[@"runtime_url"] isKindOfClass:[NSString class]] ? action[@"runtime_url"] : nil;
    NSURL *runtimeURL = runtimeURLString.length > 0 ? [NSURL URLWithString:runtimeURLString] : nil;
    if (!runtimeURL) {
        [progressView dismiss];
        [DYYYUtils showToast:@"该服务器未提供热更动作配置"];
        return;
    }

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:runtimeURL
                                                           cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                       timeoutInterval:10.0];
    request.HTTPMethod = @"GET";
    [request setValue:@"application/json" forHTTPHeaderField:@"Accept"];
    [request setValue:@"no-cache" forHTTPHeaderField:@"Cache-Control"];

    [progressView setProgress:0.0f statusText:@"正在读取兼容热更配置…"];

    [self dyyyRuntimeSendRequest:request transport:@"nsurlsession" completion:^(NSDictionary *json, NSHTTPURLResponse *response, NSError *error) {
      if (error) {
          dispatch_async(dispatch_get_main_queue(), ^{
            [progressView dismiss];
            [DYYYUtils showToast:[NSString stringWithFormat:@"热更配置读取失败: %@", error.localizedDescription]];
          });
          return;
      }

      NSDictionary *runtimeAction = [json[@"data"] isKindOfClass:[NSDictionary class]] ? json[@"data"] : nil;
      if (response.statusCode < 200 || response.statusCode >= 300 || !runtimeAction) {
          NSString *message = [json[@"msg"] isKindOfClass:[NSString class]] ? json[@"msg"] : @"runtime 配置无效";
          dispatch_async(dispatch_get_main_queue(), ^{
            [progressView dismiss];
            [DYYYUtils showToast:message];
          });
          return;
      }

      [self dyyyExecuteRuntimeAction:runtimeAction progressView:progressView];
    }];
}
'''

text = text.replace(signature, helpers + "\n" + signature, 1)

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
nas_action_block = r'''        NSDictionary *embeddedRuntime = [nasAction[@"runtime"] isKindOfClass:[NSDictionary class]] ? nasAction[@"runtime"] : nil;
        NSString *runtimeURL = [nasAction[@"runtime_url"] isKindOfClass:[NSString class]] ? nasAction[@"runtime_url"] : nil;
        if (embeddedRuntime || runtimeURL.length > 0) {
            NSString *nasBaseTitle = [nasAction[@"title"] isKindOfClass:[NSString class]] && [nasAction[@"title"] length] > 0
                ? nasAction[@"title"]
                : @"下载原画至NAS";
            NSString *runtimeVersion = [nasAction[@"runtime_version"] isKindOfClass:[NSString class]] ? nasAction[@"runtime_version"] : @"hot";
            NSString *nasTitle = [NSString stringWithFormat:@"%@ · %@", nasBaseTitle, runtimeVersion];

            AWEUserSheetAction *nasDownloadAction = [NSClassFromString(@"AWEUserSheetAction") actionWithTitle:nasTitle
                                                                                                      imgName:nil
                                                                                                      handler:^{
                                                                                                        DYYYToast *nasProgressView = [[DYYYToast alloc] initWithFrame:[UIScreen mainScreen].bounds];
                                                                                                        nasProgressView.userInteractionEnabled = NO;
                                                                                                        [nasProgressView setProgress:0.0f statusText:@"NAS 热更动作准备中…"];
                                                                                                        [self dyyyStartRemoteAction:nasAction progressView:nasProgressView];
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
print("Added DYYY server-driven remote action runtime")
