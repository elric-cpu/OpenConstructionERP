# a11y follow-ups for QuickEstimatePage.tsx — STILL OPEN (2026-05-24)

Deferred from prior-agent audit (2026-05-21). Backend cost-tracking part
of the same audit shipped in v4.7.x (see migration v3128_ai_estimate_cost_usd).
The 10 frontend a11y findings (4×P1: textarea label, aria-live on
LoadingState, role="alert" on error banners, focus management after
submit; 6×P2: aria-describedby on disabled submit, tablist ARIA, label
htmlFor wiring, color-only banners, decorative-icon aria-hidden,
SaveDialog focus trap + Escape) remain open. Owner: frontend a11y wave.
