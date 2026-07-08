// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
import { describe, expect, it } from 'vitest';
import {
  isEmptyStatement,
  kindAccentClass,
  resourceStatementCsvName,
  statementCurrency,
} from './api';

describe('resourceStatementCsvName', () => {
  it('builds a stable, safe filename from a project id', () => {
    const name = resourceStatementCsvName('3fa85f64-5717-4562-b3fc-2c963f66afa6');
    expect(name.startsWith('resource-statement-')).toBe(true);
    expect(name.endsWith('.csv')).toBe(true);
  });

  it('strips unsafe path characters', () => {
    const name = resourceStatementCsvName('abc/../../x');
    expect(name).not.toContain('/');
    expect(name).not.toContain('..');
    expect(name).toBe('resource-statement-abcx.csv');
  });

  it('falls back to a placeholder for an empty id', () => {
    expect(resourceStatementCsvName('')).toBe('resource-statement-project.csv');
  });
});

describe('isEmptyStatement', () => {
  it('treats null / missing groups as empty', () => {
    expect(isEmptyStatement(null)).toBe(true);
    expect(isEmptyStatement(undefined)).toBe(true);
    expect(isEmptyStatement({ groups: [] })).toBe(true);
  });

  it('treats groups whose lines are all empty as empty', () => {
    expect(
      isEmptyStatement({
        groups: [
          { kind: 'labor', kind_i18n_key: '', label: '', line_count: 0, total_cost: '0', total_hours: null, lines: [] },
        ],
      }),
    ).toBe(true);
  });

  it('is not empty when a group carries a line', () => {
    expect(
      isEmptyStatement({
        groups: [
          {
            kind: 'material',
            kind_i18n_key: '',
            label: '',
            line_count: 1,
            total_cost: '10',
            total_hours: null,
            lines: [{ kind: 'material', kind_i18n_key: '', name: 'Brick', unit: 'pcs', quantity: '10', cost: '10', position_count: 1 }],
          },
        ],
      }),
    ).toBe(false);
  });
});

describe('statementCurrency', () => {
  it('returns a set currency code', () => {
    expect(statementCurrency({ currency: 'EUR' })).toBe('EUR');
  });

  it('returns undefined for an unset or blank currency', () => {
    expect(statementCurrency({ currency: '' })).toBeUndefined();
    expect(statementCurrency({ currency: '   ' })).toBeUndefined();
    expect(statementCurrency(null)).toBeUndefined();
  });
});

describe('kindAccentClass', () => {
  it('maps known kinds to accent classes', () => {
    expect(kindAccentClass('labor')).toContain('oe-blue');
    expect(kindAccentClass('material')).toContain('success');
    expect(kindAccentClass('machinery')).toContain('warning');
  });

  it('falls back to a neutral class for an unknown kind', () => {
    expect(kindAccentClass('mystery')).toBe('text-content-tertiary');
  });
});
