"""‌⁠‍BCF (BIM Collaboration Format) module — issues & viewpoints.

Server-backed, persistent BCF Topic / Comment / Viewpoint storage with a
full ``.bcfzip`` roundtrip for both the BCF-XML **2.1** and **3.0**
schemas. XML is hand-rolled with the stdlib (``xml.etree`` + ``zipfile``)
— there is NO IfcOpenShell / xBIM runtime dependency, in line with the
platform's CAD-agnostic constraint (the architecture guide §3).
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register RBAC permissions."""
    from app.modules.bcf.permissions import register_bcf_permissions

    register_bcf_permissions()
