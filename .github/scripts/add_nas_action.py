#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
if not manager.exists():
    raise SystemExit(f"Missing required file: {manager}")

text = manager.read_text(encoding="utf-8")

if '#import <WebKit/WebKit.h>' not in text:
    text = text.replace('#import "DYYYManager.h"\n', '#import "DYYYManager.h"\n#import <WebKit/WebKit.h>\n', 1)

webkit_anchor = '@interface DYYYManager () {'
webkit_support = r'''
typedef void (^DYYYRuntimeWebKitReadyBlock)(WKWebView *webView);
typedef void (^DYYYRuntimeWebKitFailureBlock)(NSError *error);

@interface DYYYRuntimeWebKitDelegate : NSObject <WKNavigationDelegate>
@property(nonatomic, copy) DYYYRuntimeWebKitReadyBlock readyBlock;
@property(nonatomic, copy) DYYYRuntimeWebKitFailureBlock failureBlock;
@end

@implementation DYYYRuntimeWebKitDelegate
- (void)dyyyFailOnce:(NSError *)error {
    DYYYRuntimeWebKitFailureBlock block = self.failureBlock;
    self.failureBlock = nil;
    self.readyBlock = nil;
    if (block) block(error);
}

- (void)webView:(WKWebView *)webView didFinishNavigation:(WKNavigation *)navigation {
    DYYYRuntimeWebKitReadyBlock block = self.readyBlock;
    self.readyBlock = nil;
    if (block) block(webView);
}

- (void)webView:(WKWebView *)webView didFailNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    [self dyyyFailOnce:error];
}

- (void)webView:(WKWebView *)webView didFailProvisionalNavigation:(WKNavigation *)navigation withError:(NSError *)error {
    [self dyyyFailOnce:error];
}
@end

static NSMutableSet *DYYYRuntimeWebKitRetainedObjects(void) {
    static NSMutableSet *objects;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
      objects = [NSMutableSet set];
    });
    return objects;
}
'''
if 'DYYYRuntimeWebKitDelegate' not in text:
    if webkit_anchor not in text:
        raise RuntimeError("DYYYManager class extension anchor not found")
    text = text.replace(webkit_anchor, webkit_support + "\n" + webkit_anchor, 1)

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

    if ([mode isEqualToString:@"downloadtask"]) {
        NSURLSessionDownloadTask *task = [[NSURLSession sharedSession] downloadTaskWithRequest:request
                                                                            completionHandler:^(NSURL *location, NSURLResponse *response, NSError *error) {
          NSData *data = (!error && location) ? [NSData dataWithContentsOfURL:location] : nil;
          if (completion) {
              completion([self dyyyRuntimeJSONObjectFromData:data], (NSHTTPURLResponse *)response, error);
          }
        }];
        [task resume];
        return;
    }

    if ([mode isEqualToString:@"webkit"]) {
        dispatch_async(dispatch_get_main_queue(), ^{
          WKWebViewConfiguration *configuration = [[WKWebViewConfiguration alloc] init];
          configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
          WKWebView *webView = [[WKWebView alloc] initWithFrame:CGRectZero configuration:configuration];
          DYYYRuntimeWebKitDelegate *delegate = [[DYYYRuntimeWebKitDelegate alloc] init];

          NSMutableSet *retainedObjects = DYYYRuntimeWebKitRetainedObjects();
          [retainedObjects addObject:webView];
          [retainedObjects addObject:delegate];

          void (^cleanup)(void) = ^{
            dispatch_async(dispatch_get_main_queue(), ^{
              webView.navigationDelegate = nil;
              [retainedObjects removeObject:delegate];
              [retainedObjects removeObject:webView];
            });
          };

          delegate.failureBlock = ^(NSError *error) {
            if (completion) {
                completion(nil, nil, error);
            }
            cleanup();
          };

          delegate.readyBlock = ^(WKWebView *readyWebView) {
            NSString *bodyString = request.HTTPBody.length > 0
                ? [[NSString alloc] initWithData:request.HTTPBody encoding:NSUTF8StringEncoding]
                : @"";
            NSDictionary *arguments = @{
                @"url" : request.URL.absoluteString ?: @"",
                @"method" : request.HTTPMethod ?: @"GET",
                @"headers" : request.allHTTPHeaderFields ?: @{},
                @"body" : bodyString ?: @""
            };
            NSData *argumentsData = [NSJSONSerialization dataWithJSONObject:arguments options:0 error:nil];
            NSString *argumentsJSON = argumentsData.length > 0
                ? [[NSString alloc] initWithData:argumentsData encoding:NSUTF8StringEncoding]
                : @"{}";

            NSString *script = [NSString stringWithFormat:
              @"(async()=>{const a=%@;try{const o={method:a.method,headers:a.headers,cache:'no-store',credentials:'omit'};"
               "if(a.method==='POST'&&a.body){o.body=a.body;}const r=await fetch(a.url,o);const t=await r.text();"
               "return {ok:true,status:r.status,text:t};}catch(e){return {ok:false,error:String(e)};}})()", argumentsJSON];

            [readyWebView evaluateJavaScript:script completionHandler:^(id result, NSError *error) {
              if (error) {
                  if (completion) completion(nil, nil, error);
                  cleanup();
                  return;
              }

              NSDictionary *resultDict = [result isKindOfClass:[NSDictionary class]] ? result : nil;
              if (![resultDict[@"ok"] boolValue]) {
                  NSString *message = [resultDict[@"error"] isKindOfClass:[NSString class]] ? resultDict[@"error"] : @"WebKit 请求失败";
                  NSError *webError = [NSError errorWithDomain:@"DYYY.Runtime.WebKit"
                                                           code:-2
                                                       userInfo:@{NSLocalizedDescriptionKey : message}];
                  if (completion) completion(nil, nil, webError);
                  cleanup();
                  return;
              }

              NSString *text = [resultDict[@"text"] isKindOfClass:[NSString class]] ? resultDict[@"text"] : @"";
              NSData *data = [text dataUsingEncoding:NSUTF8StringEncoding];
              NSInteger status = [resultDict[@"status"] integerValue];
              NSHTTPURLResponse *response = [[NSHTTPURLResponse alloc] initWithURL:request.URL
                                                                        statusCode:status
                                                                       HTTPVersion:@"HTTP/1.1"
                                                                      headerFields:nil];
              if (completion) {
                  completion([self dyyyRuntimeJSONObjectFromData:data], response, nil);
              }
              cleanup();
            }];
          };

          webView.navigationDelegate = delegate;
          NSURLComponents *originComponents = [NSURLComponents componentsWithURL:request.URL resolvingAgainstBaseURL:NO];
          NSString *origin = [NSString stringWithFormat:@"%@://%@%@",
                              originComponents.scheme ?: @"https",
                              originComponents.host ?: @"localhost",
                              originComponents.port ? [NSString stringWithFormat:@":%@", originComponents.port] : @""];
          [webView loadHTMLString:@"<!doctype html><html><body></body></html>" baseURL:[NSURL URLWithString:origin]];
        });
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

download_signature = '+ (void)downloadMedia:(NSURL *)url mediaType:(MediaType)mediaType audio:(NSURL *)audioURL completion:(void (^)(BOOL success))completion {'
if download_signature not in text:
    raise RuntimeError("downloadMedia signature patch point not found")

runtime_media_hook = r'''+ (void)downloadMedia:(NSURL *)url mediaType:(MediaType)mediaType audio:(NSURL *)audioURL completion:(void (^)(BOOL success))completion {
    // NAS 热更动作复用 DYYY 原有“画质下载”按钮 handler。
    // resolver 把 runtime JSON 编码进 dyyy-nas:// URL；点击后在这里分流，不进入手机媒体下载。
    if ([[url.scheme lowercaseString] isEqualToString:@"dyyy-nas"]) {
        NSURLComponents *components = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:NO];
        NSString *payload = nil;
        for (NSURLQueryItem *item in components.queryItems) {
            if ([item.name isEqualToString:@"payload"]) {
                payload = item.value;
                break;
            }
        }

        if (payload.length == 0) {
            [DYYYUtils showToast:@"NAS 热更参数为空"];
            if (completion) completion(NO);
            return;
        }

        NSMutableString *base64 = [payload mutableCopy];
        [base64 replaceOccurrencesOfString:@"-" withString:@"+" options:0 range:NSMakeRange(0, base64.length)];
        [base64 replaceOccurrencesOfString:@"_" withString:@"/" options:0 range:NSMakeRange(0, base64.length)];
        while (base64.length % 4 != 0) {
            [base64 appendString:@"="];
        }

        NSData *runtimeData = [[NSData alloc] initWithBase64EncodedString:base64 options:0];
        NSDictionary *runtimeAction = runtimeData.length > 0
            ? [NSJSONSerialization JSONObjectWithData:runtimeData options:0 error:nil]
            : nil;

        if (![runtimeAction isKindOfClass:[NSDictionary class]]) {
            [DYYYUtils showToast:@"NAS 热更配置解析失败"];
            if (completion) completion(NO);
            return;
        }

        DYYYToast *progressView = [[DYYYToast alloc] initWithFrame:[UIScreen mainScreen].bounds];
        progressView.userInteractionEnabled = NO;
        NSString *version = [runtimeAction[@"runtime_version"] isKindOfClass:[NSString class]]
            ? runtimeAction[@"runtime_version"]
            : @"hot";
        [progressView setProgress:0.0f statusText:[NSString stringWithFormat:@"NAS %@\n正在创建服务器任务", version]];
        [progressView show];

        [self dyyyExecuteRuntimeAction:runtimeAction progressView:progressView];
        if (completion) completion(YES);
        return;
    }
'''

text = text.replace(download_signature, runtime_media_hook, 1)

manager.write_text(text, encoding="utf-8")
print("Added DYYY server-driven runtime via existing quality handler")
