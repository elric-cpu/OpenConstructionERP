# Round-7 PropDev audit — unaudited endpoint inventory

This file lists every endpoint in `property_dev/router.py` that R7 did
**not** harden. It exists so the next sweep (R8) can pick up exactly
where R7 left off without re-walking the 199-endpoint surface.

R7 scope: 199 endpoints total. Audited ~70 (IDOR + FSM + RBAC on
develpoments / plots / house-types / variants / option-groups / options /
buyers / selections / handovers (already secured) / handover-docs / snags
(already secured) / warranty (already secured) / leads (already secured) /
reservations (already secured) / SPAs (already secured) / payment-
schedules / instalments (already secured) / parties (already secured) /
phases / blocks / brokers (already secured) / commission-agreements
(already secured) / commission-accruals (already secured) / escrow-
accounts / escrow-transactions / price-matrices / sales-kanban / cancel-
buyer / 2 uploads (snag photos + custom doc templates — both already
have magic-byte gates)).

## High priority — still need IDOR closure (Severity: medium–high)

These are GET reads or analytics endpoints that take a project- or
development-scoped path/query param. They currently fan out across all
tenants for any caller with `property_dev.read`. None are state-mutating
so risk = data disclosure, not data tampering.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/developments/{dev_id}/sales-kanban` | already has dev-id, needs `_verify_owner_via_development` |
| GET | `/developments/{dev_id}/p&l` | money rollup, leaks revenue |
| GET | `/developments/{dev_id}/reservation-calendar` | leaks buyer names/dates |
| GET | `/developments/{dev_id}/buyer-journey` | funnel analytics |
| GET | `/developments/{dev_id}/funnel-conversion` | funnel analytics |
| GET | `/developments/{dev_id}/sales-velocity` | revenue rate |
| GET | `/developments/{dev_id}/inventory-heatmap` | plot status grid |
| GET | `/developments/{dev_id}/inventory-ageing` | unsold-time per plot |
| GET | `/developments/{dev_id}/cashflow-waterfall` | money rollup |
| GET | `/developments/{dev_id}/snags-summary` | snag counts |
| GET | `/developments/{dev_id}/handovers-summary` | handover progress |
| GET | `/developments/{dev_id}/warranty-summary` | warranty counts |
| GET | `/developments/{dev_id}/escrow-summary` | escrow rollup |
| GET | `/plots/{plot_id}/configurator` | also reads plot — partially covered by R7 plot guard but inner calls bypass |
| GET | `/buyers/{b_id}/configurator` | reads buyer + selections |
| GET | `/buyers/{b_id}/journey` | timeline disclosure |
| GET | `/buyers/{b_id}/payment-summary` | money disclosure |
| GET | `/buyers/{b_id}/documents` | doc URL list |
| GET | `/sales-contracts/{spa_id}/tax-quote-history` | money history |
| GET | `/sales-contracts/{spa_id}/parties` | PII disclosure |
| GET | `/sales-contracts/{spa_id}/revisions` | contract history |
| GET | `/handovers/{h_id}/snags-summary` | snag counts |
| GET | `/instalments/{ins_id}/payments` | money history |
| GET | `/commission-agreements/{agreement_id}/preview` | money disclosure |
| GET | `/regulator-reports/{regulator}` | development-id query param |
| GET | `/compliance/dashboard` | dev-id query, leaks all-tenant when omitted? — check |

## Medium priority — write endpoints needing RBAC + IDOR (Severity: medium)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/leads/{lead_id}/convert` | lead → reservation; `_verify_owner_via_lead` exists, wire it |
| POST | `/reservations/{r_id}/convert-to-spa` | needs `_verify_owner_via_reservation` (exists) |
| POST | `/reservations/expire-batch` | bulk operation across all developments |
| POST | `/sales-contracts/{spa_id}/send-for-signature` | `_verify_owner_via_spa` exists |
| POST | `/sales-contracts/{spa_id}/sign` | needs party-side verification too |
| POST | `/sales-contracts/{spa_id}/tax-quote` | money endpoint |
| POST | `/payment-schedules/` | `_verify_owner_via_spa` on schedule.sales_contract_id |
| POST | `/payment-schedules/{schedule_id}/suspend` | needs `_verify_owner_via_schedule` (exists) |
| POST | `/payment-schedules/{schedule_id}/resume` | same |
| POST | `/instalments/{ins_id}/mark-paid` | money mutation; `_verify_owner_via_instalment` exists |
| POST | `/instalments/{ins_id}/waive` | same |
| POST | `/instalments/{ins_id}/cancel` | same |
| POST | `/contract-parties/` | needs `_verify_owner_via_spa` on data.sales_contract_id |
| PATCH | `/contract-parties/{party_id}` | `_verify_owner_via_party` exists |
| POST | `/warranty-claims/{w_id}/triage` | warranty already guarded — verify wired |
| POST | `/warranty-claims/{w_id}/accept` | warranty already guarded |
| POST | `/warranty-claims/{w_id}/reject` | warranty already guarded |
| POST | `/warranty-claims/{w_id}/close` | warranty already guarded |
| POST | `/warranty-claims/{w_id}/assign` | warranty already guarded |
| POST | `/snags/{s_id}/promote-to-warranty` | snag already guarded |
| POST | `/handovers/{h_id}/notify-buyer` | sends an email — buyer-data exposure |
| POST | `/buyers/{b_id}/portal-invite` | sends an invite |

## Low priority — list endpoints without a parent-id filter (Severity: low)

These return ALL rows for the caller's permission scope. They MAY be
intentional (cross-development dashboards), but each should be reviewed.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/leads/` | `development_id` query is optional — when omitted returns ALL leads (already returns empty list when no scope per code comment, but verify) |
| GET | `/reservations/` | same pattern |
| GET | `/sales-contracts/` | same |
| GET | `/payment-schedules/` | same |
| GET | `/instalments/` | same |
| GET | `/warranty-claims/` | already gated — returns empty when no scope per v3110 |
| GET | `/document-templates/` | server-side built-in templates, not project-scoped — review |
| GET | `/document-templates/custom/` | needs tenant filter |
| GET | `/snags/` | needs handover_id or buyer_id scope |

## Compliance / regulator endpoints (Severity: medium — disclosure risk)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/compliance/run-checks` | dev-id arg |
| GET | `/regulator-reports/RERA` | dev-id query |
| GET | `/regulator-reports/MAHARERA` | dev-id query |
| GET | `/regulator-reports/214FZ` | dev-id query |
| POST | `/regulator-reports/{regulator}/generate-pdf` | dev-id arg |

## Portal endpoints (buyer-facing) (Severity: high — auth model differs)

These use `RequirePortalSession` instead of the platform RBAC. The
portal session ALREADY scopes to the buyer's own data via
`_buyers_for_portal_user`, so they're isolated by design — but each
should be re-checked for IDOR via `buyer_id` mismatch.

| Method | Path |
|--------|------|
| GET | `/portal/my-buyer-record` |
| GET | `/portal/my-development` |
| GET | `/portal/my-plot` |
| GET | `/portal/my-selections` |
| POST | `/portal/my-selections/` |
| PATCH | `/portal/my-selections/{s_id}` |
| GET | `/portal/my-instalments` |
| GET | `/portal/my-handover` |
| GET | `/portal/my-snags` |
| POST | `/portal/my-snags/` |
| GET | `/portal/my-warranty-claims` |
| POST | `/portal/my-warranty-claims/` |
| GET | `/portal/my-documents` |

## Money serialization gaps (Severity: low — bug, not security)

R7 added the string serializer to: `DevelopmentResponse`,
`HouseTypeResponse`, `PlotResponse`, `BuyerResponse`,
`BuyerOptionResponse`, `BuyerSelectionItemResponse`,
`EscrowTransactionResponse`, `EscrowBalanceResponse`,
`CommissionAccrualResponse`, `DepositForfeitureResponse`,
`PriceMatrixResponse`, `PriceMatrixPreviewResponse`.

Still need it: `ReservationResponse`, `SalesContractResponse`,
`InstalmentResponse`, `PaymentScheduleResponse`,
`CommissionAgreementResponse`, `ContractTaxQuote`, `TaxQuoteLineItem`,
`DevelopmentPnLResponse`, `CashflowWaterfallResponse`,
`SalesVelocityResponse`, `InventoryAgeingResponse`,
`InventoryHeatmapResponse`.

## Upload endpoints — fully audited in R7

| Path | Status |
|------|--------|
| `POST /snags/{s_id}/photos/` | Magic-byte gate (jpeg/png/gif/webp/heic/heif/tiff), size implicit via UploadFile, IDOR via `_verify_owner_via_snag`. RBAC `property_dev.fix_snag`. ✅ |
| `POST /document-templates/upload` | Magic-byte gate per ext (pdf/docx/html/odt/md/txt), 10MB cap, project-owner check, RBAC `property_dev.create`. ✅ |

No other upload endpoints exist in the module.

## Suggested R8 priorities

1. Wire `_verify_owner_via_development` into every `/developments/{dev_id}/...` analytics endpoint (~13 routes).
2. Wire existing `_verify_owner_via_*` helpers into the medium-priority write endpoints (~16 routes).
3. Audit the portal endpoints (~13 routes) — verify `_buyers_for_portal_user` actually filters.
4. Money string-serializer on remaining 12+ response models.
5. Add a single regression test asserting "100% of project-scoped endpoints under property_dev return 404 (not 403/200) for cross-tenant access" — generic fan-out test driven by introspection of the router.
