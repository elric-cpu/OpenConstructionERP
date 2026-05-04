# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""‌⁠‍EAC v2 parameter aliases (RFC 35 §6 — Wave EAC-2).

Public surface:

* :class:`ResolveResult`              — the dataclass returned by resolvers
* :func:`resolve_alias`               — single-alias resolver
* :func:`resolve_bulk`                — bulk resolver
* :class:`AliasInUseError`            — raised when deleting an in-use alias
* Pydantic schemas                    — see :mod:`.schemas`
* Service functions                   — see :mod:`.service`
* FastAPI router                      — see :mod:`.router`
"""

from app.modules.eac.aliases.bulk_resolver import resolve_bulk
from app.modules.eac.aliases.resolver import ResolveResult, resolve_alias
from app.modules.eac.aliases.service import AliasInUseError

__all__ = [
    "AliasInUseError",
    "ResolveResult",
    "resolve_alias",
    "resolve_bulk",
]
