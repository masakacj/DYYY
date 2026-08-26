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

# 1) 接口保存按钮必须捕获创建该按钮时对应的作品模型，不能在点击时再读 self.awemeModel。
lp = longpress.read_text(encoding="utf-8")
old = '''        apiDownload.describeString = @"接口保存";
        apiDownload.action = ^{
          // 接口解析是异步链路，先在点击瞬间冻结作者/抖音号/发布时间命名上下文
          [DYYYManager setDownloadAwemeModel:self.awemeModel];
          NSString *shareLink = [self.awemeModel valueForKey:@"shareURL"];'''
new = '''        apiDownload.describeString = @"接口保存";
        // dataArray 创建按钮时就快照当前作品。后续 self.awemeModel 可能已经切到别的视频。
        AWEAwemeModel *dyyyAPIAwemeSnapshot = apiDownload.awemeModel;
        apiDownload.action = ^{
          [DYYYManager setDownloadAwemeModel:dyyyAPIAwemeSnapshot];
          NSString *shareLink = [dyyyAPIAwemeSnapshot valueForKey:@"shareURL"];'''
if new not in lp:
    if old not in lp:
        raise RuntimeError("API long-press snapshot patch point not found")
    lp = lp.replace(old, new, 1)
longpress.write_text(lp, encoding="utf-8")

# 2) 接口返回后不能只恢复一个全局 stem，因为用户还要第二次点击原画/720P。
#    把本次请求的 downloadStem 直接传进 handleVideoData，并让每个画质 action 捕获它。
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

# 只修改 handleVideoData 方法区域，避免影响普通保存。
start = m.find(new_sig)
end = m.find('\n#define DYYYLogVideo', start)
if start < 0 or end < 0:
    raise RuntimeError("handleVideoData region not found")
region = m[start:end]

# 每一个真正创建下载任务的入口，都在点击动作发生的瞬间恢复本次请求的 stem。
prefix = '''if (downloadStem.length > 0) {
                                                                                                            sDYYYDownloadStem = [downloadStem copy];
                                                                                                        }
                                                                                                        '''
region = region.replace('[self downloadMedia:', prefix + '[self downloadMedia:')

# 单图直接下载的缩进不同，再兜底一层；重复注入时不再执行。
if 'DYYY_API_QUALITY_CONTEXT_BOUND' not in region:
    region = region.replace('[self downloadAllImages:allImages];', '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
                [self downloadAllImages:allImages];''')
    region = region.replace('[self batchDownloadResources:singleVideoArray images:allImages];', '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
                                                                                                          [self batchDownloadResources:singleVideoArray images:allImages];''')
    region = region.replace('[self batchDownloadResources:videos images:allImages];', '''if (downloadStem.length > 0) sDYYYDownloadStem = [downloadStem copy];
        [self batchDownloadResources:videos images:allImages];''')
    region = region.replace(new_sig, new_sig + '\n    // DYYY_API_QUALITY_CONTEXT_BOUND')

m = m[:start] + region + m[end:]
manager.write_text(m, encoding="utf-8")

print("Bound API quality actions to per-request download metadata")
