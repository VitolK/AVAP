#!/usr/bin/env python3
"""
Picture Viewer TUI Script (Python Edition)

- Lists images in a target directory (current dir by default)
- Lets the user pick via fzf (if installed) or a simple numbered menu
- Offers a 🎲 Random Image option that can be used repeatedly
- Opens images either inline in the terminal (using chafa/viu/etc. if available)
  or in the system image viewer (Windows, macOS, Linux, WSL aware)
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
    ".svg",
    ".ico",
}

RANDOM_TOKEN = "__RANDOM_IMAGE__"
# Inline tools: terminal-based image viewers (chafa, viu, etc.) that display images in terminal
# Install with: sudo apt install chafa (or brew install chafa on macOS)
INLINE_TOOLS: Sequence[Sequence[str]] = (
    ("chafa", "--format=kitty"),
    ("chafa", "--format=sixels"),
    ("viu",),
    ("tiv",),
    ("tycat",),
    ("imgcat",),
    ("icat",),
    ("catimg",),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def command_exists(cmd: str) -> bool:
    """Return True if the command exists on PATH."""
    result = subprocess.run(
        ["where" if os.name == "nt" else "which", cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def is_wsl() -> bool:
    """Detect Windows Subsystem for Linux."""
    try:
        with open("/proc/version", "r", encoding="utf-8") as fh:
            return "microsoft" in fh.read().lower()
    except FileNotFoundError:
        return False


def wsl_to_windows_path(path: Path) -> str:
    """Convert WSL path to Windows path. Uses wslpath if available, otherwise manual conversion."""
    abs_path = path.resolve()
    path_str = str(abs_path)
    
    # Try wslpath first (most reliable)
    if command_exists("wslpath"):
        try:
            result = subprocess.run(
                ["wslpath", "-w", path_str],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
    
    # Manual conversion: /mnt/c/... to C:\...
    parts = abs_path.as_posix()
    prefix = "/mnt/"
    if parts.startswith(prefix) and len(parts) > len(prefix) + 2:
        drive = parts[len(prefix)]
        rest = parts[len(prefix) + 2:]
        # Can't use backslashes directly in f-string expressions, so do replacement first
        win_rest = rest.replace('/', '\\')
        return f"{drive.upper()}:\\{win_rest}"
    
    # If path doesn't start with /mnt/, it might be a Linux path
    # Try to use wslview or xdg-open instead
    return path_str


def list_images(directory: Path) -> List[Path]:
    """Return sorted list of image files in directory (non-recursive)."""
    files = [
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda p: p.name.lower())


def pick_with_fzf(images: List[Path]) -> Optional[Path]:
    """Use fzf for selection, with random option."""
    if not command_exists("fzf"):
        return None

    options = [RANDOM_TOKEN] + [str(p) for p in images]
    fzf = subprocess.run(
        ["fzf", "--height=40%", "--border", "--prompt", "📷 Select image > ", "--header",
         "Enter = open | Esc = quit | select random option for 🎲"],
        input="\n".join(options).encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if fzf.returncode != 0:
        return None

    selection = fzf.stdout.decode().strip()
    if not selection:
        return None
    if selection == RANDOM_TOKEN:
        return get_random_image(images)
    return Path(selection)


def fallback_menu(images: List[Path]) -> Optional[Path]:
    """Compact menu with max 50 images displayed."""
    MAX_DISPLAY = 50
    total_images = len(images)
    
    while True:
        print("\n" + "="*70)
        print(f"📷 Nimhirdykla - {total_images} image(s) found")
        print("="*70)
        
        if total_images > MAX_DISPLAY:
            print(f"\n⚠️  Too many images ({total_images}). Showing first {MAX_DISPLAY}.")
            print(f"Enter a number 1-{MAX_DISPLAY} or a range like '1-50' to view specific images.")
            display_images = images[:MAX_DISPLAY]
        else:
            display_images = images
        
        # Display in compact 2-column format
        print(f"\n{'0) 🎲 RANDOM IMAGE':<35} {'':<35}")
        print("-" * 70)
        
        # Display images in 2 columns
        for i in range(0, len(display_images), 2):
            row_images = display_images[i:i+2]
            if len(row_images) == 2:
                idx1 = i + 1
                idx2 = i + 2
                name1 = display_images[i].name[:32]  # Truncate long names
                name2 = display_images[i+1].name[:32]
                print(f"{idx1:>3}) {name1:<32} {idx2:>3}) {name2:<32}")
            else:
                idx = i + 1
                name = row_images[0].name[:32]
                print(f"{idx:>3}) {name:<32}")
        
        if total_images > MAX_DISPLAY:
            print(f"\n💡 Tip: Enter number 1-{MAX_DISPLAY} or range like '10-20'")
        
        choice = input("\nSelect number, 'r' for random, 'q' to quit: ").strip().lower()

        if choice in ("q", "quit", "exit"):
            return None
        if choice in ("r", "random", "0"):
            return get_random_image(images)
        
        # Handle range input (e.g., "1-10")
        if "-" in choice:
            try:
                start, end = map(int, choice.split("-"))
                if 1 <= start <= total_images and 1 <= end <= total_images and start <= end:
                    # Return first image in range (or could show submenu)
                    return images[start - 1]
            except ValueError:
                pass
        
        # Handle single number
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(display_images):
                return display_images[idx - 1]
            elif idx > MAX_DISPLAY and idx <= total_images:
                print(f"⚠️  Image #{idx} is beyond displayed range. Showing first {MAX_DISPLAY} only.")
                print(f"💡 Use range input like '{idx}-{min(idx+10, total_images)}' to access higher numbers.")
                continue
        
        print("❌ Invalid selection. Try again.")


def get_random_image(images: List[Path]) -> Optional[Path]:
    if not images:
        return None
    return random.choice(images)


# ---------------------------------------------------------------------------
# Image opening logic
# ---------------------------------------------------------------------------
def open_image(path: Path) -> None:
    """Open the image according to the OS."""
    if is_wsl():
        open_image_wsl(path)
    elif os.name == "nt":
        open_image_windows(path)
    elif sys.platform == "darwin":
        open_image_macos(path)
    else:
        open_image_linux(path)


def display_inline(path: Path, preferred: Optional[str] = None) -> bool:
    """
    Try to render an image inside the terminal using a helper utility.
    Returns True on success, False if no supported tool is available.
    """
    candidates: Iterable[Sequence[str]]

    if preferred:
        candidates = [
            tuple([preferred]),
        ]
    else:
        candidates = INLINE_TOOLS

    for tool_tuple in candidates:
        tool = tool_tuple[0]
        if not command_exists(tool):
            continue
        cmd = list(tool_tuple) + [str(path)]
        try:
            subprocess.run(cmd, check=False)
            return True
        except OSError:
            continue
    return False


def open_or_display(path: Path, inline: bool, inline_preferred: Optional[str]) -> None:
    """
    Try to display image. By default tries inline first, then falls back to external viewer.
    If --no-inline flag is used, skips inline and goes straight to external viewer.
    """
    # Always try inline first (unless explicitly disabled)
    if inline or inline_preferred is not None:
        # User explicitly requested inline
        if display_inline(path, inline_preferred):
            return
        # Inline failed, continue to external viewer silently
    else:
        # Default: try inline first, then fall back
        if display_inline(path, None):
            return
        # Inline failed, continue to external viewer silently
    
    # Fall back to external viewer
    open_image(path)


def open_image_wsl(path: Path) -> None:
    """Open image in WSL - tries multiple methods."""
    abs_path = path.resolve()
    path_str = str(abs_path)
    
    # Try wslview first (best for WSL)
    if command_exists("wslview"):
        try:
            subprocess.run(["wslview", path_str], check=False, timeout=5)
            return
        except Exception:
            pass
    
    # Try wslpath + Windows commands
    win_path = wsl_to_windows_path(abs_path)
    
    # Only use Windows commands if path conversion succeeded and looks like Windows path
    if win_path and (win_path.startswith(("C:", "D:", "E:", "F:")) or "\\" in win_path):
        # Try explorer.exe (most reliable on Windows)
        if command_exists("explorer.exe"):
            try:
                # Use quotes to handle paths with spaces
                subprocess.run(["explorer.exe", win_path], check=False, timeout=5)
                return
            except Exception:
                pass
        
        # Try cmd.exe start as fallback
        if command_exists("cmd.exe"):
            try:
                subprocess.run(["cmd.exe", "/c", "start", "", win_path], check=False, timeout=5)
                return
            except Exception:
                pass
    
    # Fallback to xdg-open (Linux viewer)
    if command_exists("xdg-open"):
        try:
            subprocess.run(["xdg-open", path_str], check=False, timeout=5)
            return
        except Exception:
            pass
    
    print("Error: Unable to open image (WSL). Try installing wslu (wslview) or ensure Windows shell available.")


def open_image_windows(path: Path) -> None:
    abs_path = str(path.resolve())
    if command_exists("start"):
        subprocess.run(["start", abs_path], shell=True)  # start needs shell on Windows
    else:
        subprocess.run(["explorer.exe", abs_path])


def open_image_macos(path: Path) -> None:
    subprocess.run(["open", str(path.resolve())])


def open_image_linux(path: Path) -> None:
    abs_path = str(path.resolve())
    if command_exists("xdg-open"):
        subprocess.run(["xdg-open", abs_path])
    elif command_exists("gnome-open"):
        subprocess.run(["gnome-open", abs_path])
    else:
        print("Error: xdg-open or gnome-open not found; cannot open image.")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal-friendly picture viewer.")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Folder that contains images (default: current directory)",
    )
    parser.add_argument(
        "--no-inline",
        action="store_true",
        help="Skip inline terminal display and use external viewer only.",
    )
    parser.add_argument(
        "--inline-tool",
        help="Force a specific inline tool (e.g. chafa, viu, imgcat). "
        "Falls back to auto-detection if missing. Implies --inline.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_dir = Path(args.directory)
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Directory '{target_dir}' does not exist.")
        sys.exit(1)

    while True:
        images = list_images(target_dir)
        if not images:
            print(f"No image files found in directory: {target_dir}")
            sys.exit(1)

        selected = pick_with_fzf(images)
        if selected is None:
            selected = fallback_menu(images)
        if selected is None:
            print("Exiting...")
            break

        print(f"📂 Opening: {selected.name}")
        # Use inline by default unless --no-inline is specified
        use_inline = not args.no_inline
        open_or_display(selected, inline=use_inline, inline_preferred=args.inline_tool)
        # No need to press enter - loop continues automatically


if __name__ == "__main__":
    main()
