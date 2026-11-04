"""
backend/app/db/queries/invariant_checker.py

Authoritative inventory invariant checker.
Verifies that across all inventory calendar records:
    booked_units + held_units <= total_units
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models.inventory import InventoryCalendar


async def check_inventory_invariants(
    session: AsyncSession,
    inventory_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes inventory invariant verification across inventory calendar records.
    Cross-dialect implementation compatible with PostgreSQL and SQLite test harnesses.
    """
    stmt = select(InventoryCalendar)
    if inventory_id:
        stmt = stmt.where(InventoryCalendar.inventory_id == inventory_id)

    res = await session.execute(stmt)
    records = res.scalars().all()

    violations: List[Dict[str, Any]] = []
    total_overallocated = 0

    for item in records:
        consumed = item.booked_units + item.held_units
        if consumed > item.total_units:
            over = consumed - item.total_units
            total_overallocated += over
            violations.append({
                "inventory_id": item.inventory_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "for_date": str(item.for_date),
                "total_units": item.total_units,
                "booked_units": item.booked_units,
                "held_units": item.held_units,
                "available_units": max(0, item.total_units - consumed),
                "overallocation": over,
                "is_violation": 1,
            })

    return {
        "passed": len(violations) == 0,
        "total_items_checked": len(records),
        "total_violations": len(violations),
        "total_overallocated_units": total_overallocated,
        "violations": violations,
    }
