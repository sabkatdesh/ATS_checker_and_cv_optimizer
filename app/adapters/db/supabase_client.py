"""Supabase client factory; credentials come from settings, never from os.environ."""

from pydantic import SecretStr

from supabase import Client, create_client


def make_supabase_client(url: str, key: SecretStr) -> Client:
    return create_client(url, key.get_secret_value())
