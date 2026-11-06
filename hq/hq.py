#!/usr/bin/env python3
"""Agenten HQ – meldet, welcher Agent gerade arbeitet.

Installiert unter ~/Library/Application Support/agenten-hq/hq.py

  hq.py set <agent> <working|idle|error> ["kurzer Text"]   # von den Agenten selbst
  hq.py hook                                                # Claude-Code-Hook (JSON auf stdin)
  hq.py heartbeat                                           # LaunchAgent alle 15 Min
  hq.py show                                                # aktuellen Stand anzeigen

Der öffentliche Stand liegt als status.json auf dem Branch `status` von
nicoklein-nkzsde/agenten-hq (immer nur ein Commit, wird überschrieben).
Private Details (Session-IDs) bleiben lokal in local.json.
"""
import datetime, json, os, re, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(BASE, "status-repo")
LOCAL = os.path.join(BASE, "local.json")
STATUS = os.path.join(REPO, "status.json")
LOCK = os.path.join(BASE, ".lock")
PUSHLOCK = os.path.join(BASE, ".pushlock")
LOG = os.path.join(BASE, "hq.log")
AGENTS = ["chef", "leadtracker", "autohaus", "berater", "aufraeumen", "kartbahn"]
STATES = ["working", "idle", "error"]
MARKER = re.compile(r"\[hq:([a-z]+)\]")
# Themen-Agenten: jede Chat-Session zu diesem Thema läuft über diesen Agenten
TOPICS = {
    "kartbahn": re.compile(r"kartbahn|heuchelheim|\bkarts?\b|go-?kart", re.I),
}
TOPIC_TEXT = {
    "kartbahn": ("Kümmert sich um die Kartbahn …", "Wartet auf den nächsten Kartbahn-Chat."),
}
PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def age(iso):
    try:
        return time.time() - datetime.datetime.fromisoformat(iso).timestamp()
    except Exception:
        return 1e12


def log(msg):
    try:
        with open(LOG, "a") as f:
            f.write(f"{now()} {msg}\n")
        if os.path.getsize(LOG) > 200_000:
            os.replace(LOG, LOG + ".old")
    except Exception:
        pass


class Lock:
    def __init__(self, path, wait=3.0):
        self.path, self.wait, self.ok = path, wait, False

    def __enter__(self):
        end = time.time() + self.wait
        while True:
            try:
                os.mkdir(self.path)
                self.ok = True
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 60:
                        os.rmdir(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > end:
                    return self
                time.sleep(0.05)

    def __exit__(self, *a):
        if self.ok:
            try:
                os.rmdir(self.path)
            except OSError:
                pass


def load():
    try:
        with open(LOCAL) as f:
            d = json.load(f)
    except Exception:
        d = {}
    d.setdefault("agents", {})
    d.setdefault("sessions", {})
    return d


def save(d):
    tmp = LOCAL + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, LOCAL)
    publish(d)


def publish(d):
    # alte Sessions aufräumen
    for sid in list(d["sessions"]):
        s = d["sessions"][sid]
        if age(s.get("since", "")) > 2 * 86400:
            del d["sessions"][sid]
    chat = [s for s in d["sessions"].values() if not s.get("agent")]
    working = [s for s in chat if s.get("state") == "working" and age(s.get("since", "")) < 3 * 3600]
    last = max((s.get("since", "") for s in chat), default=None)
    public = {
        "updated": now(),
        "heartbeat": d.get("heartbeat"),
        "agents": {k: v for k, v in d["agents"].items() if k in AGENTS},
        "chat": {"working": len(working), "lastActive": last},
    }
    os.makedirs(REPO, exist_ok=True)
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(public, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATUS)


def set_agent(d, aid, state, text=None):
    a = d["agents"].setdefault(aid, {"state": "idle"})
    prev = a.get("state")
    if prev != state:
        a["since"] = now()
        if prev == "working" and state == "idle":
            a["lastDone"] = now()
    a["state"] = state
    if text:
        a["text"] = text.strip()[:90]
    elif state == "working" and prev != "working":
        a["text"] = "Legt los …"


def spawn_push():
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "_push"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, cwd=BASE,
        )
    except Exception as e:
        log(f"spawn failed: {e}")


def git(*args):
    env = dict(os.environ, PATH=PATH_ENV + ":" + os.environ.get("PATH", ""))
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, env=env, timeout=60)


def do_push():
    # bündelt schnelle Änderungen und schiebt nur, wenn sich etwas geändert hat
    time.sleep(3)
    with Lock(PUSHLOCK, wait=0) as lk:
        if not lk.ok:
            return  # ein anderer Pusher läuft schon und nimmt den neuesten Stand mit
        for _ in range(5):
            with open(STATUS, "rb") as f:
                content = f.read()
            git("add", "status.json")
            has_head = git("rev-parse", "--verify", "-q", "HEAD").returncode == 0
            if has_head:
                r = git("commit", "--amend", "-q", "-m", "status")
            else:
                r = git("commit", "-q", "-m", "status")
            p = git("push", "-f", "-q", "origin", "HEAD:status")
            if p.returncode != 0:
                log(f"push failed: {p.stderr.strip()[:300]}")
                return
            with open(STATUS, "rb") as f:
                if f.read() == content:
                    return
            time.sleep(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]

    if cmd == "_push":
        do_push()
        return 0

    if cmd == "show":
        print(open(STATUS).read() if os.path.exists(STATUS) else "(noch kein Status)")
        return 0

    if cmd == "set":
        if len(sys.argv) < 4 or sys.argv[2] not in AGENTS or sys.argv[3] not in STATES:
            print("Nutzung: hq.py set <" + "|".join(AGENTS) + "> <working|idle|error> [\"Text\"]")
            return 1
        text = sys.argv[4] if len(sys.argv) > 4 else None
        with Lock(LOCK):
            d = load()
            set_agent(d, sys.argv[2], sys.argv[3], text)
            save(d)
        spawn_push()
        print(f"HQ: {sys.argv[2]} -> {sys.argv[3]}")
        return 0

    if cmd == "heartbeat":
        with Lock(LOCK):
            d = load()
            d["heartbeat"] = now()
            # Agenten, die seit > 3 h "arbeiten", gelten als abgestürzt
            for aid, a in d["agents"].items():
                if a.get("state") == "working" and age(a.get("since", "")) > 3 * 3600:
                    set_agent(d, aid, "error", "Lauf ist hängen geblieben oder abgebrochen.")
            save(d)
        spawn_push()
        return 0

    if cmd == "hook":
        # darf Claude nie blockieren: alles in try, immer exit 0
        try:
            data = json.load(sys.stdin)
            ev = data.get("hook_event_name", "")
            sid = str(data.get("session_id", "?"))
            with Lock(LOCK, wait=2):
                d = load()
                s = d["sessions"].setdefault(sid, {})
                if ev == "UserPromptSubmit":
                    prompt = data.get("prompt") or ""
                    m = MARKER.search(prompt)
                    if m and m.group(1) in AGENTS:
                        s["agent"] = m.group(1)
                    elif not s.get("agent"):
                        where = prompt + " " + str(data.get("cwd", ""))
                        for tid, rx in TOPICS.items():
                            if rx.search(where):
                                s["agent"] = tid
                                break
                    s["state"] = "working"
                    s["since"] = now()
                    a = s.get("agent")
                    if a:
                        set_agent(d, a, "working", TOPIC_TEXT.get(a, (None,))[0])
                elif ev in ("Stop", "SessionEnd"):
                    s["state"] = "idle"
                    s["since"] = now()
                    a = s.get("agent")
                    others = [x for x in d["sessions"].values()
                              if x is not s and x.get("agent") == a and x.get("state") == "working"
                              and age(x.get("since", "")) < 3 * 3600]
                    if a and not others and d["agents"].get(a, {}).get("state") != "error":
                        set_agent(d, a, "idle", TOPIC_TEXT.get(a, (None, None))[1])
                save(d)
            spawn_push()
        except Exception as e:
            log(f"hook error: {e}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
