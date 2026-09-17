"""Measured design contracts. No fixture variant or expected-answer input to Jev."""

from pathlib import Path

MEASURE = Path(__file__).with_name("measure.js").read_text()
CHECKS = {
    "details": {
        "title": "The full session title must be readable in its box, without clipping. Compare textBox with box, overflow styles and scroll dimensions. Offscreen scrolling is not clipping.",
        "badge": "An availability status badge may overlap the decorative session-art color band. It must remain visible and must not cover any session-title text. The art band is not meaningful text or a control. Classify this observed overlap against that policy.",
        "artwork": "The canvas brand artwork must depict the approved brand mark. Decide whether the supplied measurements establish this visual requirement. Pixel content was not inspected; do not infer it from dimensions or surrounding text.",
    },
    "booking": {
        "status": "The enabled booking status message must have text contrast of at least 4.5 against its solid background. Unsupported contrast evidence means uncertain.",
        "disabled": "The Email receipt control is unavailable until confirmation. Reduced contrast is permitted for a genuinely disabled control with that role. It must be disabled, not an enabled action merely styled as disabled. Decide whether this disabled-control presentation meets that rule.",
        "alignment": "The stacked Attendee name and Attendee email input boxes must have matching left edges and widths, each within 2 CSS pixels. Both must be visible.",
    },
    "review": {
        "confirm": "The Confirm reservation action must remain visible and unobstructed. Its center and sampled interior points must receive hits on the control or its descendants, not on an unrelated element. Being elsewhere in a scrollable document is not itself a defect; missing usable hit evidence is uncertain.",
        "overflow": "At this viewport, the page must fit horizontally without document-wide horizontal scrolling. A documentWidth greater than viewport width by over 1 CSS pixel violates the rule.",
        "reference": "This project reference is secondary information. Single-line ellipsis is permitted if a native title attribute exposes exactly the same full reference text. The visible label need not show the complete text at once. Decide if the observed truncation follows this policy.",
    },
}
ELEMENTS = {
    "details": ["session-title", "session-art", "availability-badge", "brand-art"],
    "booking": ["code-status", "receipt-button", "attendee-name", "attendee-email"],
    "review": ["confirm-button", "project-label"],
}


def evidence_for(stage, measurements):
    """Send bounded observed facts; do not send URL, classes, variant, source or oracle."""
    return {
        "viewport": measurements["viewport"],
        "coverage": measurements["coverage"],
        "elements": {k: measurements["elements"].get(k) for k in ELEMENTS[stage]},
        "relationships": measurements["relationships"] if stage == "details" else {},
    }


def rule_verdicts(stage, evidence):
    result = {key: "uncertain" for key in CHECKS[stage]}
    elements = evidence.get("elements", {})
    if stage == "details":
        title = elements.get("session-title")
        if title and title["visible"]:
            b, t, s = title["box"], title["textBox"], title["style"]
            clipped_y = s["overflowY"] in ("hidden", "clip") and (
                t["bottom"] > b["bottom"] + 1 or t["y"] < b["y"] - 1
            )
            clipped_x = s["overflowX"] in ("hidden", "clip") and (
                t["right"] > b["right"] + 1 or t["x"] < b["x"] - 1
            )
            result["title"] = "fail" if clipped_y or clipped_x else "pass"
        # Context-sensitive overlaps and pixel semantics remain unresolved in this simple baseline.
    if stage == "booking":
        status = elements.get("code-status")
        if status and status["visible"] and status["contrastRatio"] is not None:
            result["status"] = "pass" if status["contrastRatio"] >= 4.5 else "fail"
        disabled = elements.get("receipt-button")
        if disabled and disabled["visible"]:
            result["disabled"] = "pass" if disabled["disabled"] else "fail"
        a, b = elements.get("attendee-name"), elements.get("attendee-email")
        if a and b and a["visible"] and b["visible"]:
            result["alignment"] = (
                "pass"
                if all(abs(a["box"][k] - b["box"][k]) <= 2 for k in ("x", "width"))
                else "fail"
            )
    if stage == "review":
        confirm = elements.get("confirm-button")
        if confirm and confirm["visible"] and confirm["hitSamples"]:
            samples = confirm["hitSamples"]
            in_view = all(
                0 <= p["x"] < evidence["viewport"]["width"]
                and 0 <= p["y"] < evidence["viewport"]["height"]
                for p in samples
            )
            if in_view:
                result["confirm"] = (
                    "pass" if all(p["targetReceivesHit"] for p in samples) else "fail"
                )
        viewport = evidence.get("viewport", {})
        if "documentWidth" in viewport and "width" in viewport:
            result["overflow"] = (
                "fail" if viewport["documentWidth"] > viewport["width"] + 1 else "pass"
            )
        # Reference truncation needs contextual permission, left unresolved by the generic baseline.
    return result


def score(actual, expected):
    if len(actual) != len(expected):
        raise ValueError("Scoring requires an outcome for every requested check")
    return {
        "correct": sum(a == e for a, e in zip(actual, expected)),
        "total": len(expected),
        "false_passes": sum(
            a == "pass" and e == "fail" for a, e in zip(actual, expected)
        ),
        "missed_defects": sum(
            a != "fail" and e == "fail" for a, e in zip(actual, expected)
        ),
    }
