.PHONY: build clean

# By default, we build the release target
build:
	@echo "Building libswiftdocc with testing enabled..."
	swift build -c release -Xswiftc -enable-testing

# Cleaning up the build directory
clean:
	@echo "Cleaning libswiftdocc..."
	swift package clean
