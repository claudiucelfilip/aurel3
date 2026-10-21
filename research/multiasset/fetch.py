"""Download and fingerprint the public research inputs without touching live state."""
import hashlib
import html.parser
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd
import numpy as np
import yfinance as yf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data" / "multiasset"
FED = "https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/first-second-third"


def xlsx_rows(path):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as z:
        strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            tree = ET.fromstring(z.read("xl/sharedStrings.xml"))
            strings = ["".join(x.itertext()) for x in tree.findall("s:si", ns)]
        tree = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
        rows = []
        for row in tree.findall(".//s:row", ns):
            values = {}
            for cell in row.findall("s:c", ns):
                col = "".join(x for x in cell.attrib["r"] if x.isalpha())
                v = cell.find("s:v", ns)
                value = v.text if v is not None else "".join(cell.itertext())
                if cell.attrib.get("t") == "s" and value:
                    value = strings[int(value)]
                values[col] = value
            rows.append(values)
        return rows


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((HERE / "protocol.json").read_text())
    manifest = {"manifest_written_at": pd.Timestamp.now(tz="UTC").isoformat(), "files": {},
                "versions": {"python": sys.version, "pandas": pd.__version__,
                             "numpy": np.__version__, "yfinance": yf.__version__}}
    manifest["protocol_sha256"] = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for ticker in [*protocol["assets"], protocol["cash_proxy"]]:
        path = DATA / f"{ticker}.csv"
        if not path.exists():
            df = yf.download(ticker, start=protocol["download_start"], end=protocol["end_exclusive"],
                             auto_adjust=False, progress=False, threads=False)
            if df.empty:
                raise RuntimeError(f"No prices for {ticker}")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.to_csv(path)
        manifest["files"][path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                      "source": "Yahoo Finance via yfinance", "ticker": ticker}
        print(ticker, flush=True)

    class Links(html.parser.HTMLParser):
        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == "a" and ".xlsx" in d.get("href", ""):
                links.append(urllib.parse.urljoin(FED, d["href"]))

    links = []
    parser = Links()
    parser.feed(urllib.request.urlopen(FED, timeout=30).read().decode())
    for name in ["pcpi", "employ_level"]:
        url = next(x for x in links if f"/{name}_first_second_third.xlsx" in x)
        path = DATA / f"{name}.xlsx"
        if not path.exists():
            path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
        rows = xlsx_rows(path)
        (DATA / f"{name}-rows.json").write_text(json.dumps(rows, indent=2))
        manifest["files"][path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "source": url}
        derived = DATA / f"{name}-rows.json"
        manifest["files"][derived.name] = {"sha256": hashlib.sha256(derived.read_bytes()).hexdigest(), "derived_from": path.name}
        print(name, rows[:5], rows[-2:], flush=True)
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
