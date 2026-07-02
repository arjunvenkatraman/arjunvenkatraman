#!/usr/bin/env python3
"""
Sync local blog markdown files against their live Blogspot source URLs.

Usage:
    python3 compare_blog.py [--dry-run] [blog_dir]

Modes:
    (default)   Fetch each post's source URL, diff against local MD, and
                overwrite the file body with the live text if different.
    --dry-run   Report differences only; write nothing.

Requirements: pip install beautifulsoup4
"""

import os, re, sys, difflib, urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency: pip install beautifulsoup4")

DRY_RUN  = "--dry-run" in sys.argv
args     = [a for a in sys.argv[1:] if not a.startswith("--")]
BLOG_DIR = Path(args[0]) if args else Path(__file__).parent / "blog"


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_blogspot_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".post-body") or soup.select_one(".entry-content")
    if not body:
        return ""
    for tag in body(["script", "style", "br"]):
        tag.decompose()
    # Preserve paragraph breaks
    for p in body.find_all(["p", "div", "h1", "h2", "h3", "h4", "li"]):
        p.insert_before("\n")
        p.insert_after("\n")
    text = body.get_text()
    # Collapse runs of blank lines to a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Returns (meta dict, body text after frontmatter)."""
    meta, body = {}, content
    if content.startswith("---"):
        end = content.index("---", 3)
        for line in content[3:end].splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"')
        body = content[end + 3:].lstrip("\n")
    return meta, body


def rebuild_file(content: str, new_body: str) -> str:
    """Swap the body section while keeping frontmatter intact."""
    if content.startswith("---"):
        end = content.index("---", 3)
        frontmatter = content[:end + 3]
        return frontmatter + "\n\n" + new_body + "\n"
    return new_body + "\n"


def main():
    files   = sorted(BLOG_DIR.glob("*.md"))
    files   = [f for f in files if f.name != "README.md"]
    synced  = []
    errors  = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        meta, local_body = parse_frontmatter(content)
        source = meta.get("source", "")

        if not source:
            print(f"[SKIP]  {path.name}  — no source URL")
            continue

        try:
            html = fetch_url(source)
        except Exception as e:
            print(f"[ERROR] {path.name}  — {e}")
            errors.append(path.name)
            continue

        live_body = extract_blogspot_body(html)
        if not live_body:
            print(f"[WARN]  {path.name}  — could not extract body from live page")
            continue

        local_norm = local_body.strip()
        live_norm  = live_body.strip()

        if local_norm == live_norm:
            print(f"[MATCH] {path.name}")
            continue

        diff = list(difflib.unified_diff(
            local_norm.splitlines(),
            live_norm.splitlines(),
            fromfile=f"local/{path.name}",
            tofile=f"live",
            lineterm="",
        ))
        print(f"\n[DIFF]  {path.name}")
        for line in diff[:60]:
            print(line)
        if len(diff) > 60:
            print(f"  ... ({len(diff) - 60} more lines)")

        if not DRY_RUN:
            path.write_text(rebuild_file(content, live_body), encoding="utf-8")
            print(f"  → Updated {path.name}")
            synced.append(path.name)

    print(f"\n{'='*60}")
    if DRY_RUN:
        print("Dry-run complete (no files written).")
    else:
        print(f"Synced {len(synced)} file(s).  Errors: {len(errors)}.")
        if synced:
            print("\nUpdated:")
            for s in synced:
                print(f"  {s}")
        if errors:
            print("\nErrors:")
            for e in errors:
                print(f"  {e}")


if __name__ == "__main__":
    main()
