#!/usr/bin/env python3
"""Email each new AI Brief issue through Buttondown, after the push that publishes it.

Runs in GitHub Actions (.github/workflows/email.yml), never on anyone's computer. Written by the
private pipeline (newsletter.py site); do not edit it in this repo.

Two stages (Shashank, November 18, 2026). "push" writes email/pending/DATE.json: it goes only to the
subscribers tagged "tester" in Buttondown, as a test. After Shashank reads it and writes "send", the file moves to
email/daily/DATE.json, and that push mails every subscriber. For email/daily/ this script:

  1. lists the email files the push ADDED (an amended issue changes its file and is not sent again),
  2. skips any issue more than MAX_AGE_DAYS old (a catch-up push never mails old issues),
  3. waits until the issue page is live, so every link in the email works,
  4. checks Buttondown has no email for that edition yet (a re-run never sends twice),
  5. asks Buttondown to send it now.

The key comes from the repository secret BUTTONDOWN_API_KEY and is never written anywhere.

    python3 tools/send_email.py --new-since BEFORE_SHA     what the workflow runs on a push
    python3 tools/send_email.py email/daily/DATE.json      send one file (manual run of the workflow)
    python3 tools/send_email.py --test-new-since BEFORE_SHA   stage one: each new or changed file in
                                                              email/pending/ goes ONLY to subscribers
                                                              tagged "tester" in Buttondown, as a test
    python3 tools/send_email.py --test FILE                    a test: the same email sent only to the
                                                              subscribers tagged "tester", never to the others
    add --dry-run to print what would be sent without calling Buttondown
"""
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.buttondown.com/v1"
API_VERSION = "2026-04-01"
SITE = "https://ai.mediancanadian.ca/"
MAX_AGE_DAYS = 3
LIVE_WAIT_SECONDS = 15 * 60
TEST_TAG = "tester"
UA = "ai-brief-mailer (+https://ai.mediancanadian.ca)"


def note(msg):
    print(msg, flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(msg + "\n\n")


def added_files(before):
    if not before or set(before) == {"0"}:
        note("No earlier commit to compare with; nothing is sent automatically.")
        return []
    # --no-renames: "send" moves a file from email/pending/ into email/daily/, which must count as added
    out = subprocess.run(["git", "diff", "--no-renames", "--diff-filter=A", "--name-only", before, "HEAD", "--", "email/daily/"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(line for line in out.split() if line.endswith(".json"))


def call(method, path, key, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Token {key}", "Content-Type": "application/json", "User-Agent": UA,
                 "X-API-Version": API_VERSION, "X-Buttondown-Live-Dangerously": "true"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"Buttondown said {e.code} to {method} {path}: {detail}")


def is_live(url):
    deadline = time.time() + LIVE_WAIT_SECONDS
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url + f"?v={int(time.time())}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(20)
    return False


def already_sent(key, edition):
    """The real email of this edition, if Buttondown has one (test drafts do not count)."""
    data = call("GET", "/emails", key) or {}
    for e in data.get("results", []):
        meta = e.get("metadata") or {}
        if meta.get("edition") == edition and not meta.get("test") and e.get("status") not in ("draft", "deleted"):
            return e.get("id") or True
    return None


def tag_id(key, name):
    data = call("GET", "/tags", key) or {}
    for t in data.get("results", []):
        if t.get("name") == name:
            return t.get("id")
    return None


def send(path, key, dry):
    e = json.load(open(path, encoding="utf-8"))
    date = datetime.date.fromisoformat(e["date"])
    age = (datetime.datetime.now(datetime.timezone.utc).date() - date).days
    if age > MAX_AGE_DAYS:
        note(f"{e['edition']}: {age} days old, not sent (only issues from the last {MAX_AGE_DAYS} days go out).")
        return
    url = SITE + e["url"]
    if dry:
        note(f"DRY RUN {e['edition']}: would wait for {url}, then send \"{e['subject']}\" ({len(e['body'])} characters).")
        return
    if not key:
        raise SystemExit("BUTTONDOWN_API_KEY is not set. Add it at "
                         "https://github.com/mediancanadian/ai-brief/settings/secrets/actions/new")
    if not is_live(url):
        raise SystemExit(f"{url} was not live after {LIVE_WAIT_SECONDS // 60} minutes; nothing sent. Re-run the workflow once the page is up.")
    found = already_sent(key, e["edition"])
    if found:
        note(f"{e['edition']}: Buttondown already has this email ({found}); not sent again.")
        return
    filters = {"filters": [], "groups": [], "predicate": "and"}
    if e.get("exclude_tag"):
        tid = tag_id(key, e["exclude_tag"])
        if tid:
            filters["filters"].append({"field": "subscriber.tags", "operator": "not_contains", "value": tid})
    body = {"subject": e["subject"], "body": e["body"], "status": "about_to_send",
            # the inbox preview line: the deck, not the headline again (Shashank, November 14, 2026)
            **({"description": e["preview"]} if e.get("preview") else {}),
            "canonical_url": url, "metadata": {"edition": e["edition"]}, "filters": filters}
    r = call("POST", "/emails", key, body) or {}
    note(f"{e['edition']}: \"{e['subject']}\" handed to Buttondown ({r.get('id', '?')}, status {r.get('status', '?')}).")


def test(path, key, dry):
    """A test send before anything goes to readers: the same email, saved as a draft (kept out of the
    archive) and sent only to the address the Buttondown account uses. Subscribers never get it. The
    previous test draft is deleted first, so at most one sits in Buttondown. One secret only."""
    e = json.load(open(path, encoding="utf-8"))
    if dry:
        note(f"DRY RUN test of {e['edition']}: \"[Test] {e['subject']}\" to the subscribers tagged \"{TEST_TAG}\" only.")
        return
    if not key:
        raise SystemExit("BUTTONDOWN_API_KEY is not set in this repository's secrets.")
    # The test goes to the subscribers tagged "tester" in Buttondown (Shashank, November 18, 2026: his own
    # address carries the tag; no address is written in this public repo). Nobody tagged: nothing is sent.
    tid = tag_id(key, TEST_TAG)
    to = []
    if tid:
        for kind in ("regular", "unactivated"):
            page = call("GET", f"/subscribers?type={kind}&tag={tid}", key) or {}
            to += [x["email_address"] for x in page.get("results", []) if tid in (x.get("tags") or []) or TEST_TAG in (x.get("tags") or [])]
    to = sorted(set(to))
    if not to:
        raise SystemExit(f"No subscriber carries the '{TEST_TAG}' tag in Buttondown; no test was sent.")
    for old in (call("GET", "/emails?status=draft", key) or {}).get("results", []):
        if old.get("status") == "draft" and (old.get("metadata") or {}).get("test"):
            try:
                call("DELETE", f"/emails/{old['id']}", key)
            except SystemExit as err:
                note(f"Could not delete the old test draft: {err}")
    draft = call("POST", "/emails", key, {"subject": "[Test] " + e["subject"], "body": e["body"], "status": "draft",
                                          **({"description": e["preview"]} if e.get("preview") else {}),
                                          "archival_mode": "disabled", "metadata": {"edition": e["edition"], "test": True}}) or {}
    call("POST", f"/emails/{draft['id']}/send-draft", key, {"recipients": to})
    note(f"Test of {e['edition']} sent to {len(to)} tester address(es) only; subscribers got nothing.")


def pending_files(before):
    """Test emails the push added or changed in email/pending/ (stage one: only Shashank gets them)."""
    if not before or set(before) == {"0"}:
        return []
    out = subprocess.run(["git", "diff", "--no-renames", "--diff-filter=AM", "--name-only", before, "HEAD", "--", "email/pending/"],
                         capture_output=True, text=True, check=True).stdout
    return sorted(line for line in out.split() if line.endswith(".json"))


def main(argv):
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if len(argv) == 2 and argv[0] == "--test":
        test(argv[1], key, dry)
        return
    if len(argv) == 2 and argv[0] == "--test-new-since":
        files = pending_files(argv[1])
        if not files:
            note("No new test email.")
        for f in files:
            test(f, key, dry)
        return
    if len(argv) == 2 and argv[0] == "--new-since":
        files = added_files(argv[1])
    elif len(argv) == 1:
        files = [argv[0]]
    else:
        raise SystemExit(__doc__)
    if not files:
        note("No new issue to email.")
    for f in files:
        send(f, key, dry)


if __name__ == "__main__":
    main(sys.argv[1:])
