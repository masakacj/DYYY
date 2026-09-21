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
    print("DYYY NAS action patch already applied")
    raise SystemExit(0)

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
nas_action_block = r'''        // DYYY_NAS_ACTION_SUPPORTED
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

                                                                                                        [DYYYUtils showToast:@"正在下载至NAS…"];

                                                                                                        NSURLSessionConfiguration *configuration = [NSURLSessionConfiguration defaultSessionConfiguration];
                                                                                                        configuration.timeoutIntervalForRequest = 300.0;
                                                                                                        configuration.timeoutIntervalForResource = 600.0;
                                                                                                        NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration];

                                                                                                        NSURLSessionDataTask *task = [session dataTaskWithURL:nasURL
                                                                                                                                                           completionHandler:^(NSData *responseData, NSURLResponse *response, NSError *error) {
                                                                                                          dispatch_async(dispatch_get_main_queue(), ^{
                                                                                                            if (error) {
                                                                                                                [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", error.localizedDescription]];
                                                                                                                return;
                                                                                                            }

                                                                                                            NSString *message = @"已下载至NAS";
                                                                                                            NSDictionary *responseJSON = nil;
                                                                                                            if (responseData.length > 0) {
                                                                                                                responseJSON = [NSJSONSerialization JSONObjectWithData:responseData options:0 error:nil];
                                                                                                                if ([responseJSON[@"msg"] isKindOfClass:[NSString class]] && [responseJSON[@"msg"] length] > 0) {
                                                                                                                    message = responseJSON[@"msg"];
                                                                                                                }
                                                                                                            }

                                                                                                            NSInteger statusCode = [(NSHTTPURLResponse *)response statusCode];
                                                                                                            if (statusCode >= 200 && statusCode < 300) {
                                                                                                                [DYYYUtils showToast:message];
                                                                                                            } else {
                                                                                                                [DYYYUtils showToast:[NSString stringWithFormat:@"NAS下载失败: %@", message]];
                                                                                                            }
                                                                                                          });
                                                                                                        }];
                                                                                                        [task resume];
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
