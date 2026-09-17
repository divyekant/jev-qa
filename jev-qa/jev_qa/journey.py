"""Verified browser journeys with Jev decisions and measured design checks."""

import os
import time
from contextlib import nullcontext
from pathlib import Path

from .browser import RunDeadline
from .runner import _new_output, _safe_exception, _text, _write_json, run_task, validate_task


def validate_journey(data):
    from .design import validate_checks

    allowed = {"url", "goal", "values", "viewport", "steps", "max_steps", "max_seconds", "min_confidence"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("Journey contains unknown fields")
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
        raise ValueError("Journey requires 1 to 30 verified steps")
    viewport = data.get("viewport", {"width": 1280, "height": 900})
    if (not isinstance(viewport, dict) or set(viewport) != {"width", "height"}
            or any(type(v) is not int or not 320 <= v <= 2560 for v in viewport.values())):
        raise ValueError("Viewport width and height must be integers from 320 to 2560")
    defaults = {k: data[k] for k in ("url", "goal", "values", "max_steps", "max_seconds", "min_confidence") if k in data}
    defaults.setdefault("max_steps", 60)
    defaults.setdefault("max_seconds", 180)
    _text(defaults.get("goal"), "goal")
    normalized = []
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) - {"name", "goal", "assertions", "checks"}:
            raise ValueError("Step contains unknown fields")
        name = _text(step.get("name"), "step.name", max_length=100)
        if name in seen:
            raise ValueError("Step names must be unique")
        seen.add(name)
        goal = _text(step.get("goal"), "step.goal", max_length=1000)
        task = validate_task({**defaults, "goal": goal, "assertions": step.get("assertions")})
        if not task["assertions"]:
            raise ValueError("Each step requires deterministic assertions")
        normalized.append({"name": name, "goal": task["goal"], "assertions": task["assertions"],
                           "checks": validate_checks(step.get("checks", []))})
    return {**task, "goal": defaults["goal"], "viewport": viewport, "steps": normalized}


def summarize(steps):
    nav = [s["navigation_status"] for s in steps]
    design = [s.get("design", {}).get("status", "pass") for s in steps]
    navigation = (
        "pass"
        if all(s == "pass" for s in nav)
        else "error"
        if "error" in nav
        else "fail"
        if "fail" in nav
        else "blocked"
        if "blocked" in nav
        else "needs_review"
    )
    design_status = "fail" if "fail" in design else "needs_review" if any(s != "pass" for s in design) else "pass"
    status = (
        "fail"
        if design_status == "fail" or navigation == "fail"
        else "error"
        if navigation == "error"
        else "blocked"
        if navigation == "blocked"
        else "pass"
        if navigation == design_status == "pass"
        else "needs_review"
    )
    return {"status": status, "navigation_status": navigation, "design_status": design_status,
            "reached": nav.count("pass"), "total": len(steps)}


def run_journey(data, output, browser_factory):
    from .design import inspect_design

    task = validate_journey(data)
    output = _new_output(Path(output))
    started = time.perf_counter()
    entries = [{"name": s["name"], "navigation_status": "not_reached", **({"design": {
        "status": "needs_review", "reason": "navigation_not_reached",
        "checks": [{"id": c["id"], "kind": c["kind"], "assessment": "not_reached", "source": "not_run"}
                   for c in s["checks"]],
    }} if s["checks"] else {})} for s in task["steps"]]
    result = {"steps": entries, "routing": {"decision_model": "jev-latest", "text_helper": "disabled"},
              "model_usage": {"operation": [], "text": [], "review": [], "design": []}, "errors": []}
    previous_model = os.environ.get("TYPESAFE_MODEL")
    previous_helper = os.environ.pop("TEXT_MODEL_API_KEY", None)
    os.environ["TYPESAFE_MODEL"] = "jev-latest"
    action_count = 0
    history = []

    def persist():
        result.update(summarize(entries))
        if result["errors"] and result["status"] == "pass":
            result["status"] = "error"
        result["execution_status"] = (
            "error"
            if result["navigation_status"] == "error"
            else "blocked"
            if result["navigation_status"] in {"blocked", "needs_review"} or result["errors"]
            else "completed"
        )
        product_values = [entry.get("product_status", "not_tested") for entry in entries]
        result["product_status"] = (
            "fail"
            if "fail" in product_values or result["design_status"] == "fail"
            else "pass"
            if result["status"] == "pass"
            else "needs_review"
            if result["design_status"] == "needs_review" and result["navigation_status"] == "pass"
            else "not_tested"
        )
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        result["actions"] = action_count
        _write_json(output / "report.json", result)

    try:
        with browser_factory(task["url"]) as browser:
            browser.call("Emulation.setDeviceMetricsOverride", **task["viewport"], deviceScaleFactor=1, mobile=False)
            browser.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
            browser.call("Runtime.evaluate", expression="new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))", awaitPromise=True)
            for index, step in enumerate(task["steps"]):
                remaining = task["max_seconds"] - (time.perf_counter() - started)
                budget = task["max_steps"] - action_count
                if remaining <= 0 or budget <= 0:
                    result["errors"].append({"code": "journey_budget"})
                    entries[index].update(
                        navigation_status="blocked",
                        execution_status="blocked",
                        assertion_status="not_tested",
                        product_status="not_tested",
                    )
                    break
                folder = output / f"step-{index + 1:02d}"
                completed = "; ".join(s["name"] for s in entries[max(0, index - 5):index])
                goal = (f"Current objective: {step['goal']}\n"
                        f"Verified previous objectives: {completed or 'none'}. "
                        "Work only on the current objective. Scroll if its control is outside the viewport. "
                        "Do not repeat completed objectives or perform later work.")
                nav = run_task({"url": task["url"], "goal": goal, "values": task["values"],
                    "assertions": step["assertions"], "max_steps": budget, "max_seconds": remaining,
                    "min_confidence": task["min_confidence"], "stop_when_assertions_pass": True,
                    "recovery_attempts": 1, "jev_only": True}, folder, lambda _: nullcontext(browser), history=history)
                entry = entries[index]
                navigation_status = (
                    "blocked"
                    if nav.get("execution_status") == "blocked"
                    else "error"
                    if nav.get("execution_status") == "error"
                    else "pass"
                    if nav.get("status") == "pass"
                    else nav.get("status", "needs_review")
                )
                entry.update(navigation_status=navigation_status, navigation_report=f"step-{index + 1:02d}/report.json",
                             assertions=nav["assertions"], actions=len(nav["actions"]))
                for key in ("execution_status", "assertion_status", "product_status"):
                    if key in nav:
                        entry[key] = nav[key]
                action_count += len(nav["actions"])
                for key in ("operation", "text", "review"):
                    result["model_usage"][key].extend(nav.get("model_usage", {}).get(key, []))
                persist()
                if navigation_status != "pass":
                    break
                if step["checks"]:
                    entry["design"]["reason"] = "assessment_incomplete"
                    persist()
                    design = inspect_design(browser, step["checks"], task["min_confidence"])
                    _write_json(folder / "design.json", design)
                    entry["design"] = design
                    result["model_usage"]["design"].extend(design.get("model_usage", []))
                    persist()
    except (Exception, KeyboardInterrupt, RunDeadline) as error:
        result["errors"].append({"code": type(error).__name__, "detail": _safe_exception(error)})
        for entry in entries:
            if entry["navigation_status"] == "not_reached":
                entry.update(
                    navigation_status="error",
                    execution_status="error",
                    assertion_status="not_tested",
                    product_status="not_tested",
                )
                break
    finally:
        if previous_model is None:
            os.environ.pop("TYPESAFE_MODEL", None)
        else:
            os.environ["TYPESAFE_MODEL"] = previous_model
        if previous_helper is not None:
            os.environ["TEXT_MODEL_API_KEY"] = previous_helper
        persist()
    return result
