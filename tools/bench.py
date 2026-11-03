"""Tool-use benchmark: asks the running Jarvis the questions in tools/bench.json.

A question passes when the expected tool was called (seen in tool-calls.txt) and the
answer contains the expected text. The result goes to ~/.openjarvis/bench-result.json,
which the HUD shows. Run it with Jarvis running:
  uv run --no-sync python tools\\bench.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, TypedDict

from helper_http import HELPER_URL

JARVIS_DIR = os.path.expanduser("~/.openjarvis")
TOOL_LOG = os.path.join(JARVIS_DIR, "tool-calls.txt")
RESULT_FILE = os.path.join(JARVIS_DIR, "bench-result.json")
QUESTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench.json")
CHAT_URL = "http://127.0.0.1:8000/v1/chat/completions"
LOG_SETTLE_SECONDS = 1.5  # the server writes tool-calls.txt just after answering


class BenchCase(TypedDict):
    """One question of bench.json: the tool it needs ("" = none) and expected text."""

    q: str
    tool: str
    expect: str


class CaseResult(TypedDict):
    q: str
    ok: bool
    tool_ok: bool
    expect_ok: bool
    called: list[str]


def post_json(url: str, body: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:  # nosec B310 - fixed local URL
        return json.load(r)


def get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as r:  # nosec B310 - fixed local URL
        return json.load(r)


def tool_log_lines() -> list[str]:
    try:
        with open(TOOL_LOG, errors="replace") as f:
            return f.read().splitlines()
    except OSError:
        return []


def tools_called(new_lines: list[str]) -> list[str]:
    """Tool names from tool-calls.txt lines ("<time> <tool> ...")."""
    return sorted({line.split()[1] for line in new_lines if len(line.split()) > 1})


def grade(case: BenchCase, answer: str, called: list[str]) -> CaseResult:
    """Pass/fail of one question: the right tool (or none) and the expected text."""
    tool_ok = (case["tool"] in called) if case["tool"] else not called
    expect_ok = (case["expect"].lower() in answer.lower()) if case["expect"] else True
    return {
        "q": case["q"],
        "ok": tool_ok and expect_ok,
        "tool_ok": tool_ok,
        "expect_ok": expect_ok,
        "called": called,
    }


def ask(model: str, question: str) -> str:
    try:
        reply = post_json(
            CHAT_URL,
            {"model": model, "messages": [{"role": "user", "content": question}]},
        )
        return reply["choices"][0]["message"]["content"] or ""
    except (OSError, ValueError, KeyError, IndexError) as e:
        # Server down or an odd reply: this case fails, the run goes on.
        return "ERROR " + str(e)[:80]


def summary(results: list[CaseResult], model: str) -> dict[str, Any]:
    passed = sum(r["ok"] for r in results)
    return {
        "accuracy": round(100.0 * passed / len(results), 1),
        "passed": passed,
        "total": len(results),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "details": results,
    }


def main() -> None:
    model = get_json(HELPER_URL)["model"]
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        cases = json.load(f)
    results: list[CaseResult] = []
    for n, case in enumerate(cases, 1):
        before = len(tool_log_lines())
        answer = ask(model, case["q"])
        time.sleep(LOG_SETTLE_SECONDS)
        r = grade(case, answer, tools_called(tool_log_lines()[before:]))
        results.append(r)
        print(
            n,
            "PASS" if r["ok"] else "FAIL",
            "tool_ok=%s expect_ok=%s called=%s"
            % (r["tool_ok"], r["expect_ok"], r["called"]),
        )
    out = summary(results, model)
    with open(RESULT_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    os.replace(RESULT_FILE + ".tmp", RESULT_FILE)  # the HUD never reads half a file
    print("ACCURACY: %s%% (%d of %d)" % (out["accuracy"], out["passed"], out["total"]))


if __name__ == "__main__":
    main()
