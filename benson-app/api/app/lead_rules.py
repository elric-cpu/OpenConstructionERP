from typing import Any


def lead_source(payload: dict[str, Any]) -> str:
    utm_source = str(payload.get("utm_source", "")).strip()
    if utm_source:
        return utm_source[:200]
    context = str(payload.get("form_context", "")).strip()
    if context and context not in {"general", "contact"}:
        return context[:200]
    source_page = str(payload.get("source_page", "")).strip()
    return source_page[:200] if source_page else "Website"


def classify_spam(payload: dict[str, Any]) -> tuple[bool, str | None]:
    content = " ".join(
        str(payload.get(field, ""))
        for field in ("name", "email", "service_type", "message")
    ).lower()
    reasons: list[str] = []
    spam_phrases = (
        "backlink",
        "guest post",
        "search engine optimization",
        "seo services",
        "crypto",
        "casino",
        "domain authority",
        "web traffic",
    )
    matched = [phrase for phrase in spam_phrases if phrase in content]
    if matched:
        reasons.append(f"spam language: {', '.join(matched[:2])}")
    link_count = (
        content.count("http://") + content.count("https://") + content.count("www.")
    )
    if link_count >= 2:
        reasons.append("multiple external links")
    is_spam = bool(matched) or link_count >= 3
    return is_spam, "; ".join(reasons)[:500] if is_spam else None
