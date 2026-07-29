const edition = __OE_EDITION__ || 'community';
const configuredLocales = (__OE_SUPPORTED_LOCALES__ || '')
  .split(',')
  .map((locale) => locale.trim())
  .filter(Boolean);

export const editionConfig = {
  edition,
  supportedLocales: configuredLocales,
  defaultLocale: __OE_DEFAULT_LOCALE__ || 'en',
  defaultRegion: __OE_DEFAULT_REGION__ || '',
} as const;

export const isBensonEdition = editionConfig.edition === 'benson';

export function supportsLocale(locale: string): boolean {
  if (editionConfig.supportedLocales.length === 0) return true;
  const base = locale.split('-')[0]!.toLowerCase();
  return editionConfig.supportedLocales.some(
    (supported) => supported.toLowerCase() === locale.toLowerCase() || supported.toLowerCase() === base,
  );
}
