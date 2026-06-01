# OpenConstructionERP

**Open-source construction cost estimation — BOQ, AI matching, CAD/BIM takeoff.**

> ### ▶ After `pip install`, type one command: **`openconstructionerp`**
>
> That's the only thing you need to remember. It prints a welcome,
> asks **press `o` + Enter** to open the app in your browser, then
> starts the server at **http://127.0.0.1:8080** (and shows a login).

---

## Install

```bash
pip install openconstructionerp
```

Python 3.12+ required. That's it — no Docker, no Postgres, no Redis.

## First run

```bash
openconstructionerp
```

This single command:

1. Starts an embedded PostgreSQL database in your home data folder (no Docker, nothing to install)
2. Seeds demo data (projects, BOQs, cost catalogues)
3. Starts the API + UI at **http://127.0.0.1:8080**
4. Prints demo login credentials

No config files. No environment variables. It just works.

> **If `openconstructionerp` is not found** right after install, pip most likely
> put the launcher in a Scripts folder that is not on your PATH (this is common
> on Windows). Run it through Python instead. This works from any folder and is
> the exact same app:
>
> ```bash
> python -m openconstructionerp
> ```

## Subsequent runs

```bash
openconstructionerp
```

Same command every time. Your data persists between runs.

## Other commands

```bash
openconstructionerp init-db    # create the local database
openconstructionerp serve      # start the server
openconstructionerp doctor     # health check if anything looks wrong
openconstructionerp welcome    # re-print the welcome screen
```

## CLI reference

```bash
openconstructionerp serve   [--host HOST] [--port PORT] [--data-dir DIR] [--open] [--quiet]
openconstructionerp init-db [--data-dir DIR]    # Create local SQLite DB + data dirs
openconstructionerp doctor  [--port PORT]       # Run installation health checks
openconstructionerp seed    [--demo]            # Load demo project data
openconstructionerp version                     # Show version
```

## What you get

- **BOQ editor** — hierarchical bill of quantities with assemblies, formulas, multi-currency
- **Cost database** — import your own rates (Excel/CSV) or use the bundled example templates
- **AI estimation** — vector search matches line items to historical cost data
- **CAD/BIM takeoff** — quantities from DWG/DXF and IFC/Revit (via DDC, no IfcOpenShell)
- **4D / 5D** — cost-loaded schedule, earned value (SPI/CPI), cash-flow, what-if scenarios
- **Validation** — DIN 276, GAEB, NRM, MasterFormat rule packs flag issues at import
- **Reporting** — PDF/Excel exports, dashboards, BCF issue exchange

## Configuration (optional)

Everything works with zero config. To customize, pass flags or set environment variables:

```bash
openconstructionerp serve --port 9000 --data-dir /var/lib/oce

# Or via environment:
DATABASE_URL=postgresql+asyncpg://user:pass@host/db   # Use Postgres instead of SQLite
OE_CLI_PORT=9000                                       # Change the port
OE_CLI_DATA_DIR=/var/lib/oce                           # Change the data location
```

## Links

- Docs: https://openconstructionerp.com
- Issues: https://github.com/DataDrivenConstruction/OpenConstructionERP/issues
- Source: https://github.com/DataDrivenConstruction/OpenConstructionERP

## License

AGPL-3.0-or-later. Commercial licensing available — contact info@datadrivenconstruction.io
