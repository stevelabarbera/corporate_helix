#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from domain_candidates import CorporateEntity  # noqa: E402
from domain_discovery import discover_all_entity_seeds  # noqa: E402
from providers.web_search import SearchResult, parse_search_html, parse_bing_rss  # noqa: E402


def _entity(name: str, lei: str) -> CorporateEntity:
    return CorporateEntity(
        entity_name=name,
        entity_lei=lei,
        relationships=["ULTIMATE_ACCOUNTING_CHILD"],
        corporate_confidence="HIGH",
        jurisdiction="GB",
        source="GLEIF",
    )


def test_parse_duckduckgo_redirect_results() -> None:
    sample = """
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.example.com%2Flegal%2F&amp;rut=x">Example Legal</a>
    <a rel="nofollow" class="result__a" href="https://other.example.org/about">Other</a>
    """
    results = parse_search_html(sample, limit=5)
    assert len(results) == 2
    assert results[0].url == "https://www.example.com/legal/"
    assert results[0].title == "Example Legal"


def test_parse_bing_rss_results() -> None:
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item><title>Example Legal</title><link>https://www.example.com/legal/</link></item>
      <item><title>Other</title><link>https://other.example.org/about</link></item>
    </channel></rss>"""
    results = parse_bing_rss(rss, limit=5)
    assert len(results) == 2
    assert results[0].url == "https://www.example.com/legal/"
    assert results[0].title == "Example Legal"


def test_discover_all_queries_every_entity() -> None:
    entities = [_entity("ALPHA LIMITED", "LEI1"), _entity("BETA LIMITED", "LEI2")]
    calls: list[str] = []

    def fake_search(name: str, *, limit: int, timeout: int):
        calls.append(name)
        return f'"{name}" official website', [
            SearchResult(url=f"https://{name.split()[0].lower()}.example/legal", title=f"{name} Legal")
        ]

    seeds, errors = discover_all_entity_seeds(entities, search_fn=fake_search)
    assert calls == ["ALPHA LIMITED", "BETA LIMITED"]
    assert len(seeds) == 2
    assert not errors


def test_discover_all_dedupes_urls_per_entity() -> None:
    entities = [_entity("ALPHA LIMITED", "LEI1")]

    def fake_search(name: str, *, limit: int, timeout: int):
        result = SearchResult(url="https://alpha.example/legal", title="Alpha")
        return "q", [result, result]

    seeds, errors = discover_all_entity_seeds(entities, search_fn=fake_search)
    assert len(seeds) == 1
    assert not errors


def test_search_failure_does_not_abort_batch() -> None:
    entities = [_entity("ALPHA LIMITED", "LEI1"), _entity("BETA LIMITED", "LEI2")]

    def fake_search(name: str, *, limit: int, timeout: int):
        if name.startswith("ALPHA"):
            raise TimeoutError("simulated timeout")
        return "q", [SearchResult(url="https://beta.example/legal", title="Beta")]

    seeds, errors = discover_all_entity_seeds(entities, search_fn=fake_search)
    assert len(seeds) == 1
    assert seeds[0]["entity_lei"] == "LEI2"
    assert len(errors) == 1
    assert "TimeoutError" in errors[0]["error"]


def main() -> int:
    tests = [
        test_parse_duckduckgo_redirect_results,
        test_parse_bing_rss_results,
        test_discover_all_queries_every_entity,
        test_discover_all_dedupes_urls_per_entity,
        test_search_failure_does_not_abort_batch,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL {test.__name__}: {exc}")
    print(f"\n{passed} passed / {len(tests) - passed} failed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
