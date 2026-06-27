/**
 * Unit tests for the File Manager "open in module" routing resolver.
 *
 * The critical invariant (issue #273): a BIM source file (IFC/RVT/...) that
 * lives under the ``document`` kind carries the *Document* id, so opening it
 * must route through the on-demand converter via ``?docId=`` - NOT the
 * ``/bim/<id>`` path that BIMPage reads as a *model* id (which 404s, because
 * no model exists yet, and the file is never converted). A real ``bim_model``
 * row carries its own model id and must keep the path route.
 */

import { describe, it, expect } from 'vitest';
import { primaryModule, modulesForKind } from './kindModule';

describe('primaryModule - BIM documents convert on demand (#273)', () => {
  it('routes a document-kind IFC through ?docId= (not a model-id path)', () => {
    const route = primaryModule('document', '.ifc').route('PROJ1', 'DOC-123');
    expect(route).toBe('/projects/PROJ1/bim?docId=DOC-123');
    // Must NOT treat the document id as a model id in the path.
    expect(route).not.toContain('/bim/DOC-123');
  });

  it('routes a document-kind RVT through ?docId= too', () => {
    expect(primaryModule('document', '.rvt').route('PROJ1', 'DOC-9')).toBe(
      '/projects/PROJ1/bim?docId=DOC-9',
    );
  });

  it('keeps a real bim_model row on the /bim/<modelId> path route', () => {
    // Regression guard: a converted model must open by its model id, never
    // be mis-sent as a ?docId= document import.
    const route = primaryModule('bim_model', '.ifc').route('PROJ1', 'MODEL-7');
    expect(route).toBe('/projects/PROJ1/bim/MODEL-7');
    expect(route).not.toContain('docId=');
  });
});

describe('primaryModule - other kinds unaffected', () => {
  it('document-kind DWG still imports on demand via ?docId=', () => {
    expect(primaryModule('document', '.dwg').route('PROJ1', 'DOC-5')).toBe(
      '/dwg-takeoff?docId=DOC-5',
    );
  });

  it('a real dwg_drawing row keeps its native ?drawingId= route', () => {
    const route = primaryModule('dwg_drawing', '.dwg').route('PROJ1', 'DRAW-2');
    expect(route).toBe('/dwg-takeoff?drawingId=DRAW-2');
    expect(route).not.toContain('docId=');
  });

  it('document-kind PDF still opens in PDF Takeoff', () => {
    expect(primaryModule('document', '.pdf').route('PROJ1', 'DOC-1')).toBe(
      '/takeoff?doc=DOC-1&source=document&tab=measurements',
    );
  });
});

describe('modulesForKind - document-kind BIM offers the convert-on-demand viewer', () => {
  it('returns only the ?docId= BIM viewer for a document-kind IFC', () => {
    const mods = modulesForKind('document', '.ifc');
    expect(mods).toHaveLength(1);
    expect(mods[0]!.route('PROJ1', 'DOC-123')).toBe('/projects/PROJ1/bim?docId=DOC-123');
  });

  it('a real bim_model row keeps its full module menu (viewer + explorer + clash)', () => {
    const mods = modulesForKind('bim_model', '.ifc');
    expect(mods.length).toBeGreaterThan(1);
    expect(mods[0]!.route('PROJ1', 'MODEL-7')).toBe('/projects/PROJ1/bim/MODEL-7');
  });
});
