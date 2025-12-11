# app.py
import os
import threading
import time
from datetime import datetime

from flask import Flask, render_template, Response, jsonify

from audio_detection import CryDetector
from lullaby_player import play_lullaby, stop_lullaby
from notifier import send_email_alert

import platform

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")

# ---------------- Camera (Windows stub vs Pi camera) ----------------
if platform.system() == "Windows":
    from io import BytesIO
    from PIL import Image

    def mjpeg_frame_generator():
        # Static black frame for Windows testing
        img = Image.new("RGB", (640, 480), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        frame = buf.getvalue()
        while True:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
else:
    # Real Pi camera generator (can raise if camera not connected)
    from camera_stream import mjpeg_frame_generator as _pi_mjpeg

    def mjpeg_frame_generator():
        """Safe wrapper so camera errors don’t crash Flask."""
        try:
            for chunk in _pi_mjpeg():
                yield chunk
        except Exception as e:
            print(f"[Video] Camera stream error: {e}")
            # End the generator; client will see disconnect instead of 500
            return

# ---------------- State ----------------
class SystemState:
    def __init__(self):
        self.last_cry_time = None
        self.cry_count = 0
        self.lock = threading.Lock()

    def record_cry(self):
        with self.lock:
            self.last_cry_time = datetime.now()
            self.cry_count += 1

    def to_dict(self):
        with self.lock:
            return {
                "last_cry_time": self.last_cry_time.isoformat(timespec="seconds")
                if self.last_cry_time else None,
                "cry_count": self.cry_count,
            }

system_state = SystemState()
cry_detector: CryDetector | None = None

# ---------------- Cry callback ----------------
def on_cry_detected(energy: float):
    print(f"[App] Cry callback received with energy {energy:.4f}")
    system_state.record_cry()

    def send_alert():
        try:
            subject = "Baby Monitor Alert: Cry detected"
            time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = f"Cry detected at {time_str} with energy {energy:.4f}."
            send_email_alert(subject, body)
        except Exception as e:
            # Never crash the app if email fails
            print(f"[Notifier] Email alert failed: {e}")

    threading.Thread(target=send_alert, daemon=True).start()

# ---------------- Routes ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    return Response(
        mjpeg_frame_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

@app.route("/api/status")
def api_status():
    return jsonify(system_state.to_dict())

# --- lullaby endpoints with pause/resume and extra logging ---
@app.route("/api/lullaby/<name>", methods=["POST"])
def api_lullaby_start(name):
    if cry_detector:
        cry_detector.pause()
    dev = os.getenv("APLAY_DEVICE")
    print(f"[Route] /api/lullaby/{name} APLAY_DEVICE={dev}")
    ok = play_lullaby(name)
    # keep paused while playing; user presses Stop to resume
    return jsonify({"ok": ok, "device": dev})

@app.route("/api/lullaby/stop", methods=["POST"])
def api_lullaby_stop():
    stop_lullaby()
    if cry_detector:
        cry_detector.resume()
    return jsonify({"ok": True})

# Optional manual control (handy while testing)
@app.route("/api/detect/pause", methods=["POST"])
def api_detect_pause():
    if cry_detector:
        cry_detector.pause()
    return jsonify({"ok": True})

@app.route("/api/detect/resume", methods=["POST"])
def api_detect_resume():
    if cry_detector:
        cry_detector.resume()
    return jsonify({"ok": True})

# ---------------- Boot ----------------
def start_cry_detector():
    global cry_detector
    cry_detector = CryDetector(on_cry_detected)
    cry_detector.start()
    print("[App] CryDetector thread started.")

if __name__ == "__main__":
    start_cry_detector()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
