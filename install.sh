#!/bin/bash
# Everything Indexer - Installation Script
# Run this script to install Everything Indexer on your system

set -e  # Exit on error

echo "========================================="
echo "Everything Indexer Installation"
echo "========================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "Warning: It's recommended to install as a regular user, not as root."
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 1
    fi
fi

# Check for Python3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 is not installed!"
    echo "Please install Python3 first:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-tk"
    echo "  Fedora: sudo dnf install python3 python3-tkinter"
    echo "  Arch: sudo pacman -S python tk"
    exit 1
fi

# Check for Tkinter
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "ERROR: Tkinter is not installed!"
    echo "Please install Tkinter:"
    echo "  Ubuntu/Debian: sudo apt install python3-tk"
    echo "  Fedora: sudo dnf install python3-tkinter"
    echo "  Arch: sudo pacman -S tk"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Everything Indexer"

echo "Installing $APP_NAME..."

# Create necessary directories
echo "Creating application directories..."
mkdir -p ~/.local/bin
mkdir -p ~/.local/share/applications
mkdir -p ~/.local/share/icons

# Copy icon
echo "Installing icon..."
if [ -f "$SCRIPT_DIR/icon.png" ]; then
    cp "$SCRIPT_DIR/icon.png" ~/.local/share/icons/everything-indexer.png
else
    echo "Warning: icon.png not found in $SCRIPT_DIR"
    echo "Using generic icon instead..."
    # You can add a fallback icon creation here if needed
fi

# Make wrapper script executable and copy it
echo "Installing executable..."
if [ -f "$SCRIPT_DIR/everything-indexer" ]; then
    chmod +x "$SCRIPT_DIR/everything-indexer"
    cp "$SCRIPT_DIR/everything-indexer" ~/.local/bin/
else
    echo "Creating wrapper script..."
    cat > ~/.local/bin/everything-indexer << 'EOF'
#!/bin/bash
# Wrapper script for Everything Indexer
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIN_SCRIPT="$(dirname "$SCRIPT_DIR")/EverythingIndexer/indexer.py"
if [ -f "$MAIN_SCRIPT" ]; then
    python3 "$MAIN_SCRIPT" "$@"
else
    # Try to find it in current directory
    if [ -f "./indexer.py" ]; then
        python3 "./indexer.py" "$@"
    else
        echo "Error: Could not find indexer.py"
        echo "Please run this from the EverythingIndexer directory"
        exit 1
    fi
fi
EOF
    chmod +x ~/.local/bin/everything-indexer
fi

# Create desktop entry
echo "Creating desktop entry..."
cat > ~/.local/share/applications/everything-indexer.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Everything Indexer
Comment=Search files like Everything for Windows - Matrix Theme
Exec=$HOME/.local/bin/everything-indexer
Icon=everything-indexer
Terminal=false
Categories=Utility;FileTools;Office;
StartupWMClass=EverythingIndexer
Keywords=search;file;finder;everything;index
EOF

# Add ~/.local/bin to PATH if not already there
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Adding ~/.local/bin to your PATH..."
    if [ -f "$HOME/.bashrc" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
    if [ -f "$HOME/.zshrc" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
    fi
    if [ -f "$HOME/.profile" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi

# Update desktop database
echo "Updating desktop database..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications
fi

echo ""
echo "========================================="
echo "Installation Complete!"
echo "========================================="
echo ""
echo "$APP_NAME has been installed successfully!"
echo ""
echo "You can now:"
echo "1. Run from terminal: everything-indexer"
echo "2. Find it in your application menu under 'Utilities'"
echo ""
echo "To uninstall, run: ./uninstall.sh"
echo ""
echo "Note: If the app doesn't appear in your menu immediately,"
echo "you may need to log out and log back in."
echo ""
