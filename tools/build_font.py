"""One-off developer tool: subset the Anybody variable font for the SVGs and record glyph widths.

    python tools/build_font.py

Needs fontTools (pip install fonttools brotli) on the developer machine only. It writes two committed files:

    assets/fonts/anybody-subset.woff2   the glyphs the SVGs use, with both variable axes (weight, width) kept
    assets/fonts/anybody-metrics.json   advance widths at the three text styles the renderer uses, so Python
                                        can measure text (and fit boxes around it) in GitHub Actions without fontTools

Anybody is by Tyler Finck / ETC, under the SIL Open Font License (assets/fonts/OFL-Anybody.txt).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "fonts" / "anybody-latin-wdth.woff2"
SUBSET = ROOT / "assets" / "fonts" / "anybody-subset.woff2"
METRICS = ROOT / "assets" / "fonts" / "anybody-metrics.json"

TEXT = "".join(chr(c) for c in range(32, 127)) + "“”‘’–—·•×→←↗…✓°≈"
STYLES = {
    "black": {"wght": 850, "wdth": 100},
    "bold": {"wght": 760, "wdth": 88},
    "label": {"wght": 700, "wdth": 76},
}


def main() -> None:
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["kern", "liga"]
    options.name_IDs = ["*"]
    font = TTFont(SOURCE)
    sub = subset.Subsetter(options)
    sub.populate(text=TEXT)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(SUBSET)

    base = TTFont(SOURCE)
    upem = base["head"].unitsPerEm
    cmap = base.getBestCmap()
    out = {"unitsPerEm": upem, "styles": {}}
    for name, axes in STYLES.items():
        inst = instancer.instantiateVariableFont(TTFont(io.BytesIO(_raw(SOURCE))), axes)
        hmtx = inst["hmtx"]
        adv = {ch: hmtx[cmap[ord(ch)]][0] for ch in TEXT if ord(ch) in cmap}
        out["styles"][name] = {**axes, "advances": adv, "fallback": round(sum(adv.values()) / len(adv))}
    METRICS.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {SUBSET.name} ({SUBSET.stat().st_size // 1024} KB) and {METRICS.name}")


def _raw(path: Path) -> bytes:
    font = TTFont(path)
    font.flavor = None
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


if __name__ == "__main__":
    main()
