#!/usr/bin/env python3
"""Render a "Top Languages by Repo" donut card as a self-contained SVG.

Third-party card services (github-readme-stats, github-profile-summary-cards)
proved unreliable, so the card is generated here and committed to the output
branch instead of being fetched at page-render time.
"""

import json
import math
import os
import sys
import urllib.error
import urllib.request
from collections import Counter

USER = os.environ.get("GH_USER", "shrutidc")
OUT = os.environ.get("OUT_PATH", "dist/top-languages.svg")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
TOP_N = 5

# tokyonight, matched to the streak card sitting beside it
BG = "#1a1b27"
BORDER = "#2f3b54"
TITLE = "#70a5fd"
TEXT = "#a9fef7"

LANG_COLORS = {
    "Python": "#3572A5",
    "Jupyter Notebook": "#DA5B0B",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "C": "#555555",
    "C++": "#f34b7d",
    "Java": "#b07219",
    "R": "#198CE7",
    "TeX": "#3D6117",
    "Shell": "#89e051",
    "Perl": "#0298c3",
    "Dockerfile": "#384d54",
    "Makefile": "#427819",
}
FALLBACK = ["#6e9ef7", "#9d7cd8", "#38bdae", "#ff9e64", "#f7768e"]


def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    """Average each repo's language mix, weighting every repo equally.

    Two simpler metrics both mislead here. Counting repos by primary language
    is degenerate (nearly every repo has a distinct one, so all slices tie).
    Summing raw bytes lets Jupyter Notebook swamp everything at ~89%, since
    notebooks embed base64 output images. Averaging per-repo shares keeps one
    large repo from speaking for the whole profile.
    """
    shares = Counter()
    repo_count = 0
    page = 1
    while True:
        repos = api(
            f"https://api.github.com/users/{USER}/repos"
            f"?per_page=100&type=owner&page={page}"
        )
        if not repos:
            break
        for repo in repos:
            if repo.get("fork") or repo.get("archived"):
                continue
            langs = api(repo["languages_url"])
            repo_total = sum(langs.values())
            if not repo_total:
                continue
            repo_count += 1
            for lang, nbytes in langs.items():
                shares[lang] += nbytes / repo_total
        if len(repos) < 100:
            break
        page += 1
    if repo_count:
        for lang in shares:
            shares[lang] /= repo_count
    return shares


def arc(cx, cy, r_out, r_in, start, end, color):
    """One donut segment. A full circle needs two arcs, so cap and split."""
    if end - start >= 2 * math.pi - 1e-9:
        return (
            f'<circle cx="{cx}" cy="{cy}" r="{(r_out + r_in) / 2:.2f}" fill="none" '
            f'stroke="{color}" stroke-width="{r_out - r_in:.2f}" />'
        )
    large = 1 if (end - start) > math.pi else 0
    x1, y1 = cx + r_out * math.cos(start), cy + r_out * math.sin(start)
    x2, y2 = cx + r_out * math.cos(end), cy + r_out * math.sin(end)
    x3, y3 = cx + r_in * math.cos(end), cy + r_in * math.sin(end)
    x4, y4 = cx + r_in * math.cos(start), cy + r_in * math.sin(start)
    return (
        f'<path d="M {x1:.2f} {y1:.2f} A {r_out} {r_out} 0 {large} 1 {x2:.2f} {y2:.2f} '
        f'L {x3:.2f} {y3:.2f} A {r_in} {r_in} 0 {large} 0 {x4:.2f} {y4:.2f} Z" '
        f'fill="{color}" />'
    )


def render(counts):
    top = counts.most_common(TOP_N)
    if not top:
        raise SystemExit("no languages found — refusing to write an empty card")

    total = sum(n for _, n in top)
    w, h = 360, 200
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="Top languages by repository">',
        "<style>text{font-family:'Segoe UI',Ubuntu,'Helvetica Neue',Sans-Serif}</style>",
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="6" fill="{BG}" '
        f'stroke="{BORDER}" />',
        f'<text x="25" y="35" fill="{TITLE}" font-size="18" font-weight="600">'
        f"Top Languages by Repo</text>",
    ]

    y = 62
    for i, (lang, n) in enumerate(top):
        color = LANG_COLORS.get(lang, FALLBACK[i % len(FALLBACK)])
        label = lang if len(lang) <= 16 else lang[:15] + "…"
        pct = 100 * n / total
        parts.append(
            f'<rect x="25" y="{y - 9}" width="11" height="11" rx="2" fill="{color}" />'
        )
        parts.append(
            f'<text x="45" y="{y}" fill="{TEXT}" font-size="13">{label} '
            f'<tspan opacity="0.65">{pct:.1f}%</tspan></text>'
        )
        y += 24

    cx, cy, r_out, r_in = 280, 110, 52, 30
    angle = -math.pi / 2
    for i, (lang, n) in enumerate(top):
        color = LANG_COLORS.get(lang, FALLBACK[i % len(FALLBACK)])
        sweep = 2 * math.pi * n / total
        parts.append(arc(cx, cy, r_out, r_in, angle, angle + sweep, color))
        angle += sweep

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    try:
        counts = collect()
    except urllib.error.HTTPError as e:
        print(f"GitHub API error: {e}", file=sys.stderr)
        return 1
    svg = render(counts)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(svg)
    print(f"wrote {OUT}: {dict(counts.most_common(TOP_N))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
