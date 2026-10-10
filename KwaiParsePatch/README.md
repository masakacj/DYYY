# KwaiParsePatch

快手 iOS（Bundle ID `com.jiangjia.gif`）接口解析注入插件。

## 当前交互

1. 在快手视频播放页长按。
2. 弹出：
   - **接口解析**
   - **设置**
3. 首次使用先进入 **设置**，填写解析接口地址。
4. 点击 **接口解析** 后，插件识别当前作品并调用接口。
5. 接口返回后弹出视频档位：
   - App 最高分辨率
   - 主文件 / 高帧率候选
   - 其它 App 播放档位
6. 点击档位后下载并写入系统相册。

插件不内置任何私有解析域名或服务器地址。

## 接口设置格式

可以填写接口参数前缀，例如：

```
https://example.com/api/kuaishou/resolve?source=dyyy&url=
```

也可以使用一个 `%@` 占位符：

```
https://example.com/api/kuaishou/resolve?source=dyyy&url=%@
```

插件会把当前快手作品 ID / 分享链接做 URL 编码后追加进去。

接口返回格式沿用 DYYY 的 `video_list` 协议。插件不会把“App 最高”或“主文件”错误标成“上传原画”。

## 当前作品识别

长按时优先从当前视频页面的 controller/model 对象图中寻找：

- 快手 `photoId`（如 `3x...`）
- 快手分享 URL

为了提高不同快手版本的兼容性，插件仍会被动缓存 App 自己写入剪贴板的快手链接，但**复制链接不再自动触发解析**。如果某个快手版本无法直接从页面 model 识别作品，可在当前视频先执行一次“分享 → 复制链接”，随后返回视频页长按解析。

## 构建

```bash
make clean all FINALPACKAGE=1
```

CI 会发布 standalone `KwaiParsePatch.dylib`，用于注入已签名/自签的快手 IPA。

## 兼容策略

- 不直接依赖固定的快手私有分享面板类名。
- 通过 `UIViewController` 生命周期给 App 页面安装非阻断型长按手势。
- 通过当前 controller/model 的运行时对象图识别 `photoId`。
- 长按手势允许与快手原有手势同时识别，尽量降低对原 App 操作的干扰。
