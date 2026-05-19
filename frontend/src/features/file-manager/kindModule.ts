import { BarChart3, Box, FileBarChart, FileText, Image as ImageIcon, MapPin, Package, Pencil, PenTool, Radar, Ruler, type LucideIcon } from 'lucide-react';
import type { FileKind } from './types';

// One file kind can be opened in several modules — a single .pdf is
// either a project document, a takeoff source, or a tender attachment.
// The first entry in each list is the "primary" / suggested module.
//
// Each `route` builder receives the project id and (optionally) a file
// id. Where the receiving module supports a deep-link param, the file
// id is appended so clicking actually opens the right file inside the
// destination — not just the bare module shell.
export interface ModuleTarget {
  label: string;
  i18nKey: string;
  description: string;
  descriptionI18nKey: string;
  icon: LucideIcon;
  /** Path template — `{projectId}` is substituted in by the consumer. */
  route: (projectId: string, fileId?: string) => string;
  /**
   * Some destinations (Clash Detection, CAD-BIM BI Explorer) resolve the
   * project from the global project-context store rather than from a path
   * param, so they'd land on the empty "no project" state when reached via
   * a deep-link. When this flag is set the consumer must call
   * `useProjectContextStore.setActiveProject(...)` for the file's project
   * BEFORE navigating so the destination opens populated.
   */
  setsActiveProject?: boolean;
}

const PROJECT = (p: string, sub: string) => `/projects/${p}/${sub}`;

// Append a deep-link query parameter only when we actually have a file
// id. Keeping the bare path when it's missing avoids URLs like
// `/takeoff?doc=` that some routers parse as an empty string.
const withParam = (path: string, key: string, value?: string): string =>
  value ? `${path}${path.includes('?') ? '&' : '?'}${key}=${encodeURIComponent(value)}` : path;

export const KIND_MODULES: Record<FileKind, ModuleTarget[]> = {
  document: [
    // Primary: open the PDF in the takeoff viewer with the measurements
    // tab pre-selected. TakeoffPage hydrates the viewer from either its
    // own server documents OR the central documents module by id, so
    // either source resolves the file. `&source=document` tells the
    // viewer to fall back to the documents module's download URL.
    {
      label: 'PDF Takeoff',
      i18nKey: 'files.module.pdf_takeoff',
      description: 'Open this PDF and start measuring',
      descriptionI18nKey: 'files.module.pdf_takeoff_desc',
      icon: Ruler,
      route: (_p, f) =>
        f
          ? `/takeoff?doc=${encodeURIComponent(f)}&source=document&tab=measurements`
          : '/takeoff',
    },
    {
      label: 'File Manager',
      i18nKey: 'files.module.documents',
      description: 'Stay in /files with this document selected',
      descriptionI18nKey: 'files.module.documents_desc',
      icon: FileText,
      route: (p, f) => withParam(PROJECT(p, 'files'), 'file', f),
    },
  ],
  photo: [
    {
      label: 'Site Photos',
      i18nKey: 'files.module.photos',
      description: 'Browse geo-tagged site photography',
      descriptionI18nKey: 'files.module.photos_desc',
      icon: ImageIcon,
      route: (_p, f) => withParam('/photos', 'photo', f),
    },
    {
      label: 'Field Reports',
      i18nKey: 'files.module.field_reports',
      description: 'Attach photos to daily field reports',
      descriptionI18nKey: 'files.module.field_reports_desc',
      icon: MapPin,
      route: () => '/field-reports',
    },
  ],
  sheet: [
    {
      label: 'PDF Takeoff',
      i18nKey: 'files.module.pdf_takeoff',
      description: 'Open the parent PDF in the takeoff viewer',
      descriptionI18nKey: 'files.module.pdf_takeoff_desc_sheet',
      icon: Ruler,
      route: (_p, f) => withParam('/takeoff', 'sheet', f),
    },
    {
      label: 'File Manager',
      i18nKey: 'files.module.documents',
      description: 'See the source PDF this sheet was extracted from',
      descriptionI18nKey: 'files.module.documents_desc_sheet',
      icon: FileText,
      route: (p, f) => withParam(PROJECT(p, 'files'), 'file', f),
    },
  ],
  bim_model: [
    {
      // Primary — opens the model directly in the 3D viewport via the
      // /projects/:projectId/bim/:modelId route (BIMPage.tsx L1496 reads
      // both path params; App.tsx L486).
      label: 'BIM 3D Viewer',
      i18nKey: 'files.module.bim_viewer',
      description: 'Inspect 3D model elements & quantities',
      descriptionI18nKey: 'files.module.bim_viewer_desc',
      icon: Box,
      route: (p, f) => (f ? PROJECT(p, `bim/${encodeURIComponent(f)}`) : PROJECT(p, 'bim')),
    },
    {
      // CAD-BIM BI Explorer — spreadsheet/pivot/chart analytics over the
      // model's element data. Route /data-explorer (App.tsx L475, sidebar
      // label `nav.cad_bim_explorer`). Its landing page lets the user
      // pick the model/session; setting the active project keeps the
      // rest of the workspace bound to the same project.
      label: 'CAD-BIM BI Explorer',
      i18nKey: 'files.module.cad_bim_explorer',
      description: 'Pivot, chart & analyse element quantities',
      descriptionI18nKey: 'files.module.cad_bim_explorer_desc',
      icon: BarChart3,
      route: () => '/data-explorer',
      setsActiveProject: true,
    },
    {
      // Clash Detection — geometric interference review. Route /clash
      // (App.tsx L482); ClashDetectionPage.tsx L167 resolves the project
      // from the global context store first, falling back to ?project=.
      // We set the store AND pass ?project= so the page opens populated.
      label: 'Clash Detection',
      i18nKey: 'files.module.clash_detection',
      description: 'Run geometric interference checks on this model',
      descriptionI18nKey: 'files.module.clash_detection_desc',
      icon: Radar,
      route: (p) => `/clash?project=${encodeURIComponent(p)}`,
      setsActiveProject: true,
    },
  ],
  dwg_drawing: [
    {
      label: 'DWG Takeoff',
      i18nKey: 'files.module.dwg_takeoff',
      description: 'Measure quantities from native CAD',
      descriptionI18nKey: 'files.module.dwg_takeoff_desc',
      icon: Pencil,
      route: (_p, f) => withParam('/dwg-takeoff', 'drawingId', f),
    },
    {
      label: 'Data Explorer',
      i18nKey: 'files.module.data_explorer',
      description: 'Inspect parsed entities, layers & blocks',
      descriptionI18nKey: 'files.module.data_explorer_desc',
      icon: Package,
      route: (_p, f) => withParam('/data-explorer', 'drawingId', f),
    },
  ],
  takeoff: [
    {
      label: 'Takeoff',
      i18nKey: 'files.module.takeoff',
      description: 'Continue measuring or review takeoff results',
      descriptionI18nKey: 'files.module.takeoff_desc',
      icon: Ruler,
      route: (_p, f) => withParam('/takeoff', 'session', f),
    },
  ],
  report: [
    {
      label: 'Reports',
      i18nKey: 'files.module.reports',
      description: 'Browse generated cost & validation reports',
      descriptionI18nKey: 'files.module.reports_desc',
      icon: FileBarChart,
      route: (_p, f) => withParam('/reporting', 'report', f),
    },
  ],
  markup: [
    {
      label: 'Markups',
      i18nKey: 'files.module.markups',
      description: 'Open markups & comment threads',
      descriptionI18nKey: 'files.module.markups_desc',
      icon: PenTool,
      route: (_p, f) => withParam('/markups', 'markup', f),
    },
  ],
};

// Per-extension override for `document` since a PDF, IFC, RVT, DXF and
// XLSX all live under the `document` kind but route to different
// modules. Returns the *primary* target — the secondary list still
// comes from KIND_MODULES so the user has the full menu.
const EXT_PRIMARY_OVERRIDE: Record<string, ModuleTarget> = {
  pdf: KIND_MODULES.document[0]!, // PDF Takeoff
  ifc: KIND_MODULES.bim_model[0]!,
  rvt: KIND_MODULES.bim_model[0]!,
  dgn: KIND_MODULES.bim_model[0]!,
  glb: KIND_MODULES.bim_model[0]!,
  gltf: KIND_MODULES.bim_model[0]!,
  dwg: KIND_MODULES.dwg_drawing[0]!,
  dxf: KIND_MODULES.dwg_drawing[0]!,
};

export function primaryModule(kind: FileKind, extension?: string | null): ModuleTarget {
  if (extension) {
    const override = EXT_PRIMARY_OVERRIDE[extension.toLowerCase().replace(/^\./, '')];
    if (override) return override;
  }
  return KIND_MODULES[kind][0]!;
}

export function modulesForKind(kind: FileKind): ModuleTarget[] {
  return KIND_MODULES[kind] ?? [];
}
