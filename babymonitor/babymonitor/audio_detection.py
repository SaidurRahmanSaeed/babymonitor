# audio_detection.py
import time
import json
import queue
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
from scipy.io import wavfile  # pip/apt: python3-scipy (if needed)

CONFIG_PATH = Path("config/settings.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def normalise_audio(data):
    """
    Convert any integer/float audio array to float32 in [-1, 1] range.
    """
    import numpy as np

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
    """Return RMS energy of an array of samples in range [-1, 1]."""
    import numpy as np

    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return 0.0

    # Remove NaN/inf values if any
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(samples * samples)))



def analyse_training_wavs():
    """
    Simple helper to look at energy in your baby-cry samples.
    Run this once to get a feeling for what threshold to use.
    """
    config = load_config()
    sr_target = config["sample_rate"]
    audio_folder = Path("audio")

    for wav_path in sorted(audio_folder.glob("baby-crying-*.wav")):
        sr, data = wavfile.read(wav_path)

        # Normalise all integer/float types to float32 in [-1,1]
        data = normalise_audio(data)

        # If stereo, take one channel
        if data.ndim > 1:
            data = data[:, 0]

        # Resampling is skipped here for simplicity; ideally match sr_target
        frame_size = int(sr * config["frame_duration_sec"])
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
    When cry is detected, it calls the callback.
    """

    def __init__(self, on_cry_callback):
        super().__init__(daemon=True)
        self.config = load_config()
        self.sample_rate = self.config["sample_rate"]
        self.frame_duration = self.config["frame_duration_sec"]
        self.threshold = self.config["cry_energy_threshold"]
        self.frames_required = self.config["cry_frames_required"]
        self.on_cry_callback = on_cry_callback

        self._audio_queue = queue.Queue()
        self._running = False
        self._cry_frame_count = 0

        # NEW: cooldown between events (seconds)
        self._last_event_time = 0.0
        self.event_cooldown = 5.0  # seconds

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print("Audio status:", status)
        # indata shape: (frames, channels)
        mono = indata[:, 0]
        self._audio_queue.put(mono.copy())

    def run(self):
        """
        Main loop of the cry detector.
        - Opens the microphone input stream.
        - Reads audio frames from the queue.
        - Computes energy for each frame.
        - Triggers a 'cry detected' event only if:
            * energy >= threshold for frames_required consecutive frames, and
            * at least event_cooldown seconds have passed since last event.
        """
        import sounddevice as sd
        import queue as _queue  # to avoid confusion with module name

        self._running = True
        print("[CryDetector] Starting audio stream...")

        try:
            # Open audio input stream (mono)
            with sd.InputStream(
                channels=1,
                samplerate=self.sample_rate,
                callback=self._audio_callback,
            ):
                # Main processing loop
                while self._running:
                    try:
                        # Wait for next frame from callback
                        frame = self._audio_queue.get(timeout=1.0)
                    except _queue.Empty:
                        # No audio arrived in 1 second, just loop again
                        continue

                    # Calculate RMS energy for this frame
                    energy = compute_frame_energy(frame)
                    current_time = time.time()

                    # Check against threshold
                    if energy >= self.threshold:
                        self._cry_frame_count += 1
                    else:
                        # Reset if this frame is quiet
                        self._cry_frame_count = 0

                    # If we got enough loud frames in a row…
                    if self._cry_frame_count >= self.frames_required:
                        # …check cooldown to avoid spamming events
                        if current_time - self._last_event_time >= self.event_cooldown:
                            print(f"[CryDetector] Cry detected! energy={energy:.4f}")
                            self._last_event_time = current_time

                            # Call the user-provided callback in the same thread
                            if self.on_cry_callback:
                                self.on_cry_callback(energy)

                        # Reset counter so we don't instantly retrigger
                        self._cry_frame_count = 0

                    # Small sleep to be kind to CPU
                    time.sleep(0.01)

        except Exception as e:
            print("[CryDetector] ERROR opening or reading audio input:", e)

        finally:
            self._running = False
            print("[CryDetector] Stopped.")



if __name__ == "__main__":
    # Small manual test: analyse samples or start live detection
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
