"""Turn AI Gateway token usage into a chargeback report.

Input is the result of chargeback.kql, in any of these forms:
  - a CSV file exported from Log Analytics (Export > CSV),
  - the JSON rows of the Azure CLI (az monitor log-analytics query ... -o json > usage.json), or
  - the JSON response of the Log Analytics query API (az rest ... /query > usage.json).

Prices come from a JSON price list (see prices.example.json). The report is an estimate:
observed tokens x the prices you supply. Reconcile it with provider billing or Azure Cost Management before you
use it for financial reporting.

Usage:
    python chargeback_report.py <usage.csv|usage.json> <prices.json> [--by Tenant,ClientApp] [--out report.csv]

Examples:
    python chargeback_report.py usage.csv prices.json
    python chargeback_report.py usage.json prices.json --by ApiKeyId,Model --out chargeback.csv
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

NUMERIC = ("Requests", "InputTokens", "CachedInputTokens", "OutputTokens")


def load_usage(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if text.lstrip().startswith("["):
        # Azure CLI: [{"Tenant": ..., "InputTokens": "123", ...}], with every value as a string
        rows = [{k: v for k, v in row.items() if k != "TableName"} for row in json.loads(text)]
    elif text.lstrip().startswith("{"):
        # Log Analytics query API: {"tables": [{"columns": [{"name": ...}], "rows": [[...]]}]}
        table = json.loads(text)["tables"][0]
        names = [c["name"] for c in table["columns"]]
        rows = [dict(zip(names, row)) for row in table["rows"]]
    else:
        rows = list(csv.DictReader(text.splitlines()))
    for row in rows:
        for key in NUMERIC:
            value = row.get(key)
            row[key] = int(float(str(value).replace(",", ""))) if value not in (None, "") else 0
        for key, value in row.items():
            if key not in NUMERIC:
                row[key] = "" if value is None else str(value)
    return rows


def find_price(model: str, prices: dict) -> dict | None:
    name = model.lower()
    table = {k.lower(): v for k, v in prices["models"].items()}
    if name in table:
        return table[name]
    # Versioned names such as my-model-2026-01-01 match the longest price key they start with.
    matches = [k for k in table if name.startswith(k + "-")]
    return table[max(matches, key=len)] if matches else None


def estimate_cost(row: dict, price: dict, per_tokens: int) -> float:
    cached = min(max(row["CachedInputTokens"], 0), row["InputTokens"])
    uncached = row["InputTokens"] - cached
    cached_price = price.get("cached_input", price["input"])
    return (uncached * price["input"] + cached * cached_price + row["OutputTokens"] * price["output"]) / per_tokens


def main() -> None:
    parser = argparse.ArgumentParser(description="Price AI Gateway token usage per owner.")
    parser.add_argument("usage", type=Path, help="CSV export or query API JSON from chargeback.kql")
    parser.add_argument("prices", type=Path, help="price list JSON, see prices.example.json")
    parser.add_argument("--by", default="Tenant,ClientApp,ApiKeyId",
                        help="comma-separated columns to group by (default: Tenant,ClientApp,ApiKeyId)")
    parser.add_argument("--out", type=Path, help="also write the report to this CSV file")
    args = parser.parse_args()

    rows = load_usage(args.usage)
    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    per_tokens = int(prices.get("per_tokens", 1_000_000))
    currency = prices.get("currency", "")
    group_by = [c.strip() for c in args.by.split(",") if c.strip()]
    if not rows:
        sys.exit("The usage file has no rows. Send traffic, wait a few minutes, and run the query again.")
    missing = [c for c in group_by + ["Model"] if c not in rows[0]]
    if missing:
        sys.exit(f"Column(s) not in the usage file: {', '.join(missing)}. Columns: {', '.join(rows[0])}")

    totals = defaultdict(lambda: {"Requests": 0, "InputTokens": 0, "CachedInputTokens": 0, "OutputTokens": 0,
                                  "UnpricedTokens": 0, "EstimatedCost": 0.0})
    unpriced_models = set()
    for row in rows:
        key = tuple(row[c] or "(none)" for c in group_by)
        group = totals[key]
        for name in NUMERIC:
            group[name] += row[name]
        price = find_price(row["Model"], prices)
        if price is None:
            group["UnpricedTokens"] += row["InputTokens"] + row["OutputTokens"]
            unpriced_models.add(row["Model"] or "(none)")
        else:
            group["EstimatedCost"] += estimate_cost(row, price, per_tokens)

    columns = group_by + ["Requests", "InputTokens", "CachedInputTokens", "OutputTokens", "UnpricedTokens",
                          f"EstimatedCost{f' ({currency})' if currency else ''}"]
    report = []
    for key, group in sorted(totals.items(), key=lambda kv: (-kv[1]["EstimatedCost"],
                                                              -(kv[1]["InputTokens"] + kv[1]["OutputTokens"]))):
        report.append(list(key) + [group["Requests"], group["InputTokens"], group["CachedInputTokens"],
                                   group["OutputTokens"], group["UnpricedTokens"], round(group["EstimatedCost"], 6)])

    widths = [max(len(str(v)) for v in [c] + [r[i] for r in report]) for i, c in enumerate(columns)]
    print("  ".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    for line in report:
        print("  ".join(str(v).ljust(w) for v, w in zip(line, widths)))
    total_cost = sum(g["EstimatedCost"] for g in totals.values())
    total_tokens = sum(g["InputTokens"] + g["OutputTokens"] for g in totals.values())
    print(f"\nTotal: {total_tokens:,} tokens, estimated {total_cost:,.6f} {currency}".rstrip())
    if unpriced_models:
        print(f"No price for: {', '.join(sorted(unpriced_models))}. Add them to {args.prices.name}; "
              "their tokens are in UnpricedTokens and not in the estimated cost.")

    if args.out:
        with args.out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(report)
        print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
