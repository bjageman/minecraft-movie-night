# Minecraft Movie Night

A Fabric Minecraft 1.21.1 server running [PixelReel](https://github.com/Samarth-programming/PixelReel). An optional Python service reads ErsatzTV's XMLTV feed and updates in-game signs and text displays with current and upcoming programming.

## What you need

- Docker Engine with the Compose plugin
- An existing ErsatzTV server and XMLTV feed
- A reverse proxy if players outside your network will use the PixelReel media proxy
- Python 3.9 or newer for the now-playing updater
- A Minecraft Java Edition 1.21.1 client with Fabric Loader, Fabric API, and PixelReel installed

## Install the Minecraft server

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/bjageman/minecraft-movie-night.git
   cd minecraft-movie-night
   ```

2. Create the environment file:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set:

   ```dotenv
   DOMAIN=example.com
   EMAIL=admin@example.com
   ```

3. The Compose file expects an external Docker network named `nginx-proxy`. Create it if needed:

   ```bash
   docker network create nginx-proxy
   ```

   If you do not use a Docker reverse proxy, remove the `VIRTUAL_HOST`, `VIRTUAL_PORT`, and `LETSENCRYPT_*` entries from `docker-compose.yml`. You can also replace the external network with your preferred network.

4. Review `docker-compose.yml` before starting. In particular:

   - Change the players listed under `RCON_CMDS_STARTUP`.
   - Change the exposed ports if `25565` or `25569` are already in use.
   - Adjust `MEMORY` for your host.

5. Start the server:

   ```bash
   docker compose up -d
   ```

6. Follow the startup log until Minecraft reports that it is ready:

   ```bash
   docker compose logs -f mc
   ```

Minecraft creates its world, generated configuration, credentials, and logs under `data/`. That directory is intentionally excluded from Git.

## Configure PixelReel

After the first server start, edit:

```text
data/config/pixelreel.json
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

1. Edit `minecraft-now-playing.service` and replace the example `User`, `WorkingDirectory`, and `ExecStart` values with the account and absolute repository path on your server.

2. Install and start the unit:

   ```bash
   sudo cp minecraft-now-playing.service /etc/systemd/system/
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
