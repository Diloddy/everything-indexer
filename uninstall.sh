#!/bin/bash
# Everything Indexer - Uninstallation Script

set -e  # Exit on error

echo "========================================="
echo "Everything Indexer Uninstallation"
echo "========================================="

echo "Removing Everything Indexer..."

# Remove files
echo "Removing executable..."
rm -f ~/.local/bin/everything-indexer

echo "Removing desktop entry..."
rm -f ~/.local/share/applications/everything-indexer.desktop

echo "Removing icon..."
rm -f ~/.local/share/icons/everything-indexer.png

# Remove application data (optional - ask user)
echo ""
read -p "Remove all application data and indexes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Removing application data..."
    rm -rf ~/.local/share/everything-indexer
    rm -rf ~/.config/everything-indexer
    echo "All data has been removed."
else
    echo "Application data preserved at:"
    echo "  ~/.local/share/everything-indexer/"
    echo "  ~/.config/everything-indexer/"
fi

# Update desktop database
echo "Updating desktop database..."
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications
fi

echo ""
echo "========================================="
echo "Uninstallation Complete!"
echo "========================================="
echo ""
echo "Everything Indexer has been removed."
echo "You may need to log out and log back in for"
echo "the application menu to update completely."
echo ""
