"""Bounded, rule-first browser design checks with optional Jev advice."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MEASURE_JS = Path(__file__).with_name("measure.js").read_text(encoding="utf-8")
MEASURE = MEASURE_JS
_MEASURE_SENTINEL = '"__JEV_QA_PAYLOAD__"'

MAX_CHECKS = 20
MAX_ID = 100
MAX_SELECTOR = 500
MAX_CRITERION = 2000
MAX_TOLERANCE = 10_000.0
MAX_MEASUREMENT_VALUE = 10_000_000.0
_VIEWPORT_FIELDS = ("width", "height", "documentWidth")
_COVERAGE_FIELDS = ("geometry", "textBounds", "contrast", "hitTesting", "pixelContentInspected")
KINDS = frozenset(
    {
        "unclipped",
        "contrast",
        "disabled",
        "aligned",
        "unobstructed",
        "horizontal_fit",
        "ellipsis",
        "decorative_overlap",
        "artwork",
        "contextual",
        "image_contained",
        "image_crop",
    }
)
_FIELDS = {
    "unclipped": {"id", "kind", "selector"},
    "contrast": {"id", "kind", "selector", "min_ratio"},
    "disabled": {"id", "kind", "selector"},
    "aligned": {"id", "kind", "selector", "other", "tolerance"},
    "unobstructed": {"id", "kind", "selector"},
    "horizontal_fit": {"id", "kind", "tolerance"},
    "ellipsis": {"id", "kind", "selector"},
    "decorative_overlap": {"id", "kind", "selector", "decorative", "content"},
    "artwork": {"id", "kind", "selector"},
    "contextual": {"id", "kind", "selector", "criterion"},
    "image_contained": {"id", "kind", "selector", "container", "tolerance"},
    "image_crop": {"id", "kind", "selector", "expected", "tolerance"},
}


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a non-empty string of at most {limit} characters")
    if any(ord(char) < 0x20 and char not in "\t\n\r" for char in value):
        raise ValueError(f"{name} contains a control character")
    return value


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def validate_checks(checks: Any) -> list[dict[str, Any]]:
    """Validate and normalize compact design check descriptors."""
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    if len(checks) > MAX_CHECKS:
        raise ValueError(f"checks must contain at most {MAX_CHECKS} items")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(checks):
        if not isinstance(item, Mapping):
            raise ValueError(f"checks[{index}] must be an object")
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise ValueError(f"checks[{index}].kind is unsupported")
        unknown = set(item) - _FIELDS[kind]
        if unknown:
            raise ValueError(f"checks[{index}] has unknown fields")
        check_id = _text(item.get("id"), f"checks[{index}].id", MAX_ID)
        if check_id in seen:
            raise ValueError(f"checks[{index}].id must be unique")
        seen.add(check_id)

        result: dict[str, Any] = {"id": check_id, "kind": kind}
        if "selector" in _FIELDS[kind]:
            result["selector"] = _text(item.get("selector"), f"checks[{index}].selector", MAX_SELECTOR)
        if kind == "contrast":
            result["min_ratio"] = _number(item.get("min_ratio", 4.5), f"checks[{index}].min_ratio", 1.0, 21.0)
        elif kind == "aligned":
            result["other"] = _text(item.get("other"), f"checks[{index}].other", MAX_SELECTOR)
            result["tolerance"] = _number(item.get("tolerance", 2.0), f"checks[{index}].tolerance", 0.0, MAX_TOLERANCE)
        elif kind == "horizontal_fit":
            result["tolerance"] = _number(item.get("tolerance", 1.0), f"checks[{index}].tolerance", 0.0, MAX_TOLERANCE)
        elif kind == "decorative_overlap":
            result["decorative"] = _text(item.get("decorative"), f"checks[{index}].decorative", MAX_SELECTOR)
            result["content"] = _text(item.get("content"), f"checks[{index}].content", MAX_SELECTOR)
        elif kind == "contextual":
            result["criterion"] = _text(item.get("criterion"), f"checks[{index}].criterion", MAX_CRITERION)
        elif kind == "image_contained":
            result["container"] = _text(item.get("container"), f"checks[{index}].container", MAX_SELECTOR)
            result["tolerance"] = _number(item.get("tolerance", 1.0), f"checks[{index}].tolerance", 0.0, MAX_TOLERANCE)
        elif kind == "image_crop":
            expected = item.get("expected")
            if not isinstance(expected, str) or expected not in {"full", "allowed"}:
                raise ValueError(f"checks[{index}].expected must be 'full' or 'allowed'")
            result["expected"] = expected
            result["tolerance"] = _number(item.get("tolerance", 1.0), f"checks[{index}].tolerance", 0.0, MAX_TOLERANCE)
        normalized.append(result)
    return normalized


def _finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _compact(value: Any, depth: int = 0) -> Any:
    """Keep report evidence JSON-safe and small."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {str(key)[:100]: _compact(item, depth + 1) for key, item in list(value.items())[:80]}
    if isinstance(value, (list, tuple)):
        return [_compact(item, depth + 1) for item in list(value)[:20]]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:2000]
    return str(value)[:500]


def _rect(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping) or not all(_finite(value.get(key)) for key in ("x", "y", "width", "height")):
        return None
    x, y, width, height = (float(value[key]) for key in ("x", "y", "width", "height"))
    right = value.get("right", x + width)
    bottom = value.get("bottom", y + height)
    if not _finite(right) or not _finite(bottom):
        return None
    return {"x": x, "y": y, "width": width, "height": height, "right": float(right), "bottom": float(bottom)}


def _measured(evidence: Any) -> bool:
    return isinstance(evidence, Mapping) and evidence.get("status") == "measured"


def _unsupported(evidence: Any) -> bool:
    return isinstance(evidence, Mapping) and (
        evidence.get("status") == "unsupported" or bool(evidence.get("unsupported"))
    )


def _visible(evidence: Any) -> bool:
    return _measured(evidence) and evidence.get("visible") is True


def _positive_rect(value: Any) -> dict[str, float] | None:
    result = _rect(value)
    if result is None or result["width"] <= 0 or result["height"] <= 0:
        return None
    if result["right"] < result["x"] or result["bottom"] < result["y"]:
        return None
    if (
        abs(result["right"] - (result["x"] + result["width"])) > 0.01
        or abs(result["bottom"] - (result["y"] + result["height"])) > 0.01
    ):
        return None
    return result


def _image_geometry(evidence: Any) -> tuple[dict[str, float], dict[str, float], dict[str, float]] | None:
    if (
        not _visible(evidence)
        or evidence.get("tag") != "img"
        or not _finite(evidence.get("naturalWidth"))
        or not _finite(evidence.get("naturalHeight"))
        or float(evidence["naturalWidth"]) <= 0
        or float(evidence["naturalHeight"]) <= 0
    ):
        return None
    content = _positive_rect(evidence.get("contentBox"))
    painted = _positive_rect(evidence.get("paintedBox"))
    visible = _positive_rect(evidence.get("visibleBox"))
    if content is None or painted is None or visible is None:
        return None
    if "sourceClipped" in evidence and type(evidence.get("sourceClipped")) is not bool:
        return None
    if "sourceClipPx" in evidence and (not _finite(evidence.get("sourceClipPx")) or evidence["sourceClipPx"] < 0):
        return None
    for key in ("sourceBox", "visibleSourceBox"):
        if key in evidence and _positive_rect(evidence.get(key)) is None:
            return None
    if (
        visible["x"] < content["x"] - 0.01
        or visible["y"] < content["y"] - 0.01
        or visible["right"] > content["right"] + 0.01
        or visible["bottom"] > content["bottom"] + 0.01
        or
        visible["x"] < painted["x"] - 0.01
        or visible["y"] < painted["y"] - 0.01
        or visible["right"] > painted["right"] + 0.01
        or visible["bottom"] > painted["bottom"] + 0.01
    ):
        return None
    return content, painted, visible


def _unknown(evidence: Any, reason: str = "measurement_unavailable") -> dict[str, Any]:
    raw = _compact(evidence) if isinstance(evidence, Mapping) else {}
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("status", "measurement_error")
    raw.setdefault("reason", reason)
    source = "unsupported" if raw.get("status") == "unsupported" or raw.get("unsupported") else "rule"
    return {"assessment": "uncertain", "source": source, "evidence": raw, "reason": raw["reason"]}


def _entry(
    assessment: str,
    evidence: Any,
    *,
    source: str = "rule",
    reason: str | None = None,
    advisory: bool = False,
) -> dict[str, Any]:
    result = {
        "assessment": assessment,
        "source": source,
        "evidence": _compact(evidence) if isinstance(evidence, Mapping) else {"status": "measurement_error"},
    }
    if reason:
        result["reason"] = reason
    if advisory:
        result["advisory"] = True
    return result


def classify_measurement(check: Mapping[str, Any], evidence: Any) -> dict[str, Any]:
    """Classify one measured fact without model input."""
    normalized = validate_checks([dict(check)])[0]
    kind = normalized["kind"]
    if kind == "artwork":
        return _entry(
            "uncertain",
            {**(dict(evidence) if isinstance(evidence, Mapping) else {}), "status": "unsupported",
             "reason": "pixel_content_not_inspected"},
            source="unsupported",
            reason="pixel_content_not_inspected",
        )
    if not _measured(evidence) or _unsupported(evidence):
        return _unknown(evidence)

    if kind == "unclipped":
        if not _visible(evidence):
            return _unknown(evidence, "target_not_visible")
        bounds = _rect(evidence.get("box"))
        text_box = _rect(evidence.get("textBox"))
        if (
            bounds is None
            or evidence.get("overflowX") is None
            or evidence.get("overflowY") is None
            or (text_box is None and evidence.get("fullText", ""))
        ):
            return _unknown(evidence, "text_bounds_unavailable")
        overflow_x = evidence.get("overflowX") in {"hidden", "clip"}
        overflow_y = evidence.get("overflowY") in {"hidden", "clip"}
        out_x = bool(text_box and (text_box["x"] < bounds["x"] - 1 or text_box["right"] > bounds["right"] + 1))
        out_y = bool(text_box and (text_box["y"] < bounds["y"] - 1 or text_box["bottom"] > bounds["bottom"] + 1))
        scroll_x = evidence.get("scrollWidth")
        client_x = evidence.get("clientWidth")
        scroll_y = evidence.get("scrollHeight")
        client_y = evidence.get("clientHeight")
        overflow_x = overflow_x and ((_finite(scroll_x) and _finite(client_x) and scroll_x > client_x + 1) or out_x)
        overflow_y = overflow_y and ((_finite(scroll_y) and _finite(client_y) and scroll_y > client_y + 1) or out_y)
        return _entry("fail" if overflow_x or overflow_y else "pass", evidence,
                      reason="content_clipped" if overflow_x or overflow_y else None)

    if kind == "contrast":
        if (
            not _visible(evidence)
            or evidence.get("contrastSupported") is not True
            or not _finite(evidence.get("contrastRatio"))
        ):
            return _unknown(evidence, "contrast_measurement_unavailable")
        ratio = float(evidence["contrastRatio"])
        threshold = normalized["min_ratio"]
        return _entry("pass" if ratio >= threshold else "fail", evidence,
                      reason="contrast_below_minimum" if ratio < threshold else None)

    if kind == "disabled":
        if not _visible(evidence) or type(evidence.get("nativeDisabled")) is not bool:
            return _unknown(evidence, "disabled_state_unavailable")
        disabled = evidence["nativeDisabled"]
        return _entry("pass" if disabled else "fail", evidence,
                      reason="control_is_enabled" if not disabled else None)

    if kind == "aligned":
        first, second = evidence.get("first"), evidence.get("second")
        if (
            not _measured(evidence)
            or not _visible(first)
            or not _visible(second)
            or _unsupported(first)
            or _unsupported(second)
            or _rect(first.get("box")) is None
            or _rect(second.get("box")) is None
        ):
            return _unknown(evidence, "alignment_geometry_unavailable")
        first_box, second_box = _rect(first["box"]), _rect(second["box"])
        tolerance = normalized["tolerance"]
        aligned = all(abs(first_box[key] - second_box[key]) <= tolerance for key in ("x", "width"))
        return _entry("pass" if aligned else "fail", evidence,
                      reason="geometry_mismatch" if not aligned else None)

    if kind == "unobstructed":
        samples = evidence.get("hitSamples")
        if (
            not _visible(evidence)
            or evidence.get("inViewport") is not True
            or not isinstance(samples, list)
            or len(samples) != 9
        ):
            return _unknown(evidence, "hit_evidence_unavailable")
        if not all(isinstance(sample, Mapping) and type(sample.get("targetReceivesHit")) is bool for sample in samples):
            return _unknown(evidence, "hit_evidence_unavailable")
        clear = all(sample["targetReceivesHit"] for sample in samples)
        return _entry("pass" if clear else "fail", evidence,
                      reason="target_is_obstructed" if not clear else None)

    if kind == "horizontal_fit":
        viewport = evidence.get("viewportWidth", evidence.get("width"))
        document_width = evidence.get("documentWidth")
        if not _finite(viewport) or not _finite(document_width):
            return _unknown(evidence, "horizontal_geometry_unavailable")
        fits = float(document_width) <= float(viewport) + normalized["tolerance"]
        return _entry("pass" if fits else "fail", evidence,
                      reason="horizontal_overflow" if not fits else None)

    if kind == "ellipsis":
        if (
            not _visible(evidence)
            or not _finite(evidence.get("clientWidth"))
            or not _finite(evidence.get("scrollWidth"))
        ):
            return _unknown(evidence, "ellipsis_measurement_unavailable")
        truncated = evidence["scrollWidth"] > evidence["clientWidth"] + 1
        if not truncated:
            return _entry("pass", evidence)
        full_text = evidence.get("fullText", evidence.get("text"))
        title = evidence.get("title")
        if evidence.get("fullTextTruncated") is True or not isinstance(full_text, str) or not isinstance(title, str):
            return _unknown(evidence, "full_text_unavailable")
        valid = (
            evidence.get("whiteSpace") == "nowrap"
            and evidence.get("textOverflow") == "ellipsis"
            and title == full_text
        )
        reason = "ellipsis_policy_violation" if not valid else None
        return _entry("pass" if valid else "fail", evidence, reason=reason)

    if kind == "decorative_overlap":
        decorative = evidence.get("decorativeIntersectionPx2")
        content = evidence.get("contentIntersectionPx2")
        if not _visible(evidence) or not _finite(decorative) or not _finite(content):
            return _unknown(evidence, "overlap_geometry_unavailable")
        covered = float(content) > 0.01
        return _entry("fail" if covered else "pass", evidence,
                      reason="meaningful_content_covered" if covered else None)

    if kind in {"image_contained", "image_crop"}:
        geometry = _image_geometry(evidence)
        if geometry is None:
            return _unknown(evidence, "image_measurement_unavailable")
        _content, _painted, visible = geometry
        if kind == "image_contained":
            if evidence.get("containerIsAncestor") is not True:
                return _unknown(evidence, "image_container_unavailable")
            container = _positive_rect(evidence.get("containerInnerBox"))
            if container is None:
                return _unknown(evidence, "image_container_unavailable")
            tolerance = normalized["tolerance"]
            contained = (
                visible["x"] >= container["x"] - tolerance
                and visible["y"] >= container["y"] - tolerance
                and visible["right"] <= container["right"] + tolerance
                and visible["bottom"] <= container["bottom"] + tolerance
            )
            return _entry(
                "pass" if contained else "fail",
                evidence,
                reason="image_outside_container" if not contained else None,
            )
        if "sourceClipped" in evidence and type(evidence.get("sourceClipped")) is not bool:
            return _unknown(evidence, "image_crop_measurement_unavailable")
        if normalized["expected"] == "allowed":
            return _entry("pass", evidence)
        _content, painted, visible = geometry
        crop_px = max(
            abs(visible["x"] - painted["x"]),
            abs(visible["y"] - painted["y"]),
            abs(visible["right"] - painted["right"]),
            abs(visible["bottom"] - painted["bottom"]),
        )
        cropped = crop_px > normalized["tolerance"]
        return _entry("fail" if cropped else "pass", evidence, reason="image_source_cropped" if cropped else None)

    if kind == "contextual":
        return _unknown(evidence, "contextual_requires_jev")
    return _unknown(evidence, "unsupported_kind")


def _context_observation(evidence: Mapping[str, Any], index: int | None = None) -> dict[str, Any]:
    """Whitelist the compact element facts that a contextual reviewer may see."""
    allowed = ("tag", "role", "visible", "box", "textBox", "text", "nativeDisabled", "ariaDisabled")
    result = {key: _compact(evidence[key]) for key in allowed if key in evidence}
    if isinstance(evidence.get("fullText"), str):
        result["text"] = _compact(evidence["fullText"])
    if evidence.get("fullTextTruncated"):
        result["text_truncated"] = True
    if index is not None:
        result = {"observation_index": index, "element": result}
    return result


def _review_contextual(observations: list[dict[str, Any]], criteria: list[str], min_confidence: float) -> Any:
    """Call the existing Jev reviewer only when contextual checks need it."""
    from .runner import review_evidence

    return review_evidence({"observations": observations}, criteria, min_confidence, jev_only=True)


def _safe_error(error: BaseException) -> str:
    message = str(error).strip().lower()
    if any(marker in message for marker in ("bearer", "api_key", "authorization", "password", "secret", "token=")):
        return "browser measurement failed"
    return message[:240] or "browser measurement failed"


def _safe_error_type(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()[:100]
    sanitized = _safe_error(value)
    return "browser measurement failed" if sanitized == "browser measurement failed" else value


def _safe_measurement_error(value: Any) -> dict[str, str] | None:
    """Keep only a short, sanitized error reason from a browser measurement."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        raw_reason = value.get("reason", value.get("message"))
        if raw_reason is None:
            raw_reason = value or "browser measurement failed"
        result = {"reason": _safe_error(raw_reason)}
        error_type = _safe_error_type(value.get("type"))
        if error_type:
            result["type"] = error_type
        return result
    return {"reason": _safe_error(value)}


def _safe_measurement_number(value: Any) -> int | float | None:
    if not _finite(value) or not 0 <= float(value) <= MAX_MEASUREMENT_VALUE:
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def _safe_viewport(value: Any) -> dict[str, int | float | None] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: _safe_measurement_number(value.get(key)) for key in _VIEWPORT_FIELDS if key in value}


def _safe_coverage(value: Any) -> dict[str, bool] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: value[key] for key in _COVERAGE_FIELDS if type(value.get(key)) is bool}


def _jev_model(value: Any) -> bool:
    return isinstance(value, str) and value.lower().startswith("jev")


def _model_entry(evidence: Mapping[str, Any], judgment: Any, min_confidence: float) -> dict[str, Any]:
    model_evidence = {"status": "measured", "observation": _context_observation(evidence)}
    if not isinstance(judgment, Mapping):
        return _entry("uncertain", {**model_evidence, "reason": "malformed_model_judgment"}, source="jev",
                      reason="malformed_model_judgment")
    assessment = judgment.get("assessment")
    confidence = judgment.get("confidence")
    if assessment not in {"pass", "fail", "uncertain"}:
        assessment = "uncertain"
        reason = "malformed_model_judgment"
    elif assessment == "uncertain":
        reason = judgment.get("error", "model_uncertain")
    elif not _jev_model(judgment.get("model")):
        assessment = "uncertain"
        reason = "non_jev_model"
    elif not _finite(confidence) or float(confidence) < min_confidence:
        assessment = "uncertain"
        reason = "low_model_confidence"
    else:
        reason = None
    result = _entry(assessment, {**model_evidence, "model": _compact(dict(judgment))}, source="jev",
                    reason=str(reason) if reason else None, advisory=assessment in {"pass", "fail"})
    return result


def inspect_design(browser: Any, checks: Any, min_confidence: float = 0.8) -> dict[str, Any]:
    """Measure and assess checks; Jev receives only eligible contextual observations."""
    normalized = validate_checks(checks)
    confidence = _number(min_confidence, "min_confidence", 0.0, 1.0)
    if not normalized:
        return {"status": "pass", "checks": [], "model_usage": []}

    try:
        payload = json.dumps({"checks": normalized}, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        expression = MEASURE_JS.replace(_MEASURE_SENTINEL, json.dumps(payload), 1)
        if expression == MEASURE_JS:
            raise ValueError("measurement script is missing its parameter sentinel")
        measured = browser.evaluate(expression)
    except Exception as error:
        measured = {"checks": {}, "error": {"type": type(error).__name__, "reason": _safe_error(error)}}
    safe_error = _safe_measurement_error(measured.get("error")) if isinstance(measured, Mapping) else None
    raw_checks = measured.get("checks") if isinstance(measured, Mapping) else None
    if not isinstance(raw_checks, Mapping):
        raw_checks = {}

    entries: list[dict[str, Any]] = []
    contextual: list[tuple[int, dict[str, Any], Mapping[str, Any]]] = []
    for check in normalized:
        raw = raw_checks.get(check["id"])
        if not isinstance(raw, Mapping):
            raw = {
                "status": "measurement_error",
                "reason": safe_error["reason"] if safe_error else "missing_measurement",
            }
        elif safe_error and raw.get("reason") == "missing_measurement":
            raw = {**raw, "reason": safe_error["reason"]}
        if check["kind"] == "contextual" and _measured(raw) and _visible(raw) and not _unsupported(raw):
            entries.append({"id": check["id"], "kind": check["kind"], "_pending": True})
            contextual.append((len(entries) - 1, check, raw))
            continue
        result = classify_measurement(check, raw)
        entries.append({"id": check["id"], "kind": check["kind"], **result})

    model_usage: list[Any] = []
    if contextual:
        observations = [_context_observation(raw, offset) for offset, (_, _, raw) in enumerate(contextual)]
        criteria = [
            f"Assess observation {offset} only. {check['criterion']}"
            for offset, (_, check, _) in enumerate(contextual)
        ]
        try:
            review = _review_contextual(observations, criteria, confidence)
            judgments = review.get("judgments", []) if isinstance(review, Mapping) else review
            if not isinstance(judgments, list):
                judgments = []
            if isinstance(review, Mapping) and isinstance(review.get("model_usage"), list):
                model_usage = _compact(review["model_usage"])
        except Exception as error:
            judgments = []
            model_usage = []
            review_error = _safe_error(error)
        else:
            review_error = None
        for offset, (entry_index, _check, raw) in enumerate(contextual):
            judgment = (
                judgments[offset]
                if offset < len(judgments)
                else {"error": review_error or "missing_model_judgment"}
            )
            if review_error and not isinstance(judgment, Mapping):
                judgment = {"error": review_error}
            result = _model_entry(raw, judgment, confidence)
            entries[entry_index] = {"id": entries[entry_index]["id"], "kind": "contextual", **result}

    deterministic_fail = any(item.get("source") == "rule" and item.get("assessment") == "fail" for item in entries)
    unresolved = any(item.get("assessment") == "uncertain" or item.get("advisory") for item in entries)
    status = "fail" if deterministic_fail else "needs_review" if unresolved else "pass"
    report = {"status": status, "checks": entries, "model_usage": model_usage}
    if isinstance(measured, Mapping):
        viewport = _safe_viewport(measured.get("viewport"))
        coverage = _safe_coverage(measured.get("coverage"))
        if viewport is not None:
            report["viewport"] = viewport
        if coverage is not None:
            report["coverage"] = coverage
        if safe_error is not None:
            report["error"] = safe_error
    return report


__all__ = ["MEASURE", "MEASURE_JS", "KINDS", "validate_checks", "classify_measurement", "inspect_design"]
