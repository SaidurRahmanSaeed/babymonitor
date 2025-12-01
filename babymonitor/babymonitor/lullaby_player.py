# lullaby_player.py
import subprocess
from pathlib import Path
from threading import Lock

SOUNDS_DIR = Path("sounds")

_lullaby_process = None
_lock = Lock()


def _get_sound_path(name: str) -> Path:
    """
    Map a simple name to a file in sounds/.
    """
    candidates = {
        "lullaby1": SOUNDS_DIR / "lullaby1.wav",
        "whitenoise": SOUNDS_DIR / "whitenoise.wav",
    }
    return candidates.get(name)


def play_lullaby(name: str) -> bool:
    """
    Start playing a lullaby by name.
    Returns True if started, False if file not found.
    """
    global _lullaby_process
    with _lock:
        # Stop any existing playback first
        if _lullaby_process and _lullaby_process.poll() is None:
            _lullaby_process.terminate()
            _lullaby_process = None

        sound_path = _get_sound_path(name)
        if not sound_path or not sound_path.exists():
            print(f"[Lullaby] Sound '{name}' not found.")
            return False

        # Use ffplay in "no display" and "no interaction" mode
        cmd = [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel", "quiet",
            str(sound_path),
        ]
        print(f"[Lullaby] Playing {sound_path}")
        _lullaby_process = subprocess.Popen(cmd)
        return True


def stop_lullaby():
    """
    Stop any currently playing lullaby.
    """
    global _lullaby_process
    with _lock:
        if _lullaby_process and _lullaby_process.poll() is None:
            print("[Lullaby] Stopping playback")
            _lullaby_process.terminate()
            _lullaby_process = None
        else:
            print("[Lullaby] No active playback.")
