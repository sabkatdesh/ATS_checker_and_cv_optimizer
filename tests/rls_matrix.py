"""Expected access per public table, shared by the static and remote RLS suites.

Access values: "none", "select_own", "select_active".
Backend values: "dml" (select/insert/update/delete) or "select" (writes go
through SECURITY DEFINER functions).
"""

from typing import Literal, NamedTuple

Access = Literal["none", "select_own", "select_active"]
Backend = Literal["dml", "select"]


class Rule(NamedTuple):
    anon: Access
    authenticated: Access
    backend: Backend


_OWN = Rule("none", "select_own", "dml")
_CREDIT = Rule("none", "select_own", "select")
_DENIED = Rule("none", "none", "dml")

MATRIX: dict[str, Rule] = {
    "profiles": _OWN,
    "master_profiles": _OWN,
    "photos": _OWN,
    "cv_sessions": _OWN,
    "jobs": _OWN,
    "job_events": _OWN,
    "renders": _OWN,
    "credit_balances": _CREDIT,
    "credit_ledger": _CREDIT,
    "credit_reservations": _CREDIT,
    "templates": Rule("select_active", "select_active", "dml"),
    "llm_calls": _DENIED,
    "signup_guards": _DENIED,
    "idempotency_keys": _DENIED,
    "payment_intents": _DENIED,
    "payment_events": _DENIED,
    "audit_log": _DENIED,
    "feature_flags": _DENIED,
}

CREDIT_TABLES = ("credit_balances", "credit_ledger", "credit_reservations")

# service_role (the dashboard/admin key) on the credit tables: SELECT everywhere; on the
# ledger UPDATE/DELETE stay granted so the append-only trigger is what rejects them.
# No INSERT anywhere, no TRUNCATE (it would bypass the row trigger) and no balance/reservation
# writes: credits move only through the SECURITY DEFINER functions.
SERVICE_ROLE_CREDIT: dict[str, frozenset[str]] = {
    "credit_balances": frozenset({"SELECT"}),
    "credit_reservations": frozenset({"SELECT"}),
    "credit_ledger": frozenset({"SELECT", "UPDATE", "DELETE"}),
}
