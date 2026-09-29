#!/usr/bin/env bash
# Creates a Desktop shortcut for PocketMind. Run this directly — it doesn't
# need Python or the app's virtual environment, so it works even before
# you've ever launched PocketMind itself.
cd "$(dirname "$0")"

DESKTOP="$HOME/Desktop"
if [ ! -d "$DESKTOP" ]; then
    echo
    echo "Couldn't find a Desktop folder on this computer ($DESKTOP)."
    echo
    read -p "Press Enter to close..."
    exit 1
fi

if [ -f "./PocketMind" ]; then
    TARGET="$(pwd)/PocketMind"
else
    TARGET="$(pwd)/launch_linux.sh"
fi

SHORTCUT="$DESKTOP/PocketMind.desktop"
cat > "$SHORTCUT" <<EOF
[Desktop Entry]
Type=Application
Name=PocketMind
Exec="$TARGET"
Path=$(pwd)
Icon=$(pwd)/assets/icon_256.png
Terminal=true
EOF
chmod +x "$SHORTCUT"

if [ -f "$SHORTCUT" ]; then
    echo
    echo "Done! A PocketMind shortcut is now on your Desktop."
    echo
    echo "Two things worth knowing:"
    echo " - It points at this drive, so it only works while the drive is"
    echo "   plugged in. Run this file again any time to fix or recreate it."
    echo " - Some desktop environments (GNOME, etc.) show a one-time"
    echo "   'Trust and Launch' or 'Allow Launching' prompt the first time"
    echo "   you double-click a new .desktop file. That's normal — accept it"
    echo "   once and it won't ask again."
    echo
else
    echo
    echo "Couldn't create the shortcut. You can also just right-click"
    echo "launch_linux.sh and create a launcher/shortcut from it yourself,"
    echo "using whatever your file manager offers for that."
    echo
fi

read -p "Press Enter to close..."
