# User guide

This guide covers the main workflows in OpenConstructionERP, one short page each. The pages are written for the person doing the work, an estimator pricing a job, a site engineer recording what happened, a project controls lead watching cost and time. Each page tells you what the feature is for, when to use it, the steps to do it, and how it connects to the rest of the platform.

You do not have to read them in order, but the order below is the path most projects follow, from a first estimate to a live site.

## The workflows

1. [Estimating and the bill of quantities](./estimating-and-boq.md)
   Build a priced BOQ. Start with a rough order of magnitude, grow it into sections and positions, apply rates and assemblies, add markups, allowances and preliminaries, and export a tender-ready document.

2. [Quantity takeoff from drawings and models](./quantity-takeoff.md)
   Get the numbers. Measure from PDF drawings, from 2D DWGs, and from 3D BIM models, then send the measured quantities straight into BOQ positions.

3. [BIM to cost and carbon (5D and 6D)](./bim-to-cost-and-carbon.md)
   Turn a model into structured, priced quantities without native IFC parsing, track cost over time as 5D, and account for embodied and operational carbon as 6D.

4. [World cost bases and multi-base comparison](./world-cost-bases.md)
   Price the same scope against national cost databases, keep each currency honest, and see how a rate moves from one region to another.

5. [Design options comparison](./design-options.md)
   Load two or more design variants, give each its own priced BOQ, and compare them on total cost, by-trade differences and cost per square metre before you commit.

6. [Tendering and bid comparison](./tendering-and-bids.md)
   Package priced scope, invite subcontractors, collect their bids, and compare them side by side to support an award.

7. [Planning and cost control](./planning-and-cost-control.md)
   Schedule the work in 4D, track cost in 5D, and run earned value, forecasts, cash flow and change control as the job proceeds.

8. [Field and site operations](./field-and-site.md)
   Keep the daily diary, run inspections and safety, book deliveries, and build the contemporaneous record that protects the project.

9. [The validation pipeline](./validation.md)
   The traffic-light checks that run across imports and estimates so problems surface early, with a quality score and a jump straight to the position that needs fixing.

## A note on AI features

Several workflows offer AI help: drafting an estimate from a description or a photo, suggesting a cost match, ranking clashes, answering questions about your project data. In every case the platform shows a confidence score and asks a person to confirm before anything lands in your estimate. Treat AI output as a fast first draft that a qualified estimator checks, not as a final answer. You connect your own model provider with an API key, and the AI features degrade gracefully when no key is set, so the rest of the platform works without them.
