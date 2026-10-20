# -*- coding: utf-8 -*-
"""
VALKYRIE RE - Elite Offline Reverse Engineering, Security & Coding CLI
Author: Google Deepmind Antigravity Pair-Programming
Target: 100% Offline, Local Containment, Multilingual (EN, ZH, VI, KO)
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

# Ensure UTF-8 stdout/stderr/stdin on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Local imports
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prompts import PERSONA_PROMPTS, MODE_TEMPLATES
from re_tools import (
    calculate_shannon_entropy,
    extract_strings,
    brute_force_single_byte_xor,
    parse_pe_info,
    instant_decode,
    detect_file_triage_info,
    format_file_size
)

CONFIG_PATH = Path(__file__).parent / "config.json"

# ANSI Colors
CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

class ValkyrieCLI:
    def __init__(self):
        self.load_config()
        self.history = []
        self.current_lang = self.config.get("default_language", "en")
        self.model = self.config.get("model", "qwen2.5-coder:14b")
        self.endpoint = self.config.get("endpoint", "http://127.0.0.1:11434/v1")
        self.fast_mode = False
        self.last_output = ""
        
        # Ensure output dir exists
        self.output_dir = Path(self.config.get("output_dir", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {}
        else:
            self.config = {}

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass

    def banner(self):
        banner_art = f"""{MAGENTA}{BOLD}
██╗   ██╗ █████╗ ██╗     ██╗  ██╗██╗   ██╗██████╗ ██╗███████╗    ██████╗ ███████╗
██║   ██║██╔══██╗██║     ██║ ██╔╝╚██╗ ██╔╝██╔══██╗██║██╔════╝    ██╔══██╗██╔════╝
██║   ██║███████║██║     █████═╝  ╚████╔╝ ██████╔╝██║█████╗      ██████╔╝█████╗  
╚██╗ ██╔╝██╔══██║██║     ██╔═██╗   ╚██╔╝  ██╔══██╗██║██╔══╝      ██╔══██╗██╔══╝  
 ╚████╔╝ ██║  ██║███████╗██║ ╚██╗   ██║   ██║  ██║██║███████╗    ██║  ██║███████╗
  ╚═══╝  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚══════╝    ╚═╝  ╚═╝╚══════╝
{RESET}{CYAN}[+] Elite Offline RE, Security Researcher & Code Engine | Active Lang: {YELLOW}{self.current_lang.upper()}{CYAN} | Model: {GREEN}{self.model}{RESET}
{DIM}[+] Type /help for slash commands | /lang [en|zh|vi|ko] | /read <file> | /clear | /exit{RESET}
"""
        print(banner_art)

    def stream_chat(self, user_prompt: str, system_override: str = None) -> str:
        sys_prompt = system_override or PERSONA_PROMPTS.get(self.current_lang, PERSONA_PROMPTS["en"])
        
        messages = [{"role": "system", "content": sys_prompt}]
        if not self.fast_mode:
            messages.extend(self.history[-6:])  # Keep last 3 turns
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1 if self.fast_mode else self.config.get("temperature", 0.2),
            "max_tokens": 2048 if self.fast_mode else self.config.get("max_tokens", 4096),
            "stream": True
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint}/chat/completions",
            data=req_data,
            headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"}
        )

        full_response = []
        print(f"\n{MAGENTA}{BOLD}[Valkyrie]:{RESET} ", end="", flush=True)

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                for line in response:
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        data_json = line[6:]
                        try:
                            chunk = json.loads(data_json)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                print(delta, end="", flush=True)
                                full_response.append(delta)
                        except Exception:
                            continue
            print("\n")
            result_text = "".join(full_response)
            self.last_output = result_text
            self.history.append({"role": "user", "content": user_prompt})
            self.history.append({"role": "assistant", "content": result_text})
            return result_text

        except urllib.error.HTTPError as e:
            if e.code == 404:
                fallback = self.config.get("fallback_model", "qwen2.5-coder:7b")
                if self.model != fallback:
                    print(f"\n{YELLOW}[!] Model '{self.model}' not found in Ollama. Auto-switching to fallback: {fallback}...{RESET}\n")
                    self.model = fallback
                    self.config["model"] = fallback
                    self.save_config()
                    return self.stream_chat(user_prompt, system_override)
            print(f"\n{RED}[!] HTTP Error ({e.code}): {e.reason}{RESET}\n")
            return ""
        except urllib.error.URLError as e:
            print(f"\n{RED}[!] Local Engine Offline ({self.endpoint}): {e.reason}{RESET}")
            print(f"{YELLOW}[*] Tip: Run 'ollama run {self.model}' in another terminal to start the local LLM.{RESET}\n")
            return ""
        except Exception as e:
            print(f"\n{RED}[!] Stream error: {e}{RESET}\n")
            return ""

    def handle_read_file(self, filepath: str):
        path = Path(filepath.strip('"\''))
        if not path.exists():
            print(f"{RED}[!] File not found: {path}{RESET}")
            return

        data = path.read_bytes()
        print(f"\n{CYAN}=== Local Triage Analysis: {path.name} ({len(data)} bytes) ==={RESET}")
        
        # 1. Entropy
        entropy = calculate_shannon_entropy(data)
        color = RED if entropy > 7.2 else (YELLOW if entropy > 6.0 else GREEN)
        print(f"Entropy: {color}{entropy}/8.0{RESET} ({'Likely Packed/Encrypted' if entropy > 7.0 else 'Normal/Text/Unpacked'})")

        # 2. PE Check
        pe_info = parse_pe_info(data)
        if pe_info["is_pe"]:
            print(f"Format: {GREEN}Windows PE ({pe_info['machine']}){RESET} | .NET Managed: {YELLOW}{pe_info['is_dotnet']}{RESET} | Sections: {pe_info['num_sections']}")

        # 3. String preview
        extracted = extract_strings(data, min_len=6)
        print(f"Extracted ASCII strings: {len(extracted['ascii'])} | UTF-16 strings: {len(extracted['utf16'])}")
        if extracted['ascii']:
            print(f"Sample strings: {DIM}{', '.join(extracted['ascii'][:8])}{RESET}")

        # Send to AI for deep decompilation/analysis
        try:
            text_content = data.decode("utf-8", errors="ignore")
            if len(text_content) > 12000:
                text_content = text_content[:12000] + "\n...[TRUNCATED FOR SPEED]..."
            prompt = f"Reverse engineer and analyze this extracted file '{path.name}' (Entropy: {entropy}):\n\n```\n{text_content}\n```"
            self.stream_chat(prompt)
        except Exception as e:
            print(f"{RED}[!] Failed to read text content: {e}{RESET}")

    def handle_ls(self, arg = ""):
        if isinstance(arg, list):
            parts = arg
        else:
            import shlex
            try:
                parts = shlex.split(arg, posix=False)
            except Exception:
                parts = arg.strip().split()

        show_all = False
        path_candidates = []
        for p in parts:
            p_clean = p.strip('"\'')
            p_lower = p_clean.lower()
            if p_lower in ("-la", "-al", "-a", "--all", "-ls", "-l", "ls", "la", "/ls", "/dir"):
                if "a" in p_lower:
                    show_all = True
            else:
                if p_clean:
                    path_candidates.append(p_clean)
                
        if path_candidates:
            joined = " ".join(path_candidates)
            if Path(joined).exists():
                target_dir = Path(joined).resolve()
            elif Path(path_candidates[0]).exists():
                target_dir = Path(path_candidates[0]).resolve()
            else:
                target_dir = Path(joined).resolve()
        else:
            target_dir = Path.cwd()

        if not target_dir.exists():
            print(f"{RED}[!] Directory not found: {target_dir}{RESET}")
            return
        if not target_dir.is_dir():
            self.handle_read_file(str(target_dir))
            return

        try:
            items = list(target_dir.iterdir())
        except Exception as e:
            print(f"{RED}[!] Access denied or error reading directory: {e}{RESET}")
            return

        if not show_all:
            items = [item for item in items if not item.name.startswith(".")]

        items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

        print(f"\n{CYAN}{BOLD}📂 Valkyrie RE Local Triage Explorer{RESET}")
        print(f"{DIM}Path: {target_dir} ({'All items including hidden' if show_all else 'Standard view, use -la for all'}){RESET}")
        header = f"{'Mode':<7} {'Size':>10}  {'Format / Architecture':<22} {'Entropy / Status':<18} {'Last Modified':<17} {'Name'}"
        print(f"{DIM}{'─' * len(header)}{RESET}")
        print(f"{BOLD}{header}{RESET}")
        print(f"{DIM}{'─' * len(header)}{RESET}")

        total_bytes = 0
        file_count = 0
        dir_count = 0

        for item in items:
            triage = detect_file_triage_info(item)
            mode = "d-----" if triage["is_dir"] else "-a----"
            
            if triage["is_dir"]:
                dir_count += 1
                size_display = f"{CYAN}<DIR>{RESET}"
                fmt_display = f"{CYAN}{triage['format']:<22}{RESET}"
                ent_display = f"{DIM}—{' ' * 16}{RESET}"
                name_display = f"{CYAN}{BOLD}{item.name}{RESET}"
            else:
                file_count += 1
                total_bytes += triage["size"]
                size_display = f"{triage['size_str']:>10}"
                
                fmt = triage["format"]
                if "PE" in fmt or "ELF" in fmt or "Mach-O" in fmt:
                    fmt_display = f"{GREEN}{BOLD}{fmt:<22}{RESET}"
                    name_display = f"{GREEN}{BOLD}{item.name}{RESET}"
                elif "Script" in fmt or "Source" in fmt:
                    fmt_display = f"{YELLOW}{fmt:<22}{RESET}"
                    name_display = f"{YELLOW}{item.name}{RESET}"
                else:
                    fmt_display = f"{fmt:<22}"
                    name_display = f"{item.name}"

                ent = triage["entropy"]
                ent_tag = triage["entropy_tag"]
                if ent is not None:
                    if ent > 7.1:
                        ent_color = f"{RED}{BOLD}"
                    elif ent > 5.5:
                        ent_color = f"{YELLOW}"
                    else:
                        ent_color = f"{GREEN}"
                    ent_str = f"[{ent:.2f} {ent_tag}]"
                    ent_display = f"{ent_color}{ent_str:<18}{RESET}"
                else:
                    ent_display = f"{DIM}—{' ' * 16}{RESET}"

            mtime = triage["mtime"]
            print(f"{DIM}{mode:<7}{RESET} {size_display}  {fmt_display} {ent_display} {mtime:<17} {name_display}")

        print(f"{DIM}{'─' * len(header)}{RESET}")
        print(f"{CYAN}[+] Summary:{RESET} {dir_count} directories, {file_count} files ({format_file_size(total_bytes)})\n")

    def handle_slash_command(self, cmd: str) -> bool:
        parts = cmd.strip().split(maxsplit=1)
        action = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if action in ("/exit", "/quit", "/q"):
            print(f"{MAGENTA}[*] Valkyrie session terminated. Stay vigilant.{RESET}")
            sys.exit(0)

        elif action in ("/help", "/h"):
            print(f"""
{CYAN}{BOLD}=== Valkyrie CLI Commands ==={RESET}
  {GREEN}/ls [-la] [path]{RESET}      : Triage & list directory files (formats, entropy, sizes)
  {GREEN}/lang [en|zh|vi|ko]{RESET}   : Switch language (English, Chinese, Vietnamese, Korean)
  {GREEN}/read <path>{RESET}          : Triage, unpack strings, calculate entropy & reverse file
  {GREEN}/decode <text>{RESET}        : Instant multi-layer decode (Hex, Base64, XOR, Entropy)
  {GREEN}/asm <disasm>{RESET}         : Reconstruct x86/x64/ARM assembly into clean C/C++
  {GREEN}/csharp <code/IL>{RESET}     : Deobfuscate and reconstruct .NET / C#
  {GREEN}/audit <code/script>{RESET}  : Security vulnerability & logic flaw review
  {GREEN}/fast{RESET}                 : Toggle ultra-speed low-latency mode (Current: {self.fast_mode})
  {GREEN}/model <name>{RESET}         : Change local model (Current: {self.model})
  {GREEN}/save [filename]{RESET}      : Save last output to {self.output_dir}
  {GREEN}/clear{RESET}                : Reset conversation history to free context tokens
  {GREEN}/exit{RESET}                 : Terminate session
""")
            return True

        elif action in ("/ls", "/dir", "ls", "dir", "-ls", "-la", "-l"):
            self.handle_ls(arg)
            return True

        elif action == "/lang":
            if arg.lower() in ("en", "zh", "vi", "ko"):
                self.current_lang = arg.lower()
                self.config["default_language"] = self.current_lang
                self.save_config()
                print(f"{GREEN}[+] Language updated to: {self.current_lang.upper()}{RESET}")
            else:
                print(f"{YELLOW}[!] Supported languages: en (English), zh (中文), vi (Tiếng Việt), ko (한국어){RESET}")
            return True

        elif action == "/clear":
            self.history.clear()
            print(f"{GREEN}[+] Context history wiped. Running at maximum speed.{RESET}")
            return True

        elif action == "/fast":
            self.fast_mode = not self.fast_mode
            status = f"{GREEN}ON{RESET}" if self.fast_mode else f"{YELLOW}OFF{RESET}"
            print(f"[+] Ultra-Fast mode: {status}")
            return True

        elif action == "/model":
            if arg:
                self.model = arg.strip()
                self.config["model"] = self.model
                self.save_config()
                print(f"{GREEN}[+] Active model set to: {self.model}{RESET}")
            else:
                print(f"Current model: {self.model}")
            return True

        elif action == "/save":
            if not self.last_output:
                print(f"{YELLOW}[!] No output to save yet.{RESET}")
                return True
            filename = arg.strip() or f"valkyrie_out_{int(time.time())}.txt"
            out_file = self.output_dir / filename
            out_file.write_text(self.last_output, encoding="utf-8")
            print(f"{GREEN}[+] Output successfully saved to: {out_file}{RESET}")
            return True

        elif action == "/read":
            if not arg:
                print(f"{YELLOW}Usage: /read <filepath>{RESET}")
            else:
                self.handle_read_file(arg)
            return True

        elif action == "/decode":
            if not arg:
                print(f"{YELLOW}Usage: /decode <hex/base64/xor string>{RESET}")
                return True
            print(f"\n{CYAN}=== Instant Native Decoding ==={RESET}")
            dec_results = instant_decode(arg)
            if "hex_ascii" in dec_results:
                print(f"Hex Decoded: {GREEN}{dec_results['hex_ascii']}{RESET}")
            if "base64_ascii" in dec_results:
                print(f"Base64 Decoded: {GREEN}{dec_results['base64_ascii']}{RESET}")
            if "entropy" in dec_results:
                print(f"Shannon Entropy: {YELLOW}{dec_results['entropy']}{RESET}")
            if "top_xors" in dec_results:
                for x in dec_results["top_xors"]:
                    print(f"XOR Key {x['hex_key']}: {x['sample']}")
            # Pass to AI
            self.stream_chat(f"Decode and explain this obfuscated payload:\n\n{arg}")
            return True

        elif action == "/asm":
            if not arg:
                print(f"{YELLOW}Usage: /asm <paste assembly snippet>{RESET}")
            else:
                prompt = MODE_TEMPLATES["asm"].format(lang="C", input=arg)
                self.stream_chat(prompt)
            return True

        elif action in ("/csharp", "/dotnet"):
            if not arg:
                print(f"{YELLOW}Usage: /csharp <code snippet>{RESET}")
            else:
                prompt = MODE_TEMPLATES["deobfuscate"].format(format="csharp", input=arg)
                self.stream_chat(prompt)
            return True

        elif action == "/audit":
            if not arg:
                print(f"{YELLOW}Usage: /audit <code snippet>{RESET}")
            else:
                prompt = MODE_TEMPLATES["audit"].format(format="c", input=arg)
                self.stream_chat(prompt)
            return True

        return False

    def run(self):
        self.banner()
        while True:
            try:
                prompt_label = f"{CYAN}[{self.current_lang.upper()}|{self.model.split(':')[0]}]> {RESET}"
                user_input = input(prompt_label).strip()

                if not user_input:
                    continue

                cmd_first = user_input.lower().split()[0]
                if user_input.startswith("/"):
                    self.handle_slash_command(user_input)
                elif cmd_first in ("ls", "dir", "-ls", "-la", "-l", "ll"):
                    self.handle_ls(user_input)
                else:
                    self.stream_chat(user_input)

            except (KeyboardInterrupt, EOFError):
                print(f"\n{MAGENTA}[*] Session closed.{RESET}")
                break

if __name__ == "__main__":
    app = ValkyrieCLI()
    if len(sys.argv) > 1:
        first_arg = sys.argv[1].lower()
        arg_str = " ".join(sys.argv[1:]).strip()
        if first_arg in ("-h", "--help"):
            app.banner()
            print(f"{CYAN}Usage:{RESET}")
            print(f"  valkyrie                     Start interactive CLI session")
            print(f"  valkyrie -ls [-la] [path]    Triage and list files with entropy & format tags")
            print(f"  valkyrie <prompt>            One-shot query to Valkyrie AI")
            print(f"  valkyrie /<command> [args]   Execute slash command directly (e.g. /read, /decode, /ls)")
            print(f"  valkyrie /help               List available slash commands\n")
        elif first_arg in ("-ls", "--ls", "-la", "--la", "-l", "ls", "dir", "/ls", "/dir") or any(a.lower() in ("-ls", "-la", "-al") for a in sys.argv[1:]):
            app.handle_ls(sys.argv[1:])
        elif arg_str.startswith("/"):
            app.handle_slash_command(arg_str)
        else:
            app.stream_chat(arg_str)
    else:
        app.run()
