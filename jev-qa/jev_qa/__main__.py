"""Command-line boundary for browser QA and evidence-only review."""

import argparse
import json
import os
import re
import shlex
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .browser import BrowserSetupError, RunDeadline, browser_session, chrome_path, isolated_runtime

CONFIG = Path.home() / ".config/jev-qa/env"
ENV_KEYS = {
    "TYPESAFE_API_KEY",
    "TYPESAFE_MODEL",
    "TEXT_MODEL_API_KEY",
    "TEXT_MODEL_BASE_URL",
    "TEXT_MODEL",
    "TEXT_MODEL_REASONING",
    "JEV_QA_CHROME",
}


def load_env(path):
    if not path.exists():
        return
    if path.stat().st_mode & 0o077:
        raise ValueError("Credential file must have owner-only permissions (chmod 600).")
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        key = key.removeprefix("export ").strip()
        if not separator or key not in ENV_KEYS:
            raise ValueError("Unsupported setting in the QA environment file.")
        values = shlex.split(raw, comments=True)
        if len(values) != 1:
            raise ValueError("Invalid value in the QA environment file.")
        os.environ.setdefault(key, values[0])


def read_json(path):
    if path.stat().st_size > 100_000:
        raise ValueError("Input must be at most 100 KB.")
    value = json.loads(path.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid number")))
    if not isinstance(value, dict):
        raise ValueError("Input must be a JSON object.")
    return value


def deadline(_signum, _frame):
    raise RunDeadline("QA execution deadline exceeded.")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=CONFIG)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check setup without calling any model")
    for name in ("run", "review", "journey"):
        command = sub.add_parser(name)
        command.add_argument("input", type=Path)
        command.add_argument("--output", type=Path)
        if name != "review":
            command.add_argument(
                "--browser",
                choices=("isolated", "existing-chrome"),
                default="isolated",
                help="Browser session to use (default: isolated)",
            )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    output = getattr(args, "output", None)
    fresh_output = False
    try:
        load_env(args.env_file)
        if args.command == "doctor":
            print(
                json.dumps(
                    {
                        "chrome": chrome_path(),
                        "typesafe_key_present": bool(os.environ.get("TYPESAFE_API_KEY")),
                        "text_helper_key_present": bool(os.environ.get("TEXT_MODEL_API_KEY")),
                        "credential_file": str(args.env_file),
                        "browser_profile": "disposable; no signed-in sessions",
                        "browser_modes": {"default": "isolated", "supported": ["isolated", "existing-chrome"]},
                    },
                    indent=2,
                )
            )
            return 0 if os.environ.get("TYPESAFE_API_KEY") else 2
        data = read_json(args.input)
        output = output or Path("work/jev-qa-runs") / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        )
        fresh_output = not output.exists()
        with isolated_runtime():
            from .runner import review_evidence, run_task, validate_task

            if args.command == "journey":
                from .journey import run_journey, validate_journey

                task = validate_journey(data)
                signal.signal(signal.SIGALRM, deadline)
                signal.setitimer(signal.ITIMER_REAL, task["max_seconds"])
                try:
                    result = run_journey(
                        data,
                        output,
                        lambda url: browser_session(url, existing=args.browser == "existing-chrome"),
                    )
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
            elif args.command == "run":
                task = validate_task(data)
                signal.signal(signal.SIGALRM, deadline)
                signal.setitimer(signal.ITIMER_REAL, task.get("max_seconds", 120))
                try:
                    result = run_task(
                        task,
                        output,
                        lambda url: browser_session(url, existing=args.browser == "existing-chrome"),
                    )
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
            else:
                if set(data) - {"evidence", "criteria", "min_confidence"} or "evidence" not in data:
                    raise ValueError("Review input needs evidence, criteria, and optional min_confidence.")
                output.mkdir(parents=True, mode=0o700, exist_ok=False)
                signal.signal(signal.SIGALRM, deadline)
                signal.setitimer(signal.ITIMER_REAL, 120)
                try:
                    result = review_evidence(
                        data["evidence"], data.get("criteria", []), data.get("min_confidence", 0.8)
                    )
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                report = output / "report.json"
                report.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
                report.chmod(0o600)
        print(
            json.dumps(
                {"status": result["status"], "report": str((output / "report.json").resolve()), "result": result},
                indent=2,
                allow_nan=False,
            )
        )
        return {"pass": 0, "fail": 1, "needs_review": 2, "blocked": 2, "error": 2}.get(result["status"], 2)
    except (Exception, KeyboardInterrupt, RunDeadline) as exc:
        # Never print provider response bodies, input contents, or credentials.
        reason = (
            str(exc)
            if isinstance(exc, (BrowserSetupError, ValueError, TimeoutError, RunDeadline))
            else type(exc).__name__
        )
        for key in ("TYPESAFE_API_KEY", "TEXT_MODEL_API_KEY"):
            if os.environ.get(key):
                reason = reason.replace(os.environ[key], "[REDACTED]")
        reason = re.sub(r"[A-Za-z0-9_-]{40,}", "[REDACTED]", reason)[:300]
        error = {"status": "error", "reason": reason}
        if getattr(exc, "jev_qa_cleanup_incomplete", False) is True:
            error.update(cleanup_incomplete=True, cleanup_message="Browser cleanup incomplete.")
        if fresh_output and output.is_dir() and not (output / "report.json").exists():
            with (output / "report.json").open("x") as report:
                json.dump(error, report)
                report.write("\n")
            (output / "report.json").chmod(0o600)
            error["report"] = str((output / "report.json").resolve())
        print(json.dumps(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
