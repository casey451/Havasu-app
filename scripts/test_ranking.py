from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
import sys


TEST_QUERIES = [
    "kids activities",
    "things to do tonight",
    "date night",
    "free events",
    "live music",
    "family events",
    "weekend events",
    "plumber",
    "electrician",
]

SIGNALS = ("base", "click", "popularity", "recency", "semantic")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class RankedRow:
    id: str
    final_score: float
    components: dict[str, float]
    reason: str


class HttpApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _post_json(self, path: str, body: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def recommend(self, query: str, debug: bool) -> Any:
        suffix = "?debug=true" if debug else ""
        return self._post_json(f"/ai/recommend{suffix}", {"query": query})

    def click(self, query: str, clicked_id: str) -> Any:
        # Current backend contract uses query + clicked_id.
        return self._post_json("/ai/click", {"query": query, "clicked_id": clicked_id})


class InternalApiClient:
    def __init__(self) -> None:
        from fastapi.testclient import TestClient
        from api.main import app

        self.client = TestClient(app)

    def recommend(self, query: str, debug: bool) -> Any:
        suffix = "?debug=true" if debug else ""
        resp = self.client.post(f"/ai/recommend{suffix}", json={"query": query})
        resp.raise_for_status()
        return resp.json()

    def click(self, query: str, clicked_id: str) -> Any:
        resp = self.client.post("/ai/click", json={"query": query, "clicked_id": clicked_id})
        resp.raise_for_status()
        return resp.json()


def parse_recommend_payload(payload: Any) -> list[RankedRow]:
    if isinstance(payload, list):
        rows: list[RankedRow] = []
        for item in payload[:5]:
            rid = str(item.get("id") or "").strip()
            if not rid:
                continue
            rows.append(
                RankedRow(
                    id=rid,
                    final_score=float(item.get("score") or 0.0),
                    components={k: 0.0 for k in SIGNALS},
                    reason=str(item.get("reason") or ""),
                )
            )
        return rows

    results = payload.get("results") if isinstance(payload, dict) else []
    breakdown = payload.get("breakdown") if isinstance(payload, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(breakdown, list):
        for b in breakdown:
            rid = str((b or {}).get("id") or "").strip()
            if rid:
                by_id[rid] = b or {}

    rows = []
    for item in (results or [])[:5]:
        rid = str(item.get("id") or "").strip()
        if not rid:
            continue
        b = by_id.get(rid, {})
        comp = (b.get("components") or {}) if isinstance(b, dict) else {}
        components = {k: float(comp.get(k) or 0.0) for k in SIGNALS}
        rows.append(
            RankedRow(
                id=rid,
                final_score=float((b.get("final_score") if isinstance(b, dict) else None) or item.get("score") or 0.0),
                components=components,
                reason=str(item.get("reason") or ""),
            )
        )
    return rows


def dominant_signal(rows: list[RankedRow]) -> str:
    if not rows:
        return "none"
    totals = Counter()
    for row in rows:
        for key, val in row.components.items():
            totals[key] += float(val)
    return totals.most_common(1)[0][0] if totals else "none"


def detect_issues(rows: list[RankedRow]) -> list[str]:
    issues: list[str] = []
    if not rows:
        return ["no_results"]

    pop_dom = 0
    sem_dom = 0
    rec_vals = []
    sem_vals = []
    scores = [r.final_score for r in rows]

    for row in rows:
        c = row.components
        pop = c.get("popularity", 0.0)
        sem = c.get("semantic", 0.0)
        other_pop = [c.get("click", 0.0), c.get("recency", 0.0), c.get("semantic", 0.0)]
        other_sem = [c.get("click", 0.0), c.get("recency", 0.0), c.get("popularity", 0.0)]
        if pop > max(other_pop):
            pop_dom += 1
        if sem > max(other_sem):
            sem_dom += 1
        rec_vals.append(c.get("recency", 0.0))
        sem_vals.append(c.get("semantic", 0.0))

    if pop_dom >= 3:
        issues.append("popularity dominance")
    if sem_dom >= 3:
        issues.append("semantic dominance")
    if sum(rec_vals) / max(1, len(rec_vals)) < 0.05:
        issues.append("no recency impact")
    if len(scores) >= 2 and (max(scores) - min(scores)) < 0.08:
        issues.append("flat scoring")
    if sum(sem_vals) / max(1, len(sem_vals)) < 0.05:
        issues.append("low semantic relevance")
    return issues


def print_rows(query: str, rows: list[RankedRow]) -> None:
    print(f'\nQuery: "{query}"')
    print("Top Results:")
    for idx, row in enumerate(rows, start=1):
        c = row.components
        print(f"{idx}. {row.id} (score: {row.final_score:.4f})")
        print(f"   base: {c['base']:.4f}")
        print(f"   click: {c['click']:.4f}")
        print(f"   popularity: {c['popularity']:.4f}")
        print(f"   recency: {c['recency']:.4f}")
        print(f"   semantic: {c['semantic']:.4f}")
    dom = dominant_signal(rows)
    issues = detect_issues(rows)
    print("Observations:")
    print(f"- Dominant signal: {dom}")
    if issues:
        print(f"- Issues: {', '.join(issues)}")


def rank_positions(rows: list[RankedRow]) -> dict[str, int]:
    return {r.id: i for i, r in enumerate(rows, start=1)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automated ranking validation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Backend base URL for HTTP mode.")
    parser.add_argument(
        "--mode",
        choices=("http", "internal"),
        default="http",
        help="Use real HTTP API or in-process FastAPI TestClient.",
    )
    parser.add_argument("--no-click-sim", action="store_true", help="Disable click simulation pass.")
    args = parser.parse_args()

    client: Any
    if args.mode == "internal":
        client = InternalApiClient()
    else:
        client = HttpApiClient(args.base_url)

    all_rows: dict[str, list[RankedRow]] = {}
    issue_counts = Counter()
    dominant_counts = Counter()

    print("=== Ranking Validation ===")
    print(f"Mode: {args.mode}")
    if args.mode == "http":
        print(f"Base URL: {args.base_url.rstrip('/')}")

    for query in TEST_QUERIES:
        payload = client.recommend(query, debug=True)
        rows = parse_recommend_payload(payload)
        all_rows[query] = rows
        print_rows(query, rows)
        dom = dominant_signal(rows)
        if dom != "none":
            dominant_counts[dom] += 1
        for issue in detect_issues(rows):
            issue_counts[issue] += 1

    if not args.no_click_sim:
        print("\n=== Click Simulation ===")
        for query in TEST_QUERIES:
            before = all_rows.get(query, [])
            if not before:
                continue
            before_rank = rank_positions(before)
            for row in before[:2]:
                try:
                    client.click(query, row.id)
                except urllib.error.HTTPError:
                    # Ignore single click failure and continue analysis.
                    continue
            after_payload = client.recommend(query, debug=True)
            after = parse_recommend_payload(after_payload)
            after_rank = rank_positions(after)
            print(f'\nQuery: "{query}" click impact')
            for row in before[:2]:
                bpos = before_rank.get(row.id, -1)
                apos = after_rank.get(row.id, -1)
                bclick = row.components.get("click", 0.0)
                aclick = next((r.components.get("click", 0.0) for r in after if r.id == row.id), 0.0)
                print(
                    f"- {row.id}: rank {bpos} -> {apos}, click component {bclick:.4f} -> {aclick:.4f}"
                )

    print("\n=== System-wide Findings ===")
    most_dom = dominant_counts.most_common(1)[0][0] if dominant_counts else "none"
    weakest = min(dominant_counts, key=dominant_counts.get) if dominant_counts else "none"
    print(f"Most dominant signal overall: {most_dom}")
    print(f"Weakest signal overall: {weakest}")

    print("\nIssues:")
    if issue_counts:
        for issue, count in issue_counts.most_common():
            print(f"- {issue} ({count} query runs)")
    else:
        print("- none detected")

    print("\nRecommendations (no code changes applied):")
    if issue_counts.get("popularity dominance", 0) > 0:
        print("- Lower popularity weight slightly (e.g., 0.5 -> 0.35).")
    if issue_counts.get("semantic dominance", 0) > 0:
        print("- Lower semantic weight slightly (e.g., 0.8 -> 0.65).")
    if issue_counts.get("no recency impact", 0) > 0:
        print("- Increase recency weight or shorten recency decay window.")
    if issue_counts.get("flat scoring", 0) > 0:
        print("- Increase spread by scaling the strongest discriminating signal.")
    if issue_counts.get("low semantic relevance", 0) > 0:
        print("- Increase semantic weight modestly and validate query/event text quality.")


if __name__ == "__main__":
    main()
