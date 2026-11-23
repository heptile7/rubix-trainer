#!/usr/bin/env python3
"""
Put a "Cube Timer" icon on the desktop that opens the desktop app.

    python make_shortcut.py               # desktop shortcut
    python make_shortcut.py --start-menu  # also add it to the Start menu (searchable)
    python make_shortcut.py --remove      # take the shortcut(s) away again

The shortcut runs cube_timer_gui.py with pythonw.exe from the Python that runs
this script: no console window, the latest code every time, and the usual
database (cube_times.db next to the scripts). Run this script with the Python
that has the packages from requirements.txt; it checks before making anything.

It also writes cube_timer.ico (a yellow cube face, drawn here: Pillow isn't
needed), which the shortcut and the app's window and taskbar button use.
"""

import argparse
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "cube_timer_gui.py"
ICON = ROOT / "cube_timer.ico"
NAME = "Cube Timer"

YELLOW = (0xF6, 0xD9, 0x0B)
BODY = (0x1B, 0x1B, 0x1B)


# ---------------------------------------------------------------------------
# Icon: a cube's top face, 3x3 yellow stickers on a dark rounded body
# ---------------------------------------------------------------------------
def _in_rounded(x, y, x0, y0, x1, y1, r):
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _render(size, ss=3):
    """RGBA bytes of the icon at size x size, anti-aliased with ss x ss samples per pixel."""
    s = float(size)
    pad, radius = s * 0.04, s * 0.16
    inner = s * 0.10                       # margin from body edge to the stickers
    pitch = (s - 2 * pad - 2 * inner) / 3
    gap = pitch * 0.10
    sr = pitch * 0.14                      # sticker corner radius
    out = bytearray()
    for py in range(size):
        for px in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sy in range(ss):
                for sx in range(ss):
                    x = px + (sx + 0.5) / ss
                    y = py + (sy + 0.5) / ss
                    if not _in_rounded(x, y, pad, pad, s - pad, s - pad, radius):
                        continue
                    color = BODY
                    gx, gy = x - pad - inner, y - pad - inner
                    i, j = int(gx // pitch), int(gy // pitch)
                    if 0 <= i < 3 and 0 <= j < 3 and gx >= 0 and gy >= 0:
                        x0, y0 = pad + inner + i * pitch + gap / 2, pad + inner + j * pitch + gap / 2
                        if _in_rounded(x, y, x0, y0, x0 + pitch - gap, y0 + pitch - gap, sr):
                            color = YELLOW
                    acc[0] += color[0]; acc[1] += color[1]; acc[2] += color[2]; acc[3] += 1
            n = ss * ss
            if acc[3]:
                out += bytes((round(acc[0] / acc[3]), round(acc[1] / acc[3]),
                              round(acc[2] / acc[3]), round(255 * acc[3] / n)))
            else:
                out += b"\0\0\0\0"
    return bytes(out)


def _png(size, rgba):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def write_icon(path=ICON, sizes=(16, 24, 32, 48, 64, 256)):
    """An .ico with one PNG image per size (Windows Vista and later read these)."""
    images = [_png(n, _render(n, ss=4 if n <= 64 else 2)) for n in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for n, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(images))
    return path


# ---------------------------------------------------------------------------
# Shortcut
# ---------------------------------------------------------------------------
def _powershell(script):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"PowerShell failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def special_folder(name):
    """Desktop / Programs folder as Windows reports it (follows OneDrive redirection)."""
    return Path(_powershell(f"[Environment]::GetFolderPath('{name}')"))


def check_packages(python):
    """Exit with the fix if this Python can't run the desktop app."""
    r = subprocess.run([str(python), "-c", "import customtkinter, rich"], capture_output=True, text=True)
    if r.returncode:
        missing = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "an import failed"
        raise SystemExit(f"This Python can't run the desktop app ({missing}).\n"
                         f"Fix:  \"{python}\" -m pip install -r \"{ROOT / 'requirements.txt'}\"\n"
                         f"then run this script again.")


def make_shortcut(folder, pythonw):
    link = folder / f"{NAME}.lnk"
    q = lambda p: str(p).replace("'", "''")      # PowerShell single-quoted string
    _powershell(
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('" + q(link) + "'); "
        f"$s.TargetPath = '{q(pythonw)}'; "
        f"$s.Arguments = '\"{q(APP)}\"'; "
        f"$s.WorkingDirectory = '{q(ROOT)}'; "
        f"$s.IconLocation = '{q(ICON)},0'; "
        "$s.Description = 'Rubik''s Cube practice timer (desktop app)'; "
        "$s.WindowStyle = 1; $s.Save()")
    return link


def main():
    parser = argparse.ArgumentParser(description="Desktop shortcut for the Cube Timer desktop app")
    parser.add_argument("--start-menu", action="store_true", help="also add it to the Start menu")
    parser.add_argument("--remove", action="store_true", help="remove the shortcut(s)")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This makes a Windows shortcut; on other systems run: python cube_timer_gui.py")

    folders = [special_folder("Desktop")] + ([special_folder("Programs")] if args.start_menu or args.remove else [])
    if args.remove:
        for folder in folders:
            link = folder / f"{NAME}.lnk"
            if link.exists():
                link.unlink()
                print(f"Removed {link}")
        return

    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    if not pythonw.exists():
        raise SystemExit(f"No pythonw.exe next to {python}; run this script with a regular Python install.")
    check_packages(python.with_name("python.exe") if python.name.lower() == "pythonw.exe" else python)

    if not ICON.exists():
        write_icon()
        print(f"Drew {ICON.name}")
    for folder in folders:
        print(f"Made {make_shortcut(folder, pythonw)}")
    print(f"It runs: \"{pythonw}\" \"{APP}\"")


if __name__ == "__main__":
    main()
