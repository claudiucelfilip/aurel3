"""Download SEC Form 3/4/5 insider transaction data set zips listed on the official SEC page (cached)."""
import re
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / 'data' / 'broad_search' / 'insider'
PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'
UA = 'Aurel3-research personal-noncommercial admin@example.org'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    out = DATA / 'sec_zips'
    out.mkdir(parents=True, exist_ok=True)
    html = get(PAGE).decode('utf-8', 'replace')
    urls = sorted({'https://www.sec.gov' + h for h in re.findall(r'href="(/files/[^"]+_form345\.zip)"', html)})
    (DATA / 'zip_urls.txt').write_text('\n'.join(urls) + '\n')
    print(len(urls), 'zips listed', flush=True)
    for u in urls:
        dest = out / u.rsplit('/', 1)[1]
        if dest.exists() and dest.stat().st_size > 0:
            continue
        for attempt in range(5):
            try:
                time.sleep(1.0)
                dest.write_bytes(get(u))
                print('ok', dest.name, dest.stat().st_size, flush=True)
                break
            except Exception as exc:
                print('retry', dest.name, exc, flush=True)
                time.sleep(10 * (attempt + 1))
        else:
            sys.exit('failed ' + u)


if __name__ == '__main__':
    main()
