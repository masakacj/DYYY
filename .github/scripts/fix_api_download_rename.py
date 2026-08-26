#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
if not manager.exists():
    raise SystemExit(f"Missing required file: {manager}")

text = manager.read_text(encoding="utf-8")

# 接口请求与真实媒体下载之间是异步链路。这里在发起接口请求时冻结
# 已由 apply_filename_patch.py 从当前 awemeModel 生成的文件名前缀，
# 等接口返回后再恢复它。之后 downloadMedia -> NSURLSession 下载代理会：
# 1. 下载到系统临时文件
# 2. 按 desiredFilename 移动/重命名到新的临时文件
# 3. saveMedia 使用该文件保存到 Photos，并设置 originalFilename
capture_old = '''+ (void)parseAndDownloadVideoWithShareLink:(NSString *)shareLink apiKey:(NSString *)apiKey {
    if (shareLink.length == 0 || apiKey.length == 0) {
        [DYYYUtils showToast:@"分享链接或API密钥无效"];
        return;
    }

    NSString *apiUrl ='''
capture_new = '''+ (void)parseAndDownloadVideoWithShareLink:(NSString *)shareLink apiKey:(NSString *)apiKey {
    if (shareLink.length == 0 || apiKey.length == 0) {
        [DYYYUtils showToast:@"分享链接或API密钥无效"];
        return;
    }

    // 冻结点击“接口保存”时的作品命名上下文，避免异步接口返回后丢失作者信息
    NSString *dyyyAPIStem = [sDYYYDownloadStem copy];

    NSString *apiUrl ='''

if capture_new not in text:
    if capture_old not in text:
        raise RuntimeError("API parse capture patch point not found")
    text = text.replace(capture_old, capture_new, 1)

restore_old = '''                                                    // 交给handleVideoData处理数据
                                                    [self handleVideoData:dataDict];'''
restore_new = '''                                                    // 接口只返回媒体下载链接；在真正创建下载任务前恢复作品文件名前缀
                                                    if (dyyyAPIStem.length > 0) {
                                                        sDYYYDownloadStem = [dyyyAPIStem copy];
                                                    }
                                                    // 后续统一走 downloadMedia，下载完成代理会先改名再保存到相册
                                                    [self handleVideoData:dataDict];'''

if restore_new not in text:
    if restore_old not in text:
        raise RuntimeError("API parse restore patch point not found")
    text = text.replace(restore_old, restore_new, 1)

manager.write_text(text, encoding="utf-8")
print("Applied API post-download rename context patch")
