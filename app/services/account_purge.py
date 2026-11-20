"""Hard-delete an account, in an order that is safe to re-run after a crash at any step.

Cascade design (05 section 9):
- public.profiles cascades to every user-owned table (ON DELETE CASCADE chains from profiles).
- auth.users deletion cascades to profiles, so deleting the Auth user last removes all rows.
- credit_ledger, payment_intents, llm_calls and audit_log rows survive with user_id/actor set
  to null (ON DELETE SET NULL; the ledger trigger permits exactly that), keeping amounts for
  accounting without the identity.
- Storage objects and LangGraph checkpoints are outside FK reach, so this service clears them
  first. Session ids are read before anything is deleted because the cascade removes the rows.
Each step is idempotent (empty prefixes, absent threads and a 404 from Auth are all fine), so a
crashed run is simply run again. The audit entry is written last and carries only counts and a
hash of the id. A user-facing endpoint and the grace-period cron are out of scope in M4;
DeletionSettings.grace_days is ready for them.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

from app.ports.blob_storage import BlobStorage
from app.ports.repositories import AuditRepo, is_uuid
from app.ports.user_admin import UserAdmin

PURGE_BUCKETS = ("photos", "renders", "imports", "exports")


class ThreadStore(Protocol):
    def delete_thread(self, thread_id: str) -> None: ...


class SessionIds(Protocol):
    def session_ids(self, user_id: str) -> list[str]: ...


@dataclass(frozen=True)
class PurgeDeps:
    storage: BlobStorage
    checkpoints: ThreadStore
    sessions: SessionIds
    admin: UserAdmin
    audit: AuditRepo


@dataclass(frozen=True)
class PurgeReport:
    objects_removed: int
    threads_removed: int
    user_deleted: bool


def purge_account(user_id: str, deps: PurgeDeps) -> PurgeReport:
    if not is_uuid(user_id):
        raise ValueError("user_id must be a canonical UUID")
    session_ids = deps.sessions.session_ids(user_id)
    objects = sum(deps.storage.delete_prefix(b, f"{user_id}/") for b in PURGE_BUCKETS)
    for sid in session_ids:
        deps.checkpoints.delete_thread(sid)
    deleted = deps.admin.delete_user(user_id)
    report = PurgeReport(objects, len(session_ids), deleted)
    deps.audit.write(
        actor=None,
        action="account.purged",
        target=hashlib.sha256(user_id.encode()).hexdigest()[:16],
        meta={
            "objects_removed": report.objects_removed,
            "threads_removed": report.threads_removed,
            "user_deleted": report.user_deleted,
        },
    )
    return report
