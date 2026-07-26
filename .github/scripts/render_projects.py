#!/usr/bin/env python3
"""Regenerate the Featured Projects table in the profile README from PINNED repos.

Single source of truth: whatever is pinned on the GitHub profile shows here. Each
project's description comes from the repo's own GitHub description (encode awards
there, e.g. "🏆 ..."), and tech tags come from the repo's topics (falling back to
primary language). Runs in CI and edits README.md between the PROJECTS markers.

If the API returns no pinned repos (or errors), the README is left untouched so a
transient failure can never wipe the section.
"""

import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GH_USER", "shrutidc")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
README = os.environ.get("README_PATH", "README.md")
START = "<!-- PROJECTS:START -->"
END = "<!-- PROJECTS:END -->"

# Words to keep uppercased when prettifying repo names into display titles.
ACRONYMS = {"ai", "ml", "vep", "jpm", "api", "os", "ddm", "ui", "ux", "sql",
            "html", "css", "llm", "etl"}

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


def fetch_pinned():
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
    return data["data"]["user"]["pinnedItems"]["nodes"]


def prettify(name):
    parts = re.split(r"[-_]", name)
    return " ".join(p.upper() if p.lower() in ACRONYMS else p.capitalize()
                    for p in parts if p)


def tech(node):
    topics = [t["topic"]["name"] for t in node["repositoryTopics"]["nodes"]]
    if topics:
        return " · ".join(f"`{t}`" for t in topics[:4])
    lang = (node.get("primaryLanguage") or {}).get("name")
    return f"`{lang}`" if lang else ""


def render(nodes):
    rows = ["| Project | Description | Tech |", "|---|---|---|"]
    for n in nodes:
        desc = (n.get("description") or "").replace("|", "\\|").strip()
        rows.append(f"| **[{prettify(n['name'])}]({n['url']})** | {desc} | {tech(n)} |")
    return "\n".join(rows)


def main():
    nodes = fetch_pinned()
    if not nodes:
        print("no pinned repos returned — leaving README unchanged", file=sys.stderr)
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
    print(f"updated projects section from {len(nodes)} pinned repos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
