#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_DIR="$DIR/audio2text-env"

if [ ! -d "$ENV_DIR" ]; then
    echo "Розпакування середовища..."
    mkdir -p "$ENV_DIR"
    tar -xzf "$DIR/audio2text-env.tar.gz" -C "$ENV_DIR"
fi

source "$ENV_DIR/bin/activate"
python "$DIR/main.py" "$@"
