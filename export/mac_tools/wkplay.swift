// wkplay.swift — 在透明 NSWindow + 透明 WKWebView 里打开一个页面，定时截图，等标题变成 DONE
//
// 用法: swift tools/wkplay.swift <URL> <截图输出目录> [超时秒=60]
//
// - 窗口无边框、透明；内容视图最底层是纯绿 rgb(0,255,0)，上面盖一个不画背景的 WKWebView
// - 每 0.5 秒查一次 document.title；每 1 秒 takeSnapshot 存一张 snap_NNN.png（最多 30 张）
// - 标题变成 DONE（退出码 0）、超时（1）或页面加载失败（2）后，再存最后一张并退出
// - 启动时会删掉输出目录里上一次留下的 snap_*.png
//
// 需要能连上 WindowServer（即本用户已在这台 Mac 的图形界面登录）。

import AppKit
import WebKit

func emit(_ message: String) {
    FileHandle.standardOutput.write(Data(("wkplay: " + message + "\n").utf8))
}

func emitError(_ message: String) {
    FileHandle.standardError.write(Data(("wkplay: error: " + message + "\n").utf8))
}

@MainActor
final class Player: NSObject, WKNavigationDelegate {
    private static let maxPeriodicSnapshots = 30
    private static let windowSize = NSSize(width: 1000, height: 640)

    private let url: URL
    private let outDir: URL
    private let timeout: TimeInterval
    private let window: NSWindow
    private let webView: WKWebView

    private var timer: Timer?
    private var startDate = Date()
    private var tickCount = 0
    private var periodicRequested = 0
    private var savedCount = 0
    private var nextIndex = 0
    private var snapshotInFlight = false
    private var titleQueryInFlight = false
    private var lastTitle: String? = nil
    private var finishing = false
    private var completed = false
    private var exitCode: Int32 = 0

    init(url: URL, outDir: URL, timeout: TimeInterval) {
        self.url = url
        self.outDir = outDir
        self.timeout = timeout

        let size = Player.windowSize
        var origin = NSPoint(x: 80, y: 80)
        if let screen = NSScreen.main {
            let vf = screen.visibleFrame
            origin = NSPoint(x: vf.minX + 40, y: max(vf.minY, vf.maxY - size.height - 40))
        }
        let contentRect = NSRect(origin: origin, size: size)
        let window = NSWindow(contentRect: contentRect,
                              styleMask: [.borderless],
                              backing: .buffered,
                              defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.isReleasedWhenClosed = false
        window.level = .floating   // 保持可见，避免被遮挡后 WebKit 降频
        self.window = window

        let bounds = NSRect(origin: .zero, size: size)
        let container = NSView(frame: bounds)
        container.wantsLayer = true

        let green = NSView(frame: bounds)
        green.wantsLayer = true
        green.layer?.backgroundColor = CGColor(red: 0, green: 1, blue: 0, alpha: 1)
        green.autoresizingMask = [.width, .height]
        container.addSubview(green)

        let configuration = WKWebViewConfiguration()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        let webView = WKWebView(frame: bounds, configuration: configuration)
        webView.setValue(false, forKey: "drawsBackground")
        webView.autoresizingMask = [.width, .height]
        container.addSubview(webView)   // 后加的在上层
        self.webView = webView

        window.contentView = container

        super.init()
        webView.navigationDelegate = self
    }

    func start() {
        window.orderFrontRegardless()
        startDate = Date()
        emit("loading \(url.absoluteString) (timeout \(Int(timeout))s), snapshots -> \(outDir.path)")
        webView.load(URLRequest(url: url))
        timer = Timer.scheduledTimer(timeInterval: 0.5,
                                     target: self,
                                     selector: #selector(tick),
                                     userInfo: nil,
                                     repeats: true)
    }

    private func elapsedText() -> String {
        return String(format: "%.1fs", Date().timeIntervalSince(startDate))
    }

    @objc private func tick() {
        if finishing { return }
        tickCount += 1

        if Date().timeIntervalSince(startDate) >= timeout {
            finish(code: 1, reason: "TIMEOUT after \(Int(timeout))s (last title: \(lastTitle ?? "<none>"))")
            return
        }

        if !titleQueryInFlight {
            titleQueryInFlight = true
            webView.evaluateJavaScript("document.title") { [self] value, error in
                titleQueryInFlight = false
                if finishing { return }
                if let title = value as? String {
                    if title != lastTitle {
                        lastTitle = title
                        emit("[\(elapsedText())] title = \"\(title)\"")
                    }
                    if title == "DONE" {
                        finish(code: 0, reason: "title is DONE")
                    }
                } else if let error = error {
                    emit("[\(elapsedText())] document.title query failed: \(error.localizedDescription)")
                }
            }
        }

        if tickCount % 2 == 0 {
            periodicSnapshot()
        }
    }

    private func periodicSnapshot() {
        if snapshotInFlight || periodicRequested >= Player.maxPeriodicSnapshots { return }
        snapshotInFlight = true
        periodicRequested += 1
        webView.takeSnapshot(with: nil) { [self] image, error in
            snapshotInFlight = false
            if completed { return }
            if let image = image {
                _ = save(image, label: "periodic")
            } else {
                emit("[\(elapsedText())] snapshot failed: \(error?.localizedDescription ?? "no image")")
            }
        }
    }

    private func save(_ image: NSImage, label: String) -> Bool {
        var data: Data? = nil
        if let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) {
            data = NSBitmapImageRep(cgImage: cgImage).representation(using: .png, properties: [:])
        }
        if data == nil, let tiff = image.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff) {
            data = rep.representation(using: .png, properties: [:])
        }
        guard let png = data else {
            emit("[\(elapsedText())] could not convert snapshot to PNG")
            return false
        }
        let name = String(format: "snap_%03d.png", nextIndex)
        do {
            try png.write(to: outDir.appendingPathComponent(name))
        } catch {
            emit("[\(elapsedText())] could not write \(name): \(error.localizedDescription)")
            return false
        }
        nextIndex += 1
        savedCount += 1
        emit("[\(elapsedText())] saved \(name) (\(label), \(Int(image.size.width))x\(Int(image.size.height)) pt, \(png.count) bytes)")
        return true
    }

    private func finish(code: Int32, reason: String) {
        if finishing { return }
        finishing = true
        exitCode = code
        timer?.invalidate()
        timer = nil
        emit("[\(elapsedText())] finishing: \(reason)")

        // 万一最后一张截图的回调永远不来，也要能退出
        perform(#selector(finalSnapshotWatchdog), with: nil, afterDelay: 8.0)

        webView.takeSnapshot(with: nil) { [self] image, error in
            if completed { return }
            if let image = image {
                _ = save(image, label: "final")
            } else {
                emit("[\(elapsedText())] final snapshot failed: \(error?.localizedDescription ?? "no image")")
            }
            complete()
        }
    }

    @objc private func finalSnapshotWatchdog() {
        if completed { return }
        emit("final snapshot did not return within 8s; giving up on it")
        complete()
    }

    private func complete() {
        if completed { return }
        completed = true
        emit("saved \(savedCount) snapshot(s) to \(outDir.path); exit code \(exitCode)")
        exit(exitCode)
    }

    // MARK: - WKNavigationDelegate

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        emit("[\(elapsedText())] page loaded")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        finish(code: 2, reason: "page failed to load: \(error.localizedDescription)")
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        finish(code: 2, reason: "navigation failed: \(error.localizedDescription)")
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        finish(code: 2, reason: "web content process terminated")
    }
}

// MARK: - 参数

let arguments = CommandLine.arguments
if arguments.count < 3 || arguments.count > 4 {
    emitError("usage: swift tools/wkplay.swift <URL> <snapshot-dir> [timeout-seconds=60]")
    exit(64)
}
guard let pageURL = URL(string: arguments[1]), pageURL.scheme != nil else {
    emitError("invalid URL: \(arguments[1])")
    exit(64)
}
let snapshotDir = URL(fileURLWithPath: arguments[2], isDirectory: true)
var timeoutSeconds: TimeInterval = 60
if arguments.count == 4 {
    guard let value = Double(arguments[3]), value > 0 else {
        emitError("invalid timeout: \(arguments[3])")
        exit(64)
    }
    timeoutSeconds = value
}

do {
    try FileManager.default.createDirectory(at: snapshotDir, withIntermediateDirectories: true)
} catch {
    emitError("cannot create \(snapshotDir.path): \(error.localizedDescription)")
    exit(74)
}
// 清掉上一次运行留下的截图，避免新旧混在一起
if let oldNames = try? FileManager.default.contentsOfDirectory(atPath: snapshotDir.path) {
    for name in oldNames where name.hasPrefix("snap_") && name.hasSuffix(".png") {
        try? FileManager.default.removeItem(at: snapshotDir.appendingPathComponent(name))
    }
}

// MARK: - 运行

// 顶层代码在编译器看来不在主 actor 上，而 Player 是 @MainActor；脚本确实运行在主线程，这里显式声明
MainActor.assumeIsolated {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let player = Player(url: pageURL, outDir: snapshotDir, timeout: timeoutSeconds)
    player.start()
    app.run()
}
