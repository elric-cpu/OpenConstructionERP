# Contributors

OpenConstructionERP is authored and owned by DataDrivenConstruction (see
[AUTHORS.md](AUTHORS.md)). The people listed here are contributors: they have sent
patches, fixes and feedback that made the project better. They are not authors of the
project, and authorship and copyright remain with DataDrivenConstruction.

Thank you to everyone who has contributed.

Almost everyone listed here helped by reporting a bug, asking a question or proposing an
idea, not by shipping code into the project. When a fix does arrive as a patch, we
normally reimplement it ourselves rather than merging the change as-is. That keeps one
reviewed source of truth for a codebase that many companies run in production, and it
avoids taking in code we have not written ourselves, which is the safer path on security.
So the credit below is for the report or the idea that led to a fix, and the
implementation is our own.

- **skolodi** ([@skolodi](https://github.com/skolodi)): issue reports and field feedback
  on the BOQ AI assistant, and reported that a single budget could mix currencies and that
  an exchange rate could be entered the wrong way round
  ([#111](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/111)).
- **Mourtadha Diop** ([@Mourdi59](https://github.com/Mourdi59)): fixed three BIM viewer
  bugs ([#159](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/159)),
  COLLADA namespace-prefix serialisation in `ifc_processor`, defence-in-depth regex
  tolerance in `ElementManager`, and `degraded` model status surfacing in the viewer UI.
  Later raised ideas for driving BOQ quantities from live BIM parameters, surfacing real
  server errors on Excel paste, and resolving linked elements per model in multi-model
  setups ([#206](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/206)).
- **rjohny** ([@rjohny55](https://github.com/rjohny55)): multi-area patch set
  ([#161](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/161)),
  defensive guards for the slow-query SQLAlchemy listener and the module-presence probe
  under concurrency, a FieldReport activity-rollup column fix, Qdrant multipart snapshot
  upload so app-container snapshots reach a separate Qdrant container, and three new AI
  providers, Kimi (Moonshot AI), Ollama and vLLM, with custom base URL support for the
  two local backends.
- **Jehad Baniowda** ([@jehadbaniodeh](https://github.com/jehadbaniodeh)): fixed the
  production Docker deployment and the takeoff viewer. The backend image now installs its
  dependencies and starts correctly
  ([#173](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/173)), nginx
  upgrades WebSocket connections so real-time notifications and presence work
  ([#176](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/176)), `.mjs`
  workers are served with the correct MIME type so the PDF takeoff viewer renders
  ([#175](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/175)), the
  upload ceiling is raised to 100M for PDF and CAD drawings
  ([#174](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/174)), and
  takeoff documents open in the in-app viewer instead of a broken download navigation
  ([#172](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/172)).
- **Jérémy Christillin** ([@bvisible](https://github.com/bvisible)): feedback and feature
  proposals for the PDF takeoff module, in-canvas measurement editing and LLM-assisted
  plan reading
  ([#194](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/194)).
- **mohandshamada** ([@mohandshamada](https://github.com/mohandshamada)): issue reports and
  proposals on the converters version-check payload shape
  ([#195](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/195),
  [#196](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/196)), IFC
  zero-elements processing ([#197](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/197)),
  BIM empty-state and upload messaging
  ([#198](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/198)), and
  resumable CAD uploads ([#199](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/199)).
- **leval907** ([@leval907](https://github.com/leval907)): flagged that qdrant-client removed
  its `.search()` API and that the remaining call sites needed migrating to `query_points()`
  ([#201](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/201)).
- **alikhalilx** ([@alikhalilx](https://github.com/alikhalilx)): reported that ERP Chat
  rendered Markdown tables as raw pipe text and pointed at the hand-rolled chat renderers
  ([#224](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/224)), that
  the sidebar greyed out company-wide modules such as CRM and subcontractors even when they
  already held data
  ([#228](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/228)), and
  that the pinned-item tooltip showed a raw placeholder instead of the module name
  ([#229](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/229)).
- **arvildev** ([@arvildev](https://github.com/arvildev)): pointed out that the required
  `POSTGRES_PASSWORD` and `JWT_SECRET` interpolations in the quickstart Docker Compose file
  needed quoting so the YAML parses before the fail-fast checks run
  ([#227](https://github.com/datadrivenconstruction/OpenConstructionERP/pull/227)).
- **Aidan Koetaan** ([@aidankoetaan-tech](https://github.com/aidankoetaan-tech),
  akoetaan@cut.ac.za): proposed a South Africa construction pack and shared a reference
  implementation covering SANS 1200 and ASAQS measurement, CIDB contractor grading, the
  PPPFA 80/20 and 90/10 procurement scoring, infrastructure delivery gates and ZAR VAT. The
  shipped South Africa pack is our own implementation, written from the public standards.
- **expalex1507** ([@expalex1507](https://github.com/expalex1507)): reported that the Docker
  quickstart failed across the Dockerfile, pyproject, the first migration and some missing
  dependencies ([#26](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/26)).
- **consigcody94** ([@consigcody94](https://github.com/consigcody94)): flagged that a
  hardcoded JWT secret default could let tokens be forged in production
  ([#27](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/27)).
- **migfrazao2003** ([@migfrazao2003](https://github.com/migfrazao2003)): reported that
  `make quickstart` failed on frontend TypeScript build errors
  ([#42](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/42)) and that
  the BIM viewer drew geometry that did not match the original IFC model
  ([#53](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/53)).
- **maher00746** ([@maher00746](https://github.com/maher00746)): asked about pricing data
  sources ([#44](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/44))
  and proposed real-time collaboration
  ([#51](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/51)).
- **rrvizuete** ([@rrvizuete](https://github.com/rrvizuete)): reported an error rendering an
  IFC file exported from Civil software
  ([#52](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/52)).
- **candcconsulting** ([@candcconsulting](https://github.com/candcconsulting)): asked how to
  enable a CWICR-style catalog for a UAE sample
  ([#79](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/79)).
- **rashidengg-arch** ([@rashidengg-arch](https://github.com/rashidengg-arch)): an early bug
  report during testing
  ([#87](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/87)).
- **hungdd84** ([@hungdd84](https://github.com/hungdd84)): reported that setting a Gemini API
  key failed because the model id was out of date
  ([#103](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/103)).
- **mkozjak** ([@mkozjak](https://github.com/mkozjak)): reported that the DWG takeoff upload
  button did not work
  ([#110](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/110)).
- **ChristianSantoro** ([@ChristianSantoro](https://github.com/ChristianSantoro)): reported
  that IFC and Revit files would not open in the 3D viewer
  ([#113](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/113),
  [#115](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/115)).
- **online14230** ([@online14230](https://github.com/online14230)): proposed regional data
  support ([#116](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/116)).
- **DevpratikDevelopers** ([@DevpratikDevelopers](https://github.com/DevpratikDevelopers)):
  reported a `p.data.filter is not a function` crash
  ([#122](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/122)).
- **hanisedawy** ([@hanisedawy](https://github.com/hanisedawy)): sent in-app bug reports that
  helped surface viewer and upload issues
  ([#123](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/123),
  [#124](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/124)).
- **sergeilapp** ([@sergeilapp](https://github.com/sergeilapp)): proposed an incoming webhook
  leads module ([#147](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/147)).
- **jyloveqq** ([@jyloveqq](https://github.com/jyloveqq)): reported that the app could not
  install on their setup
  ([#154](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/154)), that
  Match Elements showed no catalogs loaded
  ([#162](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/162)), that the
  indexed vector count did not change after an import
  ([#170](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/170)) and that
  importing a cost database could crash the app
  ([#171](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/171)).
- **JORBDAAG** ([@JORBDAAG](https://github.com/JORBDAAG)): reported BIM viewer problems through
  the in-app reporter
  ([#167](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/167),
  [#168](https://github.com/datadrivenconstruction/OpenConstructionERP/issues/168)).

See the full list of everyone who has contributed:

https://github.com/datadrivenconstruction/OpenConstructionERP/graphs/contributors

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
