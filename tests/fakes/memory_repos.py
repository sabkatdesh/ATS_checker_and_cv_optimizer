"""In-memory repositories mirroring the Pg adapters' behaviour."""

from datetime import UTC, datetime

from app.ports.repositories import BonusState, JsonDict


class MemoryProfileRepo:
    def __init__(self) -> None:
        self.prefs: dict[str, JsonDict] = {}
        self.bonus: dict[str, dict[str, datetime | None]] = {}

    def get_preferences(self, user_id: str) -> JsonDict:
        return dict(self.prefs.get(user_id, {}))

    def save_preferences(self, user_id: str, prefs: JsonDict) -> None:
        self.prefs[user_id] = {**self.prefs.get(user_id, {}), **prefs}

    def bonus_state(self, user_id: str) -> BonusState:
        b = self.bonus.get(user_id, {})
        return BonusState(b.get("verified"), b.get("granted"), b.get("review"))

    def mark_bonus(self, user_id: str, *, granted: bool) -> None:
        b = self.bonus.setdefault(user_id, {})
        key = "granted" if granted else "review"
        b[key] = b.get(key) or datetime.now(UTC)


class MemoryMasterProfileRepo:
    def __init__(self) -> None:
        self.default: dict[str, JsonDict] = {}

    def get_default(self, user_id: str) -> JsonDict | None:
        if user_id not in self.default:
            return None
        return {**self.default[user_id], "user_id": user_id}

    def upsert_default(self, user_id: str, data: JsonDict) -> None:
        clean = {k: v for k, v in data.items() if k != "user_id"}
        self.default[user_id] = {**self.default.get(user_id, {}), **clean}


class MemoryTemplateRepo:
    def __init__(self) -> None:
        self.rows: list[JsonDict] = []

    def list_active(self) -> list[JsonDict]:
        return list(self.rows)


_GRANT_KINDS = ("signup_bonus", "purchase", "adjustment", "refund_admin")


class MemoryCreditRepo:
    """Models credits_grant(): one ledger row per idempotency key; replays return the balance."""

    def __init__(self) -> None:
        self.balances: dict[str, tuple[int, int]] = {}
        self.ledger_rows: list[JsonDict] = []
        self._by_key: dict[str, JsonDict] = {}

    def balance(self, user_id: str) -> tuple[int, int]:
        return self.balances.get(user_id, (0, 0))

    def ledger(self, user_id: str, limit: int = 50) -> list[JsonDict]:
        mine = [dict(r) for r in self.ledger_rows if r["user_id"] == user_id]
        mine.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
        return mine[:limit]

    def grant(self, user_id: str, amount: int, kind: str, idem: str) -> int:
        if not idem or not idem.strip():
            raise ValueError("credits_grant rejected: INVALID_IDEMPOTENCY_KEY")
        if amount is None or amount <= 0:
            raise ValueError("credits_grant rejected: INVALID_AMOUNT")
        if kind not in _GRANT_KINDS:
            raise ValueError("credits_grant rejected: INVALID_KIND")
        old = self._by_key.get(idem)
        if old is not None:
            if (old["user_id"], old["kind"]) != (user_id, kind):
                raise ValueError("credits_grant rejected: IDEMPOTENCY_MISMATCH")
            return self.balance(user_id)[0]
        row: JsonDict = {
            "id": len(self.ledger_rows) + 1,
            "user_id": user_id,
            "kind": kind,
            "delta_balance": amount,
            "delta_held": 0,
            "reason": None,
            "session_id": None,
            "idempotency_key": idem,
            "created_at": datetime.now(UTC),
        }
        self.ledger_rows.append(row)
        self._by_key[idem] = row
        balance, held = self.balance(user_id)
        self.balances[user_id] = (balance + amount, held)
        return balance + amount
