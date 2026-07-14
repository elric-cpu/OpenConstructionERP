# Benson Operations

Benson Home Solutions' focused construction operating system. This application is a full Benson-specific rewrite maintained in a sparse branch of the OpenConstructionERP repository so upstream history, AGPL attribution, and selected reference implementations remain available without shipping the global 161-module product.

## Operating profile

- English, USD, imperial units, United States, Oregon, Harney County
- CRM, estimating, jobs, schedules, field records, documents, procurement, equipment, quality, safety, service, invoicing, and portals
- QuickBooks Online is the accounting system of record
- AI actions route through an authenticated Free Claude Code gateway and NVIDIA NIM
- Agents may mutate internal records within role permissions; external sends, financial commitments, signatures, destructive deletes, and legal commitments require human confirmation

## Development

```bash
cd api
uv sync --extra dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

cd ../web
npm ci
npm run dev -- --host 0.0.0.0
```

Use `benson-ai` rather than `localhost` when sharing local URLs.

## License

AGPL-3.0-or-later. See the repository root for upstream copyright and attribution.
