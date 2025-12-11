import os
import subprocess
from pathlib import Path
from threading import RLock   # RLock avoids deadlock when stop is called inside play

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"

_lullaby_process = None
_lock = RLock()

def _resolve_sound(name: str):
    """
    Accept 'lullaby1', 'lullaby1.wav', or 'sounds/lullaby1.wav'.
    """
    p = Path(name)
    if not p.suffix:  # no extension given -> assume wav in sounds/
        p = SOUNDS_DIR / f"{name}.wav"
    elif not p.is_absolute() and p.parts and p.parts[0] != "sounds":
        # relative path like 'lullaby1.wav' -> look under sounds/
        p = SOUNDS_DIR / p.name
    if p.exists():
        return p
    # canonical short names mapping
    mapping = {
        "lullaby1": SOUNDS_DIR / "lullaby1.wav",
        "whitenoise": SOUNDS_DIR / "whitenoise.wav",
    }
    q = mapping.get(name)
    return q if q and q.exists() else None

def play_lullaby(name: str) -> bool:
    """
    Stop any previous playback and start a new one with aplay.
    Honors APLAY_DEVICE if set (e.g., 'plughw:2,0').
    """
    global _lullaby_process
    with _lock:
        # stop any previous playback (safe if none)
        if _lullaby_process and _lullaby_process.poll() is None:
            try:
                _lullaby_process.terminate()
            finally:
                _lullaby_process = None

        sound_path = _resolve_sound(name)
        if not sound_path:
            print(f"[Lullaby] Sound '{name}' not found under {SOUNDS_DIR}")
            return False

        dev = os.getenv("APLAY_DEVICE")
        cmd = ["aplay"]
        if dev:
            cmd += ["-D", dev]
        cmd += ["-q", str(sound_path)]

        print("[Lullaby] running:", " ".join(cmd))
        try:
            _lullaby_process = subprocess.Popen(cmd)
            return True
        except Exception as e:
            print(f"[Lullaby] Failed to start playback: {e}")
            _lullaby_process = None
            return False

def stop_lullaby():
    """
    Stop playback if it is running.
    """
    global _lullaby_process
    with _lock:
        if _lullaby_process and _lullaby_process.poll() is None:
            print("[Lullaby] Stopping playback")
            try:
                _lullaby_process.terminate()
            finally:
                _lullaby_process = None
        else:
            print("[Lullaby] No active playback.")
