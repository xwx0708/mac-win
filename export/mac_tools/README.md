# splash 透明视频工具

把 `frames/` 里的 PNG 序列编码成带 alpha 的 HEVC `.mov`，并在 WKWebView 和 Safari 里实测能否透明播放。
只依赖系统自带的 swift、python3、curl。所有命令都在项目根目录（`splash/`）运行。

## 一键运行

```sh
bash tools/run_all.sh
```

需要本用户已登录这台 Mac 的图形界面（WKWebView 窗口和 Safari 都要连 WindowServer），屏幕不要锁定。
全程大约几分钟，主要花在 4K 编码和解码检查上。某一步失败不会中断，最后的 `SUMMARY` 会列出失败的步骤；有失败时退出码为 1。

## 文件

| 文件 | 作用 | 单独运行 |
| --- | --- | --- |
| `encode.swift` | PNG 序列 → HEVC-with-alpha `.mov` | `swift tools/encode.swift frames/intro out/intro.mov [fps=60]` |
| `inspect.swift` | 打印轨道信息（编码、尺寸、帧数、是否带 alpha），解码首/中/末帧；`--compare` 比较本视频末帧与另一个视频首帧的 alpha | `swift tools/inspect.swift out/intro.mov --compare out/loop.mov` |
| `serve.py` | 只监听 127.0.0.1 的静态服务器，支持 Range；`POST /report?name=x` 写 `results/x.json`；`GET /quit` 退出 | `python3 tools/serve.py [端口=8766]` |
| `test.html` | 依次播放 intro ×1、loop ×2、outro ×1，采样像素、统计帧回调，把结果 POST 给服务器，然后把标题改成 `DONE` | 浏览器打开 `http://127.0.0.1:8766/tools/test.html?name=<名字>` |
| `wkplay.swift` | 透明窗口（绿色底 + 透明 WKWebView）里打开 URL，每秒截图，等标题变成 `DONE` | `swift tools/wkplay.swift <URL> <截图目录> [超时秒=60]` |
| `run_all.sh` | 按顺序跑完以上全部 | `bash tools/run_all.sh` |

`wkplay.swift` 退出码：0 = 标题变成 DONE，1 = 超时，2 = 页面加载失败或网页进程崩溃。启动时会删掉截图目录里旧的 `snap_*.png`。

## 结果怎么看

- `results/log.txt`：全部输出。先看末尾的 `SUMMARY`。
- `inspect` 部分：每个文件应为 `codec=hvc1`、`ContainsAlphaChannel=true`、3840x2160、帧数 156 / 171 / 37、约 60 fps。
  四角像素的 alpha 应为 0；outro 的 `last` 帧应 `alpha max=0`（或非常接近 0），即完全透明。
- `compare` 部分：`mean |Δalpha| per pixel` 和 `differing pixels` 越小，衔接越平滑。
  三处都是"前一段末帧 vs 后一段首帧"，本来就差一帧的运动量，所以不会是 0；明显偏大才说明衔接会跳。
- `results/wkwebview.json`、`results/safari.json`：`test.html` 的报告。先看 `summary` 一行：
  每段应 `ended=yes`、尺寸 3840x2160、`errors=0`、没有 `TIMEOUT`；
  `TL.a=[0,0,…]` 表示左上角 alpha 一直是 0，说明视频确实按透明解码（如果是 255，alpha 丢了）。
  `frameCb` 是帧回调次数，接近该段帧数 × 播放次数说明没有严重掉帧。
- `results/wk/snap_*.png`：WKWebView 每秒一张的截图，最后一张是结束时的画面。
  页面背景是洋红色，视频区域里应看到黑色形状直接叠在洋红上、没有黑色或白色矩形底。
  `takeSnapshot` 只截网页内容，不包含窗口里的绿色底；绿色底只在屏幕上肉眼看窗口时有用。
- `results/serve.log`：服务器的请求日志，排查 404 或 Range 问题时看。

Safari 里测试用的标签页不会自动关闭，跑完手动关掉即可。
