"""No test in this package may reach real Supabase Storage: a DELETE that a test did
not fake explicitly fails here (the service treats it as a failed deletion and keeps
the replaced version for a retry)."""

import pytest

from app.core import storage


@pytest.fixture(autouse=True)
def _no_real_storage_delete(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("tests never call real Supabase Storage")
    monkeypatch.setattr(storage.requests, "delete", refuse)
