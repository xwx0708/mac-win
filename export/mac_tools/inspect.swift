// inspect.swift — 检查 HEVC-with-alpha .mov 的轨道信息并解码首/中/末帧
//
// 用法: swift tools/inspect.swift <视频.mov> [--compare <另一个视频.mov>]
//
// --compare: 比较本视频【最后一帧】与另一个视频【第一帧】的 alpha 通道
//
// 说明：这里故意使用 AVAsset 的同步属性（macOS 13 起标记为 deprecated，会有编译警告），
// 以避免在顶层脚本里写 async 代码。

import Foundation
import AVFoundation
import CoreMedia
import CoreVideo

setvbuf(stdout, nil, _IOLBF, 0)

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("inspect: error: " + message + "\n").utf8))
    exit(1)
}

func fourCC(_ code: FourCharCode) -> String {
    let bytes: [UInt8] = [UInt8((code >> 24) & 0xff), UInt8((code >> 16) & 0xff),
                          UInt8((code >> 8) & 0xff), UInt8(code & 0xff)]
    return String(bytes.map { (32...126).contains($0) ? Character(UnicodeScalar($0)) : "?" })
}

func fmt(_ value: Double, _ digits: Int = 3) -> String {
    return String(format: "%.\(digits)f", value)
}

struct FrameStats {
    var index: Int
    var time: Double
    var width: Int
    var height: Int
    var samples: [(String, [UInt8])]   // BGRA
    var alphaMin: UInt8
    var alphaMax: UInt8
    var opaqueCount: Int
    var transparentCount: Int
    var alpha: [UInt8]                 // 只有需要比较时才填充，否则为空
}

func analyze(_ buffer: CVPixelBuffer, index: Int, time: Double, keepAlpha: Bool) -> FrameStats? {
    let pixelFormat = CVPixelBufferGetPixelFormatType(buffer)
    guard pixelFormat == kCVPixelFormatType_32BGRA else {
        print("  frame #\(index): unexpected pixel format '\(fourCC(pixelFormat))'")
        return nil
    }
    guard CVPixelBufferLockBaseAddress(buffer, .readOnly) == kCVReturnSuccess else {
        print("  frame #\(index): cannot lock pixel buffer")
        return nil
    }
    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
    guard let base = CVPixelBufferGetBaseAddress(buffer) else { return nil }
    let w = CVPixelBufferGetWidth(buffer)
    let h = CVPixelBufferGetHeight(buffer)
    let bytesPerRow = CVPixelBufferGetBytesPerRow(buffer)
    let p = base.assumingMemoryBound(to: UInt8.self)

    func pixel(_ x: Int, _ y: Int) -> [UInt8] {
        let o = y * bytesPerRow + x * 4
        return [p[o], p[o + 1], p[o + 2], p[o + 3]]
    }
    let samples: [(String, [UInt8])] = [
        ("TL", pixel(0, 0)),
        ("TR", pixel(w - 1, 0)),
        ("BL", pixel(0, h - 1)),
        ("BR", pixel(w - 1, h - 1)),
        ("C", pixel(w / 2, h / 2)),
    ]

    var aMin: UInt8 = 255
    var aMax: UInt8 = 0
    var opaque = 0
    var transparent = 0
    var alpha = [UInt8](repeating: 0, count: keepAlpha ? w * h : 0)
    alpha.withUnsafeMutableBufferPointer { dst in
        for y in 0..<h {
            let row = p + y * bytesPerRow
            for x in 0..<w {
                let a = row[x * 4 + 3]
                if a < aMin { aMin = a }
                if a > aMax { aMax = a }
                if a == 255 { opaque += 1 } else if a == 0 { transparent += 1 }
                if keepAlpha { dst[y * w + x] = a }
            }
        }
    }
    return FrameStats(index: index, time: time, width: w, height: h, samples: samples,
                      alphaMin: aMin, alphaMax: aMax, opaqueCount: opaque,
                      transparentCount: transparent, alpha: alpha)
}

func describe(_ label: String, _ stats: FrameStats?) {
    guard let s = stats else {
        print("  \(label): (not decoded)")
        return
    }
    let total = Double(max(1, s.width * s.height))
    let px = s.samples.map { "\($0.0)=(\($0.1.map { String($0) }.joined(separator: ",")))" }
        .joined(separator: " ")
    print("  \(label) #\(s.index) t=\(fmt(s.time))s \(s.width)x\(s.height)")
    print("    BGRA: \(px)")
    print("    alpha min=\(s.alphaMin) max=\(s.alphaMax)  a==255: \(fmt(100 * Double(s.opaqueCount) / total, 2))%  a==0: \(fmt(100 * Double(s.transparentCount) / total, 2))%")
}

func openVideo(_ path: String) -> (AVURLAsset, AVAssetTrack) {
    let url = URL(fileURLWithPath: path)
    guard FileManager.default.fileExists(atPath: url.path) else { fail("no such file: \(path)") }
    let asset = AVURLAsset(url: url)
    guard let track = asset.tracks(withMediaType: .video).first else {
        fail("no video track in \(path)")
    }
    return (asset, track)
}

func startReader(_ asset: AVAsset, _ track: AVAssetTrack, decode: Bool) -> (AVAssetReader, AVAssetReaderTrackOutput) {
    let reader: AVAssetReader
    do {
        reader = try AVAssetReader(asset: asset)
    } catch {
        fail("cannot create AVAssetReader: \(error)")
    }
    let settings: [String: Any]? = decode
        ? [kCVPixelBufferPixelFormatTypeKey as String: Int(kCVPixelFormatType_32BGRA)]
        : nil
    let output = AVAssetReaderTrackOutput(track: track, outputSettings: settings)
    output.alwaysCopiesSampleData = false
    guard reader.canAdd(output) else { fail("reader cannot add track output") }
    reader.add(output)
    guard reader.startReading() else {
        fail("startReading failed: \(reader.error.map { "\($0)" } ?? "unknown")")
    }
    return (reader, output)
}

/// 不解码，直接数压缩样本数（= 帧数）
func countSamples(_ asset: AVAsset, _ track: AVAssetTrack) -> Int {
    let (reader, output) = startReader(asset, track, decode: false)
    var count = 0
    while true {
        let done: Bool = autoreleasepool {
            guard let sb = output.copyNextSampleBuffer() else { return true }
            count += CMSampleBufferGetNumSamples(sb)
            return false
        }
        if done { break }
    }
    if reader.status != .completed {
        print("  WARN: passthrough reader status=\(reader.status.rawValue) error=\(reader.error.map { "\($0)" } ?? "nil")")
    }
    return count
}

struct DecodeResult {
    var stats: [Int: FrameStats] = [:]
    var decodedCount = 0
    var last: FrameStats?
}

func decode(_ asset: AVAsset, _ track: AVAssetTrack,
            analyzeIndices: Set<Int>, keepAlphaIndices: Set<Int>,
            analyzeLast: Bool, keepLastAlpha: Bool,
            stopAfterIndex: Int?) -> DecodeResult {
    let (reader, output) = startReader(asset, track, decode: true)
    var result = DecodeResult()
    var index = 0
    var lastBuffer: CVPixelBuffer?
    var lastTime = 0.0
    var stoppedEarly = false
    while true {
        let done: Bool = autoreleasepool {
            guard let sb = output.copyNextSampleBuffer() else { return true }
            guard let imageBuffer = CMSampleBufferGetImageBuffer(sb) else { return false }
            let t = CMSampleBufferGetPresentationTimeStamp(sb).seconds
            if analyzeIndices.contains(index),
               let s = analyze(imageBuffer, index: index, time: t, keepAlpha: keepAlphaIndices.contains(index)) {
                result.stats[index] = s
            }
            lastBuffer = imageBuffer
            lastTime = t
            index += 1
            if let stop = stopAfterIndex, index > stop {
                stoppedEarly = true
                return true
            }
            return false
        }
        if done { break }
    }
    if stoppedEarly {
        reader.cancelReading()
    } else if reader.status != .completed {
        print("  WARN: decode reader status=\(reader.status.rawValue) error=\(reader.error.map { "\($0)" } ?? "nil")")
    }
    result.decodedCount = index
    if analyzeLast, let lb = lastBuffer {
        result.last = analyze(lb, index: index - 1, time: lastTime, keepAlpha: keepLastAlpha)
    }
    return result
}

// MARK: - 参数

let rawArgs = Array(CommandLine.arguments.dropFirst())
var comparePath: String? = nil
var positional: [String] = []
var argIndex = 0
while argIndex < rawArgs.count {
    if rawArgs[argIndex] == "--compare" {
        guard argIndex + 1 < rawArgs.count else { fail("--compare needs a path") }
        comparePath = rawArgs[argIndex + 1]
        argIndex += 2
    } else {
        positional.append(rawArgs[argIndex])
        argIndex += 1
    }
}
guard positional.count == 1 else {
    fail("usage: swift tools/inspect.swift <video.mov> [--compare <other.mov>]")
}
let path = positional[0]

// MARK: - 轨道信息

let (asset, track) = openVideo(path)
print("== \(path)")

var fileSize: Int64 = 0
if let attrs = try? FileManager.default.attributesOfItem(atPath: path),
   let size = attrs[.size] as? NSNumber {
    fileSize = size.int64Value
}
print("  file size: \(fmt(Double(fileSize) / 1_048_576.0, 2)) MB (\(fileSize) bytes)")

let formatDescriptions = track.formatDescriptions.map { $0 as! CMFormatDescription }
var allHvc1 = !formatDescriptions.isEmpty
var anyAlphaExt = false
for (i, fd) in formatDescriptions.enumerated() {
    let codec = fourCC(CMFormatDescriptionGetMediaSubType(fd))
    if codec != "hvc1" { allHvc1 = false }
    let dims = CMVideoFormatDescriptionGetDimensions(fd)
    var alphaText = "absent"
    if let ext = CMFormatDescriptionGetExtension(fd, extensionKey: kCMFormatDescriptionExtension_ContainsAlphaChannel) {
        if let n = ext as? NSNumber {
            alphaText = n.boolValue ? "true" : "false"
            if n.boolValue { anyAlphaExt = true }
        } else {
            alphaText = "\(ext)"
        }
    }
    var depthText = "absent"
    if let depth = CMFormatDescriptionGetExtension(fd, extensionKey: kCMFormatDescriptionExtension_Depth) as? NSNumber {
        depthText = "\(depth.intValue)"
    }
    print("  formatDescription[\(i)]: codec=\(codec) dims=\(dims.width)x\(dims.height) ContainsAlphaChannel=\(alphaText) Depth=\(depthText)")
}

let naturalSize = track.naturalSize
let nominalFrameRate = track.nominalFrameRate
let assetDuration = asset.duration.seconds
let trackRange = track.timeRange
let hasAlphaCharacteristic = track.hasMediaCharacteristic(.containsAlphaChannel)
let frameCount = countSamples(asset, track)
let trackSeconds = trackRange.duration.seconds
let measuredFps = trackSeconds > 0 ? Double(frameCount) / trackSeconds : 0

print("  size: \(Int(naturalSize.width))x\(Int(naturalSize.height))")
print("  nominalFrameRate: \(fmt(Double(nominalFrameRate))) fps  (frames/duration = \(fmt(measuredFps)) fps)")
print("  frames: \(frameCount)")
print("  duration: asset \(fmt(assetDuration))s, track \(fmt(trackSeconds))s (timescale \(trackRange.duration.timescale), naturalTimeScale \(track.naturalTimeScale))")
print("  alpha: formatDescription ContainsAlphaChannel=\(anyAlphaExt)  AVMediaCharacteristic.containsAlphaChannel=\(hasAlphaCharacteristic)")
if !allHvc1 { print("  WARN: codec is not hvc1") }
if !anyAlphaExt && !hasAlphaCharacteristic { print("  WARN: track does not advertise an alpha channel") }

// MARK: - 解码首/中/末帧

let middleIndex = frameCount / 2
let decoded = decode(asset, track,
                     analyzeIndices: [0, middleIndex], keepAlphaIndices: [],
                     analyzeLast: true, keepLastAlpha: comparePath != nil,
                     stopAfterIndex: nil)
if decoded.decodedCount != frameCount {
    print("  WARN: decoded \(decoded.decodedCount) frames but counted \(frameCount) samples")
}
describe("first ", decoded.stats[0])
describe("middle", decoded.stats[middleIndex])
describe("last  ", decoded.last)

// MARK: - 衔接比较

if let otherPath = comparePath {
    print("== compare: last frame of \(path)  vs  first frame of \(otherPath)")
    let (asset2, track2) = openVideo(otherPath)
    let decoded2 = decode(asset2, track2,
                          analyzeIndices: [0], keepAlphaIndices: [0],
                          analyzeLast: false, keepLastAlpha: false,
                          stopAfterIndex: 0)
    guard let a = decoded.last else { fail("compare: could not decode last frame of \(path)") }
    guard let b = decoded2.stats[0] else { fail("compare: could not decode first frame of \(otherPath)") }
    guard a.width == b.width, a.height == b.height else {
        fail("compare: size mismatch \(a.width)x\(a.height) vs \(b.width)x\(b.height)")
    }
    guard a.alpha.count == b.alpha.count, !a.alpha.isEmpty else { fail("compare: alpha buffers missing") }
    describe("other first", b)

    var sum: UInt64 = 0
    var maxDiff = 0
    var differing = 0
    a.alpha.withUnsafeBufferPointer { pa in
        b.alpha.withUnsafeBufferPointer { pb in
            for k in 0..<pa.count {
                let d = abs(Int(pa[k]) - Int(pb[k]))
                if d != 0 {
                    sum += UInt64(d)
                    differing += 1
                    if d > maxDiff { maxDiff = d }
                }
            }
        }
    }
    let total = Double(a.alpha.count)
    print("  sum|Δalpha|/255 = \(fmt(Double(sum) / 255.0, 2))  (mean |Δalpha| per pixel = \(fmt(Double(sum) / total, 4)))")
    print("  max |Δalpha| = \(maxDiff)  differing pixels = \(differing) (\(fmt(100 * Double(differing) / total, 3))%)")
}

exit(0)
