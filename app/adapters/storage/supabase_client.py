"""Supabase client factory for Storage; credentials come from settings, never os.environ."""

from pydantic import SecretStr

from supabase import Client, create_client

SupabaseClient = Client


def make_supabase_client(url: str, key: SecretStr) -> SupabaseClient:
    return create_client(url, key.get_secret_value())
