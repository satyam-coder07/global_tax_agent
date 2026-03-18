from __future__ import annotations

from typing import Dict, List, Optional


TREATY_TABLE: List[Dict] = [
    {
        "country_a": "india",
        "country_b": "us",
        "income_type": "salary",
        "source_wht_rate": 0.0,
        "residence_credit": True,
        "net_rate": "Taxed in residence country (US/India). DTAA Article 16.",
        "article": "Article 16 — Dependent Personal Services",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/USA.pdf",
    },
    {
        "country_a": "india",
        "country_b": "us",
        "income_type": "dividend",
        "source_wht_rate": 0.15,
        "residence_credit": True,
        "net_rate": "15% WHT in source country. Credit available in residence country.",
        "article": "Article 11 — Dividends",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/USA.pdf",
    },
    {
        "country_a": "india",
        "country_b": "us",
        "income_type": "interest",
        "source_wht_rate": 0.10,
        "residence_credit": True,
        "net_rate": "10% WHT in source country. Full credit in residence country.",
        "article": "Article 12 — Interest",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/USA.pdf",
    },
    {
        "country_a": "india",
        "country_b": "us",
        "income_type": "royalty",
        "source_wht_rate": 0.15,
        "residence_credit": True,
        "net_rate": "15% WHT on royalties. FTC available in residence country.",
        "article": "Article 13 — Royalties and Fees for Technical Services",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/USA.pdf",
    },
    {
        "country_a": "india",
        "country_b": "uk",
        "income_type": "salary",
        "source_wht_rate": 0.0,
        "residence_credit": True,
        "net_rate": "Taxed only in state of residence. India-UK DTAA Article 15.",
        "article": "Article 15 — Dependent Personal Services",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/UK.pdf",
    },
    {
        "country_a": "india",
        "country_b": "uk",
        "income_type": "dividend",
        "source_wht_rate": 0.15,
        "residence_credit": True,
        "net_rate": "15% WHT in source country. Credit in residence country.",
        "article": "Article 11 — Dividends",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/UK.pdf",
    },
    {
        "country_a": "india",
        "country_b": "uk",
        "income_type": "interest",
        "source_wht_rate": 0.10,
        "residence_credit": True,
        "net_rate": "10% WHT at source. Full credit in UK/India.",
        "article": "Article 12 — Interest",
        "source_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/UK.pdf",
    },
    {
        "country_a": "us",
        "country_b": "uk",
        "income_type": "salary",
        "source_wht_rate": 0.0,
        "residence_credit": True,
        "net_rate": "Taxed in country of residence. US-UK Treaty Article 14.",
        "article": "Article 14 — Income from Employment",
        "source_url": "https://www.irs.gov/pub/irs-trty/uk.pdf",
    },
    {
        "country_a": "us",
        "country_b": "uk",
        "income_type": "dividend",
        "source_wht_rate": 0.15,
        "residence_credit": True,
        "net_rate": "15% WHT (5% if holding >10%). FTC available.",
        "article": "Article 10 — Dividends",
        "source_url": "https://www.irs.gov/pub/irs-trty/uk.pdf",
    },
    {
        "country_a": "us",
        "country_b": "uk",
        "income_type": "interest",
        "source_wht_rate": 0.0,
        "residence_credit": False,
        "net_rate": "0% WHT on interest under US-UK treaty. Taxed only at residence.",
        "article": "Article 11 — Interest",
        "source_url": "https://www.irs.gov/pub/irs-trty/uk.pdf",
    },
]

SUPPORTED_PAIRS: List[Dict] = [
    {"pair": "India — US",  "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/USA.pdf"},
    {"pair": "India — UK",  "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/UK.pdf"},
    {"pair": "India — UAE", "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/UAE.pdf"},
    {"pair": "India — Singapore", "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/Singapore.pdf"},
    {"pair": "India — Germany", "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/Germany.pdf"},
    {"pair": "India — Canada", "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/Canada.pdf"},
    {"pair": "India — Australia", "treaty_url": "https://www.incometax.gov.in/iec/foportal/sites/default/files/2023-06/Australia.pdf"},
    {"pair": "US — UK",    "treaty_url": "https://www.irs.gov/pub/irs-trty/uk.pdf"},
    {"pair": "US — Canada", "treaty_url": "https://www.irs.gov/pub/irs-trty/canada.pdf"},
    {"pair": "US — Germany", "treaty_url": "https://www.irs.gov/pub/irs-trty/germany.pdf"},
]

INCOME_TYPES = ["salary", "dividend", "interest", "royalty", "capital_gains", "pension", "business"]


def check_treaty(country_a: str, country_b: str, income_type: str) -> Optional[Dict]:
    ca = country_a.lower()
    cb = country_b.lower()
    it = income_type.lower()

    for row in TREATY_TABLE:
        if (
            (row["country_a"] == ca and row["country_b"] == cb) or
            (row["country_a"] == cb and row["country_b"] == ca)
        ) and row["income_type"] == it:
            return row

    return None


def get_all_pairs() -> List[Dict]:
    return SUPPORTED_PAIRS


def summarize_treaty_exposure(
    incomes: List[Dict],
) -> List[Dict]:
    results = []
    for item in incomes:
        ca = item.get("source_country", "").lower()
        cb = item.get("residence_country", "").lower()
        it = item.get("income_type", "").lower()
        amount = item.get("amount", 0.0)

        treaty = check_treaty(ca, cb, it)
        wht = 0.0
        detail = "No specific treaty found. Standard domestic rates may apply."
        source_url = ""

        if treaty:
            wht = treaty["source_wht_rate"]
            detail = treaty["net_rate"]
            source_url = treaty["source_url"]

        results.append({
            "source_country": ca,
            "residence_country": cb,
            "income_type": it,
            "amount": amount,
            "wht_rate": wht,
            "wht_amount": round(amount * wht, 2),
            "detail": detail,
            "source_url": source_url,
            "has_treaty": treaty is not None,
        })

    return results
