#!/usr/bin/env bash

set -euo pipefail

REPOSITORY="bjageman/minecraft-movie-night"
WORLD_ARCHIVE="minecraft-movie-night-world.tar.gz"
INSTALL_SERVICE=false

usage() {
    echo "Usage: $0 [--install-service]"
    echo
    echo "  --install-service  Install and enable the now-playing systemd service."
}

for argument in "$@"; do
    case "$argument" in
        --install-service)
            INSTALL_SERVICE=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $argument" >&2
            usage >&2
            exit 2
            ;;
    esac
done

for command in docker gh tar; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "Required command not found: $command" >&2
        exit 1
    fi
done

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required." >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
    domain_value=${DOMAIN:-}
    email_value=${EMAIL:-}

    if [ -z "$domain_value" ]; then
        read -r -p "Public domain (for example, example.com): " domain_value
    fi
    if [ -z "$email_value" ]; then
        read -r -p "Let's Encrypt email: " email_value
    fi
    if [ -z "$domain_value" ] || [ -z "$email_value" ]; then
        echo "Domain and email cannot be empty." >&2
        exit 1
    fi

    printf 'DOMAIN=%s\nEMAIL=%s\n' "$domain_value" "$email_value" >.env
    chmod 600 .env
    echo "Created .env."
else
    echo "Keeping existing .env."
fi

mkdir -p data/config

if [ ! -f data/server.properties ]; then
    install -m 0644 examples/server.properties data/server.properties
    echo "Installed the server.properties template."
else
    echo "Keeping existing data/server.properties."
fi

if [ ! -f data/config/pixelreel.json ]; then
    install -m 0644 examples/pixelreel.json data/config/pixelreel.json
    echo "Installed the PixelReel configuration template."
else
    echo "Keeping existing data/config/pixelreel.json."
fi

if [ ! -e data/world ]; then
    download_dir=$(mktemp -d /tmp/minecraft-movie-night.XXXXXX)
    trap 'rm -rf -- "$download_dir"' EXIT
    gh release download --repo "$REPOSITORY" --pattern "$WORLD_ARCHIVE" --dir "$download_dir"
    tar -xzf "$download_dir/$WORLD_ARCHIVE" -C data
    echo "Installed the theater world."
    rm -rf -- "$download_dir"
    trap - EXIT
else
    echo "Keeping existing data/world."
fi

if ! docker network inspect nginx-proxy >/dev/null 2>&1; then
    docker network create nginx-proxy >/dev/null
    echo "Created the nginx-proxy Docker network."
fi

docker compose up -d

if [ "$INSTALL_SERVICE" = true ]; then
    service_file=$(mktemp /tmp/minecraft-now-playing.XXXXXX.service)
    trap 'rm -f -- "$service_file"' EXIT
    current_user=$(id -un)

    cat >"$service_file" <<EOF
[Unit]
Description=Minecraft Now Playing Board Updater
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=$current_user
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/update_now_playing.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo install -m 0644 "$service_file" /etc/systemd/system/minecraft-now-playing.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now minecraft-now-playing.service
    rm -f -- "$service_file"
    trap - EXIT
    echo "Installed and started minecraft-now-playing.service."
fi

echo
echo "Installation complete."
echo "Review data/config/pixelreel.json, then run 'docker compose restart mc' after changes."
echo "Follow server startup with 'docker compose logs -f mc'."
