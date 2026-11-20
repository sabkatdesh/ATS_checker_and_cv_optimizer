"""Thin httpx clients for PostgREST and Storage, as a browser would call them.

Only the `public` schema is exposed through PostgREST (Supabase default; `lg` is not in the
exposed-schemas list), so client roles can reach public tables and RPCs only, and every access
there is decided by grants + RLS.
"""

from typing import Any

import httpx

REPRESENTATION = {"Prefer": "return=representation"}
# PostgREST: 401 for anon, 403 for an authenticated role on 42501 (permission denied).
DENIED = (401, 403)


def _eq(filters: dict[str, Any]) -> dict[str, str]:
    return {col: f"eq.{val}" for col, val in filters.items()}


class Rest:
    """PostgREST as one caller: `apikey` plus an optional bearer (user JWT or the secret key)."""

    def __init__(self, base: str, apikey: str, bearer: str | None, client: httpx.Client) -> None:
        self._url = f"{base}/rest/v1"
        self._headers = {"apikey": apikey}
        if bearer:
            self._headers["Authorization"] = f"Bearer {bearer}"
        self._http = client

    def _req(self, method: str, path: str, **kw: Any) -> httpx.Response:
        headers = {**self._headers, **kw.pop("headers", {})}
        return self._http.request(method, f"{self._url}/{path}", headers=headers, **kw)

    def select(self, table: str, **filters: Any) -> httpx.Response:
        return self._req("GET", table, params={"select": "*", **_eq(filters)})

    def insert(self, table: str, row: dict[str, Any]) -> httpx.Response:
        return self._req("POST", table, json=row, headers=REPRESENTATION)

    def update(self, table: str, patch: dict[str, Any], **filters: Any) -> httpx.Response:
        return self._req("PATCH", table, json=patch, params=_eq(filters), headers=REPRESENTATION)

    def delete(self, table: str, **filters: Any) -> httpx.Response:
        return self._req("DELETE", table, params=_eq(filters), headers=REPRESENTATION)

    def rpc(self, fn: str, args: dict[str, Any]) -> httpx.Response:
        return self._req("POST", f"rpc/{fn}", json=args)

    def select_in_schema(self, schema: str, table: str) -> httpx.Response:
        return self._req("GET", table, params={"select": "*"}, headers={"Accept-Profile": schema})


def rows(resp: httpx.Response) -> list[dict[str, Any]]:
    """The JSON rows of a 2xx response, else []."""
    if not resp.is_success:
        return []
    body = resp.json()
    return body if isinstance(body, list) else []


def denied_or_empty(resp: httpx.Response) -> bool:
    """A write or read that did nothing: refused (401/403), or succeeded on zero rows."""
    return resp.status_code in DENIED or (resp.is_success and rows(resp) == [])


class StorageHttp:
    """Storage REST as a client: apikey (publishable) plus the user's JWT."""

    def __init__(self, base: str, apikey: str, bearer: str | None, client: httpx.Client) -> None:
        self._base = base
        self._headers = {"apikey": apikey}
        if bearer:
            self._headers["Authorization"] = f"Bearer {bearer}"
        self._http = client

    def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> httpx.Response:
        headers = {**self._headers, "Content-Type": content_type, "x-upsert": "true"}
        url = f"{self._base}/storage/v1/object/{bucket}/{path}"
        return self._http.post(url, content=data, headers=headers)

    def list(self, bucket: str, prefix: str) -> httpx.Response:
        url = f"{self._base}/storage/v1/object/list/{bucket}"
        body = {"prefix": prefix, "limit": 100, "offset": 0}
        return self._http.post(url, json=body, headers=self._headers)

    def download(self, bucket: str, path: str) -> httpx.Response:
        url = f"{self._base}/storage/v1/object/authenticated/{bucket}/{path}"
        return self._http.get(url, headers=self._headers)


def public_object_url(base: str, bucket: str, path: str) -> str:
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


def listed_names(resp: httpx.Response) -> list[str]:
    if not resp.is_success:
        return []
    body = resp.json()
    return [str(e.get("name")) for e in body] if isinstance(body, list) else []
