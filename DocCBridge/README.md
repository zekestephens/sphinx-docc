# libswiftdocc: Native SwiftDocC Bridge

This is the native C ABI bridge to the `SwiftDocC` compiler, allowing us to load `.docc` catalogs, parse them into RenderNodes, and serialize the data in-memory directly back to our Python script.