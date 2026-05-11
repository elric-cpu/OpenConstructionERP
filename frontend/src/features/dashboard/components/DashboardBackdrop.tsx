// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// Layered dashboard backdrop. Rewritten 2026-05-11 to match styles-lab
// variant 03 "Dot Grid + Spotlight" — the design-system recommendation.
// Previous version layered 4 aurora blobs + vignette + noise + grid; this
// version keeps the clean Apple-current feel: a blue radial spotlight at
// the top + an edge-masked dot grid + a pointer-tracked highlight.
//
// All layers are absolutely positioned inside a relative wrapper and
// rendered behind page content via -z-10. pointer-events: none so they
// never intercept clicks.

import { useEffect, useRef } from 'react';

export function DashboardBackdrop() {
  // Pointer-tracked highlight — a soft accent halo follows the cursor.
  // Cheap: one CSS variable update on pointermove, no JS reflow.
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onMove = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      el.style.setProperty('--mx', `${x}%`);
      el.style.setProperty('--my', `${y}%`);
    };
    el.addEventListener('pointermove', onMove);
    return () => el.removeEventListener('pointermove', onMove);
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden="true"
      /* fixed (not absolute) so the backdrop bleeds through the parent
         <main> padding and covers the entire viewport while the dashboard
         is mounted. Other routes don't render this component, so it
         disappears on navigation. */
      className="dash-backdrop pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      style={{ '--mx': '50%', '--my': '40%' } as React.CSSProperties}
    >
      {/* Layer 1 — base surface wash. */}
      <div className="absolute inset-0 bg-surface-secondary" />

      {/* Layer 2 — top radial spotlight (Apple-hero blue halo).
          Spreads from above the page; gives content a focal point. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(80% 55% at 50% -10%, rgba(0,113,227,0.20) 0%, rgba(0,113,227,0.06) 35%, rgba(0,113,227,0) 65%)',
        }}
      />

      {/* Layer 3 — pointer-tracked highlight. Subtle, indigo. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(circle 380px at var(--mx) var(--my), rgba(99, 102, 241, 0.05), transparent 70%)',
          transition: 'background 0.2s ease',
        }}
      />

      {/* Layer 4 — subtle dot grid (rgba 16%, 0.9px, 24px step).
          Matches styles-lab "Dot Grid (subtle)" exactly. Edge-masked so
          dots fade away near the viewport perimeter. */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'radial-gradient(circle, rgba(60,60,67,0.16) 0.9px, transparent 0.9px)',
          backgroundSize: '24px 24px',
          maskImage:
            'radial-gradient(ellipse 80% 75% at center, #000 25%, transparent 95%)',
          WebkitMaskImage:
            'radial-gradient(ellipse 80% 75% at center, #000 25%, transparent 95%)',
        }}
      />

      {/* Dark-mode overrides — flip the spotlight and dot colors so the
          backdrop reads correctly on deep blue-gray surfaces. */}
      <style>{`
        [data-theme="dark"] .dash-backdrop > div:nth-child(2) {
          background: radial-gradient(80% 55% at 50% -10%, rgba(59,130,246,0.18) 0%, rgba(59,130,246,0.05) 35%, rgba(59,130,246,0) 65%);
        }
        [data-theme="dark"] .dash-backdrop > div:nth-child(4) {
          background-image: radial-gradient(circle, rgba(180,184,196,0.10) 0.9px, transparent 0.9px);
        }
      `}</style>
    </div>
  );
}
