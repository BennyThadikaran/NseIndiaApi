"""Live smoke test for the XBRL helpers (hits NSE - run locally, after market hours).

Usage:
    cd /home/pricecatch/NseIndiaApi/tests
    python live_xbrl_smoke.py LINDEINDIA

Writes to ~/nse_xbrl_smoke/:
    {SYMBOL}/*.xml           downloaded XBRL filings
    {SYMBOL}_filings.csv     filing metadata (one row per filing)
    {SYMBOL}_elements.txt    element/context inventory of the latest filing
                             (used to build the fundamentals parser)
"""

import csv
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path

from context import NSE

SYMBOL = (sys.argv[1] if len(sys.argv) > 1 else "LINDEINDIA").upper()
OUT = Path("~/nse_xbrl_smoke").expanduser()
OUT.mkdir(parents=True, exist_ok=True)

COLS = [
    "symbol", "source", "period_from", "period_to", "basis", "cumulative", "audited",
    "relatingTo", "broadcast_dt", "revision_count", "seqNumber", "xbrl",
    "local_path", "error",
]


def inventory(xml_path: Path, out_txt: Path) -> None:
    """Dump contexts and every fact (element, contextRef, unit, value)."""
    root = ET.parse(xml_path).getroot()

    def local(tag):
        return tag.split("}", 1)[-1]

    lines = [f"# {xml_path.name}", "", "## Contexts"]

    for el in root:
        if local(el.tag) == "context":
            cid = el.get("id")
            period = " ".join(
                f"{local(p.tag)}={p.text}" for p in el.iter() if local(p.tag)
                in ("startDate", "endDate", "instant")
            )
            members = " ".join(
                (m.text or "").strip() for m in el.iter() if local(m.tag) == "explicitMember"
            )
            lines.append(f"{cid}\t{period}\t{members}")

    lines += ["", "## Facts (element\tcontextRef\tunitRef\tdecimals\tvalue)"]
    counts = Counter()

    for el in root:
        ctx = el.get("contextRef")
        if ctx is None:
            continue
        name = local(el.tag)
        counts[name] += 1
        val = (el.text or "").strip().replace("\n", " ")
        if len(val) > 80:
            val = val[:77] + "..."
        lines.append(f"{name}\t{ctx}\t{el.get('unitRef')}\t{el.get('decimals')}\t{val}")

    lines += ["", f"## {len(counts)} distinct elements, {sum(counts.values())} facts"]
    out_txt.write_text("\n".join(lines))


def main():
    with NSE(OUT / ".nse") as nse:
        recs = nse.fetch_xbrl_filings(
            SYMBOL,
            folder=OUT,
            from_date=datetime(2024, 4, 1),
            to_date=datetime.now(),
            basis="both",
        )

    csv_path = OUT / f"{SYMBOL}_filings.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)

    ok = [r for r in recs if r["local_path"]]
    print(f"{SYMBOL}: {len(recs)} filings, {len(ok)} downloaded, "
          f"{len(recs) - len(ok)} failed -> {csv_path}")

    for r in recs:
        status = "OK " if r["local_path"] else "ERR"
        print(f"  {status} {r['period_to']} {r['basis']} {r['source']:10} "
              f"{(r.get('cumulative') or '')[:14]:14} rev={r['revision_count']} "
              f"{r['broadcast_dt']}  {r['error'] or ''}")

    cons = [r for r in ok if r["basis"] == "C"] or ok
    if cons:
        latest = cons[-1]
        out_txt = OUT / f"{SYMBOL}_elements.txt"
        inventory(latest["local_path"], out_txt)
        print(f"Element inventory of {latest['local_path'].name} -> {out_txt}")


if __name__ == "__main__":
    main()
