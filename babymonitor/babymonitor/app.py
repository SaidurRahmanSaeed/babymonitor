# app.py
import threading
import time
from datetime import datetime

from flask import Flask, render_template, Response, jsonify

from audio_detection import CryDetector
# for pi OS camera module support
from camera_stream import mjpeg_frame_generator

# windows OS
import platform

if platform.system() == "Windows":
    # Simple dummy generator that serves a static black image
    from io import BytesIO
    from PIL import Image

    def mjpeg_frame_generator():
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
    from camera_stream import mjpeg_frame_generator


from lullaby_player import play_lullaby, stop_lullaby
from notifier import send_email_alert

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")


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
                if self.last_cry_time
                else None,
                "cry_count": self.cry_count,
            }


system_state = SystemState()
cry_detector = None


def on_cry_detected(energy: float):
    """
    Callback from CryDetector thread whenever a cry is detected.
    """
    print(f"[App] Cry callback received with energy {energy:.4f}")
    system_state.record_cry()

    # Send email alert (non-blocking thread)
    def send_alert():
        subject = "Baby Monitor Alert: Cry detected"
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        body = f"Cry detected at {time_str} with energy {energy:.4f}."
        send_email_alert(subject, body)

    threading.Thread(target=send_alert, daemon=True).start()


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


@app.route("/api/lullaby/<name>", methods=["POST"])
def api_lullaby_start(name):
    ok = play_lullaby(name)
    return jsonify({"ok": ok})


@app.route("/api/lullaby/stop", methods=["POST"])
def api_lullaby_stop():
    stop_lullaby()
    return jsonify({"ok": True})


def start_cry_detector():
    global cry_detector
    cry_detector = CryDetector(on_cry_detected)
    cry_detector.start()
    print("[App] CryDetector thread started.")


if __name__ == "__main__":
    # Start cry detection in background
    start_cry_detector()

    # Start Flask app
    # On Pi you might want host="0.0.0.0" so other devices on LAN can connect
    app.run(host="0.0.0.0", port=5000, debug=False)

