(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* ------------------------------------------------------------------ *
   *  helpers
   * ------------------------------------------------------------------ */
  const fmtPct = (v) => `${Math.round((v || 0) * 100)}%`;

  function toast(msg, kind = "", ms = 3200) {
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    el.innerHTML = msg;
    $("toasts").appendChild(el);
    setTimeout(() => {
      el.classList.add("out");
      setTimeout(() => el.remove(), 350);
    }, ms);
  }

  const postJSON = (url, body) =>
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(async (r) => {
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
      return j;
    });

  const confColor = (v) =>
    v >= 0.8 ? "var(--green)" : v >= 0.5 ? "var(--amber)" : "var(--red)";
  const foundColor = (res) =>
    res && res.label && res.label !== "None" ? "var(--green)" : "rgba(140, 152, 180, 0.85)";

  /* ------------------------------------------------------------------ *
   *  cursor follower
   * ------------------------------------------------------------------ */
  const dot = document.querySelector(".cursor-dot");
  const ring = document.querySelector(".cursor-ring");
  let mx = window.innerWidth / 2, my = window.innerHeight / 2;
  let rx = mx, ry = my;
  if (window.matchMedia("(pointer: fine)").matches) {
    document.addEventListener("mousemove", (e) => {
      mx = e.clientX;
      my = e.clientY;
      dot.style.transform = `translate(${mx}px, ${my}px) translate(-50%, -50%)`;
    });
    document.addEventListener("mouseover", (e) => {
      document.body.classList.toggle("hovering", !!e.target.closest("button, .dropzone, a, .card"));
    });
    (function ringLoop() {
      rx += (mx - rx) * 0.16;
      ry += (my - ry) * 0.16;
      ring.style.transform = `translate(${rx}px, ${ry}px) translate(-50%, -50%)`;
      requestAnimationFrame(ringLoop);
    })();
  }

  /* ------------------------------------------------------------------ *
   *  starfield backdrop
   * ------------------------------------------------------------------ */
  (function stars() {
    const cv = $("stars"), ctx = cv.getContext("2d");
    let W, H, pts;
    const resize = () => {
      W = cv.width = innerWidth;
      H = cv.height = innerHeight;
      const n = Math.min(140, Math.floor((W * H) / 9000));
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 1.3 + 0.3,
        v: Math.random() * 0.12 + 0.02,
        tw: Math.random() * Math.PI * 2,
      }));
    };
    resize();
    addEventListener("resize", resize);
    const step = (t) => {
      ctx.clearRect(0, 0, W, H);
      for (const p of pts) {
        p.y -= p.v;
        if (p.y < -2) { p.y = H + 2; p.x = Math.random() * W; }
        const a = 0.35 + 0.5 * (0.5 + 0.5 * Math.sin(t / 900 + p.tw));
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, 7);
        ctx.fillStyle = `rgba(160,190,255,${a.toFixed(2)})`;
        ctx.fill();
      }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  })();

  /* ------------------------------------------------------------------ *
   *  model + server status
   * ------------------------------------------------------------------ */
  async function refreshModel() {
    try {
      const r = await fetch("/api/model");
      const d = await r.json();
      const stat = d.stats || {};
      $("modelChip").innerHTML = `MODEL&nbsp;·&nbsp;<b>${stat.samples}</b>&nbsp;samples&nbsp;·&nbsp;<b>${stat.corrections}</b>&nbsp;reviews`;
      const tag = $("serverChip");
      tag.classList.add("online");
      tag.innerHTML = "<i></i>server online";
    } catch {
      const tag = $("serverChip");
      tag.classList.remove("online");
      tag.innerHTML = "<i></i>offline";
    }
  }
  refreshModel();

  /* ================================================================== *
   *  LIVE RECOGNITION
   * ================================================================== */
  const camBtn = $("camBtn"), camBtnTxt = $("camBtnTxt");
  const video = $("cam"), overlay = $("camOverlay");
  const octx = overlay.getContext("2d");
  const liveTag = $("liveTag"), liveLabel = $("liveLabel"), liveHint = $("liveHint");
  const confRing = $("confRing"), confNum = $("confNum");
  const CIRC = 188.5;

  let stream = null, camLoopOn = false, camBusy = false, camFrame = 0, camSession = 0;
  const hist = [];

  const setConfRing = (v, found) => {
    const on = !!(found && (v || 0) > 0);
    confRing.style.strokeDashoffset = String(CIRC * (1 - (v || 0)));
    confRing.style.stroke = on ? "var(--green)" : "rgba(140, 152, 180, 0.85)";
    confNum.style.color = on ? "var(--green)" : "var(--muted)";
    confNum.textContent = fmtPct(v || 0);
  };

  function drawCamTick(res) {
    const cw = overlay.clientWidth, ch = overlay.clientHeight;
    octx.setTransform(cw / 640, 0, 0, ch / 480, 0, 0);
    octx.clearRect(0, 0, 640, 480);
    if (!res || !res.box) return;
    const [x, y, w, h] = res.box;
    const col = foundColor(res);
    octx.strokeStyle = col;
    octx.lineWidth = 2.5;
    octx.shadowColor = col;
    octx.shadowBlur = 14;
    octx.strokeRect(x, y, w, h);
    octx.shadowBlur = 0;
    const L = 16;
    octx.lineWidth = 4;
    octx.beginPath();
    [
      [x, y, 1, 1, 0, 0], [x + w, y, -1, 1, 0, 0],
      [x, y + h, 1, -1, 0, 0], [x + w, y + h, -1, -1, 0, 0],
    ].forEach(([cx, cy, dx, dy]) => {
      octx.moveTo(cx, cy);
      octx.lineTo(cx + L * dx, cy);
      octx.moveTo(cx, cy);
      octx.lineTo(cx, cy + L * dy);
    });
    octx.stroke();

    const label = `${res.label}  ${fmtPct(res.confidence)}`;
    const f = "600 13px Space Grotesk, system-ui";
    octx.font = f;
    const tw = octx.measureText(label).width;
    octx.fillStyle = "rgba(5,7,15,0.85)";
    octx.strokeStyle = col;
    octx.lineWidth = 1;
    octx.fillRect(x, Math.max(0, y - 24), tw + 16, 22);
    octx.strokeRect(x, Math.max(0, y - 24), tw + 16, 22);
    octx.fillStyle = col;
    octx.fillText(label, x + 8, Math.max(0, y - 9) + 7 - 1);
    octx.fillText(label, x + 8, Math.max(0, y - 9));
  }

  async function camTick() {
    if (!camLoopOn) return;
    const sid = camSession;
    camFrame++;
    if (!camBusy) {
      camBusy = true;
      try {
        octx.setTransform(1, 0, 0, 1, 0, 0);
        octx.drawImage(video, 0, 0, 640, 480);
        const url = overlay.toDataURL("image/jpeg", 0.7);
        const t0 = performance.now();
        const res = await postJSON("/api/frame", { image: url });
        if (sid !== camSession || !camLoopOn) return;
        $("latency").textContent = `▲ ${Math.round(performance.now() - t0)} ms · live`;
        hist.push({ label: res.label, conf: res.confidence });
        if (hist.length > 6) hist.shift();
        const counts = {};
        let conf = 0;
        for (const h of hist) counts[h.label] = (counts[h.label] || 0) + 1;
        const best = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
        if (best && best[1] >= 3 && best[0] !== "None") {
          const matched = hist.filter((h) => h.label === best[0]);
          conf = matched.reduce((s, m) => s + m.conf, 0) / matched.length;
          liveLabel.textContent = best[0];
          liveHint.textContent = "detected & stable";
          liveLabel.style.opacity = "1";
        } else {
          liveLabel.textContent = "—";
          liveHint.textContent = res.label === "None" ? "No object detected" : "detecting…";
          liveLabel.style.opacity = "0.45";
          conf = 0;
        }
        setConfRing(res.box ? res.confidence : 0, res.label && res.label !== "None");
        drawCamTick(res);
      } catch (e) {
        toast("Camera stream error: " + e.message, "err");
        camLoopOn = false;
        stopCam();
      } finally {
        camBusy = false;
      }
    }
    setTimeout(camTick, 130);
  }

  async function startCam() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Camera not available in this browser", "err");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
    } catch {
      toast("Could not access the camera — please grant permission", "err");
      return;
    }
    video.srcObject = stream;
    await video.play().catch(() => {});
    video.classList.add("on");
    $("camPlaceholder").classList.add("hidden");
    $("camPlaceholder").classList.remove("shown");
    liveTag.classList.add("live");
    liveTag.textContent = "LIVE";
    camBtnTxt.textContent = "Stop Camera";
    document.querySelector("span.btn-ico").textContent = "■";
    camSession++;
    camLoopOn = true;
    camTick();
    toast("Live recognition started — show a shape", "ok");
  }

  function stopCam() {
    camSession++;
    camLoopOn = false;
    hist.length = 0;
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
    video.srcObject = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    video.classList.remove("on");
    $("camPlaceholder").classList.remove("hidden");
    $("camPlaceholder").classList.add("shown");
    liveTag.classList.remove("live");
    liveTag.textContent = "OFFLINE";
    camBtnTxt.textContent = "Start Camera";
    document.querySelector("span.btn-ico").textContent = "▶";
    liveLabel.textContent = "—";
    liveHint.textContent = "No object detected";
    setConfRing(0, false);
    octx.clearRect(0, 0, 640, 480);
    $("latency").textContent = "camera idle";
  }

  camBtn.addEventListener("click", () => (camLoopOn || !!stream ? stopCam() : startCam()));

  /* ================================================================== *
   *  IMAGE ANALYSIS
   * ================================================================== */
  const dropzone = $("dropzone"), fileInput = $("fileInput");
  const previewWrap = $("previewWrap"), preview = $("preview");
  const pvctx = $("previewOverlay").getContext("2d");
  const analyzeBtn = $("analyzeBtn");
  const results = $("results"), objList = $("objList"), resultsSub = $("resultsSub");
  const reviewBtn = $("reviewBtn"), resetBtn = $("resetBtn");

  const state = { file: null, imgB64: null, objects: [], votes: {} };

  dropzone.addEventListener("click", () => fileInput.click());
  ["dragenter", "dragover"].forEach((e) =>
    dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((e) =>
    dropzone.addEventListener(e, (ev) => { ev.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", (ev) => {
    const f = ev.dataTransfer.files && ev.dataTransfer.files[0];
    if (f) loadImage(f);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) loadImage(fileInput.files[0]);
  });

  function loadImage(file) {
    if (!file.type.startsWith("image/")) { toast("Please choose an image file", "err"); return; }
    const fr = new FileReader();
    fr.onload = () => {
      state.imgB64 = fr.result;
      preview.onload = () => {
        dropzone.classList.add("hidden");
        previewWrap.classList.remove("hidden");
        results.classList.add("hidden");
        state.objects = [];
        state.votes = {};
        sizeOverlay();
      };
      preview.src = fr.result;
      state.file = file.name;
    };
    fr.readAsDataURL(file);
  }

  function sizeOverlay() {
    const c = $("previewOverlay");
    c.width = preview.clientWidth * devicePixelRatio;
    c.height = preview.clientHeight * devicePixelRatio;
  }
  addEventListener("resize", () => { if (!results.classList.contains("hidden")) { sizeOverlay(); drawBoxes(); } });

  analyzeBtn.addEventListener("click", async () => {
    if (!state.imgB64) return;
    analyzeBtn.disabled = true;
    analyzeBtn.querySelector(".btn-ico").innerHTML =
      '<span style="display:inline-block;animation:blink 0.8s infinite">⋯</span>';
    try {
      const res = await postJSON("/api/analyze", { image: state.imgB64, max_objects: 20 });
      state.objects = res.objects || [];
      renderResults();
      drawBoxes();
      refreshModel();
      toast(`Analysis complete — ${state.objects.length} object(s) found`, "ok");
    } catch (e) {
      toast("Analysis failed: " + e.message, "err");
    } finally {
      analyzeBtn.disabled = false;
      analyzeBtn.querySelector(".btn-ico").textContent = "⌁";
    }
  });

  resetBtn.addEventListener("click", () => {
    state.objects = [];
    state.votes = {};
    fileInput.value = "";
    previewWrap.classList.add("hidden");
    results.classList.add("hidden");
    dropzone.classList.remove("hidden");
  });

  function drawBoxes() {
    const c = $("previewOverlay");
    const dpr = devicePixelRatio;
    const sx = (preview.clientWidth / preview.naturalWidth);
    const sy = (preview.clientHeight / preview.naturalHeight);
    pvctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    pvctx.clearRect(0, 0, c.width, c.height);
    const place = (obj, i) => {
      const [bx, by, bw, bh] = obj.box;
      const x = bx * sx, y = by * sy, w = bw * sx, h = bh * sy;
      const col = foundColor(obj);
      pvctx.strokeStyle = col;
      pvctx.lineWidth = 2.5;
      pvctx.shadowColor = col;
      pvctx.shadowBlur = 16;
      pvctx.strokeRect(x, y, w, h);
      pvctx.shadowBlur = 0;
      const L = 15;
      pvctx.lineWidth = 4;
      pvctx.beginPath();
      [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]].forEach(([cx, cy, dx, dy]) => {
        pvctx.moveTo(cx, cy); pvctx.lineTo(cx + L * dx, cy);
        pvctx.moveTo(cx, cy); pvctx.lineTo(cx, cy + L * dy);
      });
      pvctx.stroke();

      const txt = `#${i + 1} ${obj.label}`;
      const ty = Math.max(26, y - 26);
      pvctx.font = "700 13px Space Grotesk, system-ui";
      const tw = pvctx.measureText(txt).width;
      pvctx.fillStyle = "rgba(5,7,15,0.88)";
      pvctx.fillRect(x, ty - 20, tw + 18, 26);
      pvctx.strokeStyle = col;
      pvctx.lineWidth = 1;
      pvctx.strokeRect(x, ty - 20, tw + 18, 26);
      pvctx.fillStyle = col;
      pvctx.fillText(txt, x + 9, ty - 2);
      pvctx.fillStyle = "rgba(255,255,255,0.85)";
      pvctx.fillText(`${fmtPct(obj.confidence)}`, x + 9, ty + 16);
    };
    state.objects.forEach(place);
  }

  function renderResults() {
    results.classList.remove("hidden");
    resultsSub.textContent = `${state.objects.length} object(s) detected`;
    objList.innerHTML = "";
    state.objects.forEach((obj, i) => {
      const isUnknown = obj.label === "None";
      const li = document.createElement("li");
      li.className = "obj";
      li.innerHTML = `
        <div class="obj-top">
          <div class="obj-idx">${i + 1}</div>
          <div class="obj-info">
            <div class="obj-label">${isUnknown ? '<span class="unknown">Unknown</span>' : obj.label}</div>
            <div class="conf-bar-wrap"><div class="conf-bar" style="background:${confColor(obj.confidence)}"></div></div>
          </div>
          <div class="conf-note">${fmtPct(obj.confidence)}</div>
        </div>
        <div class="obj-actions">
          <button class="voteBtn" data-v="yes">✓ Correct</button>
          <button class="voteBtn" data-v="no">✕ Wrong</button>
          <div class="correction-wrap hidden"><input type="text" placeholder="Type the correct shape (e.g. Triangle, Oval…)" /></div>
        </div>`;
      const bar = li.querySelector(".conf-bar");
      requestAnimationFrame(() => (bar.style.width = `${Math.round((obj.confidence || 0) * 100)}%`));
      state.votes[i] = { verdict: "", correction: "" };
      const yesBtn = li.querySelector('[data-v="yes"]');
      const noBtn = li.querySelector('[data-v="no"]');
      const inWrap = li.querySelector(".correction-wrap");
      const input = li.querySelector("input");
      const set = (v) => {
        state.votes[i].verdict = v;
        yesBtn.classList.toggle("on-yes", v === "yes");
        noBtn.classList.toggle("on-no", v === "no");
        inWrap.classList.toggle("hidden", v !== "no");
        reviewBtn.disabled = !Object.values(state.votes).some((vv) => vv.verdict);
      };
      yesBtn.addEventListener("click", () => set("yes"));
      noBtn.addEventListener("click", () => set("no"));
      input.addEventListener("input", () => (state.votes[i].correction = input.value.trim()));
      objList.appendChild(li);
    });
    reviewBtn.disabled = true;
  }

  reviewBtn.addEventListener("click", async () => {
    const votes = [];
    for (const i in state.votes) {
      const obj = state.objects[+i];
      const v = state.votes[i];
      if (!v.verdict) continue;
      votes.push({
        index: obj.index,
        detected: obj.label,
        confidence: obj.confidence,
        box: obj.box,
        verdict: v.verdict,
        correction: v.correction,
        features: obj.features,
      });
    }
    if (!votes.length) return;
    reviewBtn.disabled = true;
    try {
      const res = await postJSON("/api/feedback", { votes });
      const stored = res.stored || 0;
      toast(
        `Feedback saved ✓ Model learned <b>${stored}</b> new sample(s) — total <b>${res.samples}</b>`,
        "ok"
      );
      refreshModel();
    } catch (e) {
      toast("Could not submit feedback: " + e.message, "err");
      reviewBtn.disabled = false;
    }
  });
})();