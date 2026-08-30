#!/usr/bin/env python3

import argparse
import gzip
import struct
from pathlib import Path


DEFAULT_PLAYER_DATA = (
    Path(__file__).resolve().parent
    / "data/world/playerdata/36af65b8-24a2-41bc-82ac-66b9b95b9d3e.dat"
)

def parse_nbt(data, offset=0):
    tag_type = data[offset]
    if tag_type == 0:
        return None, offset + 1
    name_len = struct.unpack(">H", data[offset + 1 : offset + 3])[0]
    name = data[offset + 3 : offset + 3 + name_len].decode(
        "utf-8", errors="replace"
    )
    val, end_offset = parse_value(tag_type, data, offset + 3 + name_len)
    return (name, val), end_offset

def parse_value(tag_type, data, offset):
    if tag_type == 1:
        return data[offset], offset + 1
    if tag_type == 2:
        return struct.unpack(">h", data[offset:offset+2])[0], offset + 2
    if tag_type == 3:
        return struct.unpack(">i", data[offset:offset+4])[0], offset + 4
    if tag_type == 4:
        return struct.unpack(">q", data[offset:offset+8])[0], offset + 8
    if tag_type == 5:
        return struct.unpack(">f", data[offset:offset+4])[0], offset + 4
    if tag_type == 6:
        return struct.unpack(">d", data[offset:offset+8])[0], offset + 8
    if tag_type == 7:
        length = struct.unpack(">i", data[offset:offset+4])[0]
        return data[offset+4:offset+4+length], offset + 4 + length
    if tag_type == 8:
        length = struct.unpack(">H", data[offset:offset+2])[0]
        value = data[offset + 2 : offset + 2 + length].decode(
            "utf-8", errors="replace"
        )
        return value, offset + 2 + length
    if tag_type == 9:
        elem_type = data[offset]
        length = struct.unpack(">i", data[offset+1:offset+5])[0]
        offset += 5
        elems = []
        for _ in range(length):
            val, offset = parse_value(elem_type, data, offset)
            elems.append(val)
        return elems, offset
    if tag_type == 10:
        elems = {}
        while True:
            res = parse_nbt(data, offset)
            if res[0] is None:
                offset = res[1]
                break
            name, val = res[0]
            elems[name] = val
            offset = res[1]
        return elems, offset
    if tag_type == 11:
        length = struct.unpack(">i", data[offset:offset+4])[0]
        offset += 4
        elems = []
        for _ in range(length):
            elems.append(struct.unpack(">i", data[offset:offset+4])[0])
            offset += 4
        return elems, offset
    if tag_type == 12:
        length = struct.unpack(">i", data[offset:offset+4])[0]
        offset += 4
        elems = []
        for _ in range(length):
            elems.append(struct.unpack(">q", data[offset:offset+8])[0])
            offset += 8
        return elems, offset
    raise ValueError(f"Unknown NBT tag type {tag_type}")


def main():
    parser = argparse.ArgumentParser(description="Inspect a Minecraft player NBT file.")
    parser.add_argument("player_data", nargs="?", type=Path, default=DEFAULT_PLAYER_DATA)
    args = parser.parse_args()

    with gzip.open(args.player_data, "rb") as file:
        raw_data = file.read()

    # NBT starts with a named compound (0x0A).
    name_len = struct.unpack(">H", raw_data[1:3])[0]
    root_value, _ = parse_value(10, raw_data, 3 + name_len)

    print(
        "SpawnPoint:",
        root_value.get("SpawnX"),
        root_value.get("SpawnY"),
        root_value.get("SpawnZ"),
    )
    print("Last player position (Pos):", root_value.get("Pos"))


if __name__ == "__main__":
    main()
