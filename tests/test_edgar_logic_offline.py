"""
Offline logic checks for the EDGAR fetcher — NO network required.

These exercise the pure, deterministic parts of the fetcher against synthetic
fixtures so the URL construction, CIK padding, ticker resolution, and
latest-10-K selection can be verified even when SEC hosts are unreachable.

Run:  python tests/test_edgar_logic_offline.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.edgar_fetcher import (  # noqa: E402
    EdgarFetcher,
    zero_pad_cik,
    ARCHIVES_DOC_URL,
)

# --- synthetic fixtures (shapes mirror the real SEC payloads) -----------------

FAKE_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    # Note the real KHC CIK is 1637459; used here only as a fixture, not hardcoded
    # into the fetcher itself.
    "1": {"cik_str": 1637459, "ticker": "KHC", "title": "Kraft Heinz Co"},
}

FAKE_SUBMISSIONS = {
    "name": "KRAFT HEINZ CO",
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001637459-25-000012",  # 10-K, newest
                "0001637459-24-000045",  # 10-Q
                "0001637459-24-000010",  # 10-K, older
            ],
            "form": ["10-K", "10-Q", "10-K"],
            "filingDate": ["2025-02-13", "2024-10-30", "2024-02-15"],
            "reportDate": ["2024-12-28", "2024-09-28", "2023-12-30"],
            "primaryDocument": ["khc-20241228.htm", "khc-q3.htm", "khc-20231230.htm"],
            "primaryDocDescription": ["10-K", "10-Q", "10-K"],
            "isXBRL": [1, 1, 1],
        }
    },
}


def _new_fetcher(tmp_out: Path) -> EdgarFetcher:
    # Construct without touching the network (no requests are made in __init__).
    return EdgarFetcher(out_dir=tmp_out, user_agent="Test Runner test@example.com")


def check(name: str, cond: bool) -> None:
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        raise AssertionError(name)


def main() -> int:
    tmp = Path("data/_test_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    f = _new_fetcher(tmp)

    print("zero_pad_cik:")
    check("pads int to 10 digits", zero_pad_cik(1637459) == "0001637459")
    check("pads str to 10 digits", zero_pad_cik("320193") == "0000320193")
    check("idempotent on padded", zero_pad_cik("0001637459") == "0001637459")

    print("resolve_cik (monkeypatched fetch):")
    f._get_json = lambda url: FAKE_TICKERS  # type: ignore[assignment]
    cik, name = f.resolve_cik("khc")  # lowercase on purpose
    check("resolves KHC cik", cik == 1637459)
    check("resolves company title", name == "Kraft Heinz Co")
    try:
        f.resolve_cik("ZZZZ")
        check("raises on unknown ticker", False)
    except Exception:
        check("raises on unknown ticker", True)

    print("find_latest_10k + URL construction:")
    filing = f.find_latest_10k(FAKE_SUBMISSIONS, cik=1637459)
    check("selects newest 10-K accession", filing.accession_number == "0001637459-25-000012")
    check("skips the 10-Q", filing.form == "10-K")
    check("filing date is newest", filing.filing_date == "2025-02-13")
    check("report date carried", filing.report_date == "2024-12-28")
    check("accession dashes stripped", filing.accession_nodash == "000163745925000012")

    expected_url = ARCHIVES_DOC_URL.format(
        cik_int=1637459,
        accession_nodash="000163745925000012",
        document="khc-20241228.htm",
    )
    check("primary doc URL is correct", filing.primary_document_url == expected_url)
    check(
        "URL uses integer CIK (no leading zeros)",
        "/data/1637459/" in filing.primary_document_url,
    )

    print("\nAll offline logic checks passed.")
    print("Sample constructed primary-document URL:")
    print("  " + filing.primary_document_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
