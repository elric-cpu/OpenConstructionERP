// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// boqHelpers.convertToBase — multi-currency rebase contract (Issue #88 / #111)
//
// User scenario from issue #111: project base USD, position priced in ARS,
// FX rate "1 ARS = 0.000707 USD" (the inverse of "1 USD = 1415 ARS").
// Without rebase, ARS totals were summed as if they were already USD,
// producing nonsensical figures.

import { describe, it, expect } from 'vitest';
import { convertToBase } from './boqHelpers';

describe('convertToBase — multi-currency rebase', () => {
  const fxRates = [
    { currency: 'ARS', rate: 1 / 1415 }, // 1 ARS = 0.000707 USD
    { currency: 'EUR', rate: 1.08 },     // 1 EUR = 1.08 USD
  ];

  it('returns value unchanged when source currency equals base', () => {
    expect(convertToBase(100, 'USD', 'USD', fxRates)).toBe(100);
  });

  it('returns value unchanged when source currency is empty/undefined', () => {
    expect(convertToBase(100, undefined, 'USD', fxRates)).toBe(100);
    expect(convertToBase(100, '', 'USD', fxRates)).toBe(100);
    expect(convertToBase(100, null, 'USD', fxRates)).toBe(100);
  });

  it('returns value unchanged when base currency is empty/undefined', () => {
    expect(convertToBase(100, 'ARS', undefined, fxRates)).toBe(100);
    expect(convertToBase(100, 'ARS', null, fxRates)).toBe(100);
  });

  it('rebases ARS → USD using provided FX rate', () => {
    // 1415 ARS at rate 0.000707 USD/ARS = ~1.0 USD
    const usd = convertToBase(1415, 'ARS', 'USD', fxRates);
    expect(usd).toBeCloseTo(1.0, 4);
  });

  it('rebases EUR → USD', () => {
    // 100 EUR at rate 1.08 = 108 USD
    expect(convertToBase(100, 'EUR', 'USD', fxRates)).toBeCloseTo(108, 4);
  });

  it('returns value unchanged + warns when FX rate is missing for source', () => {
    // No JPY in fxRates — fallback returns value as-is (graceful degradation)
    const result = convertToBase(100, 'JPY', 'USD', fxRates);
    expect(result).toBe(100);
  });

  it('returns value unchanged when rate is non-finite or non-positive', () => {
    const bad = [
      { currency: 'XXX', rate: 0 },
      { currency: 'YYY', rate: -1 },
      { currency: 'ZZZ', rate: NaN },
    ];
    expect(convertToBase(100, 'XXX', 'USD', bad)).toBe(100);
    expect(convertToBase(100, 'YYY', 'USD', bad)).toBe(100);
    expect(convertToBase(100, 'ZZZ', 'USD', bad)).toBe(100);
  });

  it('returns 0 when value is non-finite', () => {
    expect(convertToBase(NaN, 'ARS', 'USD', fxRates)).toBe(0);
    expect(convertToBase(Infinity, 'ARS', 'USD', fxRates)).toBe(0);
  });

  it('handles empty/missing fxRates list', () => {
    expect(convertToBase(100, 'ARS', 'USD', null)).toBe(100);
    expect(convertToBase(100, 'ARS', 'USD', undefined)).toBe(100);
    expect(convertToBase(100, 'ARS', 'USD', [])).toBe(100);
  });
});
