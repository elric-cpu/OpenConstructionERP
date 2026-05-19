# -*- coding: utf-8 -*-
"""‌⁠‍Dump heavily-mixed translations along with their English source."""
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


PROTECTED = set([
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
    "PRO", "STD", "HVAC", "BSt", "Pareto",
    "Ctrl", "Shift", "Enter", "Cmd", "Del", "Tab",
    "MB", "GB", "kg",
    "Hugging", "Face", "Yjs", "Vite", "GPT", "Berlin", "Munich",
    "Pos", "AU", "CA", "CN", "CZ", "ES", "FR", "IN", "KR", "PL",
    "UK", "US", "UAE", "NL", "JP", "IT", "RU", "BR", "TR", "DE",
    "BOQs", "RFIs", "NCRs", "Bau", "GmbH", "Nordic", "Imperial",
    "Q1", "Q2", "Q3", "Q4",
])

ASCII_WORD_RE = re.compile(r'\b[A-Za-z][A-Za-z]{3,}\b')

heavily = {}
for k, v in mn_pairs.items():
    if not has_cyrillic(v):
        continue
    en_v = en_pairs.get(k, "")
    if v == en_v:
        continue
    words = [w for w in ASCII_WORD_RE.findall(v) if w not in PROTECTED]
    if len(words) >= 5:
        heavily[k] = en_v

print(f"Heavily-mixed: {len(heavily)}\n")
for k, en_v in heavily.items():
    print(f"  KEY: {k}")
    print(f"  EN:  {en_v}")
    print()

with open("scripts/_mn_heavily_with_en.json", "w", encoding="utf-8") as f:
    json.dump(heavily, f, indent=2, ensure_ascii=False)
