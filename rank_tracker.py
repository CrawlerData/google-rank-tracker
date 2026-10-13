#!/usr/bin/env python3
"""Google rank tracker: daily keyword positions by country and device, stored in SQLite, with a change report.

Uses the CrawlerData API (https://crawlerdata.com). Set CRAWLERDATA_API_KEY first.

    python rank_tracker.py track                                   # keywords.csv, us, desktop, top 10
    python rank_tracker.py track --countries us,gb --devices desktop,mobile --pages 3
    python rank_tracker.py report                                  # latest run vs the previous one
    python rank_tracker.py export -o rankings.csv
"""
import argparse
import csv
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

SCHEMA = """
CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY,
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    domain TEXT NOT NULL,
    country TEXT NOT NULL,
    device TEXT NOT NULL,
    position INTEGER,          -- NULL = not found within the pages checked
    url TEXT,
    title TEXT,
    pages_checked INTEGER,
    has_ai_overview INTEGER,
    cited_in_ai_overview INTEGER
);
CREATE TABLE IF NOT EXISTS serp (
    run_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    country TEXT NOT NULL,
    device TEXT NOT NULL,
    position INTEGER,
    domain TEXT,
    url TEXT,
    title TEXT
);
CREATE INDEX IF NOT EXISTS rankings_key ON rankings(keyword, domain, country, device, run_at);
"""


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def host(url):
    try:
        h = urlparse(url or "").netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def matches(url, domain):
    h = host(url)
    return h == domain or h.endswith("." + domain)


def load_keywords(path, default_domain):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            kw = (r.get("keyword") or "").strip()
            dom = (r.get("domain") or default_domain or "").strip().lower()
            dom = dom[4:] if dom.startswith("www.") else dom
            if kw:
                if not dom:
                    sys.exit(f"No domain for keyword {kw!r}: add a domain column or pass --domain")
                rows.append((kw, dom))
    return rows


def track_one(client, keyword, domain, country, device, max_pages):
    """Return (position, url, title, pages_checked, has_ai, cited_in_ai, serp_rows)."""
    rank, seen, serp = 0, set(), []
    has_ai = cited = False
    for page in range(1, max_pages + 1):
        r = client.live("google-search", {"query": keyword, "country": country, "device": device, "page": page})
        if page == 1:
            ai = r.get("ai_overview") or {}
            has_ai = bool(ai)
            cited = any(matches(s.get("link"), domain) for s in ai.get("sources") or [])
        results = r.get("organic_results") or []
        for o in results:
            link = o.get("link")
            if link in seen:  # later pages can repeat earlier results
                continue
            seen.add(link)
            rank += 1
            serp.append((rank, host(link), link, o.get("title")))
            if matches(link, domain):
                return rank, link, o.get("title"), page, has_ai, cited, serp
        if not results:
            break
    return None, None, None, max_pages, has_ai, cited, serp


def cmd_track(args):
    from crawlerdata_client import CrawlerData, CrawlerDataError

    try:
        client = CrawlerData()
    except CrawlerDataError as exc:
        sys.exit(str(exc))
    db = connect(args.db)
    run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keywords = load_keywords(args.keywords, args.domain)
    countries = [c.strip() for c in args.countries.split(",") if c.strip()]
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    for keyword, domain in keywords:
        for country in countries:
            for device in devices:
                try:
                    pos, url, title, pages, has_ai, cited, serp = track_one(
                        client, keyword, domain, country, device, args.pages)
                except CrawlerDataError as exc:
                    if exc.status in (401, 402):
                        sys.exit(str(exc))
                    print(f"[skip] {keyword!r} {country}/{device}: {exc}", file=sys.stderr)
                    continue
                db.execute("INSERT INTO rankings (run_at, keyword, domain, country, device, position, url, title,"
                           " pages_checked, has_ai_overview, cited_in_ai_overview) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (run_at, keyword, domain, country, device, pos, url, title, pages, has_ai, cited))
                db.executemany("INSERT INTO serp VALUES (?,?,?,?,?,?,?,?)",
                               [(run_at, keyword, country, device, *s) for s in serp])
                db.commit()
                where = f"#{pos}  {url}" if pos else f"not in top {len(serp)}"
                ai = " | AI Overview cites you" if cited else (" | AI Overview" if has_ai else "")
                print(f"{keyword!r} [{country}/{device}] {domain}: {where}{ai}")
    print(f"Run {run_at} saved to {args.db}. Credits used: {client.credits_used}")


def runs(db):
    return [r[0] for r in db.execute("SELECT DISTINCT run_at FROM rankings ORDER BY run_at DESC")]


def cmd_report(args):
    db = connect(args.db)
    all_runs = runs(db)
    if not all_runs:
        sys.exit(f"No data in {args.db}. Run: python rank_tracker.py track")
    latest = all_runs[0]
    rows = db.execute("SELECT * FROM rankings WHERE run_at=? ORDER BY keyword, country, device", (latest,)).fetchall()
    out = []
    print(f"Rank report for run {latest}" + (f" vs previous run" if len(all_runs) > 1 else " (first run)"))
    print(f"{'keyword':32} {'cc':3} {'device':7} {'domain':22} {'pos':>4} {'prev':>4} {'change':>8}  url")
    for r in rows:
        prev = db.execute("SELECT position FROM rankings WHERE keyword=? AND domain=? AND country=? AND device=?"
                          " AND run_at<? ORDER BY run_at DESC LIMIT 1",
                          (r["keyword"], r["domain"], r["country"], r["device"], latest)).fetchone()
        p, q = r["position"], (prev["position"] if prev else None)
        if prev is None:
            change = "new"
        elif p is None and q is None:
            change = "-"
        elif p is None:
            change = "lost"
        elif q is None:
            change = "entered"
        elif p == q:
            change = "="
        else:
            change = f"{'+' if q > p else '-'}{abs(q - p)}"  # moving up = smaller number = '+'
        out.append({"run_at": latest, "keyword": r["keyword"], "country": r["country"], "device": r["device"],
                    "domain": r["domain"], "position": p, "previous": q, "change": change, "url": r["url"]})
        print(f"{r['keyword'][:32]:32} {r['country']:3} {r['device']:7} {r['domain'][:22]:22} "
              f"{p if p else '-':>4} {q if q else '-':>4} {change:>8}  {r['url'] or ''}")
    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        print(f"Wrote {args.output}")


def cmd_export(args):
    db = connect(args.db)
    rows = db.execute("SELECT run_at, keyword, domain, country, device, position, url, title, pages_checked,"
                      " has_ai_overview, cited_in_ai_overview FROM rankings ORDER BY keyword, country, device, run_at"
                      ).fetchall()
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(rows[0].keys() if rows else ["run_at"])
        w.writerows([tuple(r) for r in rows])
    print(f"Wrote {len(rows)} rows to {args.output}")


def main():
    ap = argparse.ArgumentParser(description="Track Google rankings for your keywords.")
    ap.add_argument("--db", default="ranks.db", help="SQLite file (default: ranks.db)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("track", help="check every keyword x country x device and store positions")
    p.add_argument("-k", "--keywords", default="keywords.csv", help="CSV with keyword[,domain] (default: keywords.csv)")
    p.add_argument("--domain", help="domain to track when keywords.csv has no domain column, e.g. example.com")
    p.add_argument("--countries", default="us", help="comma-separated country codes (default: us)")
    p.add_argument("--devices", default="desktop", help="desktop, mobile or desktop,mobile (default: desktop)")
    p.add_argument("--pages", type=int, default=1, choices=range(1, 11), metavar="1-10",
                   help="how deep to look; stops early once the domain is found (default: 1, about the top 10)")
    p.set_defaults(func=cmd_track)

    p = sub.add_parser("report", help="latest run vs the previous run")
    p.add_argument("-o", "--output", help="also write the report to this CSV")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("export", help="full ranking history as CSV")
    p.add_argument("-o", "--output", default="rankings.csv")
    p.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
