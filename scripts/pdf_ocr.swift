import CoreGraphics
import Foundation
import PDFKit
import Vision

struct OCRPage: Encodable {
    let page: Int
    let text: String
    let error: String?
}

func emit(_ value: OCRPage) {
    let data = try! JSONEncoder().encode(value)
    print(String(data: data, encoding: .utf8)!)
}

let arguments = CommandLine.arguments
guard arguments.count >= 2 else {
    fputs("usage: pdf_ocr.swift <pdf-path> [start-page] [end-page]\n", stderr)
    exit(2)
}

let fileURL = URL(fileURLWithPath: arguments[1])
let startPage = max(1, Int(arguments.dropFirst(2).first ?? "1") ?? 1)
let requestedEndPage = Int(arguments.dropFirst(3).first ?? "0") ?? 0

guard let document = PDFDocument(url: fileURL) else {
    emit(OCRPage(page: 0, text: "", error: "无法打开 PDF"))
    exit(1)
}

let endPage = min(document.pageCount, requestedEndPage > 0 ? requestedEndPage : document.pageCount)
for pageNumber in startPage...endPage {
    autoreleasepool {
        guard let page = document.page(at: pageNumber - 1) else {
            emit(OCRPage(page: pageNumber, text: "", error: "无法读取页面"))
            return
        }

        let bounds = page.bounds(for: .mediaBox)
        let scale: CGFloat = 2.0
        let width = Int(bounds.width * scale)
        let height = Int(bounds.height * scale)
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(
                data: nil,
                width: width,
                height: height,
                bitsPerComponent: 8,
                bytesPerRow: width * 4,
                space: colorSpace,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
              ) else {
            emit(OCRPage(page: pageNumber, text: "", error: "无法创建页面图像"))
            return
        }

        context.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.saveGState()
        context.scaleBy(x: scale, y: scale)
        page.draw(with: .mediaBox, to: context)
        context.restoreGState()

        guard let image = context.makeImage() else {
            emit(OCRPage(page: pageNumber, text: "", error: "无法生成页面图像"))
            return
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.recognitionLanguages = ["zh-Hans", "en-US"]
        request.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
            let observations = request.results ?? []
            let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
            emit(OCRPage(page: pageNumber, text: text, error: nil))
        } catch {
            emit(OCRPage(page: pageNumber, text: "", error: error.localizedDescription))
        }
    }
}
