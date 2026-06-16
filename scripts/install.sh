#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/audio2text.desktop"
BIN_LINK="$HOME/.local/bin/audio2text"

mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/bin"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Audio2Text
Comment=Транскрипція аудіо з визначенням дикторів
Exec=$DIR/audio2text.sh
Type=Application
Categories=Audio;AudioVideo;Utility;
Terminal=false
EOF

chmod +x "$DESKTOP_FILE"
ln -sf "$DIR/audio2text.sh" "$BIN_LINK"

echo "✅ Встановлено!"
echo "   Запуск: audio2text"
echo "   Або знайдіть Audio2Text у меню додатків."
