// swift-tools-version: 6.2

import PackageDescription

let package = Package(
  name: "DocCBridge",
  platforms: [
        .macOS(.v13),
  ],
  products: [
    .library(
      name: "DocCBridge",
      type: .dynamic,
      targets: ["DocCBridge"],
    ),
  ],
  dependencies: [
    .package(url: "https://github.com/swiftlang/swift-docc.git", branch: "main"),
  ],
  targets: [
    .target(
      name: "DocCBridge",
      dependencies: [
        .product(name: "SwiftDocC", package: "swift-docc")
      ],
      swiftSettings: [
          .unsafeFlags(["-package-name", "SwiftDocC"])
      ]
    ),
  ]
)
