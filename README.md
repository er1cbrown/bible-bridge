# bible-bridge

Both engines share `~/.sword`:

| Engine | Source | License | Job |
|--------|--------|---------|-----|
| **pysword** | [gitlab.com/tgc-dk/pysword](https://gitlab.com/tgc-dk/pysword) | MIT (PyPI) | In-process Bible read (KJV, GNT, RVG, SpaRV) |
| **rsword-chirho** | [github.com/loveJesus/rsword-chirho](https://github.com/loveJesus/rsword-chirho) | GPL-2.0+ | `installmgr_chirho` + `diatheke_chirho` + **TSK** |

```bash
cd ~/Desktop/bible-bridge
source .venv/bin/activate
python bible_bridge.py --status
python bible_bridge.py "John 3:16" --engine both
python bible_bridge.py "John 3:16" --engine pysword --no-xref
python bible_bridge.py "John 3:16" --engine rsword
python train.py
```

Neovim: `:luafile ~/Desktop/bible-bridge/nvim/bible_bridge.lua` then `:Bible John 3:16`
