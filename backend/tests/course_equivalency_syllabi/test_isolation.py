"""Guards that must hold whatever else changes: no service_role key anywhere in the
backend, the staff ID can only come from the verified session, uploads never
overwrite, and the Course Equivalency agent is not part of this package."""

import inspect
import pathlib
import re

from app.config import Settings
from app.course_equivalency import syllabus_files, syllabus_repository, syllabus_service
from app.api import course_equivalency_syllabi as api

APP = pathlib.Path(__file__).resolve().parents[2] / "app"


def _code(path: pathlib.Path) -> str:
    """Source without comments and docstrings (they may mention service_role to forbid it)."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    return re.sub(r"#.*", "", text)


def test_no_service_role_key_is_configured_or_used():
    assert not any("service" in field.lower() for field in Settings.__dataclass_fields__)
    offenders = [str(p.relative_to(APP)) for p in APP.rglob("*.py")
                 if re.search(r"service_role|SERVICE_ROLE|service-role", _code(p))]
    assert offenders == []


def test_staff_id_has_no_client_input_path():
    params = inspect.signature(syllabus_service.upload_syllabus).parameters
    assert "staff_id" not in params and "session" in params
    assert api._ALLOWED_FIELDS == frozenset({"file", "replaces"})
    assert "session.identity.staff_id" in inspect.getsource(syllabus_service.upload_syllabus)


def test_uploads_never_overwrite_and_only_replaced_syllabi_are_deleted():
    storage_code = _code(APP / "core" / "storage.py")
    assert '"x-upsert": "false"' in storage_code
    assert "requests.put" not in storage_code
    # One delete call, in delete_object only, and only the syllabus cleanup uses it.
    assert storage_code.count("requests.delete(") == 1
    users = [str(p.relative_to(APP)) for p in APP.rglob("*.py") if "delete_object(" in _code(p)]
    assert sorted(users) == [str(pathlib.Path("core/storage.py")),
                             str(pathlib.Path("course_equivalency/syllabus_service.py"))]
    service_code = _code(pathlib.Path(syllabus_service.__file__))
    assert service_code.count("storage.delete_object(") == 1
    cleanup = inspect.getsource(syllabus_service.remove_replaced)
    assert "repo.superseded_rows" in cleanup and "repo.evaluation_running" in cleanup
    assert cleanup.index("storage.delete_object(") < cleanup.index("repo.purge_superseded(")


def test_registry_is_written_only_through_the_database_functions():
    sql = _code(pathlib.Path(syllabus_repository.__file__))
    assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql)
    assert "app_private.register_course_syllabus" in sql
    assert "app_private.purge_superseded_course_syllabus" in sql


def test_package_contains_no_agent():
    files = sorted(p.name for p in pathlib.Path(syllabus_files.__file__).parent.glob("*.py"))
    assert files == ["__init__.py", "syllabus_files.py", "syllabus_repository.py", "syllabus_service.py"]
