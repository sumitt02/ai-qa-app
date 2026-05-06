"""Tests for security utilities."""
from datetime import timedelta

from app.core.security import (
    hash_password, verify_password, create_access_token, decode_access_token
)


def test_hash_and_verify():
    pw = "supersecret"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h)
    assert not verify_password("wrong", h)


def test_create_and_decode_token():
    token = create_access_token(subject=42)
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "42"


def test_decode_invalid_token():
    assert decode_access_token("garbage.token.string") is None


def test_token_with_custom_expiry():
    token = create_access_token(subject="user-1", expires_delta=timedelta(seconds=60))
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-1"
