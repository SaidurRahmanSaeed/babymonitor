# camera_stream.py
from picamera2 import Picamera2, Preview
import io
from threading import Lock
from time import sleep

from PIL import Image  # apt: python3-pil


_camera = None
_lock = Lock()


def init_camera():
    global _camera
    with _lock:
        if _camera is None:
            picam2 = Picamera2()
            config = picam2.create_preview_configuration(main={"size": (640, 480)})
            picam2.configure(config)
            picam2.start()
            _camera = picam2
            print("[Camera] Initialised Picamera2")


def get_jpeg_frame() -> bytes:
    """
    Capture a single JPEG frame from the camera.
    """
    global _camera
    if _camera is None:
        init_camera()

    # capture array, convert to JPEG in memory
    frame = _camera.capture_array()
    img = Image.fromarray(frame)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def mjpeg_frame_generator():
    """
    Generator to be used in a Flask Response for MJPEG streaming.
    """
    while True:
        frame = get_jpeg_frame()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        )
        sleep(0.05)  # ~20 fps
