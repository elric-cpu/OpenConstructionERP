import { describe, it, expect } from 'vitest';

import { isPdfDocument } from '../PlaceOnMapPicker';
import type { DocumentItem } from '@/features/documents/api';

// Regression guard for the "Place on map" picker crash:
// "Cannot read properties of undefined (reading 'toLowerCase')".
//
// The picker used to read a `filename` field that the CDE document API
// does not return (it returns `name`), so isPdfDocument dereferenced an
// undefined value and the whole geo page threw on modal open. These tests
// pin the classification down to the real `name`/`mime_type` fields and,
// crucially, that a missing name never throws.

const doc = (over: Partial<DocumentItem>): DocumentItem => ({ ...over } as DocumentItem);

describe('isPdfDocument', () => {
  it('classifies by .pdf name extension', () => {
    expect(isPdfDocument(doc({ name: 'A_book_of_house_plans.pdf' }))).toBe(true);
  });

  it('is case-insensitive on the extension', () => {
    expect(isPdfDocument(doc({ name: 'PLAN.PDF' }))).toBe(true);
  });

  it('classifies by application/pdf mime type even without a .pdf name', () => {
    expect(isPdfDocument(doc({ name: 'drawing', mime_type: 'application/pdf' }))).toBe(true);
  });

  it('is case-insensitive on the mime type', () => {
    expect(isPdfDocument(doc({ name: 'drawing', mime_type: 'APPLICATION/PDF' }))).toBe(true);
  });

  it('rejects non-PDF documents (e.g. CAD models)', () => {
    expect(isPdfDocument(doc({ name: 'tower.rvt', mime_type: 'application/octet-stream' }))).toBe(
      false,
    );
  });

  it('does not throw when name is undefined (the original crash)', () => {
    expect(() => isPdfDocument(doc({ name: undefined as unknown as string }))).not.toThrow();
    expect(isPdfDocument(doc({ name: undefined as unknown as string }))).toBe(false);
  });

  it('does not throw on a bare document object', () => {
    expect(() => isPdfDocument({} as DocumentItem)).not.toThrow();
    expect(isPdfDocument({} as DocumentItem)).toBe(false);
  });
});
