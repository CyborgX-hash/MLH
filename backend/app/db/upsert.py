"""PostgreSQL upserts: re-running a sync updates rows in place and never duplicates them."""
from typing import Any, Dict, List, Optional, Sequence, Type

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

BATCH = 500


def upsert(
    db: Session,
    model: Type[Any],
    rows: List[Dict[str, Any]],
    conflict: Sequence[str],
    update: Optional[Sequence[str]] = None,
) -> int:
    if not rows:
        return 0
    cols = list(update) if update is not None else [c for c in rows[0] if c not in conflict]
    for i in range(0, len(rows), BATCH):
        stmt = insert(model).values(rows[i : i + BATCH])
        stmt = stmt.on_conflict_do_update(index_elements=list(conflict), set_={c: stmt.excluded[c] for c in cols})
        db.execute(stmt)
    return len(rows)
