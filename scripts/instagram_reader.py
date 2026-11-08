"""Read club post captions in the owner's local Chromium profile; never export cookies."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from urllib.request import Request, urlopen

import websocket

HOME = Path("/home/desk/club-alerts")
PROFILE = "/home/desk/.config/chromium"


def http_json(path, method="GET"):
    with urlopen(Request("http://127.0.0.1:9222" + path, method=method), timeout=3) as response:
        return json.load(response)


def browser():
    try:
        http_json("/json/version")
    except OSError:
        # Stop only the identified browser parent using this dedicated desktop's profile.
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                args = (proc / "cmdline").read_bytes().decode(errors="replace").split(chr(0))
                executable = (proc / "exe").resolve()
                if (str(executable) == "/usr/lib/chromium/chromium" and args[0] == str(executable)
                        and not any(a.startswith("--type=") or a == "--type" for a in args)
                        and not any(a.startswith("--user-data-dir=") and a != "--user-data-dir=" + PROFILE for a in args)):
                    os.kill(int(proc.name), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        time.sleep(1)
        HOME.mkdir(parents=True, exist_ok=True)
        environment = {**os.environ, "DISPLAY": ":1"}
        # Match the desktop session so Chromium can use its existing keyring normally.
        for proc in Path("/proc").iterdir():
            try:
                if proc.name.isdigit() and (proc / "comm").read_text().strip() == "xfce4-session":
                    entries = (proc / "environ").read_bytes().decode(errors="replace").split(chr(0))
                    session = dict(v.split("=", 1) for v in entries if "=" in v)
                    for name in ("DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "XAUTHORITY", "DISPLAY"):
                        if name in session:
                            environment[name] = session[name]
                    break
            except OSError:
                continue
        with (HOME / "browser.log").open("ab") as log:
            subprocess.Popen(["/usr/bin/chromium", "--no-sandbox", "--no-first-run", "--disable-dev-shm-usage",
                              "--user-data-dir=" + PROFILE, "--remote-debugging-port=9222",
                              "--remote-debugging-address=127.0.0.1", "about:blank"],
                             env=environment, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
        for _ in range(15):
            try:
                http_json("/json/version")
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise RuntimeError("browser_unavailable")
    tabs = http_json("/json/list")
    tab = next((t for t in tabs if t.get("type") == "page" and
                (t.get("url", "").startswith("https://www.instagram.com/") or t.get("url") == "about:blank")), None)
    return tab or http_json("/json/new?about:blank", "PUT")


class CDP:
    def __init__(self, url):
        self.socket = websocket.create_connection(url, timeout=6, suppress_origin=True)
        self.sequence = 0

    def call(self, method, params=None):
        self.sequence += 1
        self.socket.send(json.dumps({"id": self.sequence, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            message = json.loads(self.socket.recv())
            if message.get("id") == self.sequence:
                if message.get("error"):
                    raise RuntimeError("browser_command_failed")
                return message.get("result", {})
        raise RuntimeError("browser_timeout")

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            raise RuntimeError("browser_script_failed")
        return result.get("result", {}).get("value")

    def navigate(self, url):
        result = self.call("Page.navigate", {"url": url})
        if result.get("errorText"):
            raise RuntimeError("navigation_failed")
        time.sleep(2)


GUARD = r"""(() => {
 const text = document.body?.innerText || '';
 const path = location.pathname;
 if (/\/accounts\/login|\/challenge|\/checkpoint/.test(path)) return 'login_required';
 if (/please wait a few minutes|try again later|we restrict certain activity/i.test(text)) return 'rate_limited';
 if (/sorry, this page isn't available|this account is private|profile isn't available/i.test(text)) return 'unavailable';
 if (document.querySelector('input[name="username"],input[name="password"]')) return 'login_required';
 return 'ok';
})()"""


def read_profile(url, seen=None):
    if not url.startswith("https://www.instagram.com/") or len(url.rstrip("/").split("/")) != 4:
        raise ValueError("Invalid Instagram profile URL")
    tab = browser()
    cdp = CDP(tab["webSocketDebuggerUrl"])
    started = time.monotonic()
    try:
        cdp.navigate(url)
        status, links = "ok", []
        for _ in range(4):
            status = cdp.evaluate(GUARD)
            if status != "ok":
                return {"status": status, "posts": []}
            links = cdp.evaluate(r"""Array.from(new Set(Array.from(document.querySelectorAll('a[href]'))
              .map(a => a.getAttribute('href').match(/^\/(?:[A-Za-z0-9_.]+\/)?((?:p|reel)\/[A-Za-z0-9_-]+)\/?$/)?.[1])
              .filter(Boolean)))
              .slice(0, 12).map(path => 'https://www.instagram.com/' + path + '/')""") or []
            if links:
                break
            time.sleep(1)
        if not links:
            return {"status": "no_readable_posts", "posts": []}
        seen = set(seen or [])
        new = [u for u in links if u not in seen]
        # New posts first, plus a previous post to detect edits on later visits.
        targets = list(dict.fromkeys([*new[:2], *[u for u in links if u in seen][:1]]))[:3]
        posts = []
        for target in targets:
            if time.monotonic() - started > 18:
                break
            cdp.navigate(target)
            status = cdp.evaluate(GUARD)
            if status != "ok":
                return {"status": status, "posts": posts}
            post = cdp.evaluate("""(() => {
              const caption = document.querySelector('h1')?.innerText || '';
              const description = document.querySelector('meta[property="og:description"]')?.content || '';
              const alt = Array.from(document.querySelectorAll('article img[alt],main img[alt]'))
                .map(i=>i.alt).filter(t=>t && !/profile picture/i.test(t)).slice(0,4);
              return {caption: caption || description, image_alt:alt};
            })()""") or {}
            if post.get("caption") or post.get("image_alt"):
                posts.append({"url": target, "caption": str(post.get("caption", ""))[:14000],
                              "image_alt": post.get("image_alt", [])})
        return {"status": "ok" if posts else "caption_unavailable", "posts": posts}
    finally:
        cdp.socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--seen", default="[]")
    args = parser.parse_args()
    try:
        result = read_profile(args.url, json.loads(args.seen))
    except Exception as exc:
        result = {"status": "browser_error", "error": type(exc).__name__, "posts": []}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
