#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_FILE="$HOME/.local/share/applications/audio2text.desktop"
BIN_LINK="$HOME/.local/bin/audio2text"
MANIFEST="$HOME/.local/share/audio2text/install.manifest"

# ── helpers ──────────────────────────────────────────
die() { echo -e "$1" >&2; exit 1; }
info() { echo -e "$1"; }

# ── language selection ───────────────────────────────
if command -v zenity &>/dev/null; then
  LANG_CHOICE=$(zenity --list --title="Audio2Text Installer" \
    --text="Select language / Оберіть мову" \
    --column="" --column="" \
    --width=400 --height=250 \
    "en" "English" \
    "uk" "Українська" \
    2>/dev/null)
  [ -z "$LANG_CHOICE" ] && exit 1
else
  echo "Select language / Оберіть мову:"
  echo "  en) English"
  echo "  uk) Українська"
  read -r LANG_CHOICE
  [ -z "$LANG_CHOICE" ] && LANG_CHOICE="en"
fi

# ── i18n ─────────────────────────────────────────────
if [ "$LANG_CHOICE" = "uk" ]; then
  T_WELCOME="Встановлення Audio2Text"
  T_NOT_FOUND="audio2text.sh не знайдено"
  T_RUN_FROM="Запустіть скрипт з розпакованої папки Audio2Text"
  T_INSTALL_DIR="Папка встановлення"
  T_DESKTOP="Створити ярлик на робочому столі"
  T_DONE="✅ Встановлено!"
  T_LAUNCH="Запуск: audio2text"
  T_MENU="Або знайдіть у меню додатків"
  T_PATH_HELP="Якщо команда не знайдена, додайте ~/.local/bin до PATH:"
  T_DESKTOP_LINK="Створено ярлик на робочому столі"
  T_CANCEL="Встановлення скасовано"
else
  T_WELCOME="Installing Audio2Text"
  T_NOT_FOUND="audio2text.sh not found"
  T_RUN_FROM="Run this script from the extracted Audio2Text folder"
  T_INSTALL_DIR="Installation directory"
  T_DESKTOP="Create desktop shortcut"
  T_DONE="✅ Installed!"
  T_LAUNCH="Run: audio2text"
  T_MENU="Or find Audio2Text in the applications menu"
  T_PATH_HELP="If command not found, add ~/.local/bin to PATH:"
  T_DESKTOP_LINK="Created desktop shortcut"
  T_CANCEL="Installation cancelled"
fi

# ── checks ───────────────────────────────────────────
if [ ! -f "$DIR/audio2text.sh" ]; then
  die "$T_NOT_FOUND $DIR\n$T_RUN_FROM."
fi

# ── install dir ──────────────────────────────────────
INSTALL_DIR="$DIR"
if command -v zenity &>/dev/null; then
  INSTALL_DIR=$(zenity --file-selection --directory \
    --title="$T_INSTALL_DIR" --filename="$DIR/" 2>/dev/null)
  [ -z "$INSTALL_DIR" ] && die "$T_CANCEL"
fi

# ── desktop shortcut ─────────────────────────────────
DO_DESKTOP=false
if command -v zenity &>/dev/null; then
  zenity --question --title="Audio2Text" --text="$T_DESKTOP?" \
    --width=350 2>/dev/null && DO_DESKTOP=true
else
  echo -n "$T_DESKTOP? [y/N]: "; read -r ans
  [[ "$ans" =~ ^[yY] ]] && DO_DESKTOP=true
fi

# ── do install ───────────────────────────────────────
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/share/audio2text"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Audio2Text
Comment=Transcribe audio to text with WhisperX
Exec=$INSTALL_DIR/audio2text.sh
Path=$INSTALL_DIR
Type=Application
Categories=Audio;AudioVideo;Utility;
Terminal=false
EOF

chmod +x "$DESKTOP_FILE"
ln -sf "$INSTALL_DIR/audio2text.sh" "$BIN_LINK"

# ── desktop shortcut ─────────────────────────────────
if [ "$DO_DESKTOP" = true ]; then
  DESKTOP_LINK="$HOME/Desktop/audio2text.desktop"
  cp "$DESKTOP_FILE" "$DESKTOP_LINK"
  chmod +x "$DESKTOP_LINK"
  info "$T_DESKTOP_LINK: $DESKTOP_LINK"
fi

# ── manifest ─────────────────────────────────────────
cat > "$MANIFEST" << EOF
install_dir=$INSTALL_DIR
desktop_file=$DESKTOP_FILE
bin_link=$BIN_LINK
config_dir=$HOME/.config/audio2text
cache_dir=$HOME/.cache/audio2text
EOF
if [ "$DO_DESKTOP" = true ]; then
  echo "desktop_link=$HOME/Desktop/audio2text.desktop" >> "$MANIFEST"
fi

# ── done ─────────────────────────────────────────────
info ""
info "$T_DONE"
info "   $T_LAUNCH"
info "   $T_MENU"
info ""
info "$T_PATH_HELP"
info "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
info "  source ~/.bashrc"
info ""
info "To uninstall: bash $DIR/uninstall.sh"
