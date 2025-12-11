# audio_detection.py
import os
import time
import json
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io import wavfile  # apt/pip: python3-scipy

CONFIG_PATH = Path("config/settings.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def normalise_audio(data):
    """Convert any integer/float audio array to float32 in [-1, 1]."""
    data = np.asarray(data)
    if np.issubdtype(data.dtype, np.integer):
        max_val = float(np.iinfo(data.dtype).max)
        data = data.astype(np.float32) / max_val
    elif np.issubdtype(data.dtype, np.floating):
        data = data.astype(np.float32)
    else:
        data = data.astype(np.float32)
    return data


def compute_frame_energy(samples: np.ndarray) -> float:
    """Return RMS energy of an array of samples in [-1, 1]."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return 0.0
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def analyse_training_wavs():
    """Look at energy in your baby-cry samples to choose a threshold."""
    config = load_config()
    sr_target = config.get("sample_rate", 16000)
    audio_folder = Path("audio")

    for wav_path in sorted(audio_folder.glob("baby-crying-*.wav")):
        sr, data = wavfile.read(wav_path)
        data = normalise_audio(data)
        if data.ndim > 1:
            data = data[:, 0]
        frame_size = int(sr * config.get("frame_duration_sec", 0.5))
        energies = []
        for start in range(0, len(data), frame_size):
            frame = data[start:start + frame_size]
            e = compute_frame_energy(frame)
            energies.append(e)
        print(f"\nFile: {wav_path.name}")
        print("Frame energies (first 20):")
        print([round(e, 4) for e in energies[:20]])
        print(f"Max energy: {max(energies):.4f}")


class CryDetector(threading.Thread):
    """
    Background thread that listens to microphone and detects cries.
    Supports pause()/resume() so playback can mute detection temporarily.
    """

    def __init__(self, on_cry_callback):
        super().__init__(daemon=True)
        self.config = load_config()
        self.sample_rate = int(self.config.get("sample_rate", 16000))
        self.frame_duration = float(self.config.get("frame_duration_sec", 0.5))
        self.threshold = float(self.config.get("cry_energy_threshold", 0.12))
        self.frames_required = int(self.config.get("cry_frames_required", 3))
        self.on_cry_callback = on_cry_callback

        # Optional input device: index/int, name, or ALSA name; can also come from env
        self.input_device = self.config.get("input_device") or os.getenv("SD_INPUT_DEVICE")

        self._audio_queue = queue.Queue()
        self._running = False
        self._paused = False
        self._cry_frame_count = 0

        # cooldown between events (seconds)
        self._last_event_time = 0.0
        self.event_cooldown = float(self.config.get("event_cooldown_sec", 5.0))

    # --- external controls -------------------------------------------------

    def pause(self):
        """Temporarily suspend detection (used while playing lullaby)."""
        self._paused = True
        print("[CryDetector] Paused.")

    def resume(self):
        """Resume detection after lullaby stops."""
        self._paused = False
        print("[CryDetector] Resumed.")

    def stop(self):
        """Stop the thread loop cleanly."""
        self._running = False

    # --- audio plumbing ----------------------------------------------------

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print("Audio status:", status)
        # indata shape: (frames, channels), dtype float32 in [-1,1]
        mono = indata[:, 0]
        self._audio_queue.put(mono.copy())

    def _open_stream(self, samplerate):
        """Try to open the input stream with a given samplerate and device."""
        blocksize = int(max(1, round(samplerate * self.frame_duration)))
        kwargs = dict(
            channels=1,
            samplerate=int(samplerate),
            dtype="float32",
            callback=self._audio_callback,
            blocksize=blocksize,
        )
        if self.input_device:
            kwargs["device"] = self.input_device
        return sd.InputStream(**kwargs)

    # --- main loop ---------------------------------------------------------

    def run(self):
        self._running = True
        print("[CryDetector] Starting audio stream...")

        stream = None
        try:
            # First try the configured sample rate
            try:
                stream = self._open_stream(self.sample_rate)
            except sd.PortAudioError as e:
                if "Invalid sample rate" in str(e) or "paInvalidSampleRate" in str(e):
                    # Fallback commonly supported by USB mics (e.g., PCM2902)
                    fallback_sr = 48000
                    print(f"[CryDetector] {e}; retrying with {fallback_sr} Hz")
                    stream = self._open_stream(fallback_sr)
                    self.sample_rate = fallback_sr
                else:
                    raise

            with stream:
                while self._running:
                    try:
                        frame = self._audio_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue

                    if self._paused:
                        # Skip computation while paused
                        time.sleep(0.005)
                        continue

                    energy = compute_frame_energy(frame)
                    now = time.time()

                    if energy >= self.threshold:
                        self._cry_frame_count += 1
                    else:
                        self._cry_frame_count = 0

                    if self._cry_frame_count >= self.frames_required:
                        if now - self._last_event_time >= self.event_cooldown:
                            print(f"[CryDetector] Cry detected! energy={energy:.4f}")
                            self._last_event_time = now
                            if self.on_cry_callback:
                                self.on_cry_callback(energy)
                        self._cry_frame_count = 0

                    time.sleep(0.005)

        except Exception as e:
            print("[CryDetector] ERROR opening or reading audio input:", e)
        finally:
            self._running = False
            print("[CryDetector] Stopped.")


if __name__ == "__main__":
    print("1) Analyse training WAVs")
    print("2) Run live cry detection test")
    choice = input("Choose (1/2): ").strip()

    if choice == "1":
        analyse_training_wavs()
    elif choice == "2":
        def test_callback(e):
            print(f"Callback: cry detected with energy {e:.4f}")

        detector = CryDetector(test_callback)
        detector.start()
        print("Press Ctrl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            detector.stop()
            detector.join()
