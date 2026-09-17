import sys
sys.stdout.reconfigure(encoding="utf-8")
import pymupdf
from sqlalchemy import create_engine, text

eng = create_engine(r"sqlite:///C:/Projects/Literature Translator/data/lit.db")
with eng.connect() as c:
    row = c.execute(
        text("select path from documents where id=:id"),
        {"id": "f09184fa-f90f-4bf5-aa87-1c8e8bacaf87"},
    ).fetchone()
print("path", row[0])
pdf = pymupdf.open(row[0])
page = pdf[0]
for raw in sorted(page.get_text("blocks"), key=lambda b: (round(b[1], 1), round(b[0], 1))):
    x0, y0, x1, y1, t, *_ = raw
    t = (t or "").strip().replace("\n", " | ")
    if not t:
        continue
    u = t.upper()
    if (
        "INTRO" in u
        or t in ("B", "b")
        or u.startswith("IOMED")
        or "BIOMED" in u
        or (len(t) == 1 and t.isalpha())
    ):
        print(f"{x0:.0f},{y0:.0f}-{x1:.0f},{y1:.0f} h={y1 - y0:.1f} | {t[:120]!r}")
