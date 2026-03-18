from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, field_validator


TAX_LAWS_DIR = Path(__file__).parent / "tax_laws"

COUNTRY_FILE_MAP: Dict[str, str] = {
    "india": "india.json",
    "us": "us.json",
    "uk": "uk.json",
}


class TaxProfile(BaseModel):
    country: str
    gross_income: float
    age: int
    filing_status: str
    regime: Optional[str] = None
    deductions_claimed: Dict[str, float] = {}
    has_hra: bool = False
    hra_received: float = 0.0
    rent_paid: float = 0.0
    is_metro: bool = False
    num_children: int = 0
    has_home_loan: bool = False

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.lower()
        if v not in COUNTRY_FILE_MAP:
            raise ValueError(f"Unsupported country '{v}'. Must be one of: {list(COUNTRY_FILE_MAP.keys())}")
        return v

    @field_validator("gross_income")
    @classmethod
    def validate_income(cls, v: float) -> float:
        if v < 0:
            raise ValueError("gross_income must be non-negative")
        return v


class TaxBracketResult(BaseModel):
    band: str
    income_in_band: float
    rate: float
    tax: float


class RegimeResult(BaseModel):
    regime: str
    taxable_income: float
    total_deductions: float
    bracket_breakdown: List[TaxBracketResult]
    base_tax: float
    surcharge: float
    cess_or_nic: float
    rebate: float
    total_tax: float
    effective_rate: float
    take_home: float


class OptimizationRecommendation(BaseModel):
    deduction_id: str
    label: str
    current_claimed: float
    max_allowed: float
    additional_room: float
    tax_saving: float
    source_url: str


class OptimizationReport(BaseModel):
    best_regime: str
    best_regime_tax: float
    worst_regime_tax: float
    money_left_on_table: float
    recommendations: List[OptimizationRecommendation]
    total_recoverable_tax: float


class ScenarioComparison(BaseModel):
    scenarios: Dict[str, RegimeResult]
    best_scenario: str


def _load_tax_law(country: str) -> Dict[str, Any]:
    file_path = TAX_LAWS_DIR / COUNTRY_FILE_MAP[country]
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _apply_brackets(taxable_income: float, brackets: List[Dict]) -> Tuple[float, List[TaxBracketResult]]:
    total_tax = 0.0
    breakdown: List[TaxBracketResult] = []
    for i, bracket in enumerate(brackets):
        low = bracket["min"]
        high = bracket["max"] if bracket["max"] is not None else float("inf")
        rate = bracket["rate"]
        band_label = bracket.get("band", f"Band {i+1}")

        if taxable_income <= low:
            break

        income_in_band = min(taxable_income, high) - low
        if income_in_band <= 0:
            continue

        tax_in_band = income_in_band * rate
        total_tax += tax_in_band

        breakdown.append(TaxBracketResult(
            band=band_label,
            income_in_band=income_in_band,
            rate=rate,
            tax=tax_in_band,
        ))

    return total_tax, breakdown


def _compute_surcharge_india(base_tax: float, taxable_income: float, surcharges: List[Dict]) -> float:
    applicable_rate = 0.0
    for band in surcharges:
        low = band["income_above"]
        high = band["income_upto"] if band["income_upto"] is not None else float("inf")
        if taxable_income > low and taxable_income <= high:
            applicable_rate = band["rate"]
            break
        if taxable_income > low and band["income_upto"] is None:
            applicable_rate = band["rate"]
    return base_tax * applicable_rate


def _apply_india_rebate(base_tax: float, surcharge: float, taxable_income: float, regime: str, rebates: List[Dict]) -> float:
    for rebate in rebates:
        if rebate.get("applicable_regime") == regime:
            if taxable_income <= rebate["income_limit"]:
                return min(rebate["rebate_amount"], base_tax + surcharge)
    return 0.0


def _compute_india_deductions(profile: TaxProfile, tax_law: Dict, regime: str) -> float:
    deductions = tax_law.get("deductions", {})
    std_ded = tax_law["standard_deduction"].get(regime, 0)
    total = std_ded

    for ded_id, ded_info in deductions.items():
        if regime not in ded_info.get("regimes", []):
            continue
        claimed = profile.deductions_claimed.get(ded_id, 0.0)
        limit = ded_info.get("limit")
        if limit is not None:
            total += min(claimed, limit)
        else:
            total += claimed

    if regime == "old" and profile.has_hra:
        basic_salary = profile.gross_income * 0.5
        hra_exempt = min(
            profile.hra_received,
            profile.rent_paid - 0.1 * basic_salary,
            0.5 * basic_salary if profile.is_metro else 0.4 * basic_salary,
        )
        total += max(0.0, hra_exempt)

    return min(total, profile.gross_income)


def _calculate_india(profile: TaxProfile, tax_law: Dict, regime: str) -> RegimeResult:
    total_deductions = _compute_india_deductions(profile, tax_law, regime)
    taxable_income = max(0.0, profile.gross_income - total_deductions)

    age_key = "individual"
    if regime == "old":
        if profile.age >= 80:
            age_key = "individual_above_80"
        elif profile.age >= 60:
            age_key = "individual_60_to_80"
        else:
            age_key = "individual_below_60"

    brackets = tax_law["brackets"][regime][age_key]
    base_tax, breakdown = _apply_brackets(taxable_income, brackets)

    surcharge = _compute_surcharge_india(base_tax, taxable_income, tax_law.get("surcharges", []))
    rebate = _apply_india_rebate(base_tax, surcharge, taxable_income, regime, tax_law.get("rebates", []))
    tax_after_rebate = max(0.0, base_tax + surcharge - rebate)
    cess = round(tax_after_rebate * tax_law.get("cess", 0.04), 2)
    total_tax = round(tax_after_rebate + cess, 2)
    effective_rate = (total_tax / profile.gross_income * 100) if profile.gross_income > 0 else 0.0

    return RegimeResult(
        regime=regime,
        taxable_income=taxable_income,
        total_deductions=total_deductions,
        bracket_breakdown=breakdown,
        base_tax=round(base_tax, 2),
        surcharge=round(surcharge, 2),
        cess_or_nic=cess,
        rebate=round(rebate, 2),
        total_tax=total_tax,
        effective_rate=round(effective_rate, 2),
        take_home=round(profile.gross_income - total_tax, 2),
    )


def _compute_us_deductions(profile: TaxProfile, tax_law: Dict) -> float:
    std_ded_map = tax_law.get("standard_deduction", {})
    std_ded = std_ded_map.get(profile.filing_status, 15000)

    itemized = 0.0
    deductions = tax_law.get("deductions", {})
    for ded_id, ded_info in deductions.items():
        claimed = profile.deductions_claimed.get(ded_id, 0.0)
        limit = ded_info.get("limit")
        if limit is not None:
            itemized += min(claimed, limit)
        else:
            itemized += claimed

    return max(std_ded, itemized)


def _calculate_us(profile: TaxProfile, tax_law: Dict) -> RegimeResult:
    total_deductions = _compute_us_deductions(profile, tax_law)
    taxable_income = max(0.0, profile.gross_income - total_deductions)

    brackets = tax_law["brackets"]["federal"].get(profile.filing_status, tax_law["brackets"]["federal"]["single"])
    base_tax, breakdown = _apply_brackets(taxable_income, brackets)

    ss_info = tax_law.get("social_security", {})
    ss_wage = min(profile.gross_income, ss_info.get("wage_base", 176100))
    fica = ss_wage * ss_info.get("employee_rate", 0.062) + profile.gross_income * ss_info.get("medicare_rate", 0.0145)
    add_medicare_threshold = ss_info.get("additional_medicare_threshold_single", 200000)
    if profile.gross_income > add_medicare_threshold:
        fica += (profile.gross_income - add_medicare_threshold) * ss_info.get("additional_medicare_rate", 0.009)

    total_tax = round(base_tax + fica, 2)
    effective_rate = (total_tax / profile.gross_income * 100) if profile.gross_income > 0 else 0.0

    return RegimeResult(
        regime="federal",
        taxable_income=taxable_income,
        total_deductions=total_deductions,
        bracket_breakdown=breakdown,
        base_tax=round(base_tax, 2),
        surcharge=0.0,
        cess_or_nic=round(fica, 2),
        rebate=0.0,
        total_tax=total_tax,
        effective_rate=round(effective_rate, 2),
        take_home=round(profile.gross_income - total_tax, 2),
    )


def _compute_uk_deductions(profile: TaxProfile, tax_law: Dict) -> float:
    personal_allowance = tax_law.get("personal_allowance", 12570)
    taper_threshold = tax_law.get("personal_allowance_taper_threshold", 100000)

    if profile.gross_income > taper_threshold:
        excess = profile.gross_income - taper_threshold
        taper_reduction = min(excess / 2, personal_allowance)
        personal_allowance = max(0.0, personal_allowance - taper_reduction)

    extra = 0.0
    for ded_id, ded_info in tax_law.get("deductions", {}).items():
        claimed = profile.deductions_claimed.get(ded_id, 0.0)
        limit = ded_info.get("limit")
        if limit is not None:
            extra += min(claimed, limit)
        else:
            extra += claimed

    return personal_allowance + extra


def _calculate_uk_nic(gross_income: float, nic_info: Dict) -> float:
    lower = nic_info.get("threshold_lower", 12570)
    upper = nic_info.get("threshold_upper", 50270)
    rate_mid = nic_info.get("rate_lower_to_upper", 0.08)
    rate_high = nic_info.get("rate_above_upper", 0.02)

    nic = 0.0
    if gross_income > lower:
        nic += min(gross_income, upper) * rate_mid - lower * rate_mid
    if gross_income > upper:
        nic += (gross_income - upper) * rate_high
    return max(0.0, nic)


def _calculate_uk(profile: TaxProfile, tax_law: Dict) -> RegimeResult:
    total_deductions = _compute_uk_deductions(profile, tax_law)
    taxable_income = max(0.0, profile.gross_income - total_deductions)

    region = profile.filing_status if profile.filing_status == "scotland" else "individual"
    brackets = tax_law["brackets"]["default"].get(region, tax_law["brackets"]["default"]["individual"])
    adjusted_brackets = []
    for b in brackets:
        if b["rate"] == 0.0:
            continue
        adjusted_brackets.append(b)

    base_tax = 0.0
    breakdown = []
    remaining = taxable_income
    for b in tax_law["brackets"]["default"].get(region, tax_law["brackets"]["default"]["individual"]):
        low = b["min"]
        high = b["max"] if b["max"] is not None else float("inf")
        rate = b["rate"]
        band = b.get("band", "")

        if taxable_income + total_deductions <= low:
            break
        effective_low = max(0, low - total_deductions)
        effective_high = max(0, (min(high, taxable_income + total_deductions) - total_deductions))
        band_income = effective_high - effective_low
        if band_income <= 0:
            continue
        tax_in_band = band_income * rate
        base_tax += tax_in_band
        breakdown.append(TaxBracketResult(band=band, income_in_band=band_income, rate=rate, tax=tax_in_band))

    nic_info = tax_law.get("national_insurance", {}).get("class1_primary", {})
    nic = _calculate_uk_nic(profile.gross_income, nic_info)

    total_tax = round(base_tax + nic, 2)
    effective_rate = (total_tax / profile.gross_income * 100) if profile.gross_income > 0 else 0.0

    return RegimeResult(
        regime="default",
        taxable_income=taxable_income,
        total_deductions=total_deductions,
        bracket_breakdown=breakdown,
        base_tax=round(base_tax, 2),
        surcharge=0.0,
        cess_or_nic=round(nic, 2),
        rebate=0.0,
        total_tax=total_tax,
        effective_rate=round(effective_rate, 2),
        take_home=round(profile.gross_income - total_tax, 2),
    )


def calculate_tax(profile: TaxProfile) -> RegimeResult:
    tax_law = _load_tax_law(profile.country)
    if profile.country == "india":
        regime = profile.regime if profile.regime in ("old", "new") else "new"
        return _calculate_india(profile, tax_law, regime)
    if profile.country == "us":
        return _calculate_us(profile, tax_law)
    if profile.country == "uk":
        return _calculate_uk(profile, tax_law)
    raise ValueError(f"No calculation logic for country: {profile.country}")


def simulate_scenarios(profile: TaxProfile) -> ScenarioComparison:
    tax_law = _load_tax_law(profile.country)
    scenarios: Dict[str, RegimeResult] = {}

    if profile.country == "india":
        for regime in ("new", "old"):
            p = profile.model_copy(update={"regime": regime})
            scenarios[regime] = _calculate_india(p, tax_law, regime)
        best = min(scenarios, key=lambda k: scenarios[k].total_tax)

    elif profile.country == "us":
        for status in ("single", "married_filing_jointly", "head_of_household"):
            p = profile.model_copy(update={"filing_status": status})
            scenarios[status] = _calculate_us(p, tax_law)
        best = min(scenarios, key=lambda k: scenarios[k].total_tax)

    elif profile.country == "uk":
        for region in ("individual", "scotland"):
            p = profile.model_copy(update={"filing_status": region})
            scenarios[region] = _calculate_uk(p, tax_law)
        best = min(scenarios, key=lambda k: scenarios[k].total_tax)

    else:
        raise ValueError(f"No scenario logic for country: {profile.country}")

    return ScenarioComparison(scenarios=scenarios, best_scenario=best)


def optimize(profile: TaxProfile) -> OptimizationReport:
    tax_law = _load_tax_law(profile.country)
    recommendations: List[OptimizationRecommendation] = []
    total_recoverable = 0.0

    current_result = calculate_tax(profile)

    if profile.country == "india":
        regime = profile.regime if profile.regime in ("old", "new") else "new"
        deductions = tax_law.get("deductions", {})
        for ded_id, ded_info in deductions.items():
            if regime not in ded_info.get("regimes", []):
                continue
            limit = ded_info.get("limit")
            if limit is None:
                continue
            claimed = profile.deductions_claimed.get(ded_id, 0.0)
            additional_room = max(0.0, limit - claimed)
            if additional_room <= 0:
                continue

            test_claimed = dict(profile.deductions_claimed)
            test_claimed[ded_id] = min(limit, claimed + additional_room)
            test_profile = profile.model_copy(update={"deductions_claimed": test_claimed})
            test_result = _calculate_india(test_profile, tax_law, regime)
            saving = max(0.0, current_result.total_tax - test_result.total_tax)
            total_recoverable += saving

            recommendations.append(OptimizationRecommendation(
                deduction_id=ded_id,
                label=ded_info["label"],
                current_claimed=claimed,
                max_allowed=limit,
                additional_room=additional_room,
                tax_saving=round(saving, 2),
                source_url=ded_info.get("source", tax_law["source_url"]),
            ))

        new_result = _calculate_india(profile.model_copy(update={"regime": "new"}), tax_law, "new")
        old_result = _calculate_india(profile.model_copy(update={"regime": "old"}), tax_law, "old")
        best_regime = "new" if new_result.total_tax <= old_result.total_tax else "old"
        best_tax = min(new_result.total_tax, old_result.total_tax)
        worst_tax = max(new_result.total_tax, old_result.total_tax)

    elif profile.country == "us":
        deductions = tax_law.get("deductions", {})
        for ded_id, ded_info in deductions.items():
            limit = ded_info.get("limit")
            if limit is None:
                continue
            claimed = profile.deductions_claimed.get(ded_id, 0.0)
            additional_room = max(0.0, limit - claimed)
            if additional_room <= 0:
                continue
            test_claimed = dict(profile.deductions_claimed)
            test_claimed[ded_id] = min(limit, claimed + additional_room)
            test_profile = profile.model_copy(update={"deductions_claimed": test_claimed})
            test_result = _calculate_us(test_profile, tax_law)
            saving = max(0.0, current_result.total_tax - test_result.total_tax)
            total_recoverable += saving
            recommendations.append(OptimizationRecommendation(
                deduction_id=ded_id,
                label=ded_info["label"],
                current_claimed=claimed,
                max_allowed=limit,
                additional_room=additional_room,
                tax_saving=round(saving, 2),
                source_url=ded_info.get("source", tax_law["source_url"]),
            ))
        best_regime = "federal"
        best_tax = current_result.total_tax
        worst_tax = current_result.total_tax

    elif profile.country == "uk":
        deductions = tax_law.get("deductions", {})
        for ded_id, ded_info in deductions.items():
            limit = ded_info.get("limit")
            if limit is None:
                continue
            claimed = profile.deductions_claimed.get(ded_id, 0.0)
            additional_room = max(0.0, limit - claimed)
            if additional_room <= 0:
                continue
            test_claimed = dict(profile.deductions_claimed)
            test_claimed[ded_id] = min(limit, claimed + additional_room)
            test_profile = profile.model_copy(update={"deductions_claimed": test_claimed})
            test_result = _calculate_uk(test_profile, tax_law)
            saving = max(0.0, current_result.total_tax - test_result.total_tax)
            total_recoverable += saving
            recommendations.append(OptimizationRecommendation(
                deduction_id=ded_id,
                label=ded_info["label"],
                current_claimed=claimed,
                max_allowed=limit,
                additional_room=additional_room,
                tax_saving=round(saving, 2),
                source_url=ded_info.get("source", tax_law["source_url"]),
            ))
        best_regime = "default"
        best_tax = current_result.total_tax
        worst_tax = current_result.total_tax

    else:
        raise ValueError(f"No optimizer for country: {profile.country}")

    recommendations.sort(key=lambda r: r.tax_saving, reverse=True)
    money_left_on_table = max(0.0, worst_tax - best_tax) + total_recoverable

    return OptimizationReport(
        best_regime=best_regime,
        best_regime_tax=round(best_tax, 2),
        worst_regime_tax=round(worst_tax, 2),
        money_left_on_table=round(money_left_on_table, 2),
        recommendations=recommendations,
        total_recoverable_tax=round(total_recoverable, 2),
    )


def whatif_series(profile: TaxProfile, deduction_id: str, steps: int = 20) -> List[Dict]:
    tax_law = _load_tax_law(profile.country)
    deductions_meta = tax_law.get("deductions", {})
    if deduction_id not in deductions_meta:
        return []

    limit = deductions_meta[deduction_id].get("limit")
    if limit is None:
        return []

    results = []
    for i in range(steps + 1):
        invested = (limit / steps) * i
        test_claimed = dict(profile.deductions_claimed)
        test_claimed[deduction_id] = invested
        test_profile = profile.model_copy(update={"deductions_claimed": test_claimed})
        result = calculate_tax(test_profile)
        results.append({"investment": invested, "tax": result.total_tax, "take_home": result.take_home})

    return results
