你在一台 Apple Silicon Mac（macOS 27，装有 Xcode 命令行工具里的 swift、python3，没有 ffmpeg，不要假设能装新软件）上，当前目录是 `~/Windows互传/splash`。你只能读写文件，不能执行命令；写完后会有人通过 SSH 运行你的脚本。所以脚本必须一次能跑通：只用系统自带框架和 Python 标准库，仔细核对 API 用法，不留 TODO。

## 已有内容

- `frames/intro/0000.png … 0155.png`（156 帧）、`frames/loop/0000.png … 0170.png`（171 帧）、`frames/outro/0000.png … 0036.png`（37 帧）。都是 3840×2160 的 RGBA PNG，颜色全是纯黑，形状只在 alpha 通道里（非预乘/直通 alpha）。帧率 60。
- `src/` 是动画的源码和参数，仅供参考，不要改。

这是一个 App 的开屏动画：intro 播一次，loop 循环播放直到 App 加载完，outro 播一次后画面完全透明。最终要在 Mac 的 WKWebView（Tauri）和 Safari 里以透明视频的形式叠在界面上播放。

## 请在 `tools/` 下写这些文件

### 1. `tools/encode.swift`
用法：`swift tools/encode.swift <帧目录> <输出.mov> [fps=60]`
- 按文件名顺序读取目录里的 PNG，用 AVAssetWriter 写成 QuickTime `.mov`，编码 `AVVideoCodecType.hevcWithAlpha`，分辨率取自第一帧（3840×2160），每帧时长 1/fps，时间刻度用 600 的整数倍（如 timescale 600，每帧 10）。
- 像素缓冲用 `kCVPixelFormatType_32BGRA`，写入时必须是**预乘 alpha**（用 CGContext + `CGImageAlphaInfo.premultipliedFirst` + `byteOrder32Little` 把 CGImage 画进 CVPixelBuffer 即可；画之前先把缓冲清零，否则透明区域会残留上一帧）。
- 压缩属性里设置 `AVVideoQualityKey`（约 0.8）和 `kVTCompressionPropertyKey_TargetQualityForAlpha`（约 0.9）；不要设会导致 hevcWithAlpha 报错的属性。
- 用 `requestMediaDataWhenReady` 或轮询 `isReadyForMoreMediaData` 正确处理背压；结束时等待 `finishWriting` 完成；任何失败都打印原因并以非零码退出。输出文件已存在就先删除。
- 成功后打印一行：帧数、分辨率、时长、文件大小。
- 作为脚本运行（顶层代码，不需要 @main），注意 Swift 6 的并发检查：用信号量 / RunLoop 等待，避免写出编译不过的 async 顶层代码。

### 2. `tools/inspect.swift`
用法：`swift tools/inspect.swift <视频.mov>`
- 用 AVAsset 读取并打印：编码四字符码（应为 `hvc1`）、分辨率、帧率、帧数、时长、轨道是否带 alpha（检查 format description 的 `kCMFormatDescriptionExtension_ContainsAlphaChannel`，或 `AVMediaCharacteristic.containsAlphaChannel`）。
- 再用 AVAssetReader（输出 `kCVPixelFormatType_32BGRA`）解码首帧、中间帧、末帧，分别打印：四角和正中心像素的 BGRA 值、整帧 alpha 的最小值和最大值。
- 加一个可选参数 `--compare <另一个视频>`：解码本视频的**最后一帧**和另一个视频的**第一帧**，打印两者 alpha 通道逐像素差的绝对值之和 / 255，以及单像素最大差（用来检查段与段、循环首尾的衔接）。

### 3. `tools/serve.py`
用法：`python3 tools/serve.py [端口=8766]`，只监听 127.0.0.1，网站根目录是 `splash/`（脚本所在目录的上一级）。
- **必须支持 HTTP Range 请求**（`206 Partial Content`、`Accept-Ranges: bytes`、`Content-Range`），Safari / WKWebView 没有它不播放视频。`.mov` 的 Content-Type 用 `video/quicktime`。
- `POST /report?name=<字母数字下划线>`：把请求体（JSON）写到 `results/<name>.json`，返回 204。
- `GET /quit`：返回 200 后结束进程。
- 不要打印访问日志之外的多余内容。

### 4. `tools/test.html`
在浏览器里实际播放并自检透明效果的页面。地址参数：`?name=<结果名>`。
- 页面背景是醒目的品红色 `rgb(255,0,255)`，上面放一个 `<video>`（`muted playsinline preload="auto"`，宽 960 高 540，`object-fit: contain`），视频元素自身不设背景。透明正确时，品红应从视频的透明区域透出来。
- 依次播放 `out/intro.mov`、`out/loop.mov`（完整播放两遍，用来看循环衔接）、`out/outro.mov`，每段都真正调用 `play()` 播到结束（`ended` 事件，loop 段用计数 ended 两次、每次重新 `play()`，或设 `loop` 并监听 `timeupdate` 回绕）。
- 在每段播放过程中，用 `requestVideoFrameCallback`（没有就用 `requestAnimationFrame`）取若干时刻（至少：刚开始、中间、快结束），把当前视频帧 `drawImage` 到一个 `willReadFrequently` 的 2D canvas（canvas 先 `clearRect`，不填背景），用 `getImageData` 读出：左上角、右下角、正中心三个像素的 RGBA。
- 记录：`navigator.userAgent`、每段的 `videoWidth/videoHeight/duration`、是否成功播放到结束、`error`（若有）、上述采样值、每段实际收到的帧回调次数、`video.canPlayType('video/quicktime; codecs="hvc1"')` 和 `'video/mp4; codecs="hvc1"'` 的返回值。
- 全部结束（或总计超过 40 秒超时）后，把结果 `POST` 到 `/report?name=<name>`，然后把 `document.title` 改成 `DONE`，并在页面上显示一行摘要。任何异常都要被捕获并写进结果里再上报，不能静默失败。
- 自动播放可能被策略拦截：`play()` 被拒绝时把原因写进结果。

### 5. `tools/wkplay.swift`
用法：`swift tools/wkplay.swift <URL> <截图输出目录> [超时秒=60]`
- 一个 AppKit 小程序（`NSApplication.shared`，`setActivationPolicy(.accessory)`，脚本顶层代码运行）：创建无边框、**透明**的 NSWindow（`isOpaque = false`，`backgroundColor = .clear`），内容视图里先铺一个绿色 `rgb(0,255,0)` 的底层视图，再在上面放一个 WKWebView。
- WKWebView 设为透明：`webView.setValue(false, forKey: "drawsBackground")`；配置里 `mediaTypesRequiringUserActionForPlayback = []`，允许自动播放。
- 加载给定 URL。每隔约 0.5 秒用 `evaluateJavaScript("document.title")` 检查；期间每隔约 1 秒调用一次 `webView.takeSnapshot(with: nil)`，把得到的 NSImage 存成 PNG（`snap_000.png`、`snap_001.png` …）到输出目录，最多存 30 张。
- 标题变成 `DONE` 或超时后，再存最后一张，打印存了几张，然后 `exit(0)`（超时用非零码）。
- 注意：WKWebView 的回调都在主线程，脚本要用 `NSApp.run()` 驱动；Swift 6 下给顶层代码里用到的类标 `@MainActor` 或用合适的方式避免并发编译错误。

### 6. `tools/run_all.sh`
按顺序做完所有事并把输出写到 `results/log.txt`（同时打印到终端），`set -u`，每步失败时继续做后面的并在最后汇总：
1. `mkdir -p out results results/wk`
2. 用 `encode.swift` 把三段分别编码成 `out/intro.mov`、`out/loop.mov`、`out/outro.mov`
3. 用 `inspect.swift` 检查三个文件；并做三次衔接比较：intro→loop、loop→loop（循环首尾）、loop→outro
4. 后台启动 `serve.py`（端口 8766），等它就绪
5. 运行 `wkplay.swift http://127.0.0.1:8766/tools/test.html?name=wkwebview results/wk 70`
6. 用 `open -a Safari "http://127.0.0.1:8766/tools/test.html?name=safari"` 在 Safari 里打开，然后最多等 70 秒，直到 `results/safari.json` 出现
7. 请求 `/quit` 关掉服务器，打印 `results/` 里两个 JSON 的内容

### 7. `tools/README.md`
简短说明每个文件做什么、怎么运行、结果怎么看。

写完后，用几句话告诉我每个文件里你最没把握、最可能在运行时出错的地方。
