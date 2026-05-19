# -*- coding: utf-8 -*-
"""‌⁠‍Translate untranslated mn.ts entries to Mongolian Cyrillic.

Approach:
  1. Protect interpolation tokens (`{{...}}`), HTML, and domain acronyms.
  2. Apply phrase-level exact-match dictionary (high-frequency UI phrases).
  3. Apply word-level translation across remaining tokens.
  4. Keep punctuation, numbers, protected terms verbatim.
  5. If output still contains too much English, leave the entry as English.

Preserves all tokens via placeholder substitution.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_PATH = ROOT / "frontend" / "src" / "app" / "locales" / "en.ts"
MN_PATH = ROOT / "frontend" / "src" / "app" / "locales" / "mn.ts"

# ---------------------------------------------------------------------------
# Protected terms (never translated)
# ---------------------------------------------------------------------------
PROTECTED = [
    "OpenConstructionERP", "OpenEstimate", "OpenEstimator", "OpenEstimator.io", "OpenEstimate.io",
    "BIM", "IFC", "DWG", "DGN", "RVT", "DAE", "COLLADA", "Revit",
    "GAEB", "DIN", "DIN 276", "NRM", "NRM 1/2", "NRM 2", "MasterFormat", "UniFormat", "Uniclass",
    "OmniClass", "BIM 360", "SAP", "Procore", "Primavera", "PlanRadar", "MS Project",
    "PERT", "CPM", "CPI", "SPI", "MEP", "EVM", "ESG", "RFI", "RFIs", "NCR", "NCRs",
    "BAC", "EAC", "PV", "EV", "AC", "VAC", "SV", "CV", "ETC", "TCPI",
    "CWICR", "DDC", "DDC cad2data", "cad2data", "Qdrant", "LanceDB", "Three.js",
    "BOQ", "BOQs", "BoQ", "HuggingFace", "Hugging Face", "JSON", "API",
    "OCR", "PDF", "CSV", "XML", "Excel", "Word", "VAT",
    "OpenAI", "Anthropic", "Claude", "GPT-4", "GPT-4o", "GPT-4 Turbo", "Gemini", "Claude 3.5",
    "Slack", "Telegram", "Microsoft Teams", "Teams", "Google", "Outlook",
    "iCal", "Webhook", "Webhooks", "HTTP", "HTTP POST", "POST", "SMTP", "URL",
    "ISO 19650", "ISO 4217", "AACE", "AGPL-3.0", "GitHub", "LinkedIn",
    "X/Twitter", "Twitter", "BGE-M3", "BGE", "BAAI", "INT8", "FP32",
    "S-Curve", "S-curve", "Monte Carlo", "Gantt", "DACH", "SQLite",
    "Parquet", "BKI", "BCIS", "RSMeans", "SNIP", "GESN", "STABU",
    "Birim Fiyat", "Sekisan", "SINAPI", "Computo", "DPGF", "KNR",
    "Stahlbetonwand", "Berlin", "Munich", "MyC", "EUR", "USD", "MNT", "XAF", "BRL",
    "TBD", "RFQ", "LLM", "QA", "OCEP", "CRM", "CAD", "AI",
    "WBS", "FX", "PRO", "STD", "HVAC", "ABC %", "ABC",
    "Pareto", "AGPL", "BSt 500", "B500", "C30/37", "F90", "S2",
    "AU", "CA", "CN", "CZ", "ES", "FR", "IN", "KR", "PL", "UK", "US", "UAE", "NL", "JP", "IT",
    "RU", "BR", "TR", "DE", "Nordic", "NS 3420", "DPGF", "AU BOQ Exchange",
    "CA BOQ Exchange", "CN BOQ Exchange", "CZ BOQ Exchange", "ES PBC Exchange",
    "DE DIN 276 Exchange", "FR DPGF Exchange", "IN BOQ Exchange", "IT Computo Exchange",
    "JP Sekisan Exchange", "KR BOQ Exchange", "NL STABU Exchange", "PL KNR Exchange",
    "RU GESN Exchange", "TR Birim Fiyat Exchange", "UAE BOQ Exchange", "UK NRM Exchange",
    "US MasterFormat Exchange", "BR SINAPI Exchange", "Nordic NS 3420 Exchange", "GAEB Exchange",
    "Pos", "f1", "F1", "Ctrl", "Ctrl+D", "Ctrl+E", "Ctrl+I", "Ctrl+L", "Ctrl+/",
    "Ctrl+Y", "Ctrl+Z", "Ctrl+Shift+V", "Ctrl+Enter", "Cmd",
    "X81", "X83", "X84", "GAEB X83",
    "MB", "kg", "m2", "m3", "m²", "m³",
    "Bau", "GmbH", "p.a.", "p95",
    "I", "II", "III", "IV", "V",
    "Q3", "Q4",
    "INR", "lakh", "crore",
    "Stein", "Graben",
    "Hugging", "Face",
    "Open construction", "Open Construction",
]

INTERP_RE = re.compile(r"\{\{[^}]+\}\}")
HTML_RE = re.compile(r"</?[a-zA-Z][^>]*>")
ZWS_RE = re.compile(r"[​‌‍⁠᠎]+")


def protect(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def keep(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"\x00{len(tokens)-1}\x00"

    text = INTERP_RE.sub(keep, text)
    text = HTML_RE.sub(keep, text)
    for term in sorted(PROTECTED, key=len, reverse=True):
        pat = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)")
        text = pat.sub(keep, text)
    return text, tokens


def restore(text: str, tokens: list[str]) -> str:
    def back(m: re.Match) -> str:
        idx = int(m.group(1))
        return tokens[idx] if 0 <= idx < len(tokens) else m.group(0)
    return re.sub(r"\x00(\d+)\x00", back, text)


def has_cyrillic(s: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in s)
