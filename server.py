import base64
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import cv2

import shape_recognition as sr
import feedback_store as fb

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
STORE = fb.FeedbackStore(ROOT)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".json": "application/json; charset=utf-8",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def decode_b64_img(data):
    if isinstance(data, str) and data.startswith("data:"):
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    arr = np.frombuffer(raw, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def serialize_obj(o):
    m = o["metrics"]
    return {
        "label": m["label"],
        "confidence": m["confidence"],
        "box": [int(v) for v in o["box"]],
        "features": [round(float(x), 6) for x in o["features"]],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CVscan/1.0"

    def log_message(self, *args):
        pass

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _analyze(self, data):
        img = decode_b64_img(data.get("image", ""))
        if img is None:
            return self._json(400, {"error": "Could not decode image"})
        objs = sr.detect_objects(img, apply_skin=True,
                             max_objects=int(data.get("max_objects", 20) or 20))
        out = []
        for i, o in enumerate(objs, 1):
            s = serialize_obj(o)
            if s["label"] != "None":
                s["label"], s["confidence"] = STORE.refine(
                    s["label"], s["confidence"], s["features"])
            s["index"] = i
            out.append(s)
        return self._json(200, {"objects": out, "stats": STORE.stats()})

    def _frame(self, data):
        img = decode_b64_img(data.get("image", ""))
        if img is None:
            return self._json(400, {"error": "Could not decode frame"})
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]
        out = {"label": "None", "confidence": 0.0, "box": None, "stats": STORE.stats()}
        c = sr.find_main_contour(img)
        if c is not None:
            m = sr.classify_with_metrics(c)
            x, y, bw, bh = cv2.boundingRect(c)
            sx = 640 / w
            sy = 480 / h
            out["box"] = [int(x * sx), int(y * sy), int(bw * sx), int(bh * sy)]
            lbl, conf = m["label"], m["confidence"]
            if lbl != "None":
                lbl, conf = STORE.refine(lbl, conf, sr.extract_features(c))
            out["label"], out["confidence"] = lbl, conf
        return self._json(200, out)

    def _feedback(self, data):
        votes = data.get("votes", []) if isinstance(data, dict) else []
        res = STORE.add_feedback(votes)
        return self._json(200, {"ok": True, **res})

    def do_HEAD(self):
        self.do_GET(send_body=False)

    def do_GET(self, send_body=True):
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        if path == "/api/model":
            return self._json(200, {"stats": STORE.stats(), "shapes": fb.SHAPES})
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path.startswith("/static/"):
            fp = os.path.join(STATIC, path[len("/static/"):])
            base = os.path.realpath(STATIC)
        elif path == "/index.html":
            fp = os.path.join(STATIC, "index.html")
            base = os.path.realpath(STATIC)
        else:
            self.send_response(404)
            self.end_headers()
            return
        real = os.path.realpath(fp)
        if not (real == base or real.startswith(base + os.sep)) or not os.path.isfile(real):
            self.send_response(404)
            self.end_headers()
            return
        ext = os.path.splitext(real)[1].lower()
        try:
            body = open(real, "rb").read()
        except OSError:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            data = self._read_json()
            if path == "/api/analyze":
                return self._analyze(data)
            if path == "/api/frame":
                return self._frame(data)
            if path == "/api/feedback":
                return self._feedback(data)
        except Exception:
            traceback.print_exc()
            return self._json(500, {"error": "server error"})
        self.send_response(404)
        self.end_headers()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    port = 8000
    if argv and argv[0] == "--port" and len(argv) > 1:
        try:
            port = int(argv[1])
        except ValueError:
            port = 8000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"CV_scan -> http://127.0.0.1:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nCV_scan stopped")


if __name__ == "__main__":
    main()