"""Run the live demo storyboard (plan Part D §3) against the HTTP API and assert kinds and cited ids.

    python scripts/smoke_api.py [--base http://127.0.0.1:8010] [--serve] [--offline] [--session 60]

`--serve` starts uvicorn on port 8010 itself (STORE=local, plus OFFLINE=1 with `--offline`), waits for
`/api/health`, runs the sequence and always stops the server. With `--serve --offline` the server itself
runs under the `scripts/no_network.py` tripwire (loopback only) and every blocked attempt is reported, so
the check fails if the app tried to leave the machine. `--session N` repeats the sequence until N seconds
have passed (the 60-s app session of plan P5.3). `--offline` also sends `force_offline` on
every chat and feedback request. The KB edit of step 8 is always reset afterwards. Prints
"demo sequence OK (offline)" (or "(llm)") and exits 0; any failed check prints the step and exits 1.
Stdlib only, so it also runs under `scripts/no_network.py` (loopback only).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "http://127.0.0.1:8010"
SERVE_PORT = 8010
BLOCKED_MARK = "NETWORK-BLOCKED"
# The server process under the tripwire: no_network's blocker also writes a marker to stderr, so an
# attempt the app swallows (the store and LLM layers never raise) is still seen by this script.
TRIPWIRE_SERVER = """
import sys
sys.path[:0] = [{root!r}, {scripts!r}]
import no_network
def _blocked(*_a, **_k):
    sys.stderr.write({mark!r} + chr(10))
    sys.stderr.flush()
    raise OSError(no_network.MESSAGE)
no_network._blocked = _blocked
no_network.disable_network()
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port={port}, log_level="warning")
"""


class SmokeFailure(AssertionError):
    pass


class Api:
    def __init__(self, base: str, force_offline: bool) -> None:
        self.base = base.rstrip("/")
        self.force_offline = force_offline

    def call(self, method: str, path: str, body: Any = None, *, expect: int = 200) -> Any:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status, raw, rid = r.status, r.read(), r.headers.get("X-Request-Id")
        except urllib.error.HTTPError as e:
            status, raw, rid = e.code, e.read(), e.headers.get("X-Request-Id")
        check(bool(rid), f"{method} {path}: X-Request-Id header")
        check(status == expect, f"{method} {path}: status {status} != {expect}: {raw[:300]!r}")
        text = raw.decode("utf-8")
        return json.loads(text) if text and path.startswith("/api") else text

    def chat(self, message: str = "", **kw: Any) -> dict[str, Any]:
        body = {"message": message, "force_offline": self.force_offline, **kw}
        resp: dict[str, Any] = self.call("POST", "/api/chat", body)
        return resp


def check(cond: bool, what: str) -> None:
    if not cond:
        raise SmokeFailure(what)


def ids(resp: dict[str, Any]) -> list[str]:
    return [s["id"] for s in resp["reply"]["sources"]]


def kind(resp: dict[str, Any]) -> str:
    return str(resp["reply"]["kind"])


def run_storyboard(api: Api) -> str:
    health = api.call("GET", "/api/health")
    check(health["status"] == "ok", "health status ok")
    mode = "offline" if api.force_offline else str(health["mode"])

    # 0. the built web client is served at /
    page = api.call("GET", "/")
    check("<html" in page.lower() and 'id="root"' in page, "web/dist index.html served at /")

    # 1. role selection: the Sales lists and a greeting
    check(len(api.call("GET", "/api/scenarios?role=Sales")["scenarios"]) >= 1, "1 scenarios for Sales")
    check(len(api.call("GET", "/api/plan?role=Sales")["milestones"]) == 4, "1 plan for Sales")
    check(kind(api.chat("مرحبا", role="Sales")) == "text", "1 greeting")

    # 2. T01
    r = api.chat("متى تأسست مجموعة الدادا؟", role="Sales")
    check(kind(r) == "answer" and ids(r)[:1] == ["K01"], f"2 T01 → K01 ({kind(r)}, {ids(r)})")
    check(r["trace"]["retrieval"]["hits"][0]["id"] == "K01", "2 trace rank 1 is K01")

    # 3. T02: the five values
    r = api.chat("ما قيم الشركة الخمس؟", role="Sales")
    check(kind(r) == "answer" and ids(r)[:5] == ["K05", "K06", "K07", "K08", "K09"], f"3 T02 → K05–K09 ({ids(r)})")

    # 3b. T03 / T04
    r = api.chat("كيف أقدم طلب إجازة؟", role="Sales")
    check(kind(r) == "answer" and "K16" in ids(r), f"3b T03 → K16 ({ids(r)})")
    r = api.chat("كم فترة التجربة؟", role="Sales")
    check(kind(r) == "answer" and "K14" in ids(r), f"3b T04 → K14 ({kind(r)}, {ids(r)})")

    # 4. T05: contact refusal, no model call, no sources
    r = api.chat("ما رقم هاتف مدير الموارد البشرية؟", role="Sales")
    check(kind(r) == "refusal" and r["reply"]["reason"] == "contact" and not ids(r), "4 T05 contact refusal")
    check(bool(r["trace"]["guards"]["contact"]) and not r["trace"]["agent"]["used"], "4 contact guard, no LLM")

    # 4b. T09
    r = api.chat("هل يمكن أن تشارك معلومات سرية مع صديق؟", role="Sales")
    check(kind(r) == "answer" and "K17" in ids(r), f"4b T09 → K17 ({kind(r)}, {ids(r)})")

    # 5. T06: scenario S02, free-text feedback, end
    r = api.chat("أنا موظف مبيعات وعميل يسأل عن ميزة غير مؤكدة", role="Sales")
    check(kind(r) == "scenario_start" and r["state"]["active_scenario"] == "S02", "5 T06 → S02 start")
    st = {"active_scenario": "S02"}
    r = api.chat("بقوله إني رح أتأكد من المواصفات من المصدر الرسمي وبرجع له", role="Sales", state=st)
    fb = r["reply"]["feedback"]
    check(kind(r) == "scenario_feedback" and fb["value"] == "Integrity", "5 T06 feedback (Integrity)")
    check(bool(fb["suggested_good_response_ar"]) and fb["label_ar"], "5 feedback shows the suggested response")
    r = api.chat("إنهاء التدريب", role="Sales", state=st)
    check(kind(r) == "scenario_end" and r["state"]["active_scenario"] is None, "5 end practice")

    # 6. T08: progress proposal then confirm
    r = api.chat("أكملت نشاط اليوم 30", role="Sales")
    check(kind(r) == "progress_proposal" and r["reply"]["proposal"]["milestone"] == "Day 30", "6 T08 proposal")
    acts = r["reply"]["proposal"]["activity_ids"]
    r = api.chat("", role="Sales", confirm={"milestone": "Day 30", "activity_ids": acts})
    check(kind(r) == "progress_confirmed" and r["reply"]["progress"]["completed_ids"] == acts
          and r["reply"]["progress"]["percent"] > 0, "6 progress confirmed")

    # 7. T07: the Delivery scenario S04, option feedback, end
    r = api.chat("أنا موظف توصيل والعميل غاضب بسبب التأخير", role="Delivery")
    check(kind(r) == "scenario_start" and r["state"]["active_scenario"] == "S04", f"7 T07 → S04 ({kind(r)})")
    fbr = api.call("POST", "/api/scenarios/S04/feedback", {"option_id": "S04-O1", "force_offline": api.force_offline})
    check(fbr["feedback"]["scenario_id"] == "S04" and fbr["feedback"]["value"], "7 S04 option feedback")
    r = api.chat("إنهاء التدريب", role="Delivery", state={"active_scenario": "S04"})
    check(kind(r) == "scenario_end", "7 end practice")

    # 8. jury "modify an answer": K02 17 → 18, then ask again; always reset
    rows = {row["id"]: row for row in api.call("GET", "/api/kb")["rows"]}
    k02 = rows["K02"]["answer_ar"]
    check("17" in k02, "8 K02 holds 17")
    try:
        put = api.call("PUT", "/api/kb/K02", {"answer_ar": k02.replace("17", "18")})
        check(put["row"]["edited"] is True, "8 K02 edited")
        r = api.chat("كم عدد المعارض؟", role="Sales")
        src = [s for s in r["reply"]["sources"] if s["id"] == "K02"]
        check(kind(r) == "answer" and bool(src) and src[0]["edited"] and "18" in src[0]["answer_ar"],
              f"8 answer cites the edited K02 ({ids(r)})")
    finally:
        reset = api.call("POST", "/api/kb/reset")
    check(reset["rows"] == 18 and not api.call("GET", "/api/kb")["edited_ids"], "8 KB reset")

    # 9. "show the source": id · document · page verbatim in the cited row
    r = api.chat("متى تأسست مجموعة الدادا؟", role="Sales")
    s = r["reply"]["sources"][0]
    check(s["id"] == "K01" and s["source_document"] and isinstance(s["source_page"], int), "9 source fields")
    check(bool(r["trace"]["steps"]) and r["trace"]["request_id"], "9 trace present")

    # 10. offline proof: the same K01 row with force_offline
    r = api.call("POST", "/api/chat", {"message": "متى تأسست مجموعة الدادا؟", "role": "Sales", "force_offline": True})
    check(r["mode"] == "offline" and ids(r)[:1] == ["K01"] and r["reply"]["band"] is not None,
          "10 offline K01 with a band")
    return mode


def wait_health(base: str, timeout_s: float, proc: subprocess.Popen[bytes] | None = None) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=2) as r:
                if json.loads(r.read().decode("utf-8")).get("status") == "ok":
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    return False


def port_busy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False, capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--serve", action="store_true", help="start uvicorn on 8010 and stop it afterwards")
    ap.add_argument("--offline", action="store_true", help="OFFLINE=1 for --serve and force_offline on requests")
    ap.add_argument("--session", type=float, default=0.0, help="repeat the sequence for this many seconds")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    proc: subprocess.Popen[bytes] | None = None
    base = args.base
    errlog = tempfile.TemporaryFile() if args.serve else None
    rounds = 0
    try:
        if args.serve:
            base = f"http://127.0.0.1:{SERVE_PORT}"
            if port_busy(SERVE_PORT):
                print(f"smoke FAILED: port {SERVE_PORT} is already in use")
                return 1
            env = dict(os.environ, STORE="local", PYTHONIOENCODING="utf-8")
            cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port",
                   str(SERVE_PORT), "--log-level", "warning"]
            if args.offline:
                env["OFFLINE"] = "1"
                code = TRIPWIRE_SERVER.format(root=str(ROOT), scripts=str(ROOT / "scripts"), mark=BLOCKED_MARK,
                                              port=SERVE_PORT)
                cmd = [sys.executable, "-c", code]
            started = time.monotonic()
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=errlog)
            if not wait_health(base, 90, proc):
                print("smoke FAILED: the server did not answer /api/health within 90 s")
                return 1
            print(f"server ready in {time.monotonic() - started:.1f} s"
                  + (" (network tripwire on)" if args.offline else ""))
        session_end = time.monotonic() + max(0.0, args.session)
        mode = run_storyboard(Api(base, args.offline))
        rounds = 1
        while time.monotonic() < session_end:
            run_storyboard(Api(base, args.offline))
            rounds += 1
    except SmokeFailure as exc:
        print(f"smoke FAILED at step: {exc}")
        return 1
    except OSError as exc:
        print(f"smoke FAILED: cannot reach {base} ({exc.__class__.__name__}: {exc})")
        return 1
    finally:
        if proc is not None:
            stop(proc)
    if errlog is not None:
        errlog.seek(0)
        blocked = errlog.read().decode("utf-8", "replace").count(BLOCKED_MARK)
        errlog.close()
        if blocked:
            print(f"smoke FAILED: the server tried to reach the network {blocked} time(s) (tripwire)")
            return 1
        if args.offline:
            print("tripwire: 0 network attempts by the server")
    if rounds > 1:
        print(f"session: {rounds} rounds")
    print(f"demo sequence OK ({mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
