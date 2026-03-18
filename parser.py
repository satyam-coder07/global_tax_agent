from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


TAX_LAWS_DIR = Path(__file__).parent / "tax_laws"

INDIA_FIELD_PATTERNS = {
    "gross_income": [r"gross\s+salary[\s:]+([0-9,]+)", r"total\s+income[\s:]+([0-9,]+)", r"gross\s+total\s+income[\s:]+([0-9,]+)"],
    "tds": [r"tds\s+deducted[\s:]+([0-9,]+)", r"tax\s+deducted\s+at\s+source[\s:]+([0-9,]+)"],
    "80C": [r"80c[\s:]+([0-9,]+)", r"section\s+80c[\s:]+([0-9,]+)"],
    "80D": [r"80d[\s:]+([0-9,]+)", r"medical\s+insurance[\s:]+([0-9,]+)"],
    "hra_received": [r"hra\s+received[\s:]+([0-9,]+)", r"house\s+rent\s+allowance[\s:]+([0-9,]+)"],
    "pan": [r"pan[\s:]+([A-Z]{5}[0-9]{4}[A-Z])"],
}

US_FIELD_PATTERNS = {
    "gross_income": [r"gross\s+wages[\s:]+\$?([0-9,]+)", r"total\s+income[\s:]+\$?([0-9,]+)", r"box\s*1[\s:]+\$?([0-9,]+)"],
    "federal_tax_withheld": [r"federal\s+income\s+tax\s+withheld[\s:]+\$?([0-9,]+)", r"box\s*2[\s:]+\$?([0-9,]+)"],
    "401k": [r"401\(k\)[\s:]+\$?([0-9,]+)", r"box\s*12.*d[\s:]+\$?([0-9,]+)"],
    "ssn": [r"ssn[\s:]+([0-9]{3}-[0-9]{2}-[0-9]{4})"],
}

UK_FIELD_PATTERNS = {
    "gross_income": [r"gross\s+pay[\s:]+[£]?([0-9,]+)", r"total\s+earnings[\s:]+[£]?([0-9,]+)"],
    "tax_paid": [r"income\s+tax[\s:]+[£]?([0-9,]+)", r"paye[\s:]+[£]?([0-9,]+)"],
    "nic": [r"national\s+insurance[\s:]+[£]?([0-9,]+)", r"ni[\s:]+[£]?([0-9,]+)"],
    "ni_number": [r"ni\s+number[\s:]+([A-Z]{2}[0-9]{6}[A-Z])"],
}

COUNTRY_PATTERNS = {
    "india": INDIA_FIELD_PATTERNS,
    "us": US_FIELD_PATTERNS,
    "uk": UK_FIELD_PATTERNS,
}


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    if not PDF_AVAILABLE:
        return ""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text_parts.append(extracted)
    return "\n".join(text_parts)


def _extract_text_from_image(file_bytes: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)


def _clean_number(raw: str) -> float:
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _apply_patterns(text: str, patterns: Dict[str, List[str]]) -> Dict[str, Any]:
    extracted: Dict[str, Any] = {}
    text_lower = text.lower()

    for field, pattern_list in patterns.items():
        for pattern in pattern_list:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                raw = match.group(1)
                if field in ("pan", "ssn", "ni_number"):
                    extracted[field] = raw.upper()
                else:
                    extracted[field] = _clean_number(raw)
                break

    return extracted


def _llm_enhance(text: str, country: str, bridge: Any, raw_extracted: Dict) -> Dict:
    system = (
        "You are a tax document analyst. Extract structured tax data from the document text provided. "
        "Return ONLY a valid JSON object with numeric values (no currency symbols). "
        f"Map fields to the {country.upper()} tax schema. "
        "If a field is not found, omit it. Do not invent values."
    )
    prompt = (
        f"Document text:\n\n{text[:3000]}\n\n"
        f"Already extracted fields (may be incomplete): {json.dumps(raw_extracted)}\n\n"
        f"Return a complete JSON object for a {country.upper()} tax profile with fields: "
        f"gross_income, deductions (as a dict), tds_or_tax_withheld, age (if found)."
    )
    try:
        response = bridge.reason(system, prompt)
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass
    return {}


def parse_document(file_bytes: bytes, filename: str, country: str, bridge: Optional[Any] = None) -> Dict[str, Any]:
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        raw_text = _extract_text_from_pdf(file_bytes)
    elif any(filename_lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")):
        raw_text = _extract_text_from_image(file_bytes)
    else:
        raw_text = file_bytes.decode("utf-8", errors="ignore")

    if not raw_text.strip():
        return {"error": "Could not extract text from document. Ensure the file is a legible PDF or image."}

    patterns = COUNTRY_PATTERNS.get(country.lower(), {})
    raw_extracted = _apply_patterns(raw_text, patterns)

    llm_result: Dict = {}
    if bridge is not None:
        llm_result = _llm_enhance(raw_text, country, bridge, raw_extracted)

    merged: Dict[str, Any] = {}
    merged.update(raw_extracted)
    for key, val in llm_result.items():
        if key not in merged or merged[key] == 0:
            merged[key] = val

    merged["_raw_text_preview"] = raw_text[:500]
    merged["_source_file"] = filename
    merged["_country"] = country

    return merged
