#!/usr/bin/env python3
"""Add published app releases to the changelog and point the download links at the latest installer.

The release notes on GitHub are the source: a plain sentence becomes one item,
Markdown "- " bullets become one item each (**bold** and `code` are kept).
Versions already on the page are never touched, so hand-written entries stay as they are.
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RELEASES_REPO = os.environ.get("RELEASES_REPO", "Jhacarreiro/track-mode-studio-releases")
ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "changelog" / "index.html"
INDEX = ROOT / "index.html"
TZ = ZoneInfo("Europe/Lisbon")
EXE_LINK = re.compile(
    r"https://github\.com/" + re.escape(RELEASES_REPO) + r"/releases/download/v[^/\"]+/[^\"]+\.exe"
)


def fetch_releases():
    if len(sys.argv) > 1:
        return json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    req = urllib.request.Request(
        f"https://api.github.com/repos/{RELEASES_REPO}/releases?per_page=100",
        headers={"Accept": "application/vnd.github+json"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def version_key(tag):
    return tuple(int(n) for n in re.findall(r"\d+", tag))


def inline(text):
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)


def items(body):
    lines = [line.strip() for line in (body or "").replace("\r", "").split("\n")]
    bullets = [re.sub(r"^[-*]\s+", "", line) for line in lines if re.match(r"^[-*]\s+", line)]
    if bullets:
        return bullets
    text = " ".join(line for line in lines if line)
    return [text] if text else []


def entry(release):
    version = release["tag_name"].lstrip("v")
    published = datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")).astimezone(TZ)
    date = f"{published.day} {published:%B %Y}"
    lis = "\n".join(f"      <li>{inline(item)}</li>" for item in items(release.get("body")))
    return (
        f'    <h2 id="v{version}">{version} <span class="updated">{date}</span></h2>\n'
        f"    <ul>\n{lis}\n    </ul>\n\n"
    )


def main():
    releases = sorted(
        (r for r in fetch_releases() if not r.get("draft") and not r.get("prerelease") and r.get("published_at")),
        key=lambda r: version_key(r["tag_name"]),
    )
    if not releases:
        print("no published releases")
        return

    page = CHANGELOG.read_text(encoding="utf-8")
    if not re.search(r'^    <h2 id="v', page, re.M):
        sys.exit("changelog has no version heading to insert above")
    new = [r for r in releases if f'id="v{r["tag_name"].lstrip("v")}"' not in page and items(r.get("body"))]
    for release in new:
        # Above the first older version, so a release that gets its notes late still lands in order.
        key = version_key(release["tag_name"])
        spot = next(
            (m.start() for m in re.finditer(r'^    <h2 id="(v[^"]+)"', page, re.M) if version_key(m.group(1)) < key),
            None,
        )
        if spot is None:
            spot = page.index("  </main>")
        page = page[:spot] + entry(release) + page[spot:]
    if new:
        CHANGELOG.write_text(page, encoding="utf-8")
        print("changelog: added " + ", ".join(r["tag_name"] for r in new))

    latest = releases[-1]
    exe = next((a["browser_download_url"] for a in latest.get("assets", []) if a["name"].endswith(".exe")), None)
    if exe:
        index = INDEX.read_text(encoding="utf-8")
        updated = EXE_LINK.sub(exe, index)
        if updated != index:
            INDEX.write_text(updated, encoding="utf-8")
            print(f"download links: {exe}")


if __name__ == "__main__":
    main()
