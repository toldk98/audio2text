#!/bin/bash
set -e

MANIFEST="$HOME/.local/share/audio2text/install.manifest"

# ── helpers ──────────────────────────────────────────
die() { echo -e "$1" >&2; exit 1; }
info() { echo -e "$1"; }

# ── language ─────────────────────────────────────────
if command -v zenity &>/dev/null; then
  LANG_CHOICE=$(zenity --list --title="Audio2Text Uninstaller" \
    --text="Select language / Оберіть мову" \
    --column="" --column="" \
    --width=400 --height=250 \
    "en" "English" \
    "uk" "Українська" 2>/dev/null)
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
  T_TITLE="Видалення Audio2Text"
  T_CONFIRM="Ви дійсно хочете видалити Audio2Text?"
  T_DONE="✅ Audio2Text видалено"
  T_CACHE="Видалити кеш моделей Whisper? (~3 GB)"
  T_CACHE_DEL="Кеш моделей видалено"
  T_CACHE_KEEP="Кеш моделей збережено"
  T_CANCEL="Видалення скасовано"
  T_NO_MANIFEST="Не знайдено даних про встановлення. Можливо, програму вже видалено."
  T_REMOVED="Видалено:"
else
  T_TITLE="Uninstalling Audio2Text"
  T_CONFIRM="Are you sure you want to uninstall Audio2Text?"
  T_DONE="✅ Audio2Text uninstalled"
  T_CACHE="Delete Whisper model cache? (~3 GB)"
  T_CACHE_DEL="Model cache deleted"
  T_CACHE_KEEP="Model cache kept"
  T_CANCEL="Uninstall cancelled"
  T_NO_MANIFEST="No installation data found. The program may have already been removed."
  T_REMOVED="Removed:"
fi

# ── confirm ──────────────────────────────────────────
if command -v zenity &>/dev/null; then
  zenity --question --title="$T_TITLE" --text="$T_CONFIRM" \
    --width=350 2>/dev/null || exit 1
else
  echo "$T_CONFIRM [y/N]: "
  read -r ans
  [[ ! "$ans" =~ ^[yY] ]] && exit 1
fi

# ── remove from manifest ─────────────────────────────
REMOVED=()
if [ -f "$MANIFEST" ]; then
  source "$MANIFEST"
  [ -f "$desktop_file" ] && rm -f "$desktop_file" && REMOVED+=("$desktop_file")
  [ -f "$bin_link" ] && rm -f "$bin_link" && REMOVED+=("$bin_link")
  [ -f "$desktop_link" ] && rm -f "$desktop_link" && REMOVED+=("$desktop_link")
  [ -d "$config_dir" ] && rm -rf "$config_dir" && REMOVED+=("$config_dir (config)")
  rm -f "$MANIFEST"
  rm -rf "$HOME/.local/share/audio2text"
  REMOVED+=("$HOME/.local/share/audio2text")
fi

# ── remove from common locations (fallback) ──────────
[ -f "$HOME/.local/share/applications/audio2text.desktop" ] && \
  rm -f "$HOME/.local/share/applications/audio2text.desktop" && \
  REMOVED+=("$HOME/.local/share/applications/audio2text.desktop")
[ -f "$HOME/.local/bin/audio2text" ] && \
  rm -f "$HOME/.local/bin/audio2text" && \
  REMOVED+=("$HOME/.local/bin/audio2text")
[ -f "$HOME/Desktop/audio2text.desktop" ] && \
  rm -f "$HOME/Desktop/audio2text.desktop" && \
  REMOVED+=("$HOME/Desktop/audio2text.desktop")

info ""
for r in "${REMOVED[@]}"; do
  info "  $T_REMOVED $r"
done

# ── ask about cache ──────────────────────────────────
if command -v zenity &>/dev/null; then
  zenity --question --title="$T_TITLE" --text="$T_CACHE" \
    --width=350 2>/dev/null && DO_CACHE=true || DO_CACHE=false
else
  echo -n "$T_CACHE [y/N]: "
  read -r ans
  [[ "$ans" =~ ^[yY] ]] && DO_CACHE=true || DO_CACHE=false
fi

if [ "$DO_CACHE" = true ]; then
  rm -rf "$HOME/.cache/whisper" "$HOME/.cache/audio2text"
  info "  $T_CACHE_DEL"
else
  info "  $T_CACHE_KEEP"
fi

# ── done ─────────────────────────────────────────────
info ""
info "$T_DONE"
