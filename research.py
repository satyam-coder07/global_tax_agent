from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

try:
    from exa_py import Exa
    EXA_AVAILABLE = True
except ImportError:
    EXA_AVAILABLE = False


WHITELISTED_DOMAINS: Dict[str, List[str]] = {
    "india": [
        "incometax.gov.in",
        "gst.gov.in",
        "finmin.nic.in",
        "cbic.gov.in",
        "cbdt.gov.in",
        "egazette.gov.in",
        "mca.gov.in",
        "sebi.gov.in",
        "rbi.org.in",
        "indiabudget.gov.in",
    ],
    "us": [
        "irs.gov",
        "treasury.gov",
        "congress.gov",
        "federalregister.gov",
        "ssa.gov",
        "dol.gov",
    ],
    "uk": [
        "gov.uk",
        "hmrc.gov.uk",
        "legislation.gov.uk",
        "parliament.uk",
        "bankofengland.co.uk",
    ],
}

BILL_KEYWORDS = [
    "bill", "draft", "proposed", "amendment", "introduced",
    "first reading", "second reading", "committee stage", "consultation",
]

ACT_KEYWORDS = [
    "gazette", "enacted", "passed", "act", "circular", "notification",
    "finance act", "cbdt notification", "cbic notification", "rcm", "press release",
]

STATIC_NOTIFICATIONS: Dict[str, List[Dict]] = {
    "india": [
        {
            "title": "CBDT Notification: New Tax Regime is Default for AY 2025-26",
            "date": "2025-04-01",
            "status": "PASSED_ACT",
            "url": "https://incometax.gov.in/iec/foportal/help/individual/return-applicable-1#taxslabs",
            "summary": "The New Tax Regime under Section 115BAC is the default regime from AY 2025-26. Taxpayers must opt-out explicitly to use the Old Regime.",
        },
        {
            "title": "Budget 2025: 87A Rebate Enhanced to Rs 60,000 under New Regime",
            "date": "2025-02-01",
            "status": "PASSED_ACT",
            "url": "https://indiabudget.gov.in",
            "summary": "Income up to Rs 12 lakh is effectively tax-free under the New Regime due to enhanced 87A rebate of Rs 60,000.",
        },
        {
            "title": "Budget 2025: Standard Deduction Raised to Rs 75,000 (New Regime)",
            "date": "2025-02-01",
            "status": "PASSED_ACT",
            "url": "https://indiabudget.gov.in",
            "summary": "Standard deduction for salaried individuals increased from Rs 50,000 to Rs 75,000 under the New Regime.",
        },
        {
            "title": "Budget 2025: New Income Tax Bill 2025 Introduced in Lok Sabha",
            "date": "2025-02-13",
            "status": "PROPOSED_BILL",
            "url": "https://egazette.gov.in",
            "summary": "The new Income Tax Bill 2025 was introduced to replace the 60-year-old ITA 1961. Expected to be effective from April 2026.",
        },
    ],
    "us": [
        {
            "title": "IRS: 2025 Tax Year Inflation Adjustments Released",
            "date": "2024-11-01",
            "status": "PASSED_ACT",
            "url": "https://www.irs.gov/newsroom/irs-provides-tax-inflation-adjustments-for-tax-year-2025",
            "summary": "Standard deduction for single filers rises to $15,000. MFJ increases to $30,000 for tax year 2025.",
        },
        {
            "title": "IRS: 401(k) Contribution Limit Increased to $23,500 for 2025",
            "date": "2024-11-01",
            "status": "PASSED_ACT",
            "url": "https://www.irs.gov/newsroom/401k-contribution-limit-increases",
            "summary": "The elective deferral limit for 401(k), 403(b), and most 457 plans increases to $23,500.",
        },
        {
            "title": "TCJA Expiry: Key Provisions Set to Expire in 2025",
            "date": "2024-12-01",
            "status": "PROPOSED_BILL",
            "url": "https://www.congress.gov",
            "summary": "Several Tax Cuts and Jobs Act provisions are scheduled to sunset after 2025. Congress is evaluating extensions.",
        },
    ],
    "uk": [
        {
            "title": "HMRC: 2025-26 Income Tax Rates and Allowances Published",
            "date": "2025-04-06",
            "status": "PASSED_ACT",
            "url": "https://www.gov.uk/income-tax-rates",
            "summary": "Personal Allowance remains at £12,570. Basic Rate limit £50,270. Higher Rate threshold frozen until April 2028.",
        },
        {
            "title": "National Insurance: Employee Rate Confirmed at 8% for 2025-26",
            "date": "2025-04-06",
            "status": "PASSED_ACT",
            "url": "https://www.gov.uk/national-insurance-rates-letters",
            "summary": "Class 1 primary NIC rate for employees remains at 8% between the Primary Threshold and Upper Earnings Limit.",
        },
        {
            "title": "Autumn Budget 2024: Employer NIC Rate Raised to 13.8% from April 2025",
            "date": "2024-10-30",
            "status": "PASSED_ACT",
            "url": "https://www.gov.uk/government/publications/autumn-budget-2024",
            "summary": "Employer Class 1 Secondary NICs raised to 13.8%. Secondary threshold lowered to £5,000.",
        },
    ],
}


def _classify_status(title: str, snippet: str) -> str:
    combined = (title + " " + snippet).lower()
    bill_score = sum(1 for kw in BILL_KEYWORDS if kw in combined)
    act_score = sum(1 for kw in ACT_KEYWORDS if kw in combined)
    return "PROPOSED_BILL" if bill_score > act_score else "PASSED_ACT"


def _fetch_exa_notifications(country: str, exa_api_key: str, hours: int = 48) -> List[Dict]:
    if not EXA_AVAILABLE or not exa_api_key:
        return []

    domains = WHITELISTED_DOMAINS.get(country, [])
    if not domains:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query_map = {
        "india": "income tax notification circular CBDT CBIC GST 2025",
        "us": "IRS tax update notice 2025 tax relief inflation adjustment",
        "uk": "HMRC income tax national insurance 2025 rates allowances",
    }
    query = query_map.get(country, "tax update 2025")

    try:
        exa = Exa(api_key=exa_api_key)
        results = exa.search_and_contents(
            query,
            num_results=8,
            include_domains=domains,
            start_published_date=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            type="auto",
            text={"max_characters": 500},
        )

        notifications = []
        for r in results.results:
            status = _classify_status(r.title or "", r.text or "")
            notifications.append({
                "title": r.title or "Untitled",
                "date": r.published_date or "",
                "status": status,
                "url": r.url,
                "summary": (r.text or "")[:300].strip(),
            })
        return notifications

    except Exception:
        return []


def get_latest_notifications(country: str, exa_api_key: Optional[str] = None, hours: int = 48) -> List[Dict]:
    country = country.lower()

    if exa_api_key:
        live = _fetch_exa_notifications(country, exa_api_key, hours)
        if live:
            return live

    return STATIC_NOTIFICATIONS.get(country, [])


def scout_gov_source(country: str, query: str, exa_api_key: Optional[str] = None) -> List[Dict]:
    country = country.lower()
    domains = WHITELISTED_DOMAINS.get(country, [])

    if not exa_api_key or not EXA_AVAILABLE:
        return _fallback_scrape(country, query, domains)

    try:
        exa = Exa(api_key=exa_api_key)
        results = exa.search_and_contents(
            query,
            num_results=5,
            include_domains=domains,
            type="auto",
            text={"max_characters": 800},
        )
        output = []
        for r in results.results:
            status = _classify_status(r.title or "", r.text or "")
            output.append({
                "title": r.title or "Untitled",
                "url": r.url,
                "status": status,
                "snippet": (r.text or "")[:500].strip(),
                "source_domain": re.sub(r"https?://(www\.)?", "", r.url).split("/")[0],
            })
        return output
    except Exception:
        return _fallback_scrape(country, query, domains)


def _fallback_scrape(country: str, query: str, domains: List[str]) -> List[Dict]:
    results = []
    primary_domain = domains[0] if domains else ""
    if not primary_domain:
        return results

    search_url = f"https://www.google.com/search?q=site:{primary_domain}+{requests.utils.quote(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TaxHubBot/1.0)"}

    try:
        resp = requests.get(search_url, headers=headers, timeout=8)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for g in soup.select("div.g")[:5]:
            link_tag = g.find("a")
            title_tag = g.find("h3")
            snippet_tag = g.find("div", class_=re.compile(r"VwiC3b|IsZvec"))
            if not link_tag or not title_tag:
                continue
            url = link_tag.get("href", "")
            title = title_tag.get_text(strip=True)
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            status = _classify_status(title, snippet)
            results.append({
                "title": title,
                "url": url,
                "status": status,
                "snippet": snippet[:400],
                "source_domain": primary_domain,
            })
    except Exception:
        pass

    return results
