# useLLMRun() shared-hook proposal — STILL DEFERRED (2026-05-24)

Deferred from prior-agent audit (2026-05-21). The hook unifies
AdvisorPage's useState/try-catch pattern with QuickEstimatePage's five
useMutation blocks (adds AbortController, optional focus-restore for
a11y finding #4). Owner: frontend functional-polish + a11y wave. Wait
for in-flight surfaces (example-prompts, history) to land before
extracting, otherwise the rebase surface is large.
