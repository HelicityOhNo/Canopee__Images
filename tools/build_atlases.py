#!/usr/bin/env python3
"""Pack the Station Canopée posters into the files the VRChat world downloads.

    python tools/build_atlases.py

Reads   posters/       one image per poster (JPG, PNG or WebP, portrait 1:2, ideally 512 x 1024)
        posters.json   display time, play order, and each poster's title and link
Writes  _site/         manifest.json, pub_atlas_N.jpg (2048 px, PC), pub_atlas_N_quest.jpg (1024 px, Quest and iOS),
                       and index.html with thumbs/ for the public preview page

VRChat lets a world download one image every five seconds, so posters travel as up to three atlases of
eight (four columns by two rows, left to right, then top to bottom) instead of one file each.
Posters are packed without gaps: images that are missing, unreadable or fully transparent are left out,
and the world only cycles through the posters listed in the manifest, so it never shows an empty slot.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
COLUMNS, ROWS = 4, 2
PER_ATLAS = COLUMNS * ROWS
MAX_POSTERS = 3 * PER_ATLAS
CELL_PC = (512, 1024)
CELL_QUEST = (256, 512)
THUMB = (384, 768)
BACKGROUND = (21, 27, 24)
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "HelicityOhNo/Canopee__Images")


def warn(message: str, file: str | None = None) -> None:
    """Print a warning; on GitHub Actions it also shows on the workflow run."""
    if IN_ACTIONS:
        print(f"::warning{' file=' + file if file else ''}::{message}")
    else:
        print(f"warning: {message}")


def fail(message: str, file: str | None = None, line: int | None = None) -> None:
    if IN_ACTIONS:
        location = (f" file={file}" if file else "") + (f",line={line}" if file and line else "")
        print(f"::error{location}::{message}")
    sys.exit(f"error: {message}")


def valid_link(url: str) -> bool:
    """Same rule as the world (SP_Affichage._LienValide): http(s), a dotted host name, no spaces, 300 characters at most."""
    if not url or len(url) > 300 or re.search(r"\s", url):
        return False
    match = re.match(r"^https?://([^/?#:]+)", url, re.IGNORECASE)
    if not match:
        return False
    host = re.sub(r"^www\.", "", match.group(1), flags=re.IGNORECASE)
    return len(host) >= 3 and "." in host[1:] and not host.endswith(".")


def default_title(file_name: str) -> str:
    words = re.sub(r"[-_]+", " ", Path(file_name).stem).strip()
    return words[:1].upper() + words[1:] if words else file_name


def load_config(path: Path) -> tuple[float, dict]:
    if not path.exists():
        return 10, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"{path.name} is not valid JSON: {error.msg} (line {error.lineno}, column {error.colno})", path.name, error.lineno)
    if not isinstance(data, dict):
        fail(f"{path.name} must contain a JSON object", path.name)
    seconds = data.get("slideSeconds", 10)
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 2 <= seconds <= 60:
        warn(f"slideSeconds must be a number from 2 to 60, got {seconds!r}: using 10", path.name)
        seconds = 10
    posters = data.get("posters") or {}
    if not isinstance(posters, dict):
        fail(f'"posters" in {path.name} must be an object, keyed by image file name', path.name)
    return (int(seconds) if float(seconds).is_integer() else seconds), posters


def load_poster(path: Path) -> Image.Image | None:
    """The poster as an opaque RGB image, or None if it cannot be shown."""
    where = f"posters/{path.name}"
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
    except (UnidentifiedImageError, OSError) as error:
        warn(f"{path.name} could not be read ({error}): left out", where)
        return None
    if image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGBA")
        if image.getchannel("A").getextrema()[1] == 0:
            warn(f"{path.name} is fully transparent: left out", where)
            return None
        flat = Image.new("RGBA", image.size, BACKGROUND + (255,))
        flat.alpha_composite(image)
        image = flat
    image = image.convert("RGB")
    if abs(image.width / image.height - 0.5) > 0.02:
        warn(f"{path.name} is {image.width} x {image.height}, not portrait 1:2: center-cropped", where)
    return image


CARD = """      <figure>
        <img src="thumbs/@@THUMB@@" width="384" height="768" alt="@@TITLE@@" loading="lazy">
        <figcaption><span>@@TITLE@@</span>@@LINK@@</figcaption>
      </figure>
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="description" content="The posters on the ad panels of Station Canopée, a VRChat world by Helicity.">
<title>Station Canopée posters</title>
<style>
  :root { --bg: #000; --card: #1c2420; --line: #2b3530; --text: #eef3ee; --muted: #9daaa2; --accent: #a6eb7a; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 1180px; margin: 0 auto; padding: 56px 24px 72px; }
  h1 { margin: 0 0 12px; font-size: clamp(32px, 5vw, 48px); line-height: 1.1; font-weight: 650; }
  .intro { max-width: 640px; margin: 0 0 40px; color: var(--muted); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 28px 24px; }
  figure { margin: 0; }
  figure img { display: block; width: 100%; height: auto; aspect-ratio: 1 / 2; object-fit: cover; border-radius: 14px; background: var(--card); }
  figcaption { padding: 12px 2px 0; font-size: 15px; }
  figcaption span { display: block; font-weight: 600; }
  figcaption a { display: block; overflow: hidden; color: var(--accent); font-size: 14px; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
  figcaption a:hover { text-decoration: underline; }
  footer { margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px; }
  footer a { color: var(--text); }
</style>
</head>
<body>
<main>
  <h1>Posters</h1>
  <p class="intro">The posters on the station's ad panels.</p>
  <div class="grid">
@@CARDS@@  </div>
  <footer>Station Canopée is a VRChat world by Helicity. <a href="https://github.com/@@REPO@@">Source on GitHub</a></footer>
</main>
</body>
</html>
"""


def card_html(thumb: str, title: str, link: str) -> str:
    link_html = ""
    if link:
        shown = re.sub(r"^https?://(www\.)?", "", link, flags=re.IGNORECASE).rstrip("/")
        link_html = f'<a href="{html.escape(link)}" rel="noopener">{html.escape(shown)}</a>'
    return CARD.replace("@@THUMB@@", html.escape(thumb)).replace("@@TITLE@@", html.escape(title)).replace("@@LINK@@", link_html)


def build(posters_dir: Path, config_path: Path, out: Path) -> None:
    seconds, entries = load_config(config_path)
    files = {}
    if posters_dir.is_dir():
        files = {p.name: p for p in sorted(posters_dir.iterdir(), key=lambda p: p.name.lower())
                 if p.is_file() and p.suffix.lower() in EXTENSIONS}
    for name in entries:
        if name not in files:
            warn(f"{config_path.name} lists {name}, which is not in posters/: skipped", config_path.name)
    order = [name for name in entries if name in files] + [name for name in files if name not in entries]

    posters = []
    for name in order:
        image = load_poster(files[name])
        if image is None:
            continue
        info = entries.get(name) if isinstance(entries.get(name), dict) else {}
        title = str(info.get("title") or default_title(name)).strip()[:60]
        link = str(info.get("link") or "").strip()
        if link and not valid_link(link):
            warn(f"{name}: the world would refuse the link {link!r} (it needs http:// or https:// and a domain name): no link", config_path.name)
            link = ""
        posters.append((name, image, title, link))
    if len(posters) > MAX_POSTERS:
        warn(f"{len(posters)} posters, the world shows at most {MAX_POSTERS}: left out " + ", ".join(p[0] for p in posters[MAX_POSTERS:]))
        posters = posters[:MAX_POSTERS]
    if not posters:
        fail("no usable poster in posters/: nothing published, the live site keeps its previous version")

    atlas_count = -(-len(posters) // PER_ATLAS)
    pc = [Image.new("RGB", (CELL_PC[0] * COLUMNS, CELL_PC[1] * ROWS), BACKGROUND) for _ in range(atlas_count)]
    quest = [Image.new("RGB", (CELL_QUEST[0] * COLUMNS, CELL_QUEST[1] * ROWS), BACKGROUND) for _ in range(atlas_count)]
    (out / "thumbs").mkdir(parents=True, exist_ok=True)
    ads, cards, used = [], [], set()
    for index, (name, image, title, link) in enumerate(posters):
        atlas, cell = divmod(index, PER_ATLAS)
        column, row = cell % COLUMNS, cell // COLUMNS
        pc[atlas].paste(ImageOps.fit(image, CELL_PC, Image.Resampling.LANCZOS), (column * CELL_PC[0], row * CELL_PC[1]))
        quest[atlas].paste(ImageOps.fit(image, CELL_QUEST, Image.Resampling.LANCZOS), (column * CELL_QUEST[0], row * CELL_QUEST[1]))
        thumb, n = Path(name).stem + ".jpg", 2
        while thumb in used:
            thumb, n = f"{Path(name).stem}-{n}.jpg", n + 1
        used.add(thumb)
        ImageOps.fit(image, THUMB, Image.Resampling.LANCZOS).save(out / "thumbs" / thumb, quality=85, optimize=True)
        ads.append({"atlas": atlas, "col": column, "row": row, "title": title, "link": link, "image": name})
        cards.append(card_html(thumb, title, link))

    for atlas in range(atlas_count):
        pc[atlas].save(out / f"pub_atlas_{atlas}.jpg", quality=88, optimize=True)
        quest[atlas].save(out / f"pub_atlas_{atlas}_quest.jpg", quality=85, optimize=True)
    manifest = {"slideSeconds": seconds, "atlases": atlas_count, "ads": ads}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(PAGE.replace("@@CARDS@@", "".join(cards)).replace("@@REPO@@", html.escape(REPOSITORY)), encoding="utf-8")

    linked = sum(1 for ad in ads if ad["link"])
    print(f"{len(ads)} posters in {atlas_count} atlas(es), {seconds} s each, {linked} with a link")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        rows = "".join(f"| {ad['image']} | {ad['title']} | {ad['link'] or ''} |\n" for ad in ads)
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {len(ads)} posters, {seconds} s each, {linked} with a link\n\n| Image | Title | Link |\n|---|---|---|\n{rows}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack the Station Canopée posters into the files the VRChat world downloads.")
    parser.add_argument("--posters", type=Path, default=ROOT / "posters", help="folder of poster images (default: posters/)")
    parser.add_argument("--config", type=Path, default=ROOT / "posters.json", help="titles, links and play order (default: posters.json)")
    parser.add_argument("--out", type=Path, default=ROOT / "_site", help="output folder (default: _site/)")
    args = parser.parse_args()
    build(args.posters, args.config, args.out)


if __name__ == "__main__":
    main()
