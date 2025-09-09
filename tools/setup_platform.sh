#!/bin/bash

# Setup script for platform-specific development
# Creates symlinks and sets up development environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CORE_PATH="$PROJECT_ROOT/core"

echo "🔧 SSTV Decoder Platform Setup"
echo "=============================="

# Check if core directory exists
if [ ! -d "$CORE_PATH" ]; then
    echo "❌ Error: Core directory not found at $CORE_PATH"
    exit 1
fi

# Function to create symlink safely
create_symlink() {
    local target="$1"
    local link="$2"
    local platform="$3"
    
    if [ -L "$link" ]; then
        echo "✅ Symlink already exists: $link"
    elif [ -e "$link" ]; then
        echo "⚠️  Path exists but is not a symlink: $link"
        echo "   Please remove it manually and run this script again"
    else
        echo "🔗 Creating symlink: $link -> $target"
        ln -s "$target" "$link"
        echo "✅ Created symlink for $platform platform"
    fi
}

# Function to setup platform
setup_platform() {
    local platform="$1"
    local platform_dir="$PROJECT_ROOT/platforms/$platform"
    
    echo ""
    echo "Setting up $platform platform..."
    echo "--------------------------------"
    
    if [ ! -d "$platform_dir" ]; then
        echo "⚠️  Platform directory not found: $platform_dir"
        echo "   Skipping $platform platform"
        return
    fi
    
    # Create core symlink
    create_symlink "$CORE_PATH" "$platform_dir/core" "$platform"
    
    # Platform-specific setup
    case "$platform" in
        "swift")
            echo "📱 Swift platform setup:"
            if command -v swift >/dev/null 2>&1; then
                echo "   ✅ Swift compiler found"
                cd "$platform_dir"
                if swift package resolve; then
                    echo "   ✅ Swift dependencies resolved"
                else
                    echo "   ⚠️  Failed to resolve Swift dependencies"
                fi
            else
                echo "   ⚠️  Swift compiler not found"
            fi
            ;;
        "windows")
            echo "🪟 Windows platform setup:"
            echo "   Note: Use 'mklink /D core ..\\..\\core' on Windows"
            ;;
        "linux")
            echo "🐧 Linux platform setup:"
            if command -v cmake >/dev/null 2>&1; then
                echo "   ✅ CMake found"
            else
                echo "   ⚠️  CMake not found"
            fi
            ;;
        "web")
            echo "🌐 Web platform setup:"
            if command -v npm >/dev/null 2>&1; then
                echo "   ✅ npm found"
                cd "$platform_dir"
                if [ -f "package.json" ] && npm install; then
                    echo "   ✅ npm dependencies installed"
                else
                    echo "   ⚠️  Failed to install npm dependencies"
                fi
            else
                echo "   ⚠️  npm not found"
            fi
            ;;
    esac
}

# Check Python dependencies for core
echo "🐍 Checking Python core dependencies..."
echo "-------------------------------------"

if command -v python3 >/dev/null 2>&1; then
    echo "✅ Python 3 found"
    
    # Check if we can import the core module
    cd "$CORE_PATH/python"
    if python3 -c "import sstv_engine; print('✅ Core module can be imported')" 2>/dev/null; then
        echo "✅ Core SSTV engine is ready"
    else
        echo "⚠️  Core dependencies not installed"
        echo "   Install with: pip install -r $CORE_PATH/python/requirements.txt"
    fi
else
    echo "❌ Python 3 not found"
    echo "   Please install Python 3.8 or later"
fi

# Setup platforms
if [ $# -eq 0 ]; then
    # Setup all platforms
    echo ""
    echo "🚀 Setting up all platforms..."
    echo "============================="
    
    for platform in swift windows linux web; do
        setup_platform "$platform"
    done
else
    # Setup specific platforms
    for platform in "$@"; do
        setup_platform "$platform"
    done
fi

echo ""
echo "🎉 Platform setup complete!"
echo "=========================="
echo ""
echo "Next steps:"
echo "1. Install Python dependencies: pip install -r core/python/requirements.txt"
echo "2. Test core engine: python -m sstv_engine.cli decode --help"
echo "3. Choose your platform and start developing:"
echo "   - Swift: cd platforms/swift && swift build"
echo "   - Windows: cd platforms/windows && build with Visual Studio"
echo "   - Linux: cd platforms/linux && cmake . && make"
echo "   - Web: cd platforms/web && npm run dev"
echo ""
echo "📚 See README_MULTI_AGENT.md for detailed development instructions"