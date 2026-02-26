import Foundation
@testable import SwiftDocC

public typealias DocCCallback = @convention(c) @Sendable (Int32, UnsafePointer<CChar>?) -> Void

/// A custom consumer that serializes RenderNodes to JSON and passes them to a C callback.
class InMemoryConsumer: ConvertOutputConsumer, ExternalNodeConsumer {
    let callback: DocCCallback
    let encoder = JSONEncoder()

    init(callback: @escaping DocCCallback) {
        self.callback = callback
    }

    func consume(renderNode: RenderNode) throws {
        let data = try encoder.encode(renderNode)
        if let jsonString = String(data: data, encoding: .utf8) {
            jsonString.withCString { cString in
                // type 0 = render node JSON
                callback(0, cString)
            }
        }
    }

    func consume(externalRenderNode: ExternalRenderNode) throws {
        // We can ignore or serialize external render nodes just like regular ones.
        // For docutils, we typically only care about the main nodes.
    }

    // Unused by us, but required by protocol
    func consume(assetsInBundle bundle: DocumentationBundle) throws {}
    func consume(linkableElementSummaries: [LinkDestinationSummary]) throws {}
    func consume(indexingRecords: [IndexingRecord]) throws {}
    func consume(assets: [RenderReferenceType : [any RenderReference]]) throws {}
    func consume(benchmarks: Benchmark) throws {}
    func consume(documentationCoverageInfo: [CoverageDataEntry]) throws {}
}

@_cdecl("parse_docc_catalog")
public func parse_docc_catalog(_ path: UnsafePointer<CChar>, _ callback: @escaping DocCCallback) {
    let catalogPath = String(cString: path)
    let url = URL(fileURLWithPath: catalogPath)
    let semaphore = DispatchSemaphore(value: 0)
    
    Task {
        do {
            let fileManager = FileManager.default
            
            // 1. Discover inputs using SwiftDocC package APIs
            let (bundle, dataProvider) = try DocumentationContext.InputsProvider(fileManager: fileManager)
                .inputsAndDataProvider(
                    startingPoint: url,
                    allowArbitraryCatalogDirectories: true,
                    options: .init()
                )
            
            // 2. Build configuration & context
            let configuration = DocumentationContext.Configuration()
            let diagnosticEngine = DiagnosticEngine(filterLevel: .information)
            let context = try await DocumentationContext(
                bundle: bundle,
                dataProvider: dataProvider,
                diagnosticEngine: diagnosticEngine,
                configuration: configuration
            )
            
            // 3. Convert natively in-memory!
            let consumer = InMemoryConsumer(callback: callback)
            try await ConvertActionConverter.convert(
                context: context,
                outputConsumer: consumer,
                htmlContentConsumer: nil, // Only converting to RenderNodes
                sourceRepository: nil,
                emitDigest: false,
                documentationCoverageOptions: DocumentationCoverageOptions(level: .none)
            )
            
            // Success: type 2 indicates complete
            callback(2, nil)

        } catch {
            // Error: type 1 indicates failure
            let errorString = String(describing: error)
            errorString.withCString { cString in
                callback(1, cString)
            }
        }
        semaphore.signal()
    }
    
    semaphore.wait()
}
