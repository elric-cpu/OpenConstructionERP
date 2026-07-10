# OpenConstructionERP documentation

OpenConstructionERP is an open, self-hosted platform for construction estimating and project delivery. It covers the whole job in one place: build a bill of quantities, take off quantities from drawings and models, price the work against national cost bases, turn a BIM model into cost and carbon, run a tender, plan and control the programme, and capture what happens on site. It is modular, so you enable only the parts you need, and more than 110 modules ship in the box.

This is the written documentation. If you prefer to watch first, the project README links a short walkthrough video. If you just want to try it, install the desktop app or run `pip install openconstructionerp`, then sign in with the demo account and open a sample project.

## Start here

New to the platform? Read the [User guide](./user-guide/README.md). It walks through the main end to end workflows, one short page each, in the order most teams meet them: from a first estimate to a priced model, a tender, a live programme, and site records.

Looking for a specific capability? The [Module ecosystem overview](./modules/README.md) lists every module grouped by area, with a one line description, so you can see the full breadth and jump to what you need.

Want to extend or build on the platform? The [Platform and builder guide](./platform/README.md) explains the module system and how to ship your own module without editing the core.

## User guide

Each page explains what a feature is for, when to reach for it, the steps to use it, and how it connects to the rest of the platform.

- [Estimating and the bill of quantities](./user-guide/estimating-and-boq.md) - build a priced BOQ, from a rough order of magnitude to a full tender submission.
- [Quantity takeoff from drawings and models](./user-guide/quantity-takeoff.md) - measure from PDFs, DWGs and BIM models and push the numbers into the BOQ.
- [BIM to cost and carbon (5D and 6D)](./user-guide/bim-to-cost-and-carbon.md) - convert a model to structured quantities, price it over time, and account for its carbon.
- [World cost bases and multi-base comparison](./user-guide/world-cost-bases.md) - national cost databases, currency-aware pricing, and price spread across regions.
- [Design options comparison](./user-guide/design-options.md) - upload competing design variants and weigh them on priced BOQ and cost per option.
- [Tendering and bid comparison](./user-guide/tendering-and-bids.md) - package the work, invite subcontractors, and compare bids side by side.
- [Planning and cost control](./user-guide/planning-and-cost-control.md) - 4D schedule, 5D cost model, earned value, forecasts and cash flow.
- [Field and site operations](./user-guide/field-and-site.md) - daily diary, inspections, safety, logistics and the record that holds up later.
- [The validation pipeline](./user-guide/validation.md) - the traffic-light checks that keep an estimate clean and compliant.

## Reference and deeper material

- [Module ecosystem overview](./modules/README.md) - the full module set, grouped by area.
- [Platform and builder guide](./platform/README.md) - the developer story: the module loader, manifests, events, hooks, and the first-module tutorial.
- [Module development quickstart](./module-development/quickstart.md) and the [BOQ importer plugin walkthrough](./module-development/boq-importer-plugin.md) - worked examples for building a module.
- [Importing your own cost database](./cost-database-import.md) - load your rates from Excel or CSV.
- [Architecture decision records](./adr/README.md) - why the platform is built the way it is, including the decision to convert all CAD and BIM through the DDC canonical pipeline rather than parse IFC natively.
- [Linux install guide](./INSTALL_LINUX.md) and [desktop install guide](./desktop/INSTALL.md) - setup for servers and workstations.

## How the platform fits together

Everything reads from and writes to one canonical data layer, so the modules are not islands. A quantity you take off a drawing becomes a BOQ position. That position carries a classification code, a rate from a cost base, and a link back to the model element it came from. The same position feeds the schedule as a 4D activity, the cost model as a 5D cost, and the carbon account as a 6D figure. A validation report scores it, a tender package draws from it, and a report exports it. When you learn one workflow, the next one already speaks the same language.

Two principles run through all of it. First, the platform is open and your data is yours, exportable in open formats such as GAEB XML, Excel and JSON, with no lock-in. Second, where the platform uses AI to suggest a quantity, a classification or a rate, it always shows a confidence score and waits for a person to confirm. Nothing is applied to your estimate automatically.
