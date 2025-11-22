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
    """Convert /mnt/c/... to C:\\..."""
    parts = path.as_posix()
    prefix = "/mnt/"
    if parts.startswith(prefix) and len(parts) > len(prefix) + 2:
        drive = parts[len(prefix)]
        rest = parts[len(prefix) + 2 :]
        # Can't use backslashes directly in f-string expressions, so do replacement first
        win_rest = rest.replace('/', '\\')
        return f"{drive.upper()}:\\{win_rest}"
    return str(path)


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
    """Simple numbered menu fallback."""
    while True:
        print("\n=== Picture Viewer ===")
        print("0) 🎲 RANDOM IMAGE")
        for idx, img in enumerate(images, start=1):
            print(f"{idx}) {img.name}")
        choice = input("Select number, 'r' for random, 'q' to quit: ").strip().lower()

        if choice in ("q", "quit", "exit"):
            return None
        if choice in ("r", "random", "0"):
            return get_random_image(images)
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(images):
                return images[idx - 1]
        print("Invalid selection. Try again.")


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
    if inline:
        if display_inline(path, inline_preferred):
            return
        print("Inline tools not found, falling back to external viewer...")
    open_image(path)


def open_image_wsl(path: Path) -> None:
    abs_path = path.resolve()
    win_path = wsl_to_windows_path(abs_path)

    if command_exists("cmd.exe"):
        subprocess.run(["cmd.exe", "/c", "start", "", win_path])
        return
    if command_exists("explorer.exe"):
        subprocess.run(["explorer.exe", win_path])
        return
    if command_exists("wslview"):
        subprocess.run(["wslview", str(abs_path)])
        return
    if command_exists("xdg-open"):
        subprocess.run(["xdg-open", str(abs_path)])
        return
    print("Error: Unable to open image (WSL). Install wslu or ensure Windows shell available.")


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
        "--inline",
        action="store_true",
        help="Try to display images inside the terminal using chafa/viu/tycat/etc.",
    )
    parser.add_argument(
        "--inline-tool",
        help="Force a specific inline tool (e.g. chafa, viu, imgcat). "
        "Falls back to auto-detection if missing.",
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

        print(f"Opening: {selected}")
        open_or_display(selected, inline=args.inline, inline_preferred=args.inline_tool)

        try:
            cont = input("\nPress Enter to continue (or type 'q' to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break
        if cont.lower() == "q":
            print("Exiting...")
            break


if __name__ == "__main__":
    main()
