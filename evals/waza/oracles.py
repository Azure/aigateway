"""Small deterministic fixture oracles, not clients or live-service probes."""

import math


def valid_response(protocol, payload):
    if not isinstance(payload, dict) or "error" in payload:
        return False

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    try:
        if protocol == "chat":
            choices = payload["choices"]
            return isinstance(choices, list) and bool(choices) and all(
                isinstance(c, dict) and isinstance(c.get("message"), dict)
                and text(c["message"].get("content")) for c in choices)
        if protocol == "responses":
            output = payload["output"]
            return isinstance(output, list) and any(
                isinstance(item, dict) and item.get("type") == "message"
                and isinstance(item.get("content"), list) and any(
                    isinstance(block, dict) and block.get("type") == "output_text"
                    and text(block.get("text")) for block in item["content"])
                for item in output)
        if protocol == "anthropic":
            content = payload["content"]
            return isinstance(content, list) and any(
                isinstance(block, dict) and block.get("type") == "text"
                and text(block.get("text")) for block in content)
        if protocol == "embeddings":
            data = payload["data"]
            return isinstance(data, list) and bool(data) and all(
                isinstance(item, dict) and isinstance(item.get("embedding"), list)
                and bool(item["embedding"]) and all(
                    type(number) in (int, float) and math.isfinite(number)
                    for number in item["embedding"]) for item in data)
    except (KeyError, TypeError):
        return False
    return False


def discovery_sequence(methods, cursors, maximum_pages):
    if methods != ["initialize", "notifications/initialized", "tools/list"]:
        return False
    if type(maximum_pages) is not int or maximum_pages < 1 or len(cursors) > maximum_pages:
        return False
    seen = set()
    for cursor in cursors:
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            return False
        seen.add(cursor)
    return True


def compare_budget(scenario, baseline, candidate):
    """Illustrative paired-budget check; input samples must be observed, not invented."""
    if baseline is None or candidate is None:
        return {"status": "unscored", "reason": "missing paired observed baseline"}
    for sample in (baseline, candidate):
        if sample.get("scenario") != scenario or sample.get("evidence") != "observed":
            return {"status": "unscored", "reason": "unpaired or unobserved sample"}
        if sample.get("contextFingerprint") != baseline.get("contextFingerprint"):
            return {"status": "unscored", "reason": "different scenario conditions"}
        if not sample.get("contextFingerprint"):
            return {"status": "unscored", "reason": "missing scenario conditions"}
        if type(sample.get("toolCalls")) is not int or sample["toolCalls"] < 0:
            raise ValueError("tool count must be a nonnegative integer")
        if type(sample.get("medianSeconds")) not in (int, float) or not math.isfinite(
                sample["medianSeconds"]) or sample["medianSeconds"] <= 0:
            raise ValueError("median latency must be measured and positive")
    tool_limit = baseline["toolCalls"] + 2
    latency_limit = baseline["medianSeconds"] * 1.5 + 30
    return {
        "status": "pass" if candidate["toolCalls"] <= tool_limit
        and candidate["medianSeconds"] <= latency_limit else "fail",
        "toolLimit": tool_limit, "medianSecondsLimit": latency_limit,
    }
