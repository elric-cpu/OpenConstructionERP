/**
 * Locale-aware number and date formatters.
 *
 * Maps i18next language codes to Intl locale tags.
 * Falls back to browser locale when no mapping exists.
 */
import i18next from 'i18next';

/** i18next language code → Intl BCP-47 locale tag */
const LOCALE_MAP: Record<string, string> = {
  de: 'de-DE',
  da: 'da-DK',
  cs: 'cs-CZ',
  en: 'en-US',
  es: 'es-ES',
  fr: 'fr-FR',
  fi: 'fi-FI',
  hi: 'hi-IN',
  it: 'it-IT',
  ja: 'ja-JP',
  ko: 'ko-KR',
  nl: 'nl-NL',
  no: 'nb-NO',
  pl: 'pl-PL',
  pt: 'pt-BR',
  ru: 'ru-RU',
  sv: 'sv-SE',
  tr: 'tr-TR',
  uk: 'uk-UA',
  bg: 'bg-BG',
  ar: 'ar-SA',
  zh: 'zh-CN',
};

/** Returns the Intl-compatible locale string for the current i18next language. */
export function getIntlLocale(): string {
  const lang = i18next.language || 'en';
  return LOCALE_MAP[lang] || lang;
}

/** Currency-style number formatter (e.g. 1,234.56) using current locale. */
export function fmtNumber(value: number, decimals = 2): string {
  return new Intl.NumberFormat(getIntlLocale(), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Compact number formatter (e.g. 1.2M) using current locale. */
export function fmtCompact(value: number): string {
  return new Intl.NumberFormat(getIntlLocale(), {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

/**
 * Currency formatter using current locale.
 *
 * When ``currency`` is empty / null / not a valid ISO 4217 code, falls
 * back to a plain number with no currency symbol — preferable to the
 * historical "default EUR" because rendering ``1,234,567 EUR`` on a
 * USD/BRL/JPY project is actively wrong (lies to the operator about
 * the unit). A bare formatted number is honest: "we don't know the
 * currency for this value, ask before relying on it".
 *
 * Callers that genuinely want a EUR fallback (legacy LanceDB rows
 * that pre-date currency stamping) can still pass ``"EUR"`` explicitly.
 */
export function fmtCurrency(value: number, currency?: string | null): string {
  const trimmed = (currency || '').trim().toUpperCase();
  const isValid = /^[A-Z]{3}$/.test(trimmed);
  if (!isValid) {
    // No currency known — render the number with locale grouping but
    // without a currency symbol. Prevents the EUR-on-USD-project bug.
    return new Intl.NumberFormat(getIntlLocale(), {
      maximumFractionDigits: 0,
    }).format(value);
  }
  try {
    return new Intl.NumberFormat(getIntlLocale(), {
      style: 'currency',
      currency: trimmed,
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${trimmed}`;
  }
}

/** Date formatter using current locale. */
export function fmtDate(dateStr: string, options?: Intl.DateTimeFormatOptions): string {
  const defaults: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  };
  return new Date(dateStr).toLocaleDateString(getIntlLocale(), options || defaults);
}
