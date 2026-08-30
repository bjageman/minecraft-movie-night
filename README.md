# Minecraft Movie Night

A Fabric Minecraft 1.21.1 server running [PixelReel](https://github.com/Samarth-programming/PixelReel). An optional Python service reads ErsatzTV's XMLTV feed and updates in-game signs and text displays with current and upcoming programming.

## What you need

- Docker Engine with the Compose plugin
- An existing ErsatzTV server and XMLTV feed
- A reverse proxy if players outside your network will use the PixelReel media proxy
- Python 3.9 or newer for the now-playing updater
- A Minecraft Java Edition 1.21.1 client with Fabric Loader, Fabric API, and PixelReel installed

## Quick install

Clone the repository and run the installer:

```bash
git clone https://github.com/bjageman/minecraft-movie-night.git
cd minecraft-movie-night
./install.sh
```

The installer prompts for the domain and Let's Encrypt email, installs sanitized configuration templates, downloads the theater world, creates the `nginx-proxy` Docker network if needed, and starts Minecraft.

To also install the continuous now-playing updater as a systemd service:

```bash
./install.sh --install-service
```

The script is safe to rerun: it keeps existing environment, configuration, and world files.

Before starting, review `docker-compose.yml` if you need to change the operator names, memory limit, ports, reverse-proxy settings, or Docker network.

Minecraft creates its world, generated configuration, credentials, and logs under `data/`. That directory is intentionally excluded from Git.

## Install the included world

The world is distributed as a GitHub release asset instead of being committed directly. Minecraft region files change during normal play; keeping them out of Git avoids a dirty working tree and rapidly growing binary history.

The installer downloads and extracts it automatically. For a manual installation, stop Minecraft before replacing the world:

```bash
docker compose down
curl -LO https://github.com/bjageman/minecraft-movie-night/releases/latest/download/minecraft-movie-night-world.tar.gz
mkdir -p data
tar -xzf minecraft-movie-night-world.tar.gz -C data
rm minecraft-movie-night-world.tar.gz
```

The archive excludes player inventories, player locations, advancements, statistics, and session locks. The constructed world, entities, datapacks, dimensions, and world settings are included.

## Configure PixelReel

After the first server start, edit:

```text
data/config/pixelreel.json
```

Sanitized server and PixelReel templates are available under `examples/`. To use them as a starting point:

```bash
mkdir -p data/config
cp examples/server.properties data/server.properties
cp examples/pixelreel.json data/config/pixelreel.json
```

Set the ErsatzTV endpoints and public media-proxy address for your environment. For example:

```json
{
    "m3uUrl": "http://ersatztv:8409/iptv/channels.m3u",
    "xmltvUrl": "http://ersatztv:8409/iptv/xmltv.xml",
    "mediaProxyPublicHost": "https://movies.example.com:443"
}
```

Restart Minecraft after changing the PixelReel configuration:

```bash
docker compose restart mc
```

Do not commit `data/config/pixelreel.json`; it can contain private media-server tokens.

## Install the client mods

Each player needs the Minecraft 1.21.1 Fabric profile and these matching mods:

- Fabric API `0.116.15+1.21.1`
- PixelReel `2.0.0` for Minecraft 1.21.1

Place both JARs in the client's Minecraft `mods` directory. PixelReel also uses VLC for media playback, so install VLC on each client computer.

## Configure the now-playing displays

Edit `now_playing_config.json` and set `ersatztv_url` to an address reachable from the host running the updater.

The updater supports three display types:

- `signs`: normal block signs identified by dimension and coordinates
- `text_displays`: text-display entities showing the current program
- `schedule_displays`: text-display entities showing current and upcoming programs

### Tag text displays

Create or select a text-display entity in Minecraft, then add the tag used in `now_playing_config.json`. For example:

```mcfunction
/tag @e[type=minecraft:text_display,sort=nearest,limit=1] add now_playing_chan_1
```

For another channel:

```mcfunction
/tag @e[type=minecraft:text_display,sort=nearest,limit=1] add now_playing_chan_16
```

For the combined schedule board:

```mcfunction
/tag @e[type=minecraft:text_display,sort=nearest,limit=1] add single_schedule_board
```

Multiple displays can share a tag. Every display with that tag will update together.

### Test one update

Run the updater once from the repository directory:

```bash
./update_now_playing.py once
```

Check that the configured signs and displays change. If an update fails, inspect the Minecraft log and verify that RCON is enabled inside the container.

## Run the updater with systemd

1. Create `/etc/systemd/system/minecraft-now-playing.service` with the following content. Replace `YOUR_USER` and both `/absolute/path/to/minecraft-movie-night` values for your server:

   ```ini
   [Unit]
   Description=Minecraft Now Playing Board Updater
   After=docker.service
   Requires=docker.service

   [Service]
   Type=simple
   User=YOUR_USER
   WorkingDirectory=/absolute/path/to/minecraft-movie-night
   ExecStart=/absolute/path/to/minecraft-movie-night/update_now_playing.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. Reload systemd and start the unit:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now minecraft-now-playing.service
   ```

3. Check its status and follow its log:

   ```bash
   systemctl status minecraft-now-playing.service
   journalctl -u minecraft-now-playing.service -f
   ```

After editing `update_now_playing.py` or the service unit, restart the updater:

```bash
sudo systemctl restart minecraft-now-playing.service
```

## Updating

Pull repository changes and recreate the Minecraft container:

```bash
git pull
docker compose pull
docker compose up -d
sudo systemctl restart minecraft-now-playing.service
```

The `data/` directory remains in place when the container is recreated. Back it up separately because it contains the Minecraft world and player data.
