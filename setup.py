#!/usr/bin/env python3
"""One-command setup for the post helper.

    Windows:      double-click "Setup (Windows).bat"   (or:  py setup.py)
    Mac / Linux:  python3 setup.py

What it does, start to finish:
  1. Checks you have Git and the GitHub CLI (tells you how to install them if not)
  2. Signs you in to GitHub (opens your browser)
  3. Asks for your Claude API key and checks that it works
  4. Creates your GitHub repository and uploads the project
  5. Saves your key and phone-notification channel as private GitHub secrets
  6. Turns on your post page
  7. Connects your phone and sends a test notification
  8. Writes your first post

Safe to run again any time (for example, to change your API key or after editing files):
it updates what's already there instead of starting over.
Only uses Python's standard library.
"""

from __future__ import annotations

import getpass
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / ".setup-state.json"  # remembers your choices for re-runs; never uploaded

# ── small helpers ────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if os.name == "nt":
    os.system("")  # turns on color support in the Windows terminal


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def step(n: int, total: int, text: str) -> None:
    print("\n" + _c("1", f"[{n}/{total}] {text}"))


def ok(text: str) -> None:
    print(_c("32", "  OK  ") + text)


def info(text: str) -> None:
    print("      " + text)


def warn(text: str) -> None:
    print(_c("33", "  !!  ") + text)


def fail(text: str, hint: str = "") -> None:
    print("\n" + _c("31", "  Setup stopped: ") + text)
    if hint:
        for line in hint.strip().splitlines():
            print("      " + line)
    print("\n      Fix that, then run setup again. It picks up where it left off.")
    sys.exit(1)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"      {prompt}{suffix}: ").strip()
    except EOFError:
        value = ""
    return value or default


def yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    try:
        v = input(f"      {prompt} ({d}): ").strip().lower()
    except EOFError:
        v = ""
    return default if not v else v.startswith("y")


def run(cmd: list[str], *, check: bool = True, capture: bool = True, input_text: str | None = None,
        cwd: Path = ROOT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, cwd=cwd, check=check, text=True, input=input_text,
            capture_output=capture, encoding="utf-8", errors="replace",
        )
    except subprocess.CalledProcessError as e:
        if not check:
            raise
        detail = (e.stderr or e.stdout or "").strip()
        fail(f"This command didn't work: {' '.join(cmd[:3])}...", detail[-800:])
    except FileNotFoundError:
        fail(f"Couldn't find '{cmd[0]}' on this computer.")
    raise AssertionError("unreachable")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2))


# ── the steps ────────────────────────────────────────────────────────────

TOTAL = 8


def check_tools() -> None:
    step(1, TOTAL, "Checking this computer")
    if sys.version_info < (3, 9):
        fail("This needs Python 3.9 or newer.", "Get it from https://www.python.org/downloads/")
    system = platform.system()
    missing = [t for t in ("git", "gh") if not shutil.which(t)]
    if missing:
        names = {"git": "Git", "gh": "GitHub CLI"}
        if system == "Windows":
            ids = {"git": "Git.Git", "gh": "GitHub.cli"}
            cmd = "winget install --silent " + " ".join(f"--id {ids[m]}" for m in missing)
            hint = f"Open PowerShell and run:\n  {cmd}\nThen close and reopen your terminal."
        elif system == "Darwin":
            hint = "In Terminal run:\n  brew install " + " ".join(missing) + \
                   "\n(No Homebrew? Get it at https://brew.sh first.)"
        else:
            hint = "Install with your package manager, e.g.:\n  sudo apt install " + \
                   " ".join("gh" if m == "gh" else "git" for m in missing) + \
                   "\nGitHub CLI instructions: https://cli.github.com"
        fail("Missing " + " and ".join(names[m] for m in missing) + ".", hint)
    ok("Python, Git, and GitHub CLI are ready.")


def github_login() -> str:
    step(2, TOTAL, "Signing in to GitHub")
    status = run(["gh", "auth", "status"], check=False)
    if status.returncode != 0:
        info("A browser window will open. Sign in (or create a free account) and approve.")
        info("If it shows a one-time code here, type it into the browser page.")
        res = subprocess.run(["gh", "auth", "login", "--web", "--git-protocol", "https",
                              "--scopes", "repo,workflow"], cwd=ROOT)
        if res.returncode != 0:
            fail("GitHub sign-in didn't finish.")
    else:
        # Make sure we're allowed to upload the schedule files.
        scopes = (status.stdout + status.stderr).lower()
        if "workflow" not in scopes:
            info("Asking GitHub for one more permission (to upload the posting schedule)...")
            subprocess.run(["gh", "auth", "refresh", "--scopes", "repo,workflow"], cwd=ROOT)
    run(["gh", "auth", "setup-git"], check=False)
    user = run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    if not user:
        fail("Couldn't read your GitHub username after signing in.")
    ok(f"Signed in as {user}.")
    return user


def check_key(key: str) -> tuple[bool, str]:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200, ""
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read().decode()).get("error", {}).get("message", "")
        except Exception:
            message = ""
        if "workspace" in message.lower():
            return False, ("That key isn't tied to a workspace, so it can't be used on its own.\n"
                           "      Create a new key in the Console and set its Scope to 'Default workspace'.")
        if e.code in (401, 403):
            return False, "That key was rejected. Double-check you copied the whole thing."
        return False, f"Claude's servers answered with an error ({e.code}). Try again in a minute."
    except (urllib.error.URLError, TimeoutError) as e:
        return False, f"Couldn't reach Claude's servers ({e}). Check your internet connection."


def get_api_key(state: dict) -> str | None:
    """Returns a new key to save, or None to keep the one already saved on GitHub."""
    step(3, TOTAL, "Your Claude API key")
    if state.get("api_key_saved"):
        if not yes("Your key is already saved on GitHub. Replace it with a new one?", default=False):
            ok("Keeping your saved key.")
            return None
    else:
        info("Get one at https://console.anthropic.com  ->  API Keys  ->  Create Key.")
        info("Add a few dollars of credit under Billing; this uses well under $1 a month.")
        if yes("Open that page in your browser now?"):
            webbrowser.open("https://console.anthropic.com/settings/keys")
    for _ in range(3):
        key = getpass.getpass("      Paste your key (it stays hidden as you paste): ").strip()
        if not key:
            continue
        good, why = check_key(key)
        if good:
            ok("Key works.")
            return key
        warn(why)
    fail("Couldn't get a working API key.", "You can create a new key at https://console.anthropic.com/settings/keys")
    return None


def create_repo(user: str, state: dict) -> str:
    step(4, TOTAL, "Creating your GitHub repository")
    name = state.get("repo")
    if not name:
        info("Your posts page will live at  https://" + user + ".github.io/<name>/")
        name = ask("Name for the repository", "posts")
        name = "".join(ch for ch in name if ch.isalnum() or ch in "-_.") or "posts"
    full = f"{user}/{name}"

    # Local Git setup (first run only).
    if not (ROOT / ".git").exists():
        run(["git", "init", "-q", "-b", "main"])
    if not run(["git", "config", "user.name"], check=False).stdout.strip():
        run(["git", "config", "user.name", user])
    if not run(["git", "config", "user.email"], check=False).stdout.strip():
        uid = run(["gh", "api", "user", "--jq", ".id"]).stdout.strip()
        run(["git", "config", "user.email", f"{uid}+{user}@users.noreply.github.com"])
    run(["git", "branch", "-M", "main"])
    run(["git", "add", "-A"])
    if run(["git", "diff", "--cached", "--quiet"], check=False).returncode != 0:
        msg = "Set up post helper" if not state.get("repo") else "Update post helper"
        run(["git", "commit", "-q", "-m", msg])

    exists = run(["gh", "repo", "view", full, "--json", "name"], check=False).returncode == 0
    if not exists:
        info("Creating it as a public repository (needed for the free page; it's hidden from")
        info("search engines, and everything on it is meant to be posted publicly anyway).")
        run(["git", "remote", "remove", "origin"], check=False)
        run(["gh", "repo", "create", full, "--public",
             "--description", "My post helper", "--source", ".", "--remote", "origin"])
        ok(f"Created github.com/{full}")
    else:
        ok(f"Using your existing repository github.com/{full}")
        remote_url = f"https://github.com/{full}.git"
        if run(["git", "remote", "get-url", "origin"], check=False).returncode != 0:
            run(["git", "remote", "add", "origin", remote_url])
        else:
            run(["git", "remote", "set-url", "origin", remote_url])

    # Keep anything the scheduler already posted, then upload.
    if exists:
        run(["git", "pull", "--rebase", "-q", "origin", "main"], check=False)
    run(["git", "push", "-q", "-u", "origin", "main"])
    ok("Project uploaded.")
    state["repo"] = name
    save_state(state)
    return full


def save_secrets(full: str, key: str | None, state: dict) -> str:
    step(5, TOTAL, "Saving private settings on GitHub")
    if key:
        run(["gh", "secret", "set", "ANTHROPIC_API_KEY", "--repo", full], input_text=key)
        state["api_key_saved"] = True
        ok("Claude API key saved (only GitHub's scheduler can read it).")
    topic = state.get("ntfy_topic") or f"posts-{secrets.token_hex(8)}"
    run(["gh", "secret", "set", "NTFY_TOPIC", "--repo", full], input_text=topic)
    state["ntfy_topic"] = topic
    save_state(state)
    ok("Private notification channel saved.")
    # Let the scheduler save new posts back to the repository.
    run(["gh", "api", "-X", "PUT", f"repos/{full}/actions/permissions/workflow",
         "-f", "default_workflow_permissions=write"], check=False)
    return topic


def enable_pages(full: str, user: str) -> str:
    step(6, TOTAL, "Turning on your post page")
    args = ["-f", "build_type=legacy", "-f", "source[branch]=main", "-f", "source[path]=/docs"]
    res = run(["gh", "api", "-X", "POST", f"repos/{full}/pages", *args], check=False)
    if res.returncode != 0:
        # Already on: make sure it points at the right folder.
        res = run(["gh", "api", "-X", "PUT", f"repos/{full}/pages", *args], check=False)
        if res.returncode != 0:
            warn("Couldn't switch the page on automatically.")
            info(f"Do it by hand: github.com/{full}/settings/pages  ->  Deploy from a branch,")
            info("branch 'main', folder '/docs', Save.")
    url = run(["gh", "api", f"repos/{full}/pages", "--jq", ".html_url"], check=False).stdout.strip()
    url = (url or f"https://{user}.github.io/{full.split('/')[1]}/").rstrip("/") + "/"
    ok(f"Your page: {url}")
    info("(It can take a minute or two to appear the first time.)")
    return url


def show_qr(data: str) -> bool:
    try:
        import qrcode  # optional; only used if it's already installed
    except ImportError:
        return False
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.print_ascii(invert=True)
    return True


def connect_phone(topic: str) -> None:
    step(7, TOTAL, "Connecting your phone")
    link = f"https://ntfy.sh/{topic}"
    info("1. Install the free 'ntfy' app on your phone (App Store or Google Play).")
    info("2. In the app, tap  +  and enter this channel name exactly:")
    print("\n         " + _c("1", topic) + "\n")
    if show_qr(link):
        info("   (Or scan the code above with your phone's camera.)")
    info("   Keep it private: anyone with the name can see your post previews.")
    if yes("Done? Send a test notification now?"):
        try:
            req = urllib.request.Request(
                link,
                data="Your phone is connected. New posts will show up here.".encode(),
                headers={"Title": "Post helper is set up", "Tags": "tada"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=20).close()
            ok("Test sent. Check your phone.")
        except (urllib.error.URLError, TimeoutError):
            warn("Couldn't send the test, but your first real post will still notify you.")


def first_post(full: str) -> None:
    step(8, TOTAL, "Writing your first posts")
    if not yes("Write a Facebook/Instagram post and a LinkedIn post right now?"):
        info("Skipped. They'll start on the normal schedule.")
        return
    started = []
    for wf, label in (("post.yml", "Facebook/Instagram"), ("linkedin.yml", "LinkedIn")):
        for attempt in range(6):  # GitHub needs a moment to notice newly uploaded schedules
            if run(["gh", "workflow", "run", wf, "--repo", full], check=False).returncode == 0:
                started.append(label)
                break
            time.sleep(5)
        else:
            warn(f"Couldn't start the {label} post yet. Start it from the Actions tab later.")
        if wf == "post.yml" and started:
            time.sleep(3)  # avoid both runs saving at the same instant
    if started:
        noun = "posts" if len(started) > 1 else "post"
        ok(" and ".join(started) + f" {noun} started. Your phone should buzz in about 3 minutes.")
        info(f"Watch progress at github.com/{full}/actions")


def main() -> None:
    print(_c("1", "\nPost helper setup") + "  (about 5 minutes)")
    state = load_state()
    check_tools()
    user = github_login()
    key = get_api_key(state)
    full = create_repo(user, state)
    topic = save_secrets(full, key, state)
    page = enable_pages(full, user)
    connect_phone(topic)
    first_post(full)

    print("\n" + _c("1;32", "All set!"))
    info(f"Your post page (bookmark it on your phone):  {page}")
    info(f"Your settings and schedule:                   github.com/{full}")
    info("From now on: phone buzzes -> tap -> big button -> paste. That's it.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n      Setup cancelled. Run it again whenever you're ready.\n")
        sys.exit(130)
