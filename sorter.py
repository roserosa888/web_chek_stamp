"""Stamp sorter - เว็บแยกไฟล์รูป  (รัน: python sorter.py แล้วเปิด http://localhost:8000)"""
import json
import mimetypes
import shutil
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = Path(__file__).resolve().parent
PORT = 8000
EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
SOURCES = {"root": BASE, "_unmatched": BASE / "_unmatched"}
DESTS = {"checked": BASE / "checked", "not_stamp": BASE / "not_stamp"}
FOLDERS = {**SOURCES, **DESTS}
history = []  # [(moved_to_path, original_path)] สำหรับ undo


def list_images(folder):
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTS)


def safe_path(folder_key, name):
    folder = FOLDERS.get(folder_key)
    if folder is None or not name or "/" in name or "\\" in name or name in (".", ".."):
        return None
    return folder / name


def unique_target(folder, name):
    target = folder / name
    stem, suffix, i = target.stem, target.suffix, 1
    while target.exists():
        target = folder / f"{stem}_dup{i}{suffix}"
        i += 1
    return target


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/list":
            lists = {k: list_images(v) for k, v in FOLDERS.items()}
            self.send_json({
                "root": lists["root"],
                "_unmatched": lists["_unmatched"],
                "counts": {k: len(v) for k, v in lists.items()},
                "canUndo": bool(history),
            })
        elif path.startswith("/img/"):
            parts = path[len("/img/"):].split("/", 1)
            file = safe_path(*parts) if len(parts) == 2 else None
            if file is None or not file.is_file():
                self.send_error(404)
                return
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        if path == "/api/move":
            src = safe_path(req.get("src"), req.get("name"))
            dest = DESTS.get(req.get("dest"))
            if src is None or req.get("src") not in SOURCES or dest is None or not src.is_file():
                self.send_json({"error": "ไม่พบไฟล์หรือปลายทางไม่ถูกต้อง"}, 400)
                return
            dest.mkdir(exist_ok=True)
            target = unique_target(dest, src.name)
            shutil.move(str(src), str(target))
            history.append((target, src))
            self.send_json({"ok": True, "movedTo": f"{dest.name}/{target.name}"})
        elif path == "/api/undo":
            if not history:
                self.send_json({"error": "ไม่มีรายการให้ย้อนกลับ"}, 400)
                return
            moved, original = history.pop()
            if not moved.is_file() or original.exists():
                self.send_json({"error": "ย้อนกลับไม่ได้ (ไฟล์ถูกเปลี่ยนแปลง)"}, 409)
                return
            shutil.move(str(moved), str(original))
            src_key = "root" if original.parent == BASE else "_unmatched"
            self.send_json({"ok": True, "src": src_key, "name": original.name})
        else:
            self.send_error(404)


PAGE = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stamp Sorter</title>
<style>
  :root { --bg:#0f0f10; --panel:#18181b; --line:#2a2a2e; --text:#e6e6e6; --muted:#8a8a92;
          --accent:#4f8cff; --ok:#22a55a; --no:#d9443c; }
  * { box-sizing:border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--text);
               font-family:"Segoe UI","Noto Sans Thai",Tahoma,sans-serif; font-size:14px; }
  body { display:flex; }
  aside { width:340px; min-width:260px; background:var(--panel); border-right:1px solid var(--line);
          display:flex; flex-direction:column; }
  .counts { display:grid; grid-template-columns:1fr 1fr; gap:6px; padding:12px; border-bottom:1px solid var(--line); }
  .count { background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:6px 8px; }
  .count b { display:block; font-size:18px; }
  .count span { color:var(--muted); font-size:12px; }
  .count.ok b { color:var(--ok); } .count.no b { color:var(--no); }
  .tabs { display:flex; border-bottom:1px solid var(--line); }
  .tab { flex:1; padding:10px; background:none; border:none; color:var(--muted); cursor:pointer;
         font:inherit; border-bottom:2px solid transparent; }
  .tab.active { color:var(--text); border-bottom-color:var(--accent); }
  #list { flex:1; overflow-y:auto; margin:0; padding:0; list-style:none; }
  #list li { padding:7px 12px; border-bottom:1px solid #1f1f23; cursor:pointer;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:#c8c8cc; }
  #list li:hover { background:#222227; }
  #list li.active { background:#1e3a6e; color:#fff; }
  main { flex:1; display:flex; flex-direction:column; min-width:0; }
  .name { padding:12px 16px; border-bottom:1px solid var(--line); word-break:break-all; }
  .name small { color:var(--muted); margin-left:8px; }
  .viewer { flex:1; display:flex; align-items:center; justify-content:center; padding:16px; min-height:0; }
  .viewer img { max-width:100%; max-height:100%; object-fit:contain; cursor:zoom-in;
                background:#fff; border-radius:4px; }
  .empty { color:var(--muted); }
  .actions { display:flex; gap:12px; justify-content:center; align-items:center; padding:14px;
             border-top:1px solid var(--line); }
  .actions button { font:inherit; border:none; border-radius:6px; padding:12px 28px; cursor:pointer;
                    color:#fff; font-size:15px; }
  .actions button:disabled { opacity:.35; cursor:default; }
  .btn-ok { background:var(--ok); } .btn-no { background:var(--no); }
  .btn-nav, .btn-undo { background:#2c2c32; padding:12px 16px !important; }
  .hint { color:var(--muted); font-size:12px; text-align:center; padding-bottom:10px; }
  #zoom { position:fixed; inset:0; background:rgba(0,0,0,.92); display:none; overflow:auto; cursor:zoom-out; z-index:10; }
  #zoom.show { display:block; }
  #zoom img { display:block; margin:auto; background:#fff; transform-origin:0 0; }
  #toast { position:fixed; bottom:90px; left:50%; transform:translateX(-50%); background:#333; padding:8px 16px;
           border-radius:6px; opacity:0; transition:opacity .2s; pointer-events:none; z-index:20; }
  #toast.show { opacity:1; }
</style>
</head>
<body>
<aside>
  <div class="counts">
    <div class="count"><b id="c-root">0</b><span>all_stamp</span></div>
    <div class="count"><b id="c-_unmatched">0</b><span>_unmatched</span></div>
    <div class="count ok"><b id="c-checked">0</b><span>checked</span></div>
    <div class="count no"><b id="c-not_stamp">0</b><span>not_stamp</span></div>
  </div>
  <div class="tabs">
    <button class="tab active" data-src="root">1. all_stamp</button>
    <button class="tab" data-src="_unmatched">2. _unmatched</button>
  </div>
  <ul id="list"></ul>
</aside>
<main>
  <div class="name" id="name">-</div>
  <div class="viewer" id="viewer"></div>
  <div class="actions">
    <button class="btn-nav" id="prev" title="ก่อนหน้า (←)">◀</button>
    <button class="btn-ok" id="toChecked">✔ checked (1)</button>
    <button class="btn-no" id="toNot">✖ not_stamp (2)</button>
    <button class="btn-nav" id="next" title="ถัดไป (→)">▶</button>
    <button class="btn-undo" id="undo" title="ย้อนกลับ (Z)">↶ Undo</button>
  </div>
  <div class="hint">คีย์ลัด: ← → เลื่อนรูป · 1 = checked · 2 = not_stamp · Z = undo · คลิกรูปเพื่อขยาย (คลิกในหน้าขยายเพื่อซูม 2 เท่า, Esc ปิด)</div>
</main>
<div id="zoom"><img id="zoomImg" alt=""></div>
<div id="toast"></div>
<script>
const state = { src: "root", files: { root: [], _unmatched: [] }, idx: { root: 0, _unmatched: 0 }, busy: false };
const $ = id => document.getElementById(id);
const imgUrl = (src, name) => `/img/${src}/${encodeURIComponent(name)}`;

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 1400);
}

async function refresh() {
  const data = await (await fetch("/api/list")).json();
  state.files.root = data.root; state.files._unmatched = data._unmatched;
  for (const [k, v] of Object.entries(data.counts)) $("c-" + k).textContent = v;
  document.querySelector('.tab[data-src="root"]').textContent = `1. all_stamp (${data.counts.root})`;
  document.querySelector('.tab[data-src="_unmatched"]').textContent = `2. _unmatched (${data.counts._unmatched})`;
  $("undo").disabled = !data.canUndo;
  render(true);
}

function current() { return state.files[state.src][state.idx[state.src]]; }

function render(rebuildList) {
  const files = state.files[state.src];
  if (state.idx[state.src] >= files.length) state.idx[state.src] = Math.max(0, files.length - 1);
  const i = state.idx[state.src], name = files[i];
  const list = $("list");
  if (rebuildList) {
    list.innerHTML = "";
    files.forEach((f, n) => {
      const li = document.createElement("li");
      li.textContent = f; li.title = f;
      li.onclick = () => { state.idx[state.src] = n; render(false); };
      list.appendChild(li);
    });
  }
  [...list.children].forEach((li, n) => li.classList.toggle("active", n === i));
  list.children[i]?.scrollIntoView({ block: "nearest" });

  const viewer = $("viewer");
  if (!name) {
    $("name").innerHTML = "-";
    viewer.innerHTML = '<div class="empty">ไม่มีรูปในโฟลเดอร์นี้</div>';
  } else {
    $("name").textContent = name;
    const small = document.createElement("small");
    small.textContent = `${i + 1} / ${files.length}`;
    $("name").appendChild(small);
    const img = document.createElement("img");
    img.src = imgUrl(state.src, name); img.alt = name;
    img.onclick = openZoom;
    viewer.replaceChildren(img);
  }
  $("toChecked").disabled = $("toNot").disabled = !name;
}

async function move(dest) {
  const name = current();
  if (!name || state.busy) return;
  state.busy = true;
  try {
    const r = await fetch("/api/move", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: state.src, name, dest }) });
    const data = await r.json();
    toast(r.ok ? `ย้ายไป ${dest} แล้ว` : data.error);
    await refresh();
  } finally { state.busy = false; }
}

async function undo() {
  if (state.busy) return;
  state.busy = true;
  try {
    const r = await fetch("/api/undo", { method: "POST" });
    const data = await r.json();
    if (!r.ok) { toast(data.error); return; }
    state.src = data.src;
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.src === data.src));
    await refresh();
    const n = state.files[data.src].indexOf(data.name);
    if (n >= 0) { state.idx[data.src] = n; render(false); }
    toast("ย้อนกลับแล้ว");
  } finally { state.busy = false; }
}

function step(d) {
  const len = state.files[state.src].length;
  if (!len) return;
  state.idx[state.src] = Math.min(len - 1, Math.max(0, state.idx[state.src] + d));
  render(false);
}

let zoomed = false;
function openZoom() {
  const name = current(); if (!name) return;
  const z = $("zoom"), img = $("zoomImg");
  zoomed = false; img.style.width = ""; img.style.maxWidth = "95vw"; img.style.marginTop = "2.5vh";
  img.src = imgUrl(state.src, name);
  z.classList.add("show");
}
$("zoomImg").onclick = e => {
  e.stopPropagation();
  const img = e.target; zoomed = !zoomed;
  img.style.maxWidth = zoomed ? "none" : "95vw";
  img.style.width = zoomed ? (img.naturalWidth * 2) + "px" : "";
};
$("zoom").onclick = () => $("zoom").classList.remove("show");

document.querySelectorAll(".tab").forEach(t => t.onclick = () => {
  state.src = t.dataset.src;
  document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
  render(true);
});
$("toChecked").onclick = () => move("checked");
$("toNot").onclick = () => move("not_stamp");
$("prev").onclick = () => step(-1);
$("next").onclick = () => step(1);
$("undo").onclick = undo;

document.addEventListener("keydown", e => {
  if ($("zoom").classList.contains("show")) {
    if (e.key === "Escape") $("zoom").classList.remove("show");
    return;
  }
  if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); step(1); }
  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); step(-1); }
  else if (e.key === "1") move("checked");
  else if (e.key === "2") move("not_stamp");
  else if (e.key.toLowerCase() === "z") undo();
});

refresh();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Stamp sorter running at {url}  (Ctrl+C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
