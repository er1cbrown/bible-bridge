#!/usr/bin/env python3
"""Bible bridge: SWORD text + Bible NLP CSV + TSK cross-references + optional ML.

Examples:
  python bible_bridge.py "John 3:16"
  python bible_bridge.py "John 3:16" --versions KJV,GNT,RVG
  python bible_bridge.py "God so loved the world" --predict
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / "models"
RSWORD_DIR = Path.home() / "Desktop/rsword-chirho"
DIATHEKE = RSWORD_DIR / "target/release/diatheke_chirho"
INSTALLMGR = RSWORD_DIR / "target/release/installmgr_chirho"
SWORD_HOME = Path.home() / ".sword"
NLP_CSV = Path(
    "/Users/ebrown63/Desktop/Computer Science Projects/projectFile1/kjv_final1.csv"
)
# TSK is a commentary (zCom). pysword only reads Bible modules.
COMMENTARY_MODULES = {"TSK"}

BOOK_ALIASES = {
    "psalm": "Psalms",
    "ps": "Psalms",
    "song of songs": "Song of Solomon",
    "song of solomon": "Song of Solomon",
    "revelation": "Revelation",
    "rev": "Revelation",
}

_NLP_INDEX: dict[tuple[str, int, int], dict] | None = None


_PYSWORD = None


def _pysword_modules():
    global _PYSWORD
    if _PYSWORD is not None:
        return _PYSWORD
    try:
        from pysword.modules import SwordModules

        mgr = SwordModules(str(SWORD_HOME))
        mgr.parse_modules()
        _PYSWORD = mgr
    except Exception:
        _PYSWORD = False
    return _PYSWORD


def sword_diatheke(module: str, ref: str) -> str:
    if not DIATHEKE.exists():
        return f"(missing diatheke at {DIATHEKE})"
    r = subprocess.run(
        [str(DIATHEKE), "-b", module, "-k", ref],
        capture_output=True,
        text=True,
    )
    out = (r.stdout or r.stderr or "").strip()
    if r.returncode != 0:
        return out or f"(lookup failed for {module} {ref})"
    line = out.splitlines()[0] if out else ""
    if ": " in line:
        return line.split(": ", 1)[1]
    return line


def sword_pysword(module: str, ref: str) -> str | None:
    """In-process read of ~/.sword Bible modules (MIT pysword). Not for TSK."""
    parsed = parse_ref(ref)
    if not parsed:
        return None
    book, ch, vs = parsed
    mgr = _pysword_modules()
    if not mgr:
        return None
    found = mgr.parse_modules()
    key = module if module in found else None
    if key is None:
        for k in found:
            if k.lower() == module.lower():
                key = k
                break
    if key is None:
        return None
    if (found[key].get("moddrv") or "").lower() in {"zcom", "rawcom"}:
        return None
    try:
        bible = mgr.get_bible_from_module(key)
        book_key = book.lower().replace(" ", "")
        aliases = {
            "songofsolomon": "song",
            "psalms": "ps",
            "revelation": "rev",
            "revelationofjohn": "rev",
        }
        book_key = aliases.get(book_key, book_key)
        text = bible.get(books=[book_key], chapters=[ch], verses=[vs])
        if isinstance(text, (list, tuple)):
            text = "\n".join(str(x) for x in text)
        return str(text).strip() if text else None
    except Exception:
        return None


def sword(module: str, ref: str, engine: str = "auto") -> str:
    """Read one module. engine: auto | pysword | rsword | both.

    auto: pysword for Bibles (MIT, in-process); rsword-chirho diatheke for TSK/commentaries.
    both: pysword first, fall back to rsword; attach mismatch in JSON via dual_lookup.
    """
    want = engine.lower()
    is_com = module.upper() in COMMENTARY_MODULES
    if want == "pysword":
        if is_com:
            return "(pysword does not read commentaries; use rsword/diatheke for TSK)"
        return sword_pysword(module, ref) or f"(pysword miss {module} {ref})"
    if want == "rsword":
        return sword_diatheke(module, ref)
    # auto / both
    if not is_com:
        got = sword_pysword(module, ref)
        if got:
            if want == "both":
                other = sword_diatheke(module, ref)
                if other and other != got and not other.startswith("("):
                    return got  # display pysword; dual_lookup records both
            return got
    return sword_diatheke(module, ref)


def dual_lookup(module: str, ref: str) -> dict:
    """Always hit both engines so apps can see they share ~/.sword."""
    py = None if module.upper() in COMMENTARY_MODULES else sword_pysword(module, ref)
    rs = sword_diatheke(module, ref)
    agree = py is not None and rs and not rs.startswith("(") and py.strip() == rs.strip()
    return {
        "pysword": py,
        "rsword": rs if not (rs or "").startswith("(missing") else rs,
        "agree": agree,
        "used": "pysword" if py else "rsword",
    }


def backend_status() -> dict:
    pysword_ok = False
    pysword_mods: list[str] = []
    try:
        mgr = _pysword_modules()
        if mgr:
            pysword_ok = True
            pysword_mods = sorted(mgr.parse_modules().keys())
    except Exception as e:
        pysword_mods = [str(e)]
    rsword_ok = DIATHEKE.exists()
    rsword_mods: list[str] = []
    if rsword_ok and INSTALLMGR.exists():
        r = subprocess.run([str(INSTALLMGR), "-l"], capture_output=True, text=True)
        rsword_mods = [
            ln.strip()
            for ln in (r.stdout or "").splitlines()
            if ln.strip() and not ln.lower().startswith("installed")
        ]
    return {
        "sword_home": str(SWORD_HOME),
        "pysword": {
            "ok": pysword_ok,
            "source": "https://gitlab.com/tgc-dk/pysword",
            "role": "MIT in-process Bible reader (Python, BlkSpace-safe, nvim)",
            "modules": pysword_mods,
            "limit": "Bibles only (zText/RawText). No TSK.",
        },
        "rsword_chirho": {
            "ok": rsword_ok,
            "source": "https://github.com/loveJesus/rsword-chirho",
            "role": "GPL CLI: installmgr + diatheke + TSK commentaries",
            "diatheke": str(DIATHEKE),
            "installmgr": str(INSTALLMGR),
            "modules": rsword_mods,
        },
        "shared_store": str(SWORD_HOME),
        "both_required": True,
    }


def parse_ref(raw: str) -> tuple[str, int, int] | None:
    m = re.match(r"^\s*([1-3]?\s*[A-Za-z.]+(?:\s+[A-Za-z.]+)?)\s+(\d+):(\d+)\s*$", raw)
    if not m:
        return None
    book = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
    key = book.lower()
    book = BOOK_ALIASES.get(key, book)
    # CSV uses Psalms, 1 John, etc.
    if book.lower() == "psalms":
        book = "Psalms"
    return book, int(m.group(2)), int(m.group(3))


def nlp_index() -> dict[tuple[str, int, int], dict]:
    global _NLP_INDEX
    if _NLP_INDEX is not None:
        return _NLP_INDEX
    idx: dict[tuple[str, int, int], dict] = {}
    with NLP_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                key = (row["book"], int(row["chapter"]), int(row["verse"]))
            except (KeyError, ValueError, TypeError):
                continue
            idx[key] = row
    _NLP_INDEX = idx
    return idx


def nlp_for(ref: str) -> dict | None:
    parsed = parse_ref(ref)
    if not parsed:
        return None
    book, ch, vs = parsed
    idx = nlp_index()
    row = idx.get((book, ch, vs))
    if row:
        return row
    # try Psalms/Psalm
    alt = "Psalms" if book == "Psalm" else "Psalm"
    return idx.get((alt, ch, vs))


def parse_tsk(blob: str) -> list[str]:
    """Turn TSK dump into a short list of cross-ref tokens."""
    if ": " in blob:
        blob = blob.split(": ", 1)[1]
    blob = re.sub(r"<[^>]+>", " ", blob)
    blob = re.sub(r"\s+", " ", blob).strip()
    # Keep it readable; TSK is already compact (Lu 2:14; Ro 5:8; ...)
    return [p.strip() for p in re.split(r";\s*", blob) if p.strip()][:24]


def predict(text: str) -> dict:
    try:
        import joblib
    except ImportError:
        return {"error": "joblib not installed; use bible-bridge/.venv"}
    tpath = MODELS / "testament.joblib"
    bpath = MODELS / "book.joblib"
    if not tpath.exists() or not bpath.exists():
        return {"error": f"models missing; run train.py (looked in {MODELS})"}
    testament_clf = joblib.load(tpath)
    book_clf = joblib.load(bpath)
    t_pred = testament_clf.predict([text])[0]
    b_pred = book_clf.predict([text])[0]
    t_prob = max(testament_clf.predict_proba([text])[0])
    b_prob = max(book_clf.predict_proba([text])[0])
    return {
        "testament": str(t_pred),
        "testament_confidence": round(float(t_prob), 3),
        "book": str(b_pred),
        "book_confidence": round(float(b_prob), 3),
    }


def verse_record(
    query: str,
    versions: list[str],
    do_xref: bool,
    do_predict: bool,
    engine: str = "auto",
) -> dict:
    """One JSON object every app can share: SWORD text + Bible NLP + TSK + ML."""
    parsed = parse_ref(query)
    rec: dict = {
        "query": query,
        "ref": None,
        "engine": engine,
        "sword": {},
        "engines": {},
        "nlp": None,
        "xref": [],
        "ml": None,
        "sources": {
            "pysword": "https://gitlab.com/tgc-dk/pysword",
            "rsword_chirho": "https://github.com/loveJesus/rsword-chirho",
            "store": str(SWORD_HOME),
            "nlp": str(NLP_CSV),
            "ml": str(MODELS),
        },
    }
    if parsed:
        book, ch, vs = parsed
        rec["ref"] = {"book": book, "chapter": ch, "verse": vs, "osis": f"{book}.{ch}.{vs}"}
        for ver in versions:
            rec["sword"][ver] = sword(ver, query, engine)
            rec["engines"][ver] = dual_lookup(ver, query)
        row = nlp_for(query)
        if row:
            rec["nlp"] = {
                "polarity": row.get("verse_polarity"),
                "subjectivity": row.get("verse_subjectivity"),
                "length": row.get("verse_length"),
                "entities": row.get("named_entities"),
                "csv_book": row.get("book"),
            }
        if do_xref:
            rec["xref"] = parse_tsk(sword("TSK", query, "rsword"))
            rec["engines"]["TSK"] = dual_lookup("TSK", query)
        if do_predict:
            rec["ml"] = predict(rec["sword"].get("KJV") or sword("KJV", query, engine))
    else:
        rec["ml"] = predict(query)
    return rec


def format_report(
    query: str,
    versions: list[str],
    do_xref: bool,
    do_predict: bool,
    engine: str = "auto",
) -> str:
    lines: list[str] = []
    lines.append(f"# {query}")
    lines.append(f"engines: pysword (GitLab tgc-dk) + rsword-chirho  mode={engine}")
    parsed = parse_ref(query)
    is_ref = parsed is not None

    if is_ref:
        for ver in versions:
            text = sword(ver, query, engine)
            dual = dual_lookup(ver, query)
            tag = "pysword+rsword" if dual.get("agree") else f"used={dual.get('used')}"
            lines.append(f"\n## {ver} ({tag})")
            lines.append(text)
            if engine == "both" and dual.get("pysword") and dual.get("rsword"):
                if not dual.get("agree"):
                    lines.append(f"rsword: {dual['rsword']}")
        row = nlp_for(query)
        lines.append("\n## Bible NLP (kjv_final1.csv)")
        if row:
            lines.append(f"book={row.get('book')} {row.get('chapter')}:{row.get('verse')}")
            lines.append(f"polarity={row.get('verse_polarity')}  subjectivity={row.get('verse_subjectivity')}")
            lines.append(f"length={row.get('verse_length')}")
            lines.append(f"entities={row.get('named_entities')}")
            lines.append("(CSV text is study-only; SWORD is canonical.)")
        else:
            lines.append("no NLP row for this reference")
        if do_xref:
            lines.append("\n## Cross-references (TSK via rsword-chirho)")
            raw = sword("TSK", query, "rsword")
            refs = parse_tsk(raw)
            if refs:
                for item in refs:
                    lines.append(f"- {item}")
            else:
                lines.append(raw or "(none)")
        if do_predict:
            kjv = sword("KJV", query, engine)
            lines.append("\n## ML guess from KJV wording")
            p = predict(kjv)
            lines.append(str(p))
    else:
        lines.append("\n## Not a verse reference — running ML on pasted text")
        lines.append(str(predict(query)))
        if do_xref:
            lines.append("(cross-references need a verse like John 3:16)")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="SWORD + Bible NLP + TSK. Both pysword (GitLab) and rsword-chirho (GitHub)."
    )
    ap.add_argument("query", nargs="?", help='Verse like "John 3:16" or free text')
    ap.add_argument("--status", action="store_true", help="Show pysword + rsword-chirho health")
    ap.add_argument("--versions", default="KJV,GNT,RVG", help="Comma-separated SWORD modules")
    ap.add_argument(
        "--engine",
        choices=("auto", "pysword", "rsword", "both"),
        default="auto",
        help="auto=pysword Bibles + rsword TSK; both=compare; rsword=diatheke only",
    )
    ap.add_argument("--xref", action="store_true", default=True, help="Show TSK (rsword)")
    ap.add_argument("--no-xref", action="store_true")
    ap.add_argument("--predict", action="store_true", help="Run testament/book classifier")
    ap.add_argument("--json", action="store_true", help="Machine record for other apps")
    args = ap.parse_args()
    if args.status or not args.query:
        st = backend_status()
        if args.json or args.status:
            sys.stdout.write(json.dumps(st, indent=2) + "\n")
            if args.status and not args.query:
                return
        if not args.query:
            if not args.status:
                ap.print_help()
            return
    do_xref = not args.no_xref
    versions = [v.strip() for v in args.versions.split(",") if v.strip()]
    do_predict = args.predict or not parse_ref(args.query)
    if args.json:
        rec = verse_record(args.query, versions, do_xref, do_predict, args.engine)
        sys.stdout.write(json.dumps(rec, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(format_report(args.query, versions, do_xref, do_predict, args.engine))


if __name__ == "__main__":
    main()
