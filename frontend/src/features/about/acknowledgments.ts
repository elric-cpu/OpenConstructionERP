/**
 * Community acknowledgments - the people who shaped OpenConstructionERP by
 * reporting issues, asking questions and funding the work.
 *
 * Keep this file in sync with /ACKNOWLEDGMENTS.md at the repo root. When a new
 * reporter row is added there, add the person here too, deduplicated by handle
 * (one entry per person, even when they filed several issues).
 *
 * SPONSORS is intentionally empty for now. As GitHub Sponsors and PayPal
 * donors come in, add them to the SPONSORS array below so the "Thank you"
 * wall on the About page can credit them.
 */

export interface Acknowledged {
  name: string;
  handle?: string;
  url?: string;
}

/**
 * Resolve the public profile link for an entry. Uses an explicit url when
 * provided, otherwise derives the GitHub profile from the handle.
 */
export function acknowledgedUrl(entry: Acknowledged): string | undefined {
  if (entry.url) return entry.url;
  if (entry.handle) return `https://github.com/${entry.handle}`;
  return undefined;
}

/**
 * Contributors and reporters - community members who opened issues,
 * discussions or questions that improved the platform. Deduplicated by
 * handle and ordered by first appearance in /ACKNOWLEDGMENTS.md.
 */
export const CONTRIBUTORS: Acknowledged[] = [
  { name: 'AliK', handle: 'alikhalilx' },
  { name: 'C&C Consulting', handle: 'candcconsulting' },
  { name: 'Christian Santoro', handle: 'ChristianSantoro' },
  { name: 'Cody Churchwell', handle: 'consigcody94' },
  { name: 'DevpratikDevelopers', handle: 'DevpratikDevelopers' },
  { name: 'expalex1507', handle: 'expalex1507' },
  { name: 'hanisedawy', handle: 'hanisedawy' },
  { name: 'Hung', handle: 'hungdd84' },
  { name: 'JRS', handle: 'JORBDAAG' },
  { name: 'jyloveqq', handle: 'jyloveqq' },
  { name: 'maher00746', handle: 'maher00746' },
  { name: 'migfrazao2003', handle: 'migfrazao2003' },
  { name: 'Mario Kozjak', handle: 'mkozjak' },
  { name: 'Mohammed Shousha', handle: 'mohandshamada' },
  { name: 'online14230', handle: 'online14230' },
  { name: 'rashidengg-arch', handle: 'rashidengg-arch' },
  { name: 'rrvizuete', handle: 'rrvizuete' },
  { name: 'Thiemo Ferreira Torres', handle: 'thiemotorres' },
  { name: 'Braedon Saunders', handle: 'braedonsaunders' },
  { name: 'BG', handle: 'gbatkhuyag' },
  { name: 'skolodi', handle: 'skolodi' },
  { name: 'Mourdi59', handle: 'Mourdi59' },
  { name: 'sergeilapp', handle: 'sergeilapp' },
  { name: 'Jérémy Christillin', handle: 'bvisible' },
  { name: 'rjohny', handle: 'rjohny55' },
  { name: 'Jehad Baniowda', handle: 'jehadbaniodeh' },
  { name: 'leval907', handle: 'leval907' },
  { name: 'arvildev', handle: 'arvildev' },
  { name: 'Tigercatman', handle: 'Tigercatman' },
  { name: 'skeltic-wq', handle: 'skeltic-wq' },
  { name: 'MeCode4', handle: 'MeCode4' },
  { name: 'Nebulasunrise-OG', handle: 'Nebulasunrise-OG' },
];

/**
 * Sponsors and donors - GitHub Sponsors and PayPal supporters. Empty for now.
 * Add entries here as backers come in (name plus a handle or url) and the
 * About page will surface a "Sponsors and donors" subsection automatically.
 */
export const SPONSORS: Acknowledged[] = [];
