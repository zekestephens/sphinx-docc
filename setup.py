import os
import sys
import subprocess
import shutil
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext

class SwiftExtension(Extension):
    def __init__(self, name, sourcedir=""):
        super().__init__(name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)

class SwiftBuildExt(build_ext):
    def run(self):
        try:
            subprocess.check_output(["swift", "--version"])
        except OSError:
            raise RuntimeError(
                "Swift must be installed to build the following extensions: " +
                ", ".join(e.name for e in self.extensions)
            )

        for ext in self.extensions:
            if isinstance(ext, SwiftExtension):
                self.build_extension(ext)
            else:
                super().build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))
        
        # Determine architecture for macOS
        archs = []
        if sys.platform == "darwin":
            # cibuildwheel sets ARCHFLAGS on macOS e.g. "-arch arm64" or "-arch x86_64"
            archflags = os.environ.get("ARCHFLAGS", "")
            if "-arch arm64" in archflags:
                archs.append("arm64")
            elif "-arch x86_64" in archflags:
                archs.append("x86_64")
            else:
                import platform
                machine = platform.machine()
                archs.append("arm64" if machine == "arm64" else "x86_64")

        # Configure the swift build command
        build_cmd = ["swift", "build", "-c", "release", "-Xswiftc", "-enable-testing"]
        for arch in archs:
            build_cmd.extend(["--arch", arch])
        
        print(f"Building Swift extension {ext.name} in {ext.sourcedir}")
        print(f"Command: {' '.join(build_cmd)}")
        
        # Build the Swift project
        subprocess.check_call(build_cmd, cwd=ext.sourcedir)
        
        # Determine the name of the resulting dynamic library
        # By default, Swift Package Manager on macOS makes lib<Target>.dylib
        # and on Linux makes lib<Target>.so
        lib_name = "DocCBridge"
        if sys.platform == "darwin":
            dylib_name = f"lib{lib_name}.dylib"
        else:
            dylib_name = f"lib{lib_name}.so"
            
        # The build output directory depends on architecture and OS
        # `swift build --show-bin-path` is the most reliable way to find it
        bin_path = subprocess.check_output(build_cmd + ["--show-bin-path"], cwd=ext.sourcedir).decode("utf-8").strip()
        swift_lib_path = os.path.join(bin_path, dylib_name)
        
        if not os.path.exists(swift_lib_path):
            raise RuntimeError(f"Swift build succeeded, but library was not found at {swift_lib_path}")

        # The extension directory must exist
        os.makedirs(extdir, exist_ok=True)
        
        # Copy the Swift library to the python extension location
        dest_path = os.path.join(extdir, dylib_name)
        print(f"Copying {swift_lib_path} -> {dest_path}")
        shutil.copy2(swift_lib_path, dest_path)

setup(
    ext_modules=[SwiftExtension("docc_parser.libDocCBridge", "DocCBridge")],
    cmdclass={"build_ext": SwiftBuildExt},
)
