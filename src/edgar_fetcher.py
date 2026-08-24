"""
SEC EDGAR fetcher — Phase 0 (data acquisition only).

Responsibilities (and nothing beyond them):
  1. Resolve a company's CIK from its ticker using the public SEC ticker file.
     The CIK is NEVER hardcoded — it is looked up every time.
  2. Fetch the company's submissions metadata (SEC submissions API).
  3. Find the most recent 10-K and build the URL to its primary document.
  4. Fetch the primary 10-K document (HTML) and the XBRL companyfacts JSON.
  5. Save every raw artifact to disk and return a structured summary.

This module deliberately does NOT touch the Anthropic API, schema design,
extraction, ratios, or Excel. Those belong to later phases.

------------------------------------------------------------------------------
User-Agent
------------------------------------------------------------------------------
SEC requires a descriptive User-Agent identifying the requester on EVERY
request, e.g. "Your Name your.email@example.com".

The User-Agent is read from the SEC_USER_AGENT environment variable. If it is
not set, a safe placeholder is used and the fetcher warns you to set a real
contact before making live SEC requests (SEC may throttle/deny requests that
carry the placeholder).

  >>> SET YOUR CONTACT before running live requests:
      export SEC_USER_AGENT="Your Name your.email@example.com"   # macOS/Linux
      $env:SEC_USER_AGENT="Your Name your.email@example.com"     # Windows PS

------------------------------------------------------------------------------
Rate limiting
------------------------------------------------------------------------------
SEC asks clients to stay under ~10 requests/second. We enforce a minimum
interval between requests (default 0.15s -> ~6.7 req/s) which is safely below
the limit even before accounting for network latency.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional

import requests


# --- User-Agent ---------------------------------------------------------------
# Safe placeholder used ONLY when SEC_USER_AGENT is not set. No real personal
# contact is committed to the repo — set SEC_USER_AGENT to your own before
# making live SEC requests.
PLACEHOLDER_USER_AGENT = "Your Name your.email@example.com"
SEC_USER_AGENT_ENV = "SEC_USER_AGENT"

# --- SEC endpoints ------------------------------------------------------------
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
# Primary document lives under the archives tree. The CIK segment here is the
# *integer* CIK (no leading zeros); the accession number has its dashes removed.
ARCHIVES_DOC_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{document}"
)

# --- Rate limiting ------------------------------------------------------------
MIN_REQUEST_INTERVAL_S = 0.15  # ~6.7 req/s, safely below SEC's ~10 req/s ceiling

# --- Retry policy (network / transient errors only — NOT policy denials) ------
MAX_RETRIES = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SecFetchError(RuntimeError):
    """Raised when a SEC resource cannot be retrieved."""


def zero_pad_cik(cik: int | str) -> str:
    """Return the CIK zero-padded to 10 digits (as SEC APIs require)."""
    return str(int(cik)).zfill(10)


@dataclass
class FilingRef:
    """A single filing's identifying metadata, pulled from submissions.recent."""
    form: str
    accession_number: str            # with dashes, e.g. 0000123456-24-000012
    accession_nodash: str            # without dashes, e.g. 000012345624000012
    filing_date: str
    report_date: str
    primary_document: str
    primary_doc_description: str
    is_xbrl: bool
    primary_document_url: str


@dataclass
class Phase0Result:
    """Everything Phase 0 produces, ready to print/serialize as a summary."""
    ticker: str
    company_name: str
    cik: int
    cik10: str
    latest_10k_accession: str
    latest_10k_filing_date: str
    latest_10k_report_date: str
    primary_document_url: str
    tenk_file_path: str
    companyfacts_file_path: str
    submissions_file_path: str
    tickers_file_path: str
    saved_bytes: dict[str, int] = field(default_factory=dict)

    def as_summary(self) -> dict[str, Any]:
        return asdict(self)


class EdgarFetcher:
    """
    A minimal, rate-limited SEC EDGAR client for Phase 0 acquisition.

    Usage:
        fetcher = EdgarFetcher(out_dir="data/raw")
        result = fetcher.acquire("KHC")
        print(json.dumps(result.as_summary(), indent=2))
    """

    def __init__(
        self,
        out_dir: str | os.PathLike = "data/raw",
        user_agent: Optional[str] = None,
        min_interval_s: float = MIN_REQUEST_INTERVAL_S,
        timeout_s: float = 30.0,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # Resolve the User-Agent: explicit arg > SEC_USER_AGENT env var >
        # safe placeholder. `using_placeholder` lets callers warn the user
        # before they make live SEC requests with a non-descriptive UA.
        resolved = user_agent or os.environ.get(SEC_USER_AGENT_ENV)
        self.using_placeholder = not bool(resolved)
        self.user_agent = resolved or PLACEHOLDER_USER_AGENT

        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s

        self._session = requests.Session()
        self._session.headers.update(
            {
                # SEC requires a descriptive User-Agent on EVERY request.
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._last_request_ts = 0.0
        self._rate_lock = threading.Lock()

    # -- low-level HTTP --------------------------------------------------------
    def _throttle(self) -> None:
        """Block until at least min_interval_s has elapsed since last request."""
        with self._rate_lock:
            now = time.monotonic()
            wait = self.min_interval_s - (now - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.monotonic()

    def _get(self, url: str) -> requests.Response:
        """
        GET a URL with rate limiting and bounded exponential-backoff retries.

        Retries only transient failures (network errors, 429, 5xx). A 403/407
        is treated as a hard policy denial and raised immediately — never
        retried or routed around.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            try:
                resp = self._session.get(url, timeout=self.timeout_s)
            except requests.exceptions.ProxyError as exc:
                # A proxy CONNECT denial (e.g. "Tunnel connection failed: 403")
                # is a policy block, not a transient error — fail fast, no retry.
                msg = str(exc)
                if "403" in msg or "407" in msg or "Forbidden" in msg:
                    raise SecFetchError(
                        f"Access to {url} was denied by an egress proxy "
                        f"(policy block): {msg}. Allow the SEC hosts "
                        "(www.sec.gov, data.sec.gov) and re-run."
                    ) from exc
                last_exc = exc
                self._sleep_backoff(attempt)
                continue
            except requests.RequestException as exc:
                last_exc = exc
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                return resp
            if resp.status_code in (403, 407):
                raise SecFetchError(
                    f"Access denied ({resp.status_code}) for {url}. "
                    "This is a policy/authorization denial — not retried. "
                    "If running behind an egress proxy, the host may be blocked."
                )
            if resp.status_code in RETRYABLE_STATUS:
                last_exc = SecFetchError(
                    f"Transient {resp.status_code} for {url}"
                )
                self._sleep_backoff(attempt)
                continue
            raise SecFetchError(
                f"Unexpected HTTP {resp.status_code} for {url}: {resp.text[:200]}"
            )

        raise SecFetchError(
            f"Failed to GET {url} after {MAX_RETRIES + 1} attempts: {last_exc}"
        )

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        # 2s, 4s, 8s, 16s
        time.sleep(2 ** (attempt + 1))

    def _get_json(self, url: str) -> Any:
        return self._get(url).json()

    # -- steps -----------------------------------------------------------------
    def resolve_cik(self, ticker: str) -> tuple[int, str]:
        """
        Resolve (cik, company_name) from a ticker using the SEC ticker file.

        The ticker file is a JSON object keyed by row index, each value having
        {"cik_str": int, "ticker": str, "title": str}. Never hardcode the CIK.
        Also saves the raw ticker file for provenance.
        """
        data = self._get_json(TICKERS_URL)
        self._save_json("company_tickers.json", data)

        target = ticker.strip().upper()
        for row in data.values():
            if str(row.get("ticker", "")).upper() == target:
                return int(row["cik_str"]), str(row.get("title", "")).strip()

        raise SecFetchError(
            f"Ticker {target!r} not found in SEC company_tickers.json "
            f"({len(data)} tickers scanned)."
        )

    def fetch_submissions(self, cik10: str) -> dict[str, Any]:
        """Fetch and persist the submissions metadata JSON for a CIK."""
        url = SUBMISSIONS_URL.format(cik10=cik10)
        data = self._get_json(url)
        self._save_json(f"submissions_CIK{cik10}.json", data)
        return data

    def find_latest_10k(self, submissions: dict[str, Any], cik: int) -> FilingRef:
        """
        Locate the most recent 10-K in submissions.recent and build its URL.

        submissions.recent stores parallel arrays; index i describes one filing.
        We pick the newest filing whose form is exactly "10-K", ordered by
        filingDate (SEC lists most-recent first, but we sort defensively).
        """
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        if not forms:
            raise SecFetchError("submissions.filings.recent contains no filings.")

        candidates: list[tuple[str, int]] = [
            (recent["filingDate"][i], i)
            for i, form in enumerate(forms)
            if form == "10-K"
        ]
        if not candidates:
            raise SecFetchError(
                "No 10-K found in the recent submissions window. "
                "(Older filings may live in submissions.files — not needed here.)"
            )
        # Newest by filing date.
        _, idx = max(candidates, key=lambda t: t[0])

        accession = recent["accessionNumber"][idx]
        accession_nodash = accession.replace("-", "")
        document = recent["primaryDocument"][idx]
        doc_url = ARCHIVES_DOC_URL.format(
            cik_int=int(cik), accession_nodash=accession_nodash, document=document
        )
        return FilingRef(
            form=recent["form"][idx],
            accession_number=accession,
            accession_nodash=accession_nodash,
            filing_date=recent["filingDate"][idx],
            report_date=recent.get("reportDate", [""] * (idx + 1))[idx],
            primary_document=document,
            primary_doc_description=recent.get(
                "primaryDocDescription", [""] * (idx + 1)
            )[idx],
            is_xbrl=bool(recent.get("isXBRL", [0] * (idx + 1))[idx]),
            primary_document_url=doc_url,
        )

    def fetch_primary_document(self, filing: FilingRef) -> tuple[str, int]:
        """Download the 10-K primary document (HTML) and save it. Returns (path, bytes)."""
        resp = self._get(filing.primary_document_url)
        fname = f"10K_{filing.accession_nodash}_{filing.primary_document}"
        # Keep just the basename in case primary_document carries a path.
        fname = fname.replace("/", "_")
        path = self.out_dir / fname
        path.write_bytes(resp.content)
        return str(path), len(resp.content)

    def fetch_companyfacts(self, cik10: str) -> tuple[str, int]:
        """Download the XBRL companyfacts JSON (ground truth) and save it."""
        url = COMPANYFACTS_URL.format(cik10=cik10)
        resp = self._get(url)
        path = self.out_dir / f"companyfacts_CIK{cik10}.json"
        path.write_bytes(resp.content)
        return str(path), len(resp.content)

    # -- orchestration ---------------------------------------------------------
    def acquire(self, ticker: str) -> Phase0Result:
        """Run the full Phase 0 acquisition for a ticker and return a summary."""
        cik, company_name = self.resolve_cik(ticker)
        cik10 = zero_pad_cik(cik)

        submissions = self.fetch_submissions(cik10)
        # Prefer the human-readable name from submissions if present.
        company_name = submissions.get("name", company_name) or company_name

        filing = self.find_latest_10k(submissions, cik)

        tenk_path, tenk_bytes = self.fetch_primary_document(filing)
        facts_path, facts_bytes = self.fetch_companyfacts(cik10)

        return Phase0Result(
            ticker=ticker.upper(),
            company_name=company_name,
            cik=cik,
            cik10=cik10,
            latest_10k_accession=filing.accession_number,
            latest_10k_filing_date=filing.filing_date,
            latest_10k_report_date=filing.report_date,
            primary_document_url=filing.primary_document_url,
            tenk_file_path=tenk_path,
            companyfacts_file_path=facts_path,
            submissions_file_path=str(self.out_dir / f"submissions_CIK{cik10}.json"),
            tickers_file_path=str(self.out_dir / "company_tickers.json"),
            saved_bytes={
                "company_tickers.json": (self.out_dir / "company_tickers.json").stat().st_size,
                "submissions.json": (self.out_dir / f"submissions_CIK{cik10}.json").stat().st_size,
                "10k_primary_document": tenk_bytes,
                "companyfacts.json": facts_bytes,
            },
        )

    # -- helpers ---------------------------------------------------------------
    def _save_json(self, filename: str, data: Any) -> Path:
        path = self.out_dir / filename
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path
