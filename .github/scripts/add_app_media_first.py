#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DYYY App-media-first parser bridge: retain URL mode as fallback, never send signed URLs."""
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
longpress = root / "DYYYLongPressPanel.xm"
text = manager.read_text(encoding="utf-8")
menu = longpress.read_text(encoding="utf-8")
marker = "// DYYY_APP_MEDIA_FIRST_V1"

if "sDYYYDownloadAwemeModel" not in text or "sDYYYDownloadStem" not in text:
    raise RuntimeError("Expected existing filename/context patch; run the established patch sequence first")
if marker not in text:
    anchor = '    NSURL *url = [NSURL URLWithString:apiUrl];'
    if text.count(anchor) != 1:
        raise RuntimeError("Expected exactly one API URL construction site")
    code = r'''    // DYYY_APP_MEDIA_FIRST_V1
    // 当前作品的 ID 与媒体 URI 均来自同一 AWEAwemeModel，不依赖网页详情接口。
    // 只发送媒体 ID 和命名信息，不发送 App Cookie、用户令牌或签名 CDN 链接。
    NSString *appAwemeID = [DYYYUtils storyItemIDForAweme:sDYYYDownloadAwemeModel];
    NSString *appMediaURI = [DYYYUtils storyVideoURIForAweme:sDYYYDownloadAwemeModel];
    if (appAwemeID.length > 0 && appMediaURI.length > 0) {
        apiUrl = [apiUrl stringByAppendingFormat:@"&app_aweme_id=%@&app_video_id=%@", appAwemeID, appMediaURI];
        NSString *filenameStem = [sDYYYDownloadStem copy];
        if (filenameStem.length > 0 && filenameStem.length <= 160) {
            NSCharacterSet *allowed = [NSCharacterSet characterSetWithCharactersInString:@"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"];
            NSString *escaped = [filenameStem stringByAddingPercentEncodingWithAllowedCharacters:allowed];
            if (escaped.length > 0) {
                apiUrl = [apiUrl stringByAppendingFormat:@"&app_filename_stem=%@", escaped];
            }
        }
    }

'''
    text = text.replace(anchor, code + anchor, 1)
    manager.write_text(text, encoding="utf-8")

# Both the Modern and Classic long-press menus are patched AFTER align_api_with_save_video.py.
old = '''          NSString *shareLink = [awemeModel valueForKey:@"shareURL"];
          if (shareLink.length == 0) {
              [DYYYUtils showToast:@"无法获取分享链接"];
              return;
          }'''
new = '''          NSString *shareLink = [awemeModel valueForKey:@"shareURL"];
          // 无分享链接时仍可通过 App 当前作品 ID + URI 请求，不触发网页查询。
          if (shareLink.length == 0) {
              NSString *mediaID = [DYYYUtils storyVideoURIForAweme:awemeModel];
              NSString *itemID = [DYYYUtils storyItemIDForAweme:awemeModel];
              if (mediaID.length > 0 && itemID.length > 0) {
                  shareLink = [NSString stringWithFormat:@"https://www.douyin.com/video/%@", itemID];
              } else {
                  [DYYYUtils showToast:@"无法获取分享链接或视频媒体信息"];
                  return;
              }
          }'''
if menu.count(new) != 2:
    if menu.count(old) != 2:
        raise RuntimeError(f"Expected both long-press API save actions; found {menu.count(old)}")
    menu = menu.replace(old, new)
    longpress.write_text(menu, encoding="utf-8")

print("DYYY App-media-first bridge ready (2 menus, existing API save path retained)")
