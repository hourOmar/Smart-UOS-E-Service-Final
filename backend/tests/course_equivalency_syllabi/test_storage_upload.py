"""app.core.storage.upload_object: uploads AS the staff member (their bearer token
plus the public anon key), never overwriting; every Storage reply format maps to a
typed error; the token never appears in a message or log. requests is faked."""

import logging

import pytest
import requests

from app.config import get_settings
from app.core import storage

from .fakes import TOKEN

PATH = "STUD_EQVO_ECTU_000139/old/1b4e28ba-2fa1-41d2-883f-0016d3cca427.pdf"


class FakeResponse:
    def __init__(self, status=200, json_data=None):
        self.status_code = status
        self._json = json_data
        self.closed = False

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def close(self):
        self.closed = True


@pytest.fixture
def post(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co/")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-public-key")
    get_settings.cache_clear()
    seen = {}

    def install(response=None, exc=None):
        def fake_post(url, **kwargs):
            seen.update(url=url, **kwargs)
            if exc is not None:
                raise exc
            seen["response"] = response
            return response
        monkeypatch.setattr(storage.requests, "post", fake_post)
        return seen
    return install


def upload():
    storage.upload_object("course-syllabi", PATH, b"%PDF-data", "application/pdf", f"  {TOKEN}  ")


def test_success_sends_staff_token_anon_key_and_never_overwrites(post):
    seen = post(FakeResponse(200, {"Key": "x"}))
    upload()
    assert seen["url"] == f"https://project.supabase.co/storage/v1/object/course-syllabi/{PATH}"
    headers = seen["headers"]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["apikey"] == "anon-public-key"
    assert headers["x-upsert"] == "false"
    assert headers["Content-Type"] == "application/pdf"
    assert seen["data"] == b"%PDF-data"
    assert seen["allow_redirects"] is False and seen["timeout"]
    assert seen["response"].closed


def test_path_segments_are_url_encoded(post):
    seen = post(FakeResponse(200))
    storage.upload_object("course-syllabi", "STUD_EQVO_ECTU_000139/old/a b#?.pdf", b"x", "application/pdf", TOKEN)
    assert seen["url"].endswith("/STUD_EQVO_ECTU_000139/old/a%20b%23%3F.pdf")


@pytest.mark.parametrize("status,body,expected,reason", [
    (409, None, storage.StorageConflictError, None),
    (400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"},
     storage.StorageConflictError, None),
    (400, {"error": "Duplicate"}, storage.StorageConflictError, None),
    (403, None, storage.StorageAccessDeniedError, None),
    (401, None, storage.StorageAccessDeniedError, None),
    (400, {"statusCode": "403", "error": "Unauthorized",
           "message": "new row violates row-level security policy"}, storage.StorageAccessDeniedError, None),
    (413, None, storage.StorageRejectedError, "too_large"),
    (400, {"statusCode": "413", "error": "Payload too large"}, storage.StorageRejectedError, "too_large"),
    (415, None, storage.StorageRejectedError, "type"),
    (400, {"statusCode": "415", "error": "invalid_mime_type"}, storage.StorageRejectedError, "type"),
    (400, {"error": "invalid_mime_type"}, storage.StorageRejectedError, "type"),
    (400, None, storage.StorageRejectedError, "rejected"),
    (404, {"statusCode": "404", "error": "Bucket not found"}, storage.StorageUnavailableError, None),
    (500, None, storage.StorageUnavailableError, None),
    (503, None, storage.StorageUnavailableError, None),
])
def test_error_mapping(post, caplog, status, body, expected, reason):
    seen = post(FakeResponse(status, body))
    with caplog.at_level(logging.DEBUG), pytest.raises(expected) as info:
        upload()
    if reason:
        assert info.value.reason == reason
    assert TOKEN not in str(info.value) and TOKEN not in caplog.text
    assert seen["response"].closed


@pytest.mark.parametrize("exc", [requests.ConnectTimeout("t"), requests.ReadTimeout("t"), requests.ConnectionError("c")])
def test_network_failures_are_unavailable(post, exc):
    post(exc=exc)
    with pytest.raises(storage.StorageUnavailableError) as info:
        upload()
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_not_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    get_settings.cache_clear()
    with pytest.raises(storage.StorageNotConfiguredError):
        upload()


@pytest.mark.parametrize("token", ["", "   ", None])
def test_missing_token_is_refused_without_calling_storage(post, token):
    seen = post(FakeResponse(200))
    with pytest.raises(storage.StorageAccessDeniedError):
        storage.upload_object("course-syllabi", PATH, b"x", "application/pdf", token)
    assert "url" not in seen


# ------------------------------------------------------------------ delete_object (replaced syllabi only)
@pytest.fixture
def delete(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co/")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-public-key")
    get_settings.cache_clear()
    seen = {}

    def install(response=None, exc=None):
        def fake_delete(url, **kwargs):
            seen.update(url=url, **kwargs)
            if exc is not None:
                raise exc
            seen["response"] = response
            return response
        monkeypatch.setattr(storage.requests, "delete", fake_delete)
        return seen
    return install


def test_delete_sends_staff_token_and_anon_key(delete):
    seen = delete(FakeResponse(200, [{"name": PATH}]))
    assert storage.delete_object("course-syllabi", PATH, f"  {TOKEN}  ") is True
    assert seen["url"] == f"https://project.supabase.co/storage/v1/object/course-syllabi/{PATH}"
    assert seen["headers"] == {"apikey": "anon-public-key", "Authorization": f"Bearer {TOKEN}"}
    assert seen["allow_redirects"] is False and seen["timeout"] and seen["response"].closed


@pytest.mark.parametrize("response", [FakeResponse(404), FakeResponse(400, {"statusCode": "404", "error": "not_found"})])
def test_delete_not_found_is_false_never_proof_of_deletion(delete, response):
    delete(response)
    assert storage.delete_object("course-syllabi", PATH, TOKEN) is False


@pytest.mark.parametrize("response,error", [
    (FakeResponse(401), storage.StorageAccessDeniedError),
    (FakeResponse(400, {"statusCode": "403", "error": "Unauthorized"}), storage.StorageAccessDeniedError),
    (FakeResponse(500), storage.StorageUnavailableError),
])
def test_delete_refusals_are_typed(delete, response, error):
    delete(response)
    with pytest.raises(error):
        storage.delete_object("course-syllabi", PATH, TOKEN)


def test_delete_network_failure_never_leaks_the_token(delete, caplog):
    delete(exc=requests.ConnectionError(f"boom {TOKEN}"))
    with caplog.at_level(logging.DEBUG), pytest.raises(storage.StorageUnavailableError) as info:
        storage.delete_object("course-syllabi", PATH, TOKEN)
    assert TOKEN not in str(info.value) and TOKEN not in caplog.text


@pytest.mark.parametrize("token", ["", "   ", None])
def test_delete_without_a_session_never_calls_storage(delete, token):
    seen = delete(FakeResponse(200))
    with pytest.raises(storage.StorageAccessDeniedError):
        storage.delete_object("course-syllabi", PATH, token)
    assert "url" not in seen
