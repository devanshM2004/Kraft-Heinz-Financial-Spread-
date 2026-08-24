#!/usr/bin/env python3
"""
Phase 0 runner — data acquisition only.

Fetches, for a ticker (default KHC):
  1. The latest 10-K primary document (HTML) from SEC EDGAR.
  2. The XBRL companyfacts JSON (used later as ground truth).

Saves the raw files under data/raw/ and prints the Phase 0 summary.

  NOTE: This calls NO Anthropic API. It only touches SEC EDGAR.

Usage:
    python run_phase0.py               # defaults to KHC
    python run_phase0.py --ticker KHC
    SEC_USER_AGENT="Your Name you@example.com" python run_phase0.py

If you see an "Access denied (403)" error, the SEC hosts are being blocked
upstream (e.g. by an egress proxy/network policy). Allow www.sec.gov and
data.sec.gov, then re-run.
"""

import argparse
import sys

from src.edgar_fetcher import EdgarFetcher, SecFetchError


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0: SEC EDGAR acquisition")
    parser.add_argument("--ticker", default="KHC", help="Ticker symbol (default: KHC)")
    parser.add_argument("--out-dir", default="data/raw", help="Output directory")
    parser.add_argument(
        "--user-agent",
        default=None,
        help='Override SEC User-Agent, e.g. "Your Name you@example.com"',
    )
    args = parser.parse_args()

    fetcher = EdgarFetcher(out_dir=args.out_dir, user_agent=args.user_agent)
    print(f"[phase0] SEC User-Agent: {fetcher.user_agent}")
    if fetcher.using_placeholder:
        print(
            "[phase0] WARNING: SEC_USER_AGENT is not set, using a placeholder.\n"
            "         SEC asks for a descriptive User-Agent with a real contact\n"
            "         and may throttle or deny placeholder requests. Set it before\n"
            "         making live SEC requests:\n"
            '           macOS/Linux : SEC_USER_AGENT=\"Your Name your.email@example.com\" python run_phase0.py\n'
            '           Windows PS  : $env:SEC_USER_AGENT=\"Your Name your.email@example.com\"; python run_phase0.py\n',
            file=sys.stderr,
        )
    print(f"[phase0] Acquiring filings for {args.ticker.upper()} ...\n")

    try:
        result = fetcher.acquire(args.ticker)
    except SecFetchError as exc:
        print(f"[phase0] ERROR: {exc}", file=sys.stderr)
        return 2

    s = result.as_summary()
    print("=" * 68)
    print("PHASE 0 SUMMARY")
    print("=" * 68)
    print(f"  ticker                 : {s['ticker']}")
    print(f"  company name           : {s['company_name']}")
    print(f"  CIK                    : {s['cik']}  (padded: {s['cik10']})")
    print(f"  latest 10-K accession  : {s['latest_10k_accession']}")
    print(f"  filing date            : {s['latest_10k_filing_date']}")
    print(f"  report (period) date   : {s['latest_10k_report_date']}")
    print(f"  primary document URL   : {s['primary_document_url']}")
    print(f"  companyfacts file path : {s['companyfacts_file_path']}")
    print(f"  10-K file path         : {s['tenk_file_path']}")
    print("-" * 68)
    print("  saved bytes:")
    for name, size in s["saved_bytes"].items():
        print(f"    {name:24s}: {size:,} bytes")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
