/**
 * Field-worker mobile shell — DESIGN-STAGE SKELETON.
 *
 * Implements the bottom-nav + thumb-zone layout described in
 * `docs/architecture/FIELD_WORKER_MOBILE_DESIGN.md` §6. This file is a
 * structural placeholder so the `/field` route in `App.tsx` lazy-loads
 * a real chunk; the four tabs render `null` until the pilot endpoints
 * land.
 *
 * What lives HERE:
 *   - Full-viewport shell with no sidebar / no desktop AppLayout
 *   - Bottom-nav with 4 fixed tabs (My Today / Capture / Crew / Profile)
 *   - 56 px sticky header with current project name + help button
 *   - Safe-area-aware padding via `env(safe-area-inset-*)`
 *
 * What lives ELSEWHERE / not yet:
 *   - PIN-redemption screen at `/field/{token}` → separate `FieldAuthPage`
 *     (TODO Day 3, design doc §9)
 *   - Today / Capture / Crew tab bodies → separate per-tab files once the
 *     `/api/v1/field/*` endpoints exist (TODO Day 2, design doc §9)
 *   - Offline write queue helper `submitFieldMutation` → already has its
 *     substrate at `frontend/src/shared/lib/offlineStore.ts`, wiring
 *     deferred to pilot.
 *
 * Touch-target rule: every interactive element on this shell stays at
 * ≥48×48 px (WCAG 2.2 SC 2.5.8 AAA + Apple HIG + Material 3). Validated
 * by the QA crawler skill's axe-core integration.
 */

import { useState } from 'react';
import { Clock, Camera, Users, User } from 'lucide-react';

type FieldTab = 'today' | 'capture' | 'crew' | 'profile';

interface FieldTabDef {
  key: FieldTab;
  label: string;
  Icon: typeof Clock;
}

const TABS: readonly FieldTabDef[] = [
  { key: 'today', label: 'Today', Icon: Clock },
  { key: 'capture', label: 'Capture', Icon: Camera },
  { key: 'crew', label: 'Crew', Icon: Users },
  { key: 'profile', label: 'Me', Icon: User },
] as const;

export function FieldShellPage() {
  const [tab, setTab] = useState<FieldTab>('today');

  return (
    <div
      className="flex min-h-screen flex-col bg-white"
      style={{
        // iOS safe-area inset so the bottom nav doesn't sit under the
        // home indicator on iPhone X+ in standalone PWA mode.
        paddingBottom: 'env(safe-area-inset-bottom)',
        paddingTop: 'env(safe-area-inset-top)',
      }}
    >
      {/* Sticky 56 px header — project name placeholder. */}
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4">
        <span className="truncate text-base font-semibold text-slate-900">
          {/* TODO pilot: surface caller.active_project.name */}
          Field — Project pending
        </span>
        <button
          type="button"
          aria-label="Help"
          className="flex h-11 w-11 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
        >
          ?
        </button>
      </header>

      {/* Tab body — empty until pilot endpoints land. */}
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-8 text-center text-slate-400">
        {/* TODO Day 2/3 — render per-tab content. See design doc §8. */}
        Tab "{tab}" — coming in pilot
      </main>

      {/* Bottom nav — fixed 64 px, 4 tabs. */}
      <nav
        className="sticky bottom-0 flex border-t border-slate-200 bg-white"
        aria-label="Field navigation"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        {TABS.map(({ key, label, Icon }) => {
          const active = key === tab;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              aria-current={active ? 'page' : undefined}
              aria-label={label}
              className={`flex h-16 flex-1 flex-col items-center justify-center gap-1 text-xs ${
                active ? 'text-sky-600' : 'text-slate-500'
              }`}
            >
              <Icon size={28} aria-hidden="true" />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}

export default FieldShellPage;
