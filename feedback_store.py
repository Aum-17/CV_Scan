import json
import os
import time
import threading

import numpy as np

SHAPES = ["Triangle", "Square", "Rectangle", "Pentagon", "Hexagon", "Circle", "Oval"]

SIM_THRESHOLD = 0.97
AGREE_COUNT = 2
PERSIST_EVERY = 1


class FeedbackStore:
    def __init__(self, root=None):
        if root is None:
            root = os.path.dirname(os.path.abspath(__file__))
        self.dir = os.path.join(root, "data")
        os.makedirs(self.dir, exist_ok=True)
        self.corrections_path = os.path.join(self.dir, "corrections.json")
        self.samples_path = os.path.join(self.dir, "model_samples.npz")
        self.lock = threading.Lock()
        self.corrections = []
        self.labels = []
        self.feats = []
        self._dirty = 0
        self.load()

    def load(self):
        if os.path.exists(self.corrections_path):
            try:
                with open(self.corrections_path) as f:
                    self.corrections = json.load(f)
            except Exception:
                self.corrections = []
        if os.path.exists(self.samples_path):
            try:
                d = np.load(self.samples_path, allow_pickle=True)
                self.labels = [str(x) for x in d["labels"].tolist()]
                self.feats = [np.asarray(x, np.float32) for x in d["feats"].tolist()]
            except Exception:
                self.labels, self.feats = [], []

    def _persist(self):
        with open(self.corrections_path, "w") as f:
            json.dump(self.corrections, f, indent=1, default=str)
        np.savez(self.samples_path,
                 labels=np.array(self.labels, dtype=object),
                 feats=np.array(self.feats, dtype=np.float32))

    def stats(self):
        with self.lock:
            return {"corrections": len(self.corrections), "samples": len(self.labels)}

    def add_feedback(self, votes):
        stored = 0
        with self.lock:
            for v in votes:
                verdict = str(v.get("verdict", "yes")).lower()
                detected = str(v.get("detected") or "None")
                correction = str(v.get("correction") or "").strip()
                label = detected if verdict == "yes" else (correction or None)
                if not label or label == "None":
                    continue
                feats = v.get("features") if isinstance(v.get("features"), list) else []
                rec = {
                    "label": label,
                    "detected": detected,
                    "verdict": verdict,
                    "correction": correction,
                    "confidence": float(v.get("confidence", 0.0)),
                    "box": v.get("box"),
                    "ts": time.time(),
                }
                self.corrections.append(rec)
                if label in SHAPES and len(feats) == 18:
                    self.labels.append(label)
                    self.feats.append(np.asarray(feats, np.float32))
                    stored += 1
            self._dirty += 1
            if self._dirty >= PERSIST_EVERY:
                self._persist()
                self._dirty = 0
        return {"stored": stored, **self.stats()}

    def refine(self, label, confidence, features):
        if label == "None" or features is None or not self.labels:
            return label, confidence
        try:
            f = np.asarray(features, np.float32)
            if f.size == 0 or not np.isfinite(f).all():
                return label, confidence
            fn = f / (np.linalg.norm(f) + 1e-9)
        except Exception:
            return label, confidence
        best = {}
        with self.lock:
            labs = list(self.labels)
            fts = list(self.feats)
        for lab, feat in zip(labs, fts):
            try:
                g = np.asarray(feat, np.float32) / (np.linalg.norm(feat) + 1e-9)
                sim = float(np.dot(fn, g))
            except Exception:
                continue
            if sim > SIM_THRESHOLD:
                if lab not in best:
                    best[lab] = [0.0, 0]
                best[lab][0] = max(best[lab][0], sim)
                best[lab][1] += 1
        if not best:
            return label, confidence
        lab = max(best, key=lambda k: (best[k][1], best[k][0]))
        agrees = best[lab][1]
        top_sim = best[lab][0]
        if agrees >= AGREE_COUNT or (agrees == 1 and top_sim > 0.995):
            if lab != label:
                return lab, round(min(0.99, max(confidence, 0.85)), 3)
            return label, max(confidence, 0.90)
        return label, confidence