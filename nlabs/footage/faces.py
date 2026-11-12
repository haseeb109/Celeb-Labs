# footage/faces.py — Rule F8: is the person on screen really the subject?
# Backends (auto order): insightface buffalo_s → face_recognition → OpenCV YuNet+SFace
# (models auto-downloaded to cache/faces/) → none (then no clip may CLAIM the subject).
from __future__ import annotations

import numpy as np

from ..paths import cache_dir
from ..log import get_logger

log = get_logger()
YUNET = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"


def _download(url, name):
    p = cache_dir("faces") / name
    if not p.exists():
        import httpx
        r = httpx.get(url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        p.write_bytes(r.content)
    return str(p)


class FaceBackend:
    name = "none"
    available = False

    def faces(self, bgr: np.ndarray) -> list[tuple[tuple, np.ndarray | None]]:
        """Return [(box normalized (x0,y0,x1,y1), embedding or None)]."""
        return []

    def similarity(self, a, b) -> float:
        a, b = np.asarray(a, np.float32), np.asarray(b, np.float32)
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class InsightFace(FaceBackend):
    name = "insightface"

    def __init__(self):
        from insightface.app import FaceAnalysis
        self.app = FaceAnalysis(name="buffalo_s", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        self.available = True

    def faces(self, bgr):
        h, w = bgr.shape[:2]
        return [((f.bbox[0] / w, f.bbox[1] / h, f.bbox[2] / w, f.bbox[3] / h), f.normed_embedding)
                for f in self.app.get(bgr)]


class FaceRecognitionLib(FaceBackend):
    name = "face_recognition"

    def __init__(self):
        import face_recognition  # noqa
        self.fr = face_recognition
        self.available = True

    def faces(self, bgr):
        rgb = bgr[:, :, ::-1].copy()
        h, w = rgb.shape[:2]
        locs = self.fr.face_locations(rgb)
        encs = self.fr.face_encodings(rgb, locs)
        return [((l[3] / w, l[0] / h, l[1] / w, l[2] / h), e) for l, e in zip(locs, encs)]

    def similarity(self, a, b):  # convert distance (<=0.5 good) to a 0..1 similarity on the same threshold scale
        d = float(np.linalg.norm(np.asarray(a) - np.asarray(b)))
        return max(0.0, 1.0 - d) * 0.45 / 0.5


class OpenCVSFace(FaceBackend):
    name = "opencv_sface"

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.det = cv2.FaceDetectorYN.create(_download(YUNET, "yunet.onnx"), "", (320, 320), 0.8)
        self.rec = cv2.FaceRecognizerSF.create(_download(SFACE, "sface.onnx"), "")
        self.available = True

    def faces(self, bgr):
        h, w = bgr.shape[:2]
        scale = 640 / max(w, h)
        img = self.cv2.resize(bgr, (int(w * scale), int(h * scale))) if scale < 1 else bgr
        ih, iw = img.shape[:2]
        self.det.setInputSize((iw, ih))
        _, faces = self.det.detect(img)
        out = []
        for f in faces if faces is not None else []:
            aligned = self.rec.alignCrop(img, f)
            emb = self.rec.feature(aligned).flatten()
            x, y, fw, fh = f[:4]
            out.append(((x / iw, y / ih, (x + fw) / iw, (y + fh) / ih), emb))
        return out


_backend = None


def get_backend(pref: str = "auto") -> FaceBackend:
    global _backend
    if _backend is not None and (pref == "auto" or _backend.name == pref):
        return _backend
    order = [pref] if pref not in ("auto", "") else ["insightface", "face_recognition", "opencv_sface"]
    for name in order:
        try:
            _backend = {"insightface": InsightFace, "face_recognition": FaceRecognitionLib,
                        "opencv_sface": OpenCVSFace, "none": FaceBackend}[name]()
            log.info(f"face backend: {_backend.name}")
            return _backend
        except Exception as e:
            log.info(f"face backend {name} unavailable: {type(e).__name__}")
    _backend = FaceBackend()
    log.warning("no face backend — clips cannot be claimed to show the subject (F8)")
    return _backend


def build_reference(images: list[np.ndarray], backend: FaceBackend) -> np.ndarray | None:
    """Average embedding of the largest face in each trusted image."""
    embs = []
    for im in images:
        fs = [f for f in backend.faces(im) if f[1] is not None]
        if fs:
            big = max(fs, key=lambda f: (f[0][2] - f[0][0]) * (f[0][3] - f[0][1]))
            e = np.asarray(big[1], np.float32)
            embs.append(e / (np.linalg.norm(e) + 1e-9))
    if not embs:
        return None
    m = np.mean(embs, axis=0)
    return m / (np.linalg.norm(m) + 1e-9)


def match(frames: list[np.ndarray], reference, backend: FaceBackend, threshold: float) -> dict:
    """Face-match 3 frames. Returns {score, subject_present, face_box, n_faces}."""
    best, box, nf = 0.0, None, 0
    for f in frames[:3]:
        for b, e in backend.faces(f):
            nf += 1
            if reference is not None and e is not None:
                s = backend.similarity(e, reference)
                if s > best:
                    best, box = s, b
            elif box is None:
                box = b
    return {"score": round(best, 3), "subject_present": reference is not None and best >= threshold,
            "face_box": box, "n_faces": nf}
