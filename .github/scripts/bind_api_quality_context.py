#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
manager = root / "DYYYManager.m"
longpress = root / "DYYYLongPressPanel.xm"
for p in (manager, longpress):
    if not p.exists():
        raise SystemExit(f"Missing required file: {p}")

# 1) DYYY 同时有 Modern / Classic 两套长按面板。
#    接口保存必须和“保存视频”一样，在用户真正点击按钮的瞬间读取 self.awemeModel。
#    不能只 patch 第一处，也不能在 dataArray 创建按钮时快照模型。
lp = longpress.read_text(encoding="utf-8")

# apply_filename_patch.py 会先改到第一处接口保存，把它转换回统一的点击时取模型流程。
first_form = '''        apiDownload.describeString = @"接口保存";
        apiDownload.action = ^{
          // 接口解析是异步链路，先在点击瞬间冻结作者/抖音号/发布时间命名上下文
          [DYYYManager setDownloadAwemeModel:self.awemeModel];
          NSString *shareLink = [self.awemeModel valueForKey:@"shareURL"];'''

# 另一套长按面板仍可能保持原始写法。
original_form = '''        apiDownload.describeString = @"接口保存";
        apiDownload.action = ^{
          NSString *shareLink = [self.awemeModel valueForKey:@"shareURL"];'''

click_time_form = '''        apiDownload.describeString = @"接口保存";
        apiDownload.action = ^{
          // 与“保存视频”完全一致：点击时现场获取当前作品模型。
          AWEAwemeModel *awemeModel = self.awemeModel;
          [DYYYManager setDownloadAwemeModel:awemeModel];
          NSString *shareLink = [awemeModel valueForKey:@"shareURL"];'''

lp = lp.replace(first_form, click_time_form)
lp = lp.replace(original_form, click_time_form)

# 必须同时命中 Modern + Classic 两个“接口保存”。少于 2 个直接让构建失败，避免再漏 patch。
api_marker = '''AWEAwemeModel *awemeModel = self.awemeModel;
          [DYYYManager setDownloadAwemeModel:awemeModel];
          NSString *shareLink = [awemeModel valueForKey:@"shareURL"];'''
api_entry_count = lp.count(api_marker)
if api_entry_count < 2:
    raise RuntimeError(f"Expected at least 2 API save entry points, patched {api_entry_count}")

longpress.write_text(lp, encoding="utf-8")

# 2) 接口返回后用户还要第二次点击“原画/720P”。
#    把第一次点击接口保存时生成的 stem 作为方法参数传入画质菜单，
#    每个画质 action 都捕获同一份请求级上下文，真正创建下载任务前再恢复。
m = manager.read_text(encoding="utf-8")

old_call = '''                                                    // 接口只返回媒体下载链接；在真正创建下载任务前恢复作品文件名前缀
                                                    if (dyyyAPIStem.length > 0) {
                                                        sDYYYDownloadStem = [dyyyAPIStem copy];
                                                    }
                                                    // 后续统一走 downloadMedia，下载完成代理会先改名再保存到相册
                                                    [self handleVideoData:dataDict];'''
new_call = '''                                                    // 把本次接口请求的文件名前缀直接传给画质菜单。
                                                    // 用户之后第二次点击“原画/720P”时，action 仍持有这份上下文。
                                                    [self handleVideoData:dataDict downloadStem:dyyyAPIStem];'''
if new_call not in m:
    if old_call not in m:
        raise RuntimeError("handleVideoData API call patch point not found")
    m = m.replace(old_call, new_call, 1)

old_sig = '+ (void)handleVideoData:(NSDictionary *)dataDict {'
new_sig = '+ (void)handleVideoData:(NSDictionary *)dataDict downloadStem:(NSString *)downloadStem {'
if new_sig not in m:
    if old_sig not in m:
        raise RuntimeError("handleVideoData signature patch point not found")
    m = m.replace(old_sig, new_sig, 1)

start = m.find(new_sig)
end = m.find('\n#define DYYYLogVideo', start)
if start < 0 or end < 0:
    raise RuntimeError("handleVideoData region not found")
region = m[start:end]

# 每个 downloadMedia 真正创建任务前恢复本次 API 请求自己的文件名前缀。
if 'DYYY_API_QUALITY_CONTEXT_BOUND' not in region:
    region = region.replace(new_sig, new_sig + '\n    // DYYY_API_QUALITY_CONTEXT_BOUND')

    region = region.replace(
        '[self downloadMedia:',
        '''if (downloadStem.length > 0) {
                                                                                                            sDYYYDownloadStem = [downloadStem copy];
                                                                                                        }
                                                                                                        [self downloadMedia:'''
    )

    region = region.replace(
        '[self downloadAllImages:allImages];',
        '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
                [self downloadAllImages:allImages];'''
    )
    region = region.replace(
        '[self batchDownloadResources:singleVideoArray images:allImages];',
        '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
                                                                                                          [self batchDownloadResources:singleVideoArray images:allImages];'''
    )
    region = region.replace(
        '[self batchDownloadResources:videos images:allImages];',
        '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
        [self batchDownloadResources:videos images:allImages];'''
    )

m = m[:start] + region + m[end:]
manager.write_text(m, encoding="utf-8")

print(f"Patched {api_entry_count} API save entry points (Modern + Classic)")
print("Bound API quality actions to per-request download metadata")
