# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BOQ budget exporters (canonical BOQ -> external interchange formats).

The mirror of :mod:`app.modules.boq.importers`: each exporter turns a
``BOQWithSections`` into a downloadable interchange file. The first member
is the FIEBDC-3 / BC3 exporter (Spain + Hispanophone LATAM); the GAEB DA
XML and spreadsheet exporters currently live inline in ``router.py`` and
may migrate here over time.
"""

from __future__ import annotations

from app.modules.boq.exporters.bc3 import build_bc3

__all__ = ["build_bc3"]
