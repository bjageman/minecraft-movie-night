# Minecraft Movie Night

A Fabric Minecraft server running [PixelReel](https://github.com/Samarth-programming/PixelReel), with an optional updater that displays current and upcoming ErsatzTV programming in game.

## Setup

1. Copy `.env.example` to `.env` and set your domain and email address.
2. Ensure the external Docker network named `nginx-proxy` exists, or update `docker-compose.yml` for your network.
3. Start the server:

   ```bash
   docker compose up -d
   ```

Minecraft runtime data is written to `data/` and is intentionally excluded from Git because it contains world saves, player data, generated files, and credentials.

## Now-playing updater

Edit `now_playing_config.json` for your ErsatzTV URL, Minecraft container, sign coordinates, and text-display tags. Displays sharing a tag are updated together.

To run one update manually:

```bash
./update_now_playing.py once
```

For continuous operation, edit the paths and user in `minecraft-now-playing.service`, copy it to `/etc/systemd/system/`, and enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now minecraft-now-playing.service
```
