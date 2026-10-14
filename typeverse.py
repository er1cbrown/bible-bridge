#!/usr/bin/env python3
"""MonkeyType-style verse typer on SWORD (pysword + ~/.sword).

  python typeverse.py          # http://127.0.0.1:8765
  python typeverse.py --port 8765

Modes: random verse, verse-of-the-day (date-seeded).
Modules: KJV, GNT (en), RVG, SpaRV (es).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import threading
import webbrowser
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SWORD_HOME = Path.home() / ".sword"
ROOT = Path(__file__).resolve().parent
BIBLES = ("KJV", "GNT", "RVG", "SpaRV")
LANG = {"KJV": "en", "GNT": "en", "RVG": "es", "SpaRV": "es"}

_mgr = None
_pool: dict[str, list[tuple[str, int, int]]] = {}


def sword_mgr():
    global _mgr
    if _mgr is None:
        from pysword.modules import SwordModules

        _mgr = SwordModules(str(SWORD_HOME))
        _mgr.parse_modules()
    return _mgr


# What you see is what a US/Intl keyboard types. Curly quotes and long
# dashes from SWORD/OSIS look like ' and - but are different code points.
PUNCT_MAP = str.maketrans(
    {
        "\u2018": "'",  # ‘
        "\u2019": "'",  # ’
        "\u201a": "'",  # ‚
        "\u201b": "'",  # ‛
        "\u2032": "'",  # ′
        "\u00b4": "'",  # ´
        "\u0060": "'",  # `
        "\u201c": '"',  # “
        "\u201d": '"',  # ”
        "\u201e": '"',  # „
        "\u201f": '"',  # ‟
        "\u00ab": '"',  # «
        "\u00bb": '"',  # »
        "\u2033": '"',  # ″
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # –
        "\u2014": "-",  # —
        "\u2015": "-",  # ―
        "\u2212": "-",  # minus
        "\u00ad": "",  # soft hyphen
        "\u2026": "...",  # …
        "\u00a0": " ",
        "\u202f": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u200b": "",
        "\ufeff": "",
        "‹": "",
        "›": "",
        "¿": "?",  # inverted still a question; type ?
        "¡": "!",
    }
)


def clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = s.translate(PUNCT_MAP)
    s = s.replace('""', '"').replace("''", "'")
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def verse_ok(text: str) -> bool:
    if len(text) < 24:
        return False
    u = text.upper()
    if u.startswith("(SEE") or u.startswith("SEE "):
        return False
    return True


def build_pool(module: str) -> list[tuple[str, int, int]]:
    if module in _pool:
        return _pool[module]
    mgr = sword_mgr()
    bible = mgr.get_bible_from_module(module)
    st = bible.get_structure()
    books = st.get_books()
    out: list[tuple[str, int, int]] = []
    for testament in ("ot", "nt"):
        for book in books.get(testament, []):
            name = book.osis_name or book.name
            for ch, nverses in enumerate(book.chapter_lengths, start=1):
                for vs in range(1, int(nverses) + 1):
                    out.append((name, ch, vs))
    _pool[module] = out
    return out


def get_text(module: str, book: str, ch: int, vs: int) -> str:
    bible = sword_mgr().get_bible_from_module(module)
    key = (book or "").lower().replace(" ", "")
    aliases = {
        "songofsolomon": "song",
        "psalms": "ps",
        "revelation": "rev",
        "revelationofjohn": "rev",
    }
    key = aliases.get(key, key)
    raw = bible.get(books=[key], chapters=[ch], verses=[vs])
    if isinstance(raw, (list, tuple)):
        raw = " ".join(str(x) for x in raw)
    return clean_text(str(raw))


def pick(module: str, mode: str) -> dict:
    if module not in BIBLES:
        module = "KJV"
    pool = build_pool(module)
    if mode == "daily":
        day = dt.date.today().isoformat()
        h = hashlib.sha256(f"{day}:{module}".encode()).hexdigest()
        idx = int(h, 16) % len(pool)
        # walk until a typeable verse
        for i in range(len(pool)):
            book, ch, vs = pool[(idx + i) % len(pool)]
            text = get_text(module, book, ch, vs)
            if verse_ok(text):
                return payload(module, book, ch, vs, text, "daily", day)
        book, ch, vs = pool[idx]
        return payload(module, book, ch, vs, get_text(module, book, ch, vs), "daily", day)
    for _ in range(40):
        book, ch, vs = random.choice(pool)
        text = get_text(module, book, ch, vs)
        if verse_ok(text):
            return payload(module, book, ch, vs, text, "random", None)
    book, ch, vs = random.choice(pool)
    return payload(module, book, ch, vs, get_text(module, book, ch, vs), "random", None)


def payload(module, book, ch, vs, text, mode, day):
    return {
        "module": module,
        "lang": LANG.get(module, "en"),
        "book": book,
        "chapter": ch,
        "verse": vs,
        "ref": f"{book} {ch}:{vs}",
        "text": text,
        "mode": mode,
        "date": day,
        "modules": list(BIBLES),
    }


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>typeverse</title>
<style>
  :root { --bg:#323437; --sub:#646669; --text:#d1d0c5; --caret:#e2b714; --err:#ca4754; --ok:#d1d0c5; }
  * { box-sizing:border-box; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--text);
    font-family: "Roboto Mono", ui-monospace, Menlo, monospace; }
  body { display:flex; flex-direction:column; align-items:center; padding:2rem 1rem 4rem; }
  h1 { font-weight:400; color:var(--caret); letter-spacing:.08em; font-size:1.1rem; margin:0 0 1.5rem; }
  h1 span { color:var(--sub); }
  .bar { display:flex; gap:.5rem; flex-wrap:wrap; justify-content:center; margin-bottom:1.2rem; }
  button, .chip { background:#2c2e31; color:var(--sub); border:0; padding:.4rem .75rem; border-radius:.4rem;
    font: inherit; cursor:pointer; }
  button.active, .chip.active { color:var(--caret); }
  button:hover { color:var(--text); }
  #ref { color:var(--sub); margin-bottom:.8rem; min-height:1.2em; }
  #stage { max-width:42rem; width:100%; font-size:1.35rem; line-height:1.7; min-height:8rem;
    user-select:none; cursor:text; }
  #stage .ok { color:var(--ok); }
  #stage .bad { color:var(--err); background:#ca475422; }
  #stage .cur { border-left:2px solid var(--caret); animation: blink 1s step-end infinite; }
  #stage .rest { color:var(--sub); }
  @keyframes blink { 50% { border-color: transparent; } }
  #hidden { position:absolute; left:-9999px; }
  #stats { margin-top:1.5rem; color:var(--caret); font-size:1.4rem; display:flex; gap:1.5rem; }
  #stats small { color:var(--sub); font-size:.75rem; display:block; }
  kbd { color:var(--sub); font-size:.8rem; }
  footer { margin-top:2.5rem; color:var(--sub); font-size:.8rem; text-align:center; max-width:40rem; }
</style>
</head>
<body>
  <h1>typeverse <span>// monkeytype × SWORD</span></h1>
  <div class="bar" id="mods"></div>
  <div class="bar">
    <button id="mode-random" class="active" data-mode="random">random</button>
    <button id="mode-daily" data-mode="daily">verse of the day</button>
    <button id="next">tab · next</button>
  </div>
  <div id="ref"></div>
  <div id="stage" tabindex="0"></div>
  <input id="hidden" autocomplete="off" autocapitalize="off" spellcheck="false"/>
  <div id="stats">
    <div><small>wpm</small><span id="wpm">0</span></div>
    <div><small>acc</small><span id="acc">100</span>%</div>
    <div><small>streak</small><span id="streak">0</span></div>
  </div>
  <footer>
    Type the verse. <kbd>Tab</kbd> new verse. <kbd>Escape</kbd> restart this verse.
    pysword + rsword-chirho · ~/.sword · a verse a day is enough.
  </footer>
<script>
const mods = ["KJV","GNT","RVG","SpaRV"];
let module = localStorage.getItem("tv_mod") || "KJV";
let mode = localStorage.getItem("tv_mode") || "random";
let target = "";
let typed = "";
let started = 0;
let done = false;
let errors = 0;

const stage = document.getElementById("stage");
const hidden = document.getElementById("hidden");
const refEl = document.getElementById("ref");
const modBar = document.getElementById("mods");

function streakKey(){ return "tv_streak"; }
function today(){ return new Date().toISOString().slice(0,10); }
function loadStreak(){
  const s = JSON.parse(localStorage.getItem(streakKey()) || "{}");
  document.getElementById("streak").textContent = s.count || 0;
}
function bumpStreak(){
  const s = JSON.parse(localStorage.getItem(streakKey()) || "{}");
  if (s.last === today()) return;
  const y = new Date(); y.setDate(y.getDate()-1);
  const ymd = y.toISOString().slice(0,10);
  s.count = (s.last === ymd ? (s.count||0) : 0) + 1;
  s.last = today();
  localStorage.setItem(streakKey(), JSON.stringify(s));
  loadStreak();
}

mods.forEach(m => {
  const b = document.createElement("button");
  b.textContent = m;
  b.className = m === module ? "active" : "";
  b.onclick = () => { module = m; localStorage.setItem("tv_mod", m); document.querySelectorAll("#mods button").forEach(x=>x.classList.remove("active")); b.classList.add("active"); loadVerse(); };
  modBar.appendChild(b);
});
document.getElementById("mode-random").classList.toggle("active", mode==="random");
document.getElementById("mode-daily").classList.toggle("active", mode==="daily");
document.getElementById("mode-random").onclick = () => setMode("random");
document.getElementById("mode-daily").onclick = () => setMode("daily");
document.getElementById("next").onclick = () => { mode = "random"; setMode("random"); };
function setMode(m){
  mode = m; localStorage.setItem("tv_mode", m);
  document.getElementById("mode-random").classList.toggle("active", m==="random");
  document.getElementById("mode-daily").classList.toggle("active", m==="daily");
  loadVerse();
}

async function loadVerse(){
  typed = ""; started = 0; done = false; errors = 0;
  refEl.textContent = "loading " + module + "…";
  const r = await fetch(`/api/verse?module=${encodeURIComponent(module)}&mode=${encodeURIComponent(mode)}`);
  const j = await r.json();
  target = j.text || "";
  refEl.textContent = `${j.ref} · ${j.module} · ${j.lang} · ${j.mode}`;
  render();
  hidden.focus();
}

function render(){
  let html = "";
  for (let i=0;i<target.length;i++){
    const ch = target[i] === " " ? " " : target[i];
    if (i < typed.length){
      const ok = typed[i] === target[i];
      html += `<span class="${ok?"ok":"bad"}">${escape(ch)}</span>`;
    } else if (i === typed.length){
      html += `<span class="cur rest">${escape(ch)}</span>`;
    } else {
      html += `<span class="rest">${escape(ch)}</span>`;
    }
  }
  stage.innerHTML = html || "<span class='rest'>…</span>";
  liveStats();
}
function escape(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function liveStats(){
  const now = performance.now();
  const mins = started ? Math.max((now-started)/60000, 1/60000) : 0;
  const correct = [...typed].filter((c,i)=>c===target[i]).length;
  const wpm = started ? Math.round((correct/5)/mins) : 0;
  const acc = typed.length ? Math.round(100*correct/typed.length) : 100;
  document.getElementById("wpm").textContent = wpm;
  document.getElementById("acc").textContent = acc;
}

function foldKeys(s){
  return s
    .replace(/[\u2018\u2019\u201A\u201B\u2032\u00B4`]/g, "'")
    .replace(/[\u201C\u201D\u201E\u201F\u00AB\u00BB\u2033]/g, '"')
    .replace(/[\u2010-\u2015\u2212]/g, "-")
    .replace(/¿/g, "?").replace(/¡/g, "!");
}
hidden.addEventListener("input", (e) => {
  if (done) return;
  if (!started) started = performance.now();
  typed = foldKeys(hidden.value);
  if (typed.length > target.length) typed = typed.slice(0, target.length);
  hidden.value = typed;
  render();
  if (typed.length === target.length){
    done = true;
    liveStats();
    const acc = typed.length ? [...typed].filter((c,i)=>c===target[i]).length/typed.length : 0;
    if (acc >= 0.9) bumpStreak();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Tab"){
    e.preventDefault();
    mode = "random"; setMode("random");
    hidden.value = "";
  }
  if (e.key === "Escape"){
    e.preventDefault();
    typed = ""; hidden.value = ""; started = 0; done = false; render();
  }
});
stage.addEventListener("click", () => hidden.focus());
loadStreak();
loadVerse();
</script>
</body>
</html>
"""


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"typeverse {self.address_string()} {fmt % args}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/verse":
            q = parse_qs(u.query)
            module = (q.get("module") or ["KJV"])[0]
            mode = (q.get("mode") or ["random"])[0]
            try:
                data = pick(module, mode)
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    # warmup default module so first click is fast
    print("Loading SWORD via pysword…", flush=True)
    build_pool("KJV")
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"typeverse {url}", flush=True)
    print("Tab = next random verse · Escape = restart · verse of the day is date-seeded", flush=True)
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
