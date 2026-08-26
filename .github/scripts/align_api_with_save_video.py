#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import re
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
longpress = root / "DYYYLongPressPanel.xm"
if not longpress.exists():
    raise SystemExit(f"Missing required file: {longpress}")

text = longpress.read_text(encoding="utf-8")

# DYYY 同时有 Modern / Classic 两套长按面板。
# 保存视频在点击时始终实时读取 self.awemeModel：
#   AWEAwemeModel *awemeModel = self.awemeModel;
# 接口保存也强制采用完全相同的取作品方式。
#
# 匹配每一个 apiDownload.action 的开头，一直到 shareLink 声明，
# 无论前序补丁把它改成 self.awemeModel、snapshot 或其它形式，统一重写。
pattern = re.compile(
    r'(apiDownload\.action\s*=\s*\^\{)'
    r'.*?'
    r'(NSString\s*\*shareLink\s*=\s*\[[^;]+?valueForKey:@"shareURL"\]\s*;)',
    re.S,
)

replacement = r'''\1
          // 与“保存视频”完全一致：点击按钮这一刻实时获取当前作品模型。
          AWEAwemeModel *awemeModel = self.awemeModel;
          [DYYYManager setDownloadAwemeModel:awemeModel];
          NSString *shareLink = [awemeModel valueForKey:@"shareURL"];'''

text, count = pattern.subn(replacement, text)
if count < 2:
    raise RuntimeError(f"Expected to patch both Modern and Classic API actions, patched {count}")

longpress.write_text(text, encoding="utf-8")
print(f"Aligned {count} API download actions with save-video aweme acquisition flow")
