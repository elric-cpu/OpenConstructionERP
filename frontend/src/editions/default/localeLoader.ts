export async function importLocale(code: string): Promise<unknown> {
  return import(`../../app/locales/${code}.ts`);
}
