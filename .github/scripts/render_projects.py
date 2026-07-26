#!/usr/bin/env python3
"""Regenerate the Featured Projects table in the profile README.

Single source of truth: the repos are read from GitHub, not stored in the README.
Curation order:
  1. PINNED repos (GraphQL) — whatever is pinned on the profile; or
  2. repos tagged with the `showcase` topic (REST) — used only if no pins are
     readable, so it also covers the case where GITHUB_TOKEN can't see pins.

Each project's description comes from the repo's own GitHub description (encode
awards there, e.g. "🏆 ..."); tech tags come from the repo's topics, falling back
to primary language. Runs in CI and edits README.md between the PROJECTS markers.

If neither source returns anything (or the API errors), the README is left
untouched so a transient failure can never wipe the section.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

USER = os.environ.get("GH_USER", "shrutidc")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.environ.get("README_PATH", "README.md")
SHOWCASE_TOPIC = os.environ.get("SHOWCASE_TOPIC", "showcase")
START = "<!-- PROJECTS:START -->"
END = "<!-- PROJECTS:END -->"

# Words to keep uppercased when prettifying repo names into display titles.
ACRONYMS = {"ai", "ml", "vep", "jpm", "api", "os", "ddm", "ui", "ux", "sql",
            "html", "css", "llm", "etl"}

# Curated tech tags per repo, reflecting each project's README (major skills, not
# everything). Keyed by repo name lowercased, with both current and post-rename
# names listed so it survives the renames. Takes priority over GitHub topics —
# which are often noisy — falling back to topics, then primary language, for any
# repo not listed here.
TECH_OVERRIDES = {
    "data-science-ai-agent":        ["FastAPI", "Next.js", "pandas", "Claude API"],
    "global-budget-allocation":     ["pandas", "scikit-learn", "statsmodels", "ARIMA"],
    "financial-markets-analysis-":  ["pandas", "statsmodels", "GARCH", "scikit-learn"],
    "financial-markets-analysis":   ["pandas", "statsmodels", "GARCH", "scikit-learn"],
    "exchange-latency-forensics":   ["Python", "WebSockets", "DuckDB", "pandas"],
    "supportflow":                  ["JavaScript", "Node.js", "Express", "MongoDB"],
    "serenata":                     ["DeepFace", "Gemini API", "Spotify API", "TensorFlow"],
    "pten_main_os":                 ["Canvas API", "Gemini API", "jsPDF", "JavaScript"],
    "smart-pad-layout-optimizer":   ["Canvas API", "Gemini API", "jsPDF", "JavaScript"],
    "vep-pipeline":                 ["Python", "Numba", "SciPy", "The Virtual Brain"],
    # New brand/descriptive names (post-rename); old keys kept above so the table
    # renders correctly before and after the repos are renamed.
    "framewright":                  ["FastAPI", "Next.js", "pandas", "Claude API"],
    "nanochron":                    ["Python", "WebSockets", "DuckDB", "pandas"],
    "jpm-equity-research":          ["pandas", "statsmodels", "GARCH", "scikit-learn"],
    "global-budget-analysis":       ["pandas", "scikit-learn", "statsmodels", "ARIMA"],
}

# Display titles for repos whose prettified name would lose intended casing
# (prettify would turn "SupportFlow" into "Supportflow").
DISPLAY_NAMES = {
    "supportflow": "SupportFlow",
}

QUERY = """
query($login:String!){
  user(login:$login){
    pinnedItems(first:6, types:REPOSITORY){
      nodes{ ... on Repository {
        name
        url
        description
        primaryLanguage { name }
        repositoryTopics(first:6){ nodes{ topic{ name } } }
      }}
    }
  }
}
"""


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_pinned():
    """Pinned repos via GraphQL, normalized to {name,url,description,topics,language}."""
    if not TOKEN:
        return []
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USER,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    out = []
    for n in data["data"]["user"]["pinnedItems"]["nodes"]:
        out.append({
            "name": n["name"],
            "url": n["url"],
            "description": n.get("description"),
            "topics": [t["topic"]["name"] for t in n["repositoryTopics"]["nodes"]],
            "language": (n.get("primaryLanguage") or {}).get("name"),
        })
    return out


def fetch_showcase():
    """Fallback: repos tagged with the showcase topic, via the REST search API."""
    headers = {"User-Agent": USER, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"bearer {TOKEN}"
    q = urllib.parse.quote(f"user:{USER} topic:{SHOWCASE_TOPIC} fork:true")
    data = _get(
        f"https://api.github.com/search/repositories?q={q}&sort=updated&per_page=6",
        headers,
    )
    out = []
    for r in data.get("items", []):
        out.append({
            "name": r["name"],
            "url": r["html_url"],
            "description": r.get("description"),
            "topics": [t for t in r.get("topics", []) if t != SHOWCASE_TOPIC],
            "language": r.get("language"),
        })
    return out


def prettify(name):
    parts = re.split(r"[-_]", name)
    return " ".join(p.upper() if p.lower() in ACRONYMS else p.capitalize()
                    for p in parts if p)


def tech(node):
    override = TECH_OVERRIDES.get(node["name"].lower())
    if override:
        return " · ".join(f"`{t}`" for t in override)
    if node["topics"]:
        return " · ".join(f"`{t}`" for t in node["topics"][:4])
    return f"`{node['language']}`" if node["language"] else ""


def render(nodes):
    rows = ["| Project | Description | Tech |", "|---|---|---|"]
    for n in nodes:
        desc = (n.get("description") or "").replace("|", "\\|").strip()
        title = DISPLAY_NAMES.get(n["name"].lower(), prettify(n["name"]))
        rows.append(f"| **[{title}]({n['url']})** | {desc} | {tech(n)} |")
    return "\n".join(rows)


def main():
    nodes = fetch_pinned()
    source = "pinned"
    if not nodes:
        nodes = fetch_showcase()
        source = f"topic:{SHOWCASE_TOPIC}"
    if not nodes:
        print("no pinned or showcase repos found — leaving README unchanged",
              file=sys.stderr)
        return 0

    block = f"{START}\n{render(nodes)}\n{END}"
    with open(README) as f:
        content = f.read()

    pattern = re.escape(START) + r".*?" + re.escape(END)
    if not re.search(pattern, content, flags=re.S):
        raise SystemExit("PROJECTS markers not found in README")

    new = re.sub(pattern, lambda _m: block, content, flags=re.S)
    if new == content:
        print("projects section already up to date")
        return 0

    with open(README, "w") as f:
        f.write(new)
    print(f"updated projects section from {len(nodes)} repos (source: {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
