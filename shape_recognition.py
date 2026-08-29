import cv2
import numpy as np
import collections

PREVIEW_WIDTH = 640
HISTORY_LEN = 12
STABLE_VOTES = 6
MIN_OBJECT_AREA = 0.02

def skin_mask(frame):
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8), iterations=1)
    mask = cv2.GaussianBlur(mask, (9, 9), 0)
    return mask

def angle_between(a, b, c):
    v1 = a - b
    v2 = c - b
    denom = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom == 0:
        return 180.0
    return np.degrees(np.arccos(np.clip(np.dot(v1, v2) / denom, -1.0, 1.0)))

def interior_angles(approx):
    pts = approx.reshape(-1, 2)
    angles = []
    for i in range(len(pts)):
        angles.append(angle_between(pts[i - 1], pts[i], pts[(i + 1) % len(pts)]))
    return angles

def polygon_iou(contour, approx):
    x, y, w, h = cv2.boundingRect(contour)
    if w < 3 or h < 3:
        return 0.0
    off = np.array([x, y], np.int32)

    def mask(arr):
        m = np.zeros((h + 1, w + 1), np.uint8)
        pts = arr.reshape(-1, 2).astype(np.int32) - off
        cv2.fillPoly(m, [pts.reshape(-1, 1, 2)], 255)
        return m

    m1 = mask(contour)
    m2 = mask(approx)
    union = cv2.countNonZero(cv2.bitwise_or(m1, m2))
    if union == 0:
        return 0.0
    return cv2.countNonZero(cv2.bitwise_and(m1, m2)) / union

def best_polygon_fits(contour):
    smooth = contour.reshape(-1, 2).astype(np.float32)
    n = len(smooth)
    half = 2 if n >= 40 else (1 if n >= 12 else 0)
    if half:
        idx = (np.arange(n)[:, None] + np.arange(-half, half + 1)) % n
        smooth = smooth[idx].mean(axis=1).astype(np.int32).reshape(-1, 1, 2)
    per = cv2.arcLength(smooth, True)
    fits = {}
    if per <= 0:
        return fits
    for eps in np.linspace(0.01, 0.18, 25):
        approx = cv2.approxPolyDP(smooth, eps * per, True)
        k = len(approx)
        if k < 3 or k > 8:
            continue
        iou = polygon_iou(contour, approx)
        if iou > fits.get(k, (0, None))[0]:
            fits[k] = (iou, approx)
    return fits

def classify_with_metrics(contour):
    result = {
        "label": "None", "confidence": 0.0, "iou": 0.0, "n": 0,
        "circle_fill": 0.0, "circularity": 0.0, "ellipse_fill": 0.0,
        "aspect": 0.0, "rect_fill": 0.0, "angles": [],
    }
    if contour is None or len(contour) < 3:
        return result
    area = cv2.contourArea(contour)
    per = cv2.arcLength(contour, True)
    if area <= 0 or per <= 0:
        return result

    def conf(score):
        return round(float(np.clip(score, 0.0, 0.99)), 3)

    _, r = cv2.minEnclosingCircle(contour)
    circle_fill = area / (np.pi * r * r) if r > 0 else 0
    circularity = 4 * np.pi * area / (per * per)
    hue_circle = False
    try:
        hull = cv2.convexHull(contour)
        harea = cv2.contourArea(hull)
        hper = cv2.arcLength(hull, True)
        if harea > 0 and hper > 0:
            hr = cv2.minEnclosingCircle(hull)[1]
            h_fill = harea / (np.pi * hr * hr) if hr > 0 else 0
            h_circ = 4 * np.pi * harea / (hper * hper)
            hue_circle = h_fill > 0.90 and h_circ > 0.88 and circle_fill > 0.70
    except cv2.error:
        pass
    result.update(circle_fill=round(float(circle_fill), 4),
                  circularity=round(float(circularity), 4))
    if (circle_fill > 0.83 and circularity > 0.83) or hue_circle:
        result.update(label="Circle",
                      confidence=conf(0.40 + 0.60 * min(circle_fill, circularity)))
        return result

    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    rw, rh = rect[1]
    aspect = max(rw, rh) / min(rw, rh) if min(rw, rh) > 0 else 0
    rect_fill = area / abs(cv2.contourArea(box)) if abs(cv2.contourArea(box)) > 0 else 0
    ellipse_fill = 0.0
    try:
        ellipse = cv2.fitEllipse(contour)
        ea = ellipse[1]
        ellipse_fill = area / (np.pi * ea[0] * ea[1] / 4) if min(ea) > 0 else 0
    except cv2.error:
        ellipse_fill = 0.0
    result.update(aspect=round(float(aspect), 4), rect_fill=round(float(rect_fill), 4),
                  ellipse_fill=round(float(ellipse_fill), 4))

    fits = best_polygon_fits(contour)
    if fits:
        scored = []
        for n, (iou, approx) in fits.items():
            angles = interior_angles(approx)
            flat = sum(1 for a in angles if a > 135)
            scored.append((flat, iou, n))
        scored.sort(key=lambda s: (s[0], -s[1], s[2]))
        _, iou, n = scored[0]
        approx = fits[n][1]
        angles = interior_angles(approx)
        result.update(iou=round(float(iou), 4), n=n,
                      angles=[round(a, 1) for a in angles])

        if n == 3:
            if ellipse_fill > 0.80 and aspect > 1.3 and min(angles) < 45:
                result.update(label="Oval", confidence=conf(ellipse_fill))
            elif iou >= 0.76:
                result.update(label="Triangle", confidence=conf(iou))
            return result
        if n == 4:
            right_angles = sum(1 for a in angles if abs(a - 90) <= 25)
            if right_angles >= 3:
                result.update(label="Square" if aspect <= 1.1 else "Rectangle",
                              confidence=conf(iou))
                return result
            if ellipse_fill > 0.80 and aspect > 1.3:
                result.update(label="Oval", confidence=conf(ellipse_fill))
                return result
            if iou >= 0.78:
                result.update(label="Quadrilateral", confidence=conf(iou))
            return result
        if n == 5:
            if ellipse_fill > 0.80 and aspect > 1.3:
                result.update(label="Oval", confidence=conf(ellipse_fill))
            elif iou >= 0.78 and min(angles) >= 55 and max(angles) <= 148:
                result.update(label="Pentagon", confidence=conf(iou))
            elif rect_fill > 0.86:
                result.update(label="Square" if aspect <= 1.15 else "Rectangle",
                              confidence=conf(max(iou, rect_fill)))
            return result
        if n == 6:
            if ellipse_fill > 0.80 and aspect > 1.3:
                result.update(label="Oval", confidence=conf(ellipse_fill))
            elif iou >= 0.78 and min(angles) >= 90 and max(angles) <= 152:
                result.update(label="Hexagon", confidence=conf(iou))
            elif rect_fill > 0.86:
                result.update(label="Square" if aspect <= 1.15 else "Rectangle",
                              confidence=conf(max(iou, rect_fill)))
            return result
        if ellipse_fill > 0.80 and aspect > 1.3:
            result.update(label="Oval", confidence=conf(ellipse_fill))
            return result
        if rect_fill > 0.86:
            result.update(label="Square" if aspect <= 1.15 else "Rectangle",
                          confidence=conf(max(iou, rect_fill)))
    return result

def classify_geometric(contour):
    return classify_with_metrics(contour)["label"]

def extract_features(contour):
    m = classify_with_metrics(contour)
    x, y, w, h = cv2.boundingRect(contour)
    if w < 2 or h < 2:
        return np.zeros(20, np.float32)
    mask = np.zeros((h + 1, w + 1), np.uint8)
    cv2.fillPoly(mask, [contour.reshape(-1, 1, 2).astype(np.int32) - np.array([x, y])], 255)
    hu = cv2.HuMoments(cv2.moments(mask)).flatten()
    hu_log = [np.sign(v) * np.log10(abs(v) + 1.0) for v in hu]
    fits = best_polygon_fits(contour)
    ious = [round(fits.get(k, (0, None))[0], 4) if fits else 0.0 for k in range(3, 9)]
    vec = (hu_log + [m["circle_fill"], m["circularity"], m["aspect"],
                     m["rect_fill"], m["ellipse_fill"]] + ious)
    return np.asarray(vec, np.float32)

def detect_objects(img, max_objects=20, min_area_frac=0.0012, apply_skin=False):
    h, w = img.shape[:2]
    orig_wh = (w, h)
    used_w, used_h = w, h
    if w > 1000:
        used_w = 1000
        used_h = int(h * used_w / w)
        img = cv2.resize(img, (used_w, used_h))
    hh, ww = used_h, used_w

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    skin = skin_mask(img) if apply_skin else None
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    small_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    masks = [cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1],
             cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]]
    try:
        ad_inv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 51, 12)
        ad_norm = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 51, 12)
        masks.extend([ad_inv, ad_norm])
    except cv2.error:
        pass

    raw = []
    for b in masks:
        if skin is not None:
            b = cv2.bitwise_and(b, cv2.bitwise_not(skin))
        b = cv2.morphologyEx(b, cv2.MORPH_OPEN, small_k, iterations=1)
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, kernel, iterations=1)
        contours, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        raw.extend(contours)

    contours = []
    for c in raw:
        x, y, w, h = cv2.boundingRect(c)
        dup = False
        for d in contours:
            dx, dy, dw, dh = cv2.boundingRect(d)
            ix = max(0, min(x + w, dx + dw) - max(x, dx))
            iy = max(0, min(y + h, dy + dh) - max(y, dy))
            un = ix * iy
            if un > 0.55 * min(w * h, dw * dh):
                dup = True
                break
        if not dup:
            contours.append(c)

    min_a = min_area_frac * hh * ww
    cap = 0.90 * hh * ww
    sx, sy = orig_wh[0] / used_w, orig_wh[1] / used_h
    cands = []
    for c in contours:
        a = cv2.contourArea(c)
        if a < min_a or a >= cap:
            continue
        bx, by, bw, bh = cv2.boundingRect(c)
        m = classify_with_metrics(c)
        f = extract_features(c)
        cands.append({
            "area": a, "contour": c, "features": f, "metrics": m,
            "box": (int(bx * sx), int(by * sy), int(bw * sx), int(bh * sy)),
        })
    cands.sort(key=lambda x: -x["area"])
    return cands[:max_objects]

def find_main_contour(frame):
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    small_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    _, inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, norm = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    skin = skin_mask(frame)

    best, best_area = None, 0
    cap = 0.90 * h * w
    for b in (inv, norm):
        b = cv2.bitwise_and(b, cv2.bitwise_not(skin))
        b = cv2.morphologyEx(b, cv2.MORPH_OPEN, small_k, iterations=1)
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, kernel, iterations=3)
        contours, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            a = cv2.contourArea(c)
            if a > best_area and a < cap:
                best, best_area = c, a

    min_area = MIN_OBJECT_AREA * h * w
    if best is not None and best_area >= min_area:
        return best

    best2, best2_area = None, 0
    for b in (inv, norm):
        b = cv2.morphologyEx(b, cv2.MORPH_OPEN, small_k, iterations=1)
        b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, kernel, iterations=3)
        contours, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            a = cv2.contourArea(c)
            if a > best2_area and a < cap:
                best2, best2_area = c, a
    if best2 is not None and best2_area >= min_area:
        return best2
    return None

def portrait(frame, contour):
    h, w = frame.shape[:2]
    blurred = cv2.GaussianBlur(frame, (31, 31), 0)
    mask = np.zeros((h, w), np.uint8)
    if contour is not None and len(contour) > 2:
        cv2.drawContours(mask, [cv2.convexHull(contour)], -1, 255, -1)
    feather = cv2.GaussianBlur(mask, (61, 61), 0).astype(np.float32) / 255.0
    feather = cv2.merge([feather, feather, feather])
    return (frame * feather + blurred * (1.0 - feather)).astype(np.uint8)

def draw_label(frame, text, pos, scale, color, thickness=2):
    x, y = int(pos[0]), int(pos[1])
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    cv2.rectangle(frame, (x - 6, y - th - 8), (x + tw + 6, y + 8), (0, 0, 0), -1)
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)

def stable_label(history):
    counts = collections.Counter(history)
    winner, votes = counts.most_common(1)[0]
    return winner if votes >= STABLE_VOTES else None

def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    history = collections.deque(maxlen=HISTORY_LEN)
    print("Show ONE shape close to the camera. Press 'q' to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame.")
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        if w > PREVIEW_WIDTH:
            frame = cv2.resize(frame, (PREVIEW_WIDTH, int(h * PREVIEW_WIDTH / w)))
        h, w = frame.shape[:2]

        contour = find_main_contour(frame)

        shape = "None"
        if contour is not None:
            shape = classify_geometric(contour)
        history.append(shape)

        winner = stable_label(history)
        display = portrait(frame, contour)

        if contour is not None:
            cx, cy = np.int32(contour[:, 0]).mean(axis=0)
            color = (0, 0, 255) if winner is None else (255, 0, 0)
            cv2.drawContours(display, [contour], -1, color, 3)
            if winner is not None:
                draw_label(display, winner, (cx - 40, cy), 0.9, (255, 0, 0), 3)

        if winner is not None:
            area_pct = 100 * cv2.contourArea(contour) / (h * w)
            draw_label(display, f"SHAPE: {winner}  ({area_pct:.0f}% of frame)", (15, 45), 0.9, (255, 0, 0), 3)
        else:
            draw_label(display, "Show one shape close to the camera", (15, 45), 0.7, (255, 255, 255))
        if contour is not None:
            draw_label(display, f"per-frame: {shape}", (15, 80), 0.5, (0, 255, 255))

        cv2.imshow("Shape Recognition", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()