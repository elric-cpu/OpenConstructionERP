/**
 * Tests for the BIM filter-report helpers (B5): the quantity summariser and
 * the printable-HTML builder. These mirror the backend BOQ exporter's
 * grouping + alias scan, so the on-screen / printed numbers match the Excel.
 */
import { describe, it, expect } from 'vitest';
import type { BIMElementData } from '@/shared/ui/BIMViewer';
import { summariseBimQuantities, round3 } from '../boqSummary';
import { escapeHtml, buildReportHtml } from '../printReport';

const els = [
  { id: 'wa', element_type: 'IfcWall', storey: 'L1', quantities: { area_m2: 10, volume_m3: 2 } },
  { id: 'wb', element_type: 'IfcWall', storey: 'L2', quantities: { area: 5, NetVolume: 1 } }, // aliases
  { id: 'wbad', element_type: 'IfcWall', storey: 'L1', quantities: { area_m2: true } }, // bool rejected
  { id: 'sl', element_type: 'IfcSlab', storey: 'L1', quantities: { area_m2: 50, volume_m3: 12.5, weight_kg: '300' } },
  { id: 'bm', element_type: 'IfcBeam', storey: 'L1', quantities: { length_m: 8 } },
] as unknown as BIMElementData[];

describe('round3', () => {
  it('rounds float dust', () => {
    expect(round3(0.1 + 0.2)).toBe(0.3);
  });
});

describe('summariseBimQuantities by element_type', () => {
  const s = summariseBimQuantities(els, 'element_type');

  it('sorts groups and counts them', () => {
    expect(s.rows.map((r) => r.key)).toEqual(['IfcBeam', 'IfcSlab', 'IfcWall']);
    expect(s.rows.find((r) => r.key === 'IfcWall')!.count).toBe(3);
  });

  it('sums quantities, scanning aliases and rejecting a bool', () => {
    const wall = s.rows.find((r) => r.key === 'IfcWall')!;
    // [area, volume, length, weight]; alias area on wb=5, bool on wbad=0 -> 15 area, 3 volume
    expect(wall.quantities).toEqual([15, 3, 0, 0]);
    const slab = s.rows.find((r) => r.key === 'IfcSlab')!;
    expect(slab.quantities).toEqual([50, 12.5, 0, 300]); // string '300' coerced
  });

  it('totals across all groups', () => {
    expect(s.totals.count).toBe(5);
    expect(s.totals.quantities).toEqual([65, 15.5, 8, 300]);
  });
});

describe('summariseBimQuantities by storey', () => {
  const s = summariseBimQuantities(els, 'storey');
  it('groups and sums per storey', () => {
    expect(s.rows.map((r) => r.key)).toEqual(['L1', 'L2']);
    const l1 = s.rows.find((r) => r.key === 'L1')!;
    expect(l1.count).toBe(4);
    expect(l1.quantities).toEqual([60, 14.5, 8, 300]);
  });
});

describe('printReport helpers', () => {
  it('escapes HTML special characters', () => {
    expect(escapeHtml('<b>&"\'')).toBe('&lt;b&gt;&amp;&quot;&#39;');
  });

  it('builds a report document with the title, scope, and a total', () => {
    const summary = summariseBimQuantities(els, 'element_type');
    const html = buildReportHtml({
      title: 'Quantity report - Tower A',
      scopeLabel: 'Whole model',
      generatedOn: '2026-06-29 10:00',
      sections: [{ heading: 'By element type', groupLabel: 'Element type', summary }],
    });
    expect(html).toContain('Quantity report - Tower A');
    expect(html).toContain('Whole model');
    expect(html).toContain('By element type');
    expect(html).toContain('65'); // total area appears in the TOTAL row
    expect(html.startsWith('<!DOCTYPE html>')).toBe(true);
  });
});
