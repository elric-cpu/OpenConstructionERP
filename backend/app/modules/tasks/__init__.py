"""‌⁠‍Tasks module.

Project task management — tasks, topics, information requests, decisions,
and personal items with checklists, assignments, and due dates.
"""


async def on_startup() -> None:
    """‌⁠‍Module startup hook — register permissions."""
    from app.modules.tasks.permissions import register_tasks_permissions

    register_tasks_permissions()
