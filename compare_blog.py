#!/usr/bin/env python3
"""
Compare local blog markdown files against their live blogspot source URLs.

Usage:
    python3 compare_blog.py [blog_dir]

Prints MATCH or a diff for each post. Requires: pip install beautifulsoup4 requests
"""

import os, sys, re, difflib, urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dependency: pip install beautifulsoup4")

BLOG_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "blog"


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def extract_blogspot_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Blogger post body is in .post-body or .entry-content
    body = soup.select_one(".post-body") or soup.select_one(".entry-content")
    if not body:
        return ""
    # Remove script/style tags
    for tag in body(["script", "style"]):
        tag.decompose()
    text = body.get_text(separator="\n")
    # Normalise whitespace
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def extract_md_body(content: str) -> str:
    # Strip frontmatter
    if content.startswith("---"):
        end = content.index("---", 3)
        content = content[end + 3:]
    lines = [ln.strip() for ln in content.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def parse_frontmatter(content: str) -> dict:
    meta = {}
    if not content.startswith("---"):
        return meta
    end = content.index("---", 3)
    for line in content[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    return meta


def main():
    files = sorted(BLOG_DIR.glob("*.md"))
    files = [f for f in files if f.name != "README.md"]

    mismatches = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        source = meta.get("source", "")
        if not source:
            print(f"[SKIP]  {path.name}  — no source URL")
            continue

        try:
            html = fetch_url(source)
        except Exception as e:
            print(f"[ERROR] {path.name}  — {e}")
            continue

        live = extract_blogspot_body(html)
        local = extract_md_body(content)

        if not live:
            print(f"[WARN]  {path.name}  — could not extract body from live page")
            continue

        if live == local:
            print(f"[MATCH] {path.name}")
        else:
            diff = list(difflib.unified_diff(
                local.splitlines(), live.splitlines(),
                fromfile=f"local/{path.name}",
                tofile=f"live/{source}",
                lineterm="",
            ))
            print(f"\n[DIFF]  {path.name}")
            print("\n".join(diff[:80]))
            if len(diff) > 80:
                print(f"  ... ({len(diff) - 80} more lines)")
            mismatches.append(path.name)

    print(f"\n{'='*60}")
    print(f"Done. {len(mismatches)} file(s) with differences.")
    if mismatches:
        for m in mismatches:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
