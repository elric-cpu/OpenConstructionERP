import enResource from '../../app/locales/en';

export async function importLocale(code: string): Promise<unknown> {
  if (code !== 'en') {
    throw new Error(`Unsupported Benson locale: ${code}`);
  }
  return { default: enResource };
}
