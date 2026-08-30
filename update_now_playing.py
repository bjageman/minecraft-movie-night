#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# Set Docker Host context path for systemd service execution
os.environ["DOCKER_HOST"] = "unix:///tank/services/docker.sock"

# Paths
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "now_playing_config.json"
STATE_PATH = BASE_DIR / "now_playing_state.json"
EMPTY_STATE = {
    "scoreboard": {},
    "signs": {},
    "text_displays": {},
    "schedules": {},
    "active_scoreboard_targets": [],
}

# Default Configuration
DEFAULT_CONFIG = {
    "ersatztv_url": "http://localhost:8409",
    "minecraft_container": "minecraft-pixelreel",
    "update_interval_seconds": 15,
    "enable_scoreboard": False,
    "scoreboard_objective": "now_playing",
    "scoreboard_title": "§e§lNow Playing",
    "scoreboard_channels": [],  # If empty, all active channels are shown
    "enable_signs": True,
    "signs": [
        {
            "channel_number": 1,
            "x": -1056,
            "y": 93,
            "z": 780,
            "dimension": "minecraft:overworld",
            "description": "Lobby All Movies Sign"
        }
    ],
    "enable_text_displays": True,
    "text_displays": [
        {
            "channel_number": 1,
            "tag": "now_playing_chan_1",
            "description": "Lobby Large Display"
        }
    ],
    "enable_schedule_displays": True,
    "schedule_displays": [],
}

def write_json(path, value):
    """Write JSON atomically so an interrupted update cannot corrupt the file."""
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(value, file, indent=4, ensure_ascii=False)
        file.write("\n")
    os.replace(temporary_path, path)


def load_config():
    if not CONFIG_PATH.exists():
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
        print(f"Created default configuration at {CONFIG_PATH}")
        return DEFAULT_CONFIG
    try:
        with CONFIG_PATH.open(encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error reading config, using defaults: {error}")
        return DEFAULT_CONFIG


def save_state(state):
    try:
        write_json(STATE_PATH, state)
    except OSError as error:
        print(f"Error saving state: {error}")


def run_rcon_command(container_name, command):
    try:
        # Run rcon-cli inside the Minecraft container
        cmd = ["docker", "--config", "/tmp", "exec", container_name, "rcon-cli", command]
        result = subprocess.run(
            cmd, capture_output=True, check=False, text=True, timeout=15
        )
        time.sleep(1.5)
        if result.returncode == 0:
            stdout_clean = result.stdout.strip()
            stdout_lower = stdout_clean.lower()
            if any(
                marker in stdout_lower
                for marker in ("invalid", "error", "expected")
            ):
                print(f"RCON Command failed: {stdout_clean}")
                return None
            return stdout_clean
        print(f"RCON error running command '{command}': {result.stderr.strip()}")
        return None
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Failed to execute RCON command '{command}': {error}")
        return None


def parse_xmltv_time(value):
    """Parse XMLTV timestamps, including their optional UTC offset."""
    parts = value.split()
    timestamp = datetime.strptime(parts[0], "%Y%m%d%H%M%S")
    if len(parts) > 1:
        timestamp = datetime.strptime(" ".join(parts[:2]), "%Y%m%d%H%M%S %z")
    return timestamp.astimezone()


def clean_title(title, sub_title=None):
    if title.endswith(('.mkv', '.mp4', '.avi', '.mov')):
        title = title.rsplit('.', 1)[0]

    cleaned = title.replace('.', ' ').replace('_', ' ')
    
    # Match years (e.g. 1996, 2023) or common release quality tags and truncate everything after
    release_tags = (
        r"19\d{2}|20\d{2}|1080p|2160p|720p|4k|bluray|proper|webrip|"
        r"web-dl|hdr|upscale|bdrip|brrip|h264|x264|h265|x265|hevc|aac|"
        r"ddp|ac3|dts|subs"
    )
    pattern = re.compile(rf"\b({release_tags})\b", re.IGNORECASE)
    
    match = pattern.search(cleaned)
    if match:
        cleaned = cleaned[:match.start()].strip()
    
    cleaned = re.sub(r'[\s\-(\[\])]+$', '', cleaned).strip()
    
    if not cleaned:
        cleaned = title
        
    if not sub_title:
        return cleaned
        
    # If it is a show, try to find SxxExx inside the sub_title
    match_show = re.search(r'S\d{2}E\d{2}', sub_title, re.IGNORECASE)
    if match_show:
        season_episode = match_show.group(0).upper()
        return f"{cleaned} {season_episode}"
    return cleaned


def split_title_for_sign(title, max_len=15):
    words = title.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        separator_len = 1 if current_line else 0
        if current_len + separator_len + len(word) <= max_len:
            current_line.append(word)
            current_len += separator_len + len(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def sanitize_display_text(value):
    """Avoid terminating the single-quoted SNBT strings used by commands."""
    return value.replace("'", "’")


def fetch_ersatztv_now_playing(ersatztv_url):
    url = f"{ersatztv_url}/iptv/xmltv.xml"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as response:
        xml_data = response.read()
    
    root = ET.fromstring(xml_data)
    
    # Map channel ID -> display name
    channels = {}
    for chan in root.findall('channel'):
        chan_id = chan.get('id')
        display_name = chan.find('display-name')
        name = display_name.text if display_name is not None else chan_id
        channels[chan_id] = name
        
    now = datetime.now().astimezone()
        
    playing = {}
    for prog in root.findall('programme'):
        chan_id = prog.get('channel')
        start_str = prog.get('start')
        stop_str = prog.get('stop')
        
        if not chan_id or not start_str or not stop_str:
            continue
            
        try:
            start_dt = parse_xmltv_time(start_str)
            stop_dt = parse_xmltv_time(stop_str)
        except ValueError:
            continue
            
        if start_dt <= now <= stop_dt:
            # Extract channel number from channel ID (e.g. C1.145.ersatztv.org -> 1)
            chan_num = None
            num_match = re.search(r'^C(\d+)\.', chan_id)
            if num_match:
                chan_num = int(num_match.group(1))
                
            title_elem = prog.find("title")
            title = (
                title_elem.text
                if title_elem is not None and title_elem.text
                else "Unknown"
            )
            
            sub_title_elem = prog.find('sub-title')
            sub_title = sub_title_elem.text if sub_title_elem is not None else None
            
            clean_name = clean_title(title, sub_title)
            
            playing[chan_id] = {
                "channel_number": chan_num,
                "channel_name": channels.get(chan_id, chan_id),
                "title": clean_name,
                "raw_title": title,
                "raw_subtitle": sub_title
            }
            
    return playing


def update_scoreboard(config, playing, state):
    container = config["minecraft_container"]
    obj = config["scoreboard_objective"]
    title = config["scoreboard_title"]
    
    # 1. Initialize scoreboard objective if it doesn't exist
    run_rcon_command(container, f"scoreboard objectives add {obj} dummy")
    run_rcon_command(container, f"scoreboard objectives setdisplay sidebar {obj}")
    
    # Format objective title (top of the scoreboard)
    if title.startswith("§") or "{" not in title:
        title_json = json.dumps({"text": title})
    else:
        title_json = title
    run_rcon_command(container, f"scoreboard objectives modify {obj} displayname {title_json}")

    active_targets = set()
    filter_channels = config.get("scoreboard_channels", [])
    
    for info in playing.values():
        chan_num = info["channel_number"]
        if chan_num is None:
            continue
        if filter_channels and chan_num not in filter_channels:
            continue
            
        target = f"ch_{chan_num}"
        active_targets.add(target)
        
        # Set score value (ordering: Ch 1 is highest score, so it displays first)
        score_val = 100 - chan_num
        run_rcon_command(container, f"scoreboard players set {target} {obj} {score_val}")
        
        # Format custom display name component
        max_title_len = 32
        short_title = info["title"]
        if len(short_title) > max_title_len:
            short_title = short_title[:max_title_len-3] + "..."
            
        display_name_component = {
            "text": f"Ch {chan_num} ",
            "color": "gold",
            "bold": True,
            "extra": [
                {"text": "| ", "color": "dark_gray", "bold": False},
                {"text": short_title, "color": "white", "bold": False}
            ]
        }
        
        # Convert to JSON and run command directly
        display_name_json = json.dumps(display_name_component)
        run_rcon_command(container, f"scoreboard players display name {target} {obj} {display_name_json}")

    # Reset any targets that are no longer playing (offline)
    old_active_targets = state.get("active_scoreboard_targets", [])
    for target in old_active_targets:
        if target not in active_targets:
            run_rcon_command(container, f"scoreboard players reset {target} {obj}")
            print(f"Cleared offline target from scoreboard: {target}")
            
    state["active_scoreboard_targets"] = list(active_targets)


def update_signs(config, playing, state):
    container = config["minecraft_container"]
    signs = config.get("signs", [])
    saved_signs = state.get("signs", {})
    
    # Create playing map by channel number for quick lookups
    playing_by_num = {info["channel_number"]: info for info in playing.values() if info["channel_number"] is not None}
    
    new_saved_signs = {}
    for sign in signs:
        chan_num = sign.get("channel_number")
        x, y, z = sign.get("x"), sign.get("y"), sign.get("z")
        dim = sign.get("dimension", "minecraft:overworld")
        
        if chan_num is None or x is None or y is None or z is None:
            continue
            
        sign_key = f"{dim}_{x}_{y}_{z}"
        info = playing_by_num.get(chan_num)
        
        title_text = info["title"] if info else "Offline"
        
        # If status didn't change for this sign, skip updating it in Minecraft to reduce spam
        if saved_signs.get(sign_key) == title_text:
            new_saved_signs[sign_key] = title_text
            continue
            
        # Format text for the sign:
        # Line 1: NOW PLAYING (bold gold)
        # Line 2: Ch {num} Channel Name (cyan)
        # Line 3 & 4: Title (wrapped or split)
        line1 = "§6§lNOW PLAYING"
        
        chan_name = info["channel_name"] if info else f"Channel {chan_num}"
        if len(chan_name) > 12:
            chan_name = chan_name[:12]
        line2 = f"§bCh {chan_num}: {chan_name}"
        
        if info:
            wrapped_title = split_title_for_sign(info["title"], max_len=15)
            line3 = f"§f{wrapped_title[0]}" if len(wrapped_title) > 0 else ""
            line4 = f"§f{wrapped_title[1]}" if len(wrapped_title) > 1 else ""
            if len(wrapped_title) > 2:
                # If it's too long, truncate with ... on line 4
                line4 = line4[:12] + "..."
        else:
            line3 = "§c§oChannel"
            line4 = "§c§oOffline"
            
        msg1 = json.dumps({"text": sanitize_display_text(line1)}, ensure_ascii=False)
        msg2 = json.dumps({"text": sanitize_display_text(line2)}, ensure_ascii=False)
        msg3 = json.dumps({"text": sanitize_display_text(line3)}, ensure_ascii=False)
        msg4 = json.dumps({"text": sanitize_display_text(line4)}, ensure_ascii=False)
        
        # Execute command to update sign NBT block data
        cmd = (
            f"execute in {dim} run data merge block {x} {y} {z} "
            f"{{front_text: {{messages: ["
            f"'{msg1}', '{msg2}', '{msg3}', '{msg4}'"
            f"]}}}}"
        )
        
        res = run_rcon_command(container, cmd)
        if res:
            print(f"Updated sign at {x} {y} {z} for Ch {chan_num}: {title_text}")
            new_saved_signs[sign_key] = title_text
        else:
            print(f"Failed to update sign at {x} {y} {z}")
            
    state["signs"] = new_saved_signs

def update_text_displays(config, playing, state):
    container = config["minecraft_container"]
    displays = config.get("text_displays", [])
    saved_displays = state.get("text_displays", {})
    
    # Create playing map by channel number
    playing_by_num = {info["channel_number"]: info for info in playing.values() if info["channel_number"] is not None}
    
    new_saved_displays = {}
    for display in displays:
        chan_num = display.get("channel_number")
        tag = display.get("tag")
        
        if chan_num is None or not tag:
            continue
            
        info = playing_by_num.get(chan_num)
        title_text = sanitize_display_text(info["title"]) if info else "Offline"
        
        # Avoid redundant RCON commands if the media title hasn't changed
        if saved_displays.get(tag) == title_text:
            new_saved_displays[tag] = title_text
            continue
            
        # Construct the text display JSON NBT component
        if info:
            display_name_component = {
                "text": "NOW PLAYING\n\n",
                "color": "white",
                "bold": True,
                "extra": [
                    {"text": title_text, "color": "white", "bold": True}
                ]
            }
        else:
            display_name_component = {
                "text": "NOW PLAYING\n\n",
                "color": "white",
                "bold": True,
                "extra": [
                    {"text": "Offline", "color": "gray", "bold": False, "italic": True}
                ]
            }
            
        # Convert to JSON and run command directly
        display_name_json = json.dumps(display_name_component, separators=(',', ':'), ensure_ascii=False)
        display_name_json = display_name_json.replace("\\n", "\\\\n")
        # `data merge entity` accepts only one target. Execute as every tagged
        # display so duplicate boards are updated by the same command.
        cmd = (
            f"execute as @e[tag={tag}] run data merge entity @s "
            f"{{text: '{display_name_json}'}}"
        )
        res = run_rcon_command(container, cmd)
        if res:
            print(f"Updated text display '{tag}' for Ch {chan_num}: {title_text}")
            new_saved_displays[tag] = title_text
        else:
            print(f"Failed to update text display '{tag}'")
            
    state["text_displays"] = new_saved_displays

def fetch_ersatztv_schedule(ersatztv_url):
    url = f"{ersatztv_url}/iptv/xmltv.xml"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as response:
        xml_data = response.read()
    
    root = ET.fromstring(xml_data)
    
    # Map channel ID -> channel number
    channel_map = {}
    for chan in root.findall('channel'):
        chan_id = chan.get('id')
        num_match = re.search(r'^C(\d+)\.', chan_id or "")
        if num_match:
            channel_map[chan_id] = int(num_match.group(1))
            
    now = datetime.now().astimezone()
        
    schedule = {}
    for prog in root.findall('programme'):
        chan_id = prog.get('channel')
        start_str = prog.get('start')
        stop_str = prog.get('stop')
        
        if not chan_id or not start_str or not stop_str or chan_id not in channel_map:
            continue
            
        try:
            start_dt = parse_xmltv_time(start_str)
            stop_dt = parse_xmltv_time(stop_str)
        except ValueError:
            continue
            
        if stop_dt > now:
            chan_num = channel_map[chan_id]
            title_elem = prog.find('title')
            title = (
                title_elem.text
                if title_elem is not None and title_elem.text
                else "Unknown"
            )
            sub_title_elem = prog.find('sub-title')
            sub_title = sub_title_elem.text if sub_title_elem is not None else None
            
            clean_name = clean_title(title, sub_title)
            
            if chan_num not in schedule:
                schedule[chan_num] = []
            schedule[chan_num].append((start_dt, stop_dt, clean_name))
            
    for chan_num in schedule:
        schedule[chan_num].sort(key=lambda x: x[0])
        
    return schedule

def update_schedule_displays(config, schedule, state):
    container = config["minecraft_container"]
    new_saved_schedules = {}
    saved_schedules = state.get("schedules", {})
    
    for disp in config.get("schedule_displays", []):
        channels = disp.get("channels")
        if not channels:
            channels = [disp.get("channel_number")]
            
        tag = disp["tag"]
        now = datetime.now().astimezone()
        extra_lines = []
        
        for idx, chan_num in enumerate(channels):
            if not chan_num:
                continue
                
            if idx > 0:
                extra_lines.append({"text": "\n", "color": "dark_gray"})
                
            progs = schedule.get(chan_num, [])
            timeline_items = []
            for start_dt, stop_dt, title in progs:
                if (start_dt - now).total_seconds() <= 24 * 3600:
                    title_clean = sanitize_display_text(title)
                    timeline_items.append((start_dt, title_clean))
                    
            arrow = "<-" if chan_num == 1 else "->"
            extra_lines.append({"text": f"{arrow}\n\n", "color": "gold", "bold": True})
            
            if not timeline_items:
                extra_lines.append({"text": "No upcoming programs\n", "color": "gray", "italic": True})
            else:
                for start_dt, title in timeline_items[:3]:
                    is_now = start_dt <= now
                    time_str = "[NOW PLAYING]" if is_now else f"[{start_dt.strftime('%I:%M %p')}]"
                    time_color = "gold" if is_now else "yellow"
                    title_color = "white" if is_now else "gray"
                    
                    extra_lines.append({"text": f"{time_str} ", "color": time_color, "bold": is_now})
                    extra_lines.append({"text": f"{title}\n", "color": title_color, "bold": is_now})
                    
        display_name_component = {
            "text": "",
            "extra": extra_lines
        }
        
        display_name_json = json.dumps(display_name_component, separators=(',', ':'), ensure_ascii=False)
        display_name_json = display_name_json.replace("\\n", "\\\\n")
        chan_str = "_".join(str(c) for c in channels)
        cache_key = f"{tag}_{chan_str}"
        if saved_schedules.get(cache_key) == display_name_json:
            new_saved_schedules[cache_key] = display_name_json
            continue
            
        cmd = (
            f"execute as @e[tag={tag}] run data merge entity @s "
            f"{{text: '{display_name_json}'}}"
        )
        res = run_rcon_command(container, cmd)
        if res:
            print(f"Updated schedule display '{tag}'")
            new_saved_schedules[cache_key] = display_name_json
        else:
            print(f"Failed to update schedule display '{tag}'")
            
    state["schedules"] = new_saved_schedules

def run_update(config, state):
    playing = fetch_ersatztv_now_playing(config["ersatztv_url"])

    if config.get("enable_scoreboard", False):
        update_scoreboard(config, playing, state)
    if config.get("enable_signs", True):
        update_signs(config, playing, state)
    if config.get("enable_text_displays", True):
        update_text_displays(config, playing, state)
    if config.get("enable_schedule_displays", True):
        schedule = fetch_ersatztv_schedule(config["ersatztv_url"])
        update_schedule_displays(config, schedule, state)

    save_state(state)


def main(run_once=False):
    config = load_config()
    # Start clean so Minecraft is synchronized after either service restarts.
    state = {
        key: value.copy() if isinstance(value, dict) else list(value)
        for key, value in EMPTY_STATE.items()
    }
    if run_once:
        run_update(config, state)
        return

    interval = config["update_interval_seconds"]
    print(
        f"Starting Now Playing updater. Checking ErsatzTV at "
        f"{config['ersatztv_url']} every {interval}s."
    )

    while True:
        try:
            run_update(config, state)
        except urllib.error.URLError as error:
            print(f"[{datetime.now()}] ErsatzTV connection error: {error}")
        except (ET.ParseError, KeyError, TypeError, ValueError):
            print(f"[{datetime.now()}] Invalid updater data:")
            traceback.print_exc()

        time.sleep(interval)

if __name__ == "__main__":
    main(run_once=len(sys.argv) > 1 and sys.argv[1] == "once")
