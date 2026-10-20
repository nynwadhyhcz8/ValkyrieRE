# -*- coding: utf-8 -*-
"""
Valkyrie RE Native Offline Decoding and Binary Triage Engine
Operates with 0 network latency and full local containment.
"""

import base64
import binascii
import math
import re
import struct
from typing import Dict, List, Tuple, Any

def calculate_shannon_entropy(data: bytes) -> float:
    """Calculates Shannon entropy (0.0 to 8.0). >7.0 indicates packing or encryption."""
    if not data:
        return 0.0
    entropy = 0.0
    for x in range(256):
        p_x = float(data.count(bytes([x]))) / len(data)
        if p_x > 0:
            entropy += - p_x * math.log2(p_x)
    return round(entropy, 4)

def extract_strings(data: bytes, min_len: int = 5) -> Dict[str, List[str]]:
    """Extracts ASCII and UTF-16LE strings from raw binary data."""
    ascii_pattern = re.compile(b'[\x20-\x7e]{' + str(min_len).encode() + b',}')
    utf16_pattern = re.compile(b'(?:[\x20-\x7e]\x00){' + str(min_len).encode() + b',}')
    
    ascii_matches = [m.decode('ascii', errors='ignore') for m in ascii_pattern.findall(data)]
    utf16_matches = [m.decode('utf-16le', errors='ignore') for m in utf16_pattern.findall(data)]
    
    return {
        "ascii": ascii_matches,
        "utf16": utf16_matches
    }

def brute_force_single_byte_xor(data: bytes, top_n: int = 3) -> List[Dict[str, Any]]:
    """Brute forces all 256 single-byte XOR keys and scores results by English frequency."""
    etaoin = b'etaoin shrdluETAOINSHRDLU'
    results = []
    
    for key in range(256):
        decrypted = bytes([b ^ key for b in data])
        score = sum(1 for b in decrypted if b in etaoin)
        printable_ratio = sum(1 for b in decrypted if 32 <= b <= 126 or b in (9, 10, 13)) / len(decrypted)
        total_score = score * printable_ratio
        
        results.append({
            "key": key,
            "hex_key": f"0x{key:02x}",
            "score": total_score,
            "sample": decrypted[:80].decode('latin1', errors='replace')
        })
        
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]

def multi_byte_xor(data: bytes, key: bytes) -> bytes:
    """Applies repeating key XOR."""
    if not key:
        return data
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])

def parse_pe_info(data: bytes) -> Dict[str, Any]:
    """Inspects basic Windows PE / DOS headers offline."""
    info = {"is_pe": False, "machine": "Unknown", "is_dotnet": False, "sections": []}
    if len(data) < 0x40 or data[:2] != b'MZ':
        return info
        
    pe_offset = struct.unpack('<I', data[0x3C:0x40])[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset+4] != b'PE\x00\x00':
        return info
        
    info["is_pe"] = True
    machine_id = struct.unpack('<H', data[pe_offset+4:pe_offset+6])[0]
    num_sections = struct.unpack('<H', data[pe_offset+6:pe_offset+8])[0]
    
    if machine_id == 0x14C:
        info["machine"] = "x86 (32-bit)"
    elif machine_id == 0x8664:
        info["machine"] = "x64 (64-bit)"
    elif machine_id == 0xAA64:
        info["machine"] = "ARM64"
    else:
        info["machine"] = f"Unknown (0x{machine_id:04x})"
        
    info["num_sections"] = num_sections
    
    # Check for .NET COM descriptor
    if b'mscoree.dll' in data or b'_CorExeMain' in data:
        info["is_dotnet"] = True
        
    return info

def instant_decode(raw_text: str) -> Dict[str, Any]:
    """Automatically attempts multi-layer decoding on input string."""
    clean = raw_text.strip()
    results = {}
    
    # 1. Hex
    hex_clean = re.sub(r'[\s,0x\\x]', '', clean)
    if len(hex_clean) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in hex_clean) and len(hex_clean) > 0:
        try:
            hex_bytes = binascii.unhexlify(hex_clean)
            results["hex_bytes"] = hex_bytes
            results["hex_ascii"] = hex_bytes.decode('latin1', errors='replace')
        except Exception:
            pass
            
    # 2. Base64
    try:
        b64_pad = clean + '=' * (-len(clean) % 4)
        b64_bytes = base64.b64decode(b64_pad, validate=True)
        if len(b64_bytes) > 2:
            results["base64_bytes"] = b64_bytes
            results["base64_ascii"] = b64_bytes.decode('latin1', errors='replace')
    except Exception:
        pass
        
    # 3. Shannon Entropy
    target_bytes = results.get("hex_bytes") or results.get("base64_bytes") or clean.encode('utf-8')
    results["entropy"] = calculate_shannon_entropy(target_bytes)
    
    # 4. Top XOR
    if len(target_bytes) >= 4:
        results["top_xors"] = brute_force_single_byte_xor(target_bytes, top_n=2)
        
    return results

def format_file_size(size_bytes: int) -> str:
    """Formats raw bytes into human-readable size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def detect_file_triage_info(path) -> Dict[str, Any]:
    """Inspects file headers, format signatures and entropy offline."""
    from pathlib import Path
    p = Path(path)
    info = {
        "name": p.name,
        "is_dir": p.is_dir(),
        "size": 0,
        "size_str": "<DIR>" if p.is_dir() else "0 B",
        "mtime": "",
        "format": "Directory" if p.is_dir() else "Unknown",
        "entropy": None,
        "entropy_tag": "—"
    }

    try:
        st = p.stat()
        import datetime
        info["mtime"] = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        
        if p.is_dir():
            return info

        info["size"] = st.st_size
        info["size_str"] = format_file_size(st.st_size)

        if st.st_size == 0:
            info["format"] = "Empty File"
            info["entropy"] = 0.0
            info["entropy_tag"] = "Zero"
            return info

        # Read first 4KB for rapid signature & entropy triage
        with open(p, "rb") as f:
            sample = f.read(min(st.st_size, 4096))

        ent = calculate_shannon_entropy(sample)
        info["entropy"] = ent
        if ent > 7.1:
            info["entropy_tag"] = "PACKED/CRYPT"
        elif ent > 5.5:
            info["entropy_tag"] = "Native"
        else:
            info["entropy_tag"] = "Normal"

        ext = p.suffix.lower()

        # Magic signatures
        if sample.startswith(b'MZ'):
            pe = parse_pe_info(sample)
            if pe["is_pe"]:
                fmt = f"PE ({pe['machine']})"
                if pe["is_dotnet"]:
                    fmt += " [.NET]"
                info["format"] = fmt
            else:
                info["format"] = "DOS Executable"
            return info

        elif sample.startswith(b'\x7fELF'):
            bitness = "64" if len(sample) > 4 and sample[4] == 2 else "32"
            info["format"] = f"ELF ({bitness}-bit)"
            return info

        elif sample[:4] in (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe'):
            info["format"] = "Mach-O Binary"
            return info

        elif sample.startswith(b'PK\x03\x04'):
            info["format"] = "ZIP Archive/Pkg"
            return info

        elif sample.startswith(b'7z\xbc\xaf\x27\x1c'):
            info["format"] = "7-Zip Archive"
            return info

        elif sample.startswith(b'Rar!\x1a\x07'):
            info["format"] = "RAR Archive"
            return info

        elif sample.startswith(b'%PDF'):
            info["format"] = "PDF Document"
            return info

        # Extension-based triage
        ext_map = {
            ".py": "Script (Python)",
            ".ps1": "Script (PowerShell)",
            ".bat": "Script (Batch)",
            ".cmd": "Script (CMD)",
            ".sh": "Script (Bash)",
            ".c": "Source (C)",
            ".cpp": "Source (C++)",
            ".h": "Header (C/C++)",
            ".cs": "Source (C#)",
            ".rs": "Source (Rust)",
            ".go": "Source (Go)",
            ".asm": "Assembly Source",
            ".json": "Data (JSON)",
            ".xml": "Data (XML)",
            ".md": "Doc (Markdown)",
            ".txt": "Text File",
            ".bin": "Binary / Shellcode",
            ".raw": "Raw Memory Dump",
            ".sys": "Kernel Driver",
            ".dll": "Dynamic Library",
            ".exe": "Executable"
        }
        if ext in ext_map:
            info["format"] = ext_map[ext]
            return info

        # Check printable ASCII ratio
        printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        if printable / len(sample) > 0.85:
            info["format"] = "ASCII / Text"
        else:
            info["format"] = "Binary Data"

    except Exception as e:
        info["format"] = f"Unreadable ({e})"

    return info
