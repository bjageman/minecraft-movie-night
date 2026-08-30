#!/usr/bin/env python3

import argparse
import zipfile
import struct
from pathlib import Path

parser = argparse.ArgumentParser(description="Inspect PixelReel client-item bytecode.")
parser.add_argument(
    "jar_path",
    nargs="?",
    type=Path,
    default=Path(__file__).resolve().parent / "data/mods/pixelreel-2.0.0.jar",
)
args = parser.parse_args()

class_name = "com/pixelreel/networking/ServerNetworking.class"

with zipfile.ZipFile(args.jar_path) as z:
    class_data = z.read(class_name)

magic, minor, major, cp_count = struct.unpack(">IHHH", class_data[:10])

# Parse constant pool
cp_types = {}
cp_strings = {}
offset = 10
i = 1
while i < cp_count:
    tag = class_data[offset]
    cp_types[i] = tag
    if tag == 1:
        length = struct.unpack(">H", class_data[offset+1:offset+3])[0]
        val = class_data[offset+3:offset+3+length].decode('utf-8', errors='ignore')
        cp_strings[i] = val
        offset += 3 + length
    elif tag in (3, 4):
        offset += 5
    elif tag in (9, 10, 11):
        c_idx, nat_idx = struct.unpack(">HH", class_data[offset+1:offset+5])
        cp_strings[i] = (c_idx, nat_idx)
        offset += 5
    elif tag == 12:
        n_idx, d_idx = struct.unpack(">HH", class_data[offset+1:offset+5])
        cp_strings[i] = (n_idx, d_idx)
        offset += 5
    elif tag == 18:
        offset += 5
    elif tag in (5, 6):
        offset += 9
        i += 1
    elif tag in (7, 8, 16, 19, 20):
        if tag == 8:
            str_idx = struct.unpack(">H", class_data[offset+1:offset+3])[0]
            cp_strings[i] = str_idx
        elif tag == 7:
            class_idx = struct.unpack(">H", class_data[offset+1:offset+3])[0]
            cp_strings[i] = class_idx
        else:
            cp_strings[i] = f"Tag{tag}"
        offset += 3
    elif tag == 15:
        offset += 4
    else:
        break
    i += 1

resolved_cp = {}
for idx in range(1, cp_count):
    if idx in cp_strings:
        val = cp_strings[idx]
        if cp_types[idx] == 1:
            resolved_cp[idx] = val
        elif cp_types[idx] == 8:
            resolved_cp[idx] = cp_strings.get(val, f"#{val}")
        elif cp_types[idx] == 7:
            resolved_cp[idx] = cp_strings.get(val, f"#{val}")
        elif cp_types[idx] in (9, 10, 11):
            c_idx, nat_idx = val
            c_name = cp_strings.get(c_idx, f"#{c_idx}")
            if cp_types.get(c_idx) == 7:
                c_name = cp_strings.get(c_name, f"#{c_name}")
            nat_val = cp_strings.get(nat_idx, f"#{nat_idx}")
            if cp_types.get(nat_idx) == 12:
                n_name = cp_strings.get(nat_val[0], f"#{nat_val[0]}")
                d_name = cp_strings.get(nat_val[1], f"#{nat_val[1]}")
                nat_val = f"{n_name}:{d_name}"
            resolved_cp[idx] = f"{c_name}.{nat_val}"
        elif cp_types[idx] == 12:
            resolved_cp[idx] = f"{cp_strings.get(val[0])}:{cp_strings.get(val[1])}"

access_flags, this_class, super_class, interfaces_count = struct.unpack(">HHHH", class_data[offset:offset+8])
offset += 8 + 2 * interfaces_count

fields_count = struct.unpack(">H", class_data[offset:offset+2])[0]
offset += 2
for _ in range(fields_count):
    af, ni, di, ac = struct.unpack(">HHHH", class_data[offset:offset+8])
    offset += 8
    for _ in range(ac):
        al = struct.unpack(">I", class_data[offset+2:offset+6])[0]
        offset += 6 + al

methods_count = struct.unpack(">H", class_data[offset:offset+2])[0]
offset += 2

opcodes = {
    18: "ldc", 19: "ldc_w", 20: "ldc2_w", 21: "iload", 25: "aload", 42: "aload_0",
    43: "aload_1", 44: "aload_2", 45: "aload_3", 153: "ifeq", 154: "ifne", 155: "iflt",
    156: "ifge", 157: "ifgt", 158: "ifle", 167: "goto", 172: "ireturn", 176: "areturn",
    178: "getstatic", 180: "getfield", 181: "putfield", 182: "invokevirtual", 183: "invokespecial",
    184: "invokestatic", 185: "invokeinterface", 187: "new"
}

for m_idx in range(methods_count):
    af, ni, di, ac = struct.unpack(">HHHH", class_data[offset:offset+8])
    name = resolved_cp.get(ni, f"#{ni}")
    desc = resolved_cp.get(di, f"#{di}")
    offset += 8
    
    code_attr = None
    for _ in range(ac):
        ani = struct.unpack(">H", class_data[offset:offset+2])[0]
        al = struct.unpack(">I", class_data[offset+2:offset+6])[0]
        attr_name = resolved_cp.get(ani, f"#{ani}")
        if attr_name == "Code":
            code_attr = class_data[offset+6:offset+6+al]
        offset += 6 + al
        
    if code_attr:
        max_stack, max_locals, code_length = struct.unpack(">HHI", code_attr[:8])
        code = code_attr[8:8+code_length]
        pc = 0
        calls_target = False
        instructions = []
        while pc < code_length:
            op = code[pc]
            op_name = opcodes.get(op, f"opcode_{op}")
            inst_str = f"  {pc}: {op_name}"
            if op == 18:
                index = code[pc+1]
                val = resolved_cp.get(index, f"CP#{index}")
                inst_str += f" {val}"
                pc += 2
            elif op in (19, 20):
                index = struct.unpack(">H", code[pc+1:pc+3])[0]
                val = resolved_cp.get(index, f"CP#{index}")
                inst_str += f" {val}"
                pc += 3
            elif op in (180, 181, 178, 182, 183, 184, 187):
                index = struct.unpack(">H", code[pc+1:pc+3])[0]
                val = resolved_cp.get(index, f"CP#{index}")
                inst_str += f" {val}"
                if "forClientItem" in val:
                    calls_target = True
                pc += 3
            elif op == 185:
                index = struct.unpack(">H", code[pc+1:pc+3])[0]
                val = resolved_cp.get(index, f"CP#{index}")
                inst_str += f" {val}"
                if "forClientItem" in val:
                    calls_target = True
                pc += 5
            elif op in (153, 154, 155, 156, 157, 158, 167):
                offset_branch = struct.unpack(">h", code[pc+1:pc+3])[0]
                target = pc + offset_branch
                inst_str += f" -> {target}"
                pc += 3
            elif op in (21, 22, 23, 24, 25, 54, 58):
                index = code[pc+1]
                inst_str += f" {index}"
                pc += 2
            else:
                pc += 1
            instructions.append(inst_str)
        if calls_target:
            print(f"\nMethod {name} {desc}:")
            for inst in instructions:
                print(inst)
