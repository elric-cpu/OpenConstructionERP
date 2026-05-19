# -*- coding: utf-8 -*-
"""‌⁠‍Find translations that are mixed English/Mongolian — likely poor quality."""
import re
import json
from pathlib import Path

en = Path("frontend/src/app/locales/en.ts").read_text(encoding="utf-8")
mn = Path("frontend/src/app/locales/mn.ts").read_text(encoding="utf-8")

pat = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
en_pairs = {m.group(1): m.group(2) for m in pat.finditer(en)}
mn_pairs = {m.group(1): m.group(2) for m in pat.finditer(mn)}


def has_cyrillic(s):
    return any("Ѐ" <= c <= "ӿ" for c in s)


# Find translations that have Cyrillic but ALSO have meaningful English words
# (i.e. ASCII words >= 4 letters that aren't placeholders, brand names, etc.)
PROTECTED_WORDS = set([
    "OpenConstructionERP", "OpenEstimate", "OpenEstimator",
    "BIM", "IFC", "DWG", "DGN", "RVT", "DAE", "COLLADA", "Revit",
    "GAEB", "DIN", "NRM", "MasterFormat", "UniFormat", "Uniclass",
    "OmniClass", "SAP", "Procore", "Primavera", "PlanRadar",
    "PERT", "CPM", "CPI", "SPI", "MEP", "EVM", "ESG", "RFI", "NCR",
    "BAC", "EAC", "PV", "EV", "AC", "VAC", "SV", "CV", "ETC", "TCPI",
    "CWICR", "DDC", "Qdrant", "LanceDB", "BOQ", "BoQ", "JSON", "API",
    "OCR", "PDF", "CSV", "XML", "Excel", "Word", "VAT",
    "OpenAI", "Anthropic", "Claude", "Gemini", "Slack", "Telegram",
    "Microsoft", "Teams", "Google", "Outlook", "iCal", "Webhook",
    "ISO", "AACE", "AGPL", "GitHub", "LinkedIn", "Twitter",
    "BGE", "BAAI", "Monte", "Carlo", "Gantt", "DACH", "SQLite",
    "Parquet", "BKI", "BCIS", "RSMeans", "SNIP", "GESN", "STABU",
    "Birim", "Fiyat", "Sekisan", "SINAPI", "Computo", "DPGF", "KNR",
    "EUR", "USD", "MNT", "XAF", "BRL", "INR", "GBP", "JPY", "CNY",
    "TBD", "RFQ", "LLM", "QA", "CRM", "CAD", "AI", "WBS", "FX",
    "PRO", "STD", "HVAC", "AGPL", "BSt", "Pareto",
    "Ctrl", "Shift", "Enter", "Cmd", "Del", "Tab",
    "MB", "GB", "kg",
    "Hugging", "Face", "HuggingFace", "Yjs", "Vite",
    "GPT", "Berlin", "Munich", "Stein", "Graben",
    "Pos", "AU", "CA", "CN", "CZ", "ES", "FR", "IN", "KR", "PL",
    "UK", "US", "UAE", "NL", "JP", "IT", "RU", "BR", "TR", "DE",
    "BIM", "BOQs", "RFIs", "NCRs",
    "Bau", "GmbH", "Nordic", "Imperial",
    "Q1", "Q2", "Q3", "Q4",
])

# Find Cyrillic-containing values that still have ASCII words
ASCII_WORD_RE = re.compile(r'\b[A-Za-z][A-Za-z]{3,}\b')

bad = {}
for k, v in mn_pairs.items():
    if not has_cyrillic(v):
        continue
    en_v = en_pairs.get(k, "")
    if v == en_v:
        continue
    # Find ASCII words
    ascii_words = [w for w in ASCII_WORD_RE.findall(v) if w not in PROTECTED_WORDS]
    if ascii_words:
        bad[k] = (en_v, v, ascii_words)

print(f"Suspect mixed translations: {len(bad)}")

with open("scripts/_mn_mixed.json", "w", encoding="utf-8") as f:
    json.dump({k: {"en": en_v, "mn": v, "ascii_words": w} for k, (en_v, v, w) in bad.items()},
              f, indent=2, ensure_ascii=False)

# Sample
print("\n=== Sample (first 15) ===")
for i, (k, (en_v, mn_v, words)) in enumerate(list(bad.items())[:15]):
    print(f"\n  KEY: {k}")
    print(f"  ASCII leftover: {words[:5]}")
    print(f"  EN: {en_v[:150]}")
    print(f"  MN: {mn_v[:150]}")
