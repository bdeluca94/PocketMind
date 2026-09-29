#!/usr/bin/env bash
# Creates a Desktop shortcut for PocketMind. Run this directly — it doesn't
# need Python or the app's virtual environment, so it works even before
# you've ever launched PocketMind itself.
cd "$(dirname "$0")"

DESKTOP="$HOME/Desktop"
if [ ! -d "$DESKTOP" ]; then
    echo
    echo "Couldn't find a Desktop folder on this Mac ($DESKTOP)."
    echo
    read -p "Press Enter to close..."
    exit 1
fi

if [ -f "./PocketMind" ]; then
    TARGET="$(pwd)/PocketMind"
else
    TARGET="$(pwd)/launch_macos.command"
fi

SHORTCUT="$DESKTOP/PocketMind.command"
cat > "$SHORTCUT" <<EOF
#!/usr/bin/env bash
exec "$TARGET"
EOF
chmod +x "$SHORTCUT"

# A plain shell script has no built-in "icon" the way a Windows .lnk does,
# so Finder would otherwise show it with a generic script icon. This sets
# a custom Finder icon directly from the PNG (no .icns/iconutil needed, so
# it works even on a Mac without Xcode's command line tools) using the same
# technique as dragging an image onto a file's Get Info icon well. Best
# effort: if osascript or AppKit isn't available for some reason, the
# shortcut still works fine, just without the custom icon.
ICON_SRC="$(pwd)/assets/icon_master.png"
if command -v osascript >/dev/null 2>&1 && [ -f "$ICON_SRC" ]; then
    osascript <<OSA >/dev/null 2>&1
use framework "AppKit"
use scripting additions
set srcImg to current application's NSImage's alloc()'s initWithContentsOfFile:"$ICON_SRC"
current application's NSWorkspace's sharedWorkspace()'s setIcon:srcImg forFile:"$SHORTCUT" options:0
OSA
fi

if [ -f "$SHORTCUT" ]; then
    echo
    echo "Done! A PocketMind shortcut is now on your Desktop."
    echo
    echo "Two things worth knowing:"
    echo " - It points at this drive, so it only works while the drive is"
    echo "   plugged in. Run this file again any time to fix or recreate it."
    echo " - The first time you double-click it, macOS may warn that it's"
    echo "   from an unidentified developer (the same warning the drive's"
    echo "   own launcher shows). Right-click the shortcut and choose Open"
    echo "   once to clear that — it won't ask again after."
    echo
else
    echo
    echo "Couldn't create the shortcut. You can also just drag"
    echo "launch_macos.command to your Desktop yourself instead, holding"
    echo "Option+Command while you drag to make it an alias rather than a copy."
    echo
fi

read -p "Press Enter to close..."
