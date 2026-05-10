// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// errorLogger contract tests — focused on the bug-report flow.
//
// Background: GitHub issue #115 was filed because a benign 404 from
// the BIM auto-detect path got captured as the "last error" by the
// in-app bug-report dialog. The page handled the 404 gracefully via
// toast, but the warning entry still leaked into the report template.
//
// `getLastError()` now prefers the most recent level=error entry over
// warning-level noise. These tests lock that contract in.

import { describe, it, expect, beforeEach } from 'vitest';
import { getLastError, logApiError, clearErrorLog } from './errorLogger';

describe('errorLogger.getLastError — bug-report payload selection', () => {
  beforeEach(() => {
    clearErrorLog();
  });

  it('returns null when nothing has been logged', () => {
    expect(getLastError()).toBeNull();
  });

  it('returns the most recent entry when only warnings exist', () => {
    logApiError('/v1/foo/', 404, 'not found');
    logApiError('/v1/bar/', 404, 'not found');
    const last = getLastError();
    expect(last).not.toBeNull();
    expect(last!.message).toContain('/v1/bar/');
  });

  it('prefers a level=error entry over a more recent warning', () => {
    // 500 → level=error
    logApiError('/v1/important/', 500, 'oops');
    // 404 → level=warning, but the 500 was the real problem
    logApiError('/v1/bim_hub/abc-123/', 404, 'not found');
    const last = getLastError();
    expect(last!.message).toContain('/v1/important/');
    expect(last!.message).not.toContain('/v1/bim_hub/');
  });

  it('falls back to most recent warning when no error exists in the window', () => {
    logApiError('/v1/some/', 404, 'not found');
    const last = getLastError();
    expect(last!.message).toContain('/v1/some/');
  });
});
