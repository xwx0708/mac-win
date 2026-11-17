// encode.swift — 把一个目录里的 PNG 序列编码成 HEVC-with-alpha 的 QuickTime .mov
//
// 用法: swift tools/encode.swift <帧目录> <输出.mov> [fps=60]
//
// - 帧按文件名排序（文件名需零填充，如 0000.png）
// - 输入 PNG 是直通（非预乘）alpha；写进 CVPixelBuffer 时由 CoreGraphics 转成预乘 alpha
// - 只用系统框架；作为脚本运行（顶层代码，不用 async）

import Foundation
import AVFoundation
import CoreVideo
import CoreGraphics
import ImageIO
import VideoToolbox

setvbuf(stdout, nil, _IOLBF, 0)

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("encode: error: " + message + "\n").utf8))
    exit(1)
}

func describeError(_ error: Error?) -> String {
    guard let error = error else { return "unknown error" }
    let ns = error as NSError
    var s = "\(ns.domain) code=\(ns.code) \(ns.localizedDescription)"
    if let reason = ns.localizedFailureReason { s += " reason=\(reason)" }
    if let underlying = ns.userInfo[NSUnderlyingErrorKey] as? NSError {
        s += " underlying=(\(underlying.domain) code=\(underlying.code) \(underlying.localizedDescription))"
    }
    return s
}

func loadCGImage(_ url: URL) -> CGImage? {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(source, 0, nil)
}

/// 清零缓冲后，把 CGImage 以预乘 alpha（BGRA，小端 premultipliedFirst）画进去。
func render(_ image: CGImage, into buffer: CVPixelBuffer, colorSpace: CGColorSpace) -> Bool {
    guard CVPixelBufferLockBaseAddress(buffer, []) == kCVReturnSuccess else { return false }
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard let base = CVPixelBufferGetBaseAddress(buffer) else { return false }
    let w = CVPixelBufferGetWidth(buffer)
    let h = CVPixelBufferGetHeight(buffer)
    let bytesPerRow = CVPixelBufferGetBytesPerRow(buffer)
    // 池里取出的缓冲可能残留上一帧内容，必须先清零
    memset(base, 0, bytesPerRow * h)
    let bitmapInfo = CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
    guard let ctx = CGContext(data: base,
                              width: w,
                              height: h,
                              bitsPerComponent: 8,
                              bytesPerRow: bytesPerRow,
                              space: colorSpace,
                              bitmapInfo: bitmapInfo) else { return false }
    ctx.interpolationQuality = .none
    ctx.setBlendMode(.copy)
    ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
    ctx.flush()
    return true
}

func makePixelBuffer(adaptor: AVAssetWriterInputPixelBufferAdaptor,
                     width: Int, height: Int,
                     attributes: [String: Any]) -> CVPixelBuffer {
    var buffer: CVPixelBuffer?
    let status: CVReturn
    if let pool = adaptor.pixelBufferPool {
        status = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &buffer)
    } else {
        status = CVPixelBufferCreate(kCFAllocatorDefault, width, height,
                                     kCVPixelFormatType_32BGRA,
                                     attributes as CFDictionary, &buffer)
    }
    guard status == kCVReturnSuccess, let result = buffer else {
        fail("could not create pixel buffer (CVReturn \(status))")
    }
    return result
}

// MARK: - 参数

let argv = CommandLine.arguments
if argv.count < 3 || argv.count > 4 {
    fail("usage: swift tools/encode.swift <frame-dir> <output.mov> [fps=60]")
}
let frameDir = URL(fileURLWithPath: argv[1], isDirectory: true)
let outputURL = URL(fileURLWithPath: argv[2])
var fps = 60
if argv.count == 4 {
    guard let v = Int(argv[3]), v > 0, v <= 600 else { fail("invalid fps: \(argv[3])") }
    fps = v
}
// 时间刻度：600 的整数倍，且能被 fps 整除
let timescale: Int32 = (600 % fps == 0) ? 600 : Int32(600 * fps)
let ticksPerFrame = Int64(timescale) / Int64(fps)

// MARK: - 帧列表

let fm = FileManager.default
let allNames: [String]
do {
    allNames = try fm.contentsOfDirectory(atPath: frameDir.path)
} catch {
    fail("cannot list \(frameDir.path): \(describeError(error))")
}
let names = allNames
    .filter { !$0.hasPrefix(".") && $0.lowercased().hasSuffix(".png") }
    .sorted()
if names.isEmpty { fail("no .png files in \(frameDir.path)") }

guard let firstImage = loadCGImage(frameDir.appendingPathComponent(names[0])) else {
    fail("cannot decode \(names[0])")
}
let width = firstImage.width
let height = firstImage.height
guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { fail("cannot create sRGB color space") }

print("encode: \(names.count) frames from \(frameDir.path), \(width)x\(height), fps=\(fps), timescale=\(timescale), ticks/frame=\(ticksPerFrame)")

// MARK: - Writer

if fm.fileExists(atPath: outputURL.path) {
    do { try fm.removeItem(at: outputURL) } catch {
        fail("cannot remove existing \(outputURL.path): \(describeError(error))")
    }
}
do {
    try fm.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
} catch {
    fail("cannot create output directory: \(describeError(error))")
}

let writer: AVAssetWriter
do {
    writer = try AVAssetWriter(outputURL: outputURL, fileType: .mov)
} catch {
    fail("cannot create AVAssetWriter: \(describeError(error))")
}
writer.shouldOptimizeForNetworkUse = true   // moov 放在文件头，便于浏览器边下边播

let compressionProperties: [String: Any] = [
    AVVideoQualityKey: 0.8,
    kVTCompressionPropertyKey_TargetQualityForAlpha as String: 0.9,
]
let outputSettings: [String: Any] = [
    AVVideoCodecKey: AVVideoCodecType.hevcWithAlpha,
    AVVideoWidthKey: width,
    AVVideoHeightKey: height,
    AVVideoCompressionPropertiesKey: compressionProperties,
]
guard writer.canApply(outputSettings: outputSettings, forMediaType: .video) else {
    fail("writer cannot apply output settings (hevcWithAlpha \(width)x\(height)) — encoder unavailable?")
}

let input = AVAssetWriterInput(mediaType: .video, outputSettings: outputSettings)
input.expectsMediaDataInRealTime = false
input.mediaTimeScale = timescale

let sourceAttributes: [String: Any] = [
    kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA),
    kCVPixelBufferWidthKey as String: width,
    kCVPixelBufferHeightKey as String: height,
    kCVPixelBufferCGImageCompatibilityKey as String: true,
    kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
    kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
]
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input,
                                                   sourcePixelBufferAttributes: sourceAttributes)

guard writer.canAdd(input) else { fail("writer cannot add video input") }
writer.add(input)

guard writer.startWriting() else {
    fail("startWriting failed: \(describeError(writer.error))")
}
writer.startSession(atSourceTime: .zero)

// MARK: - 写帧

let startDate = Date()
for (index, name) in names.enumerated() {
    autoreleasepool {
        let url = frameDir.appendingPathComponent(name)
        let image: CGImage
        if index == 0 {
            image = firstImage
        } else {
            guard let img = loadCGImage(url) else { fail("cannot decode \(url.path)") }
            image = img
        }
        guard image.width == width, image.height == height else {
            fail("\(name) is \(image.width)x\(image.height), expected \(width)x\(height)")
        }

        let buffer = makePixelBuffer(adaptor: adaptor, width: width, height: height, attributes: sourceAttributes)
        guard render(image, into: buffer, colorSpace: colorSpace) else {
            fail("cannot draw \(name) into pixel buffer")
        }

        // 背压：等编码器准备好
        let waitStart = Date()
        while !input.isReadyForMoreMediaData {
            if writer.status == .failed {
                fail("writer failed while waiting at frame \(index): \(describeError(writer.error))")
            }
            if Date().timeIntervalSince(waitStart) > 120 {
                fail("timed out waiting for isReadyForMoreMediaData at frame \(index)")
            }
            RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.001))
            Thread.sleep(forTimeInterval: 0.002)
        }

        let pts = CMTime(value: Int64(index) * ticksPerFrame, timescale: timescale)
        if !adaptor.append(buffer, withPresentationTime: pts) {
            fail("append failed at frame \(index) (\(name)): status=\(writer.status.rawValue) \(describeError(writer.error))")
        }
    }
    if (index + 1) % 30 == 0 || index + 1 == names.count {
        print("encode:   \(index + 1)/\(names.count) frames appended (\(String(format: "%.1f", Date().timeIntervalSince(startDate)))s)")
    }
}

// MARK: - 收尾

input.markAsFinished()
let endTime = CMTime(value: Int64(names.count) * ticksPerFrame, timescale: timescale)
writer.endSession(atSourceTime: endTime)

let finished = DispatchSemaphore(value: 0)
writer.finishWriting {
    finished.signal()
}
let finishStart = Date()
while finished.wait(timeout: .now() + .milliseconds(50)) == .timedOut {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.01))
    if Date().timeIntervalSince(finishStart) > 300 {
        fail("timed out waiting for finishWriting")
    }
}
guard writer.status == .completed else {
    fail("finishWriting ended with status \(writer.status.rawValue): \(describeError(writer.error))")
}

var fileSize: Int64 = 0
if let attrs = try? fm.attributesOfItem(atPath: outputURL.path),
   let size = attrs[.size] as? NSNumber {
    fileSize = size.int64Value
}
let duration = Double(names.count) / Double(fps)
print(String(format: "encode: OK %@ frames=%d size=%dx%d duration=%.3fs file=%.2f MB (%lld bytes) elapsed=%.1fs",
             outputURL.path, names.count, width, height, duration,
             Double(fileSize) / 1_048_576.0, fileSize, Date().timeIntervalSince(startDate)))
exit(0)
