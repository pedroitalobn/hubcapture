"""Helper de bookkeeping de sync em sessão autônoma.

Um erro no request dá rollback; gravar o SyncRun por fora (commit próprio)
preserva o registro do incidente. sync_runs não tem RLS.
"""

from __future__ import annotations

from ..db.session import SessionLocal
from ..models.sync_run import SyncRun


async def registrar_sync(**kwargs) -> None:
    async with SessionLocal() as s:
        async with s.begin():
            s.add(SyncRun(**kwargs))
