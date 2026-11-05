#!/usr/bin/env python3
"""Fill index.json with each issue's stories, read from the issue pages themselves.

The archive page (index.html) draws one card per issue from index.json. The
card shows the issue's story labels and lead lines, so they are copied from the
issue's own HTML here rather than typed twice. Run it after adding an issue:

    python3 tools/build_index.py          rewrites index.json
    python3 tools/build_index.py --check  exits with an error if index.json is out of date

It stops with a message if an issue page has no entry in index.json, or an
entry points at a page that does not exist.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.json"

CARD = re.compile(
    r'<h4 class="story-head">(.*?)</h4>\s*<p class="story-lead">(.*?)</p>', re.S)
DECK = re.compile(r'<p class="lead-deck">(.*?)</p>', re.S)


def plain(fragment, dash=", "):
    """Text of an HTML fragment. Em dashes in older issues become commas on the
    cards (a colon in labels); the issue pages themselves are left as published."""
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment))
    text = re.sub(r"\s*\u2014\s*", dash, text)
    return re.sub(r"\s+", " ", text).strip()


def read_issue(path):
    page = path.read_text(encoding="utf-8")
    stories = [{"label": plain(a, ": "), "text": plain(b)} for a, b in CARD.findall(page)]
    deck = DECK.search(page)
    return stories, plain(deck.group(1)) if deck else ""


def dump(data):
    """Write index.json the way it is kept by hand: one field per line, lists inline."""
    out = ["{", '  "issues": [']
    issues = data["issues"]
    for n, issue in enumerate(issues):
        out.append("    {")
        keys = list(issue.keys())
        for k, key in enumerate(keys):
            value = issue[key]
            comma = "," if k < len(keys) - 1 else ""
            if key == "stories":
                out.append('      "stories": [')
                for s, story in enumerate(value):
                    tail = "," if s < len(value) - 1 else ""
                    out.append("        " + json.dumps(story, ensure_ascii=False) + tail)
                out.append("      ]" + comma)
            else:
                out.append(f"      {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}{comma}")
        out.append("    }" + ("," if n < len(issues) - 1 else ""))
    out += ["  ]", "}", ""]
    return "\n".join(out)


def main():
    check = "--check" in sys.argv
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    listed = {issue["url"] for issue in data["issues"]}
    on_disk = {p.relative_to(ROOT).as_posix() for p in (ROOT / "issues").rglob("*.html")}
    problems = [f"no entry in index.json for {p}" for p in sorted(on_disk - listed)]
    problems += [f"index.json lists {p}, which does not exist" for p in sorted(listed - on_disk)]
    if problems:
        sys.exit("index.json and the issues folder disagree:\n  " + "\n  ".join(problems))

    for issue in data["issues"]:
        stories, deck = read_issue(ROOT / issue["url"])
        if not stories:
            sys.exit(f"{issue['url']} has no story cards to list")
        issue["stories"] = stories
        if deck:
            issue["deck"] = deck
    data["issues"].sort(key=lambda i: i["date"], reverse=True)

    text = dump(data)
    json.loads(text)  # the hand-style writer must still produce valid JSON
    if check:
        if INDEX.read_text(encoding="utf-8") != text:
            sys.exit("index.json is out of date: run python3 tools/build_index.py")
        print("index.json is up to date")
        return
    INDEX.write_text(text, encoding="utf-8")
    total = sum(len(i["stories"]) for i in data["issues"])
    print(f"index.json: {len(data['issues'])} issues, {total} stories")


if __name__ == "__main__":
    main()
