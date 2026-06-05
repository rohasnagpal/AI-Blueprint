import os
import time
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database
from app.core.database import run_migrations
from main import app


def clean_runtime() -> None:
    paths = [
        "AI_BLUEPRINT_DATABASE_URL",
        "AI_BLUEPRINT_APP_DATABASE_PATH",
        "AI_BLUEPRINT_UPLOADS_DIR",
        "AI_BLUEPRINT_SECRET_KEY_FILE",
        "AI_BLUEPRINT_APP_SECRET_KEY_FILE",
    ]
    for name in paths:
        value = os.environ.get(name)
        if not value:
            continue
        path = Path(value.removeprefix("sqlite:///"))
        resolved = path.resolve()
        if not str(resolved).startswith(("/tmp/", "/private/tmp/")):
            raise RuntimeError(f"{name} must point under /tmp for the hardening smoke cleanup: {path}")
        if name.endswith("DATABASE_URL"):
            for candidate in [path, Path(f"{path}-wal"), Path(f"{path}-shm")]:
                if candidate.exists():
                    candidate.unlink()
        elif path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
        else:
            for candidate in [path, Path(f"{path}-wal"), Path(f"{path}-shm")]:
                if candidate.exists():
                    candidate.unlink()


def assert_ok(response, status_code=200):
    assert response.status_code == status_code, response.text
    return response.json() if response.text else {}


def wait_job(client: TestClient, workspace_id: str, job_id: str) -> dict:
    last = None
    for _ in range(30):
        last = client.get(f"/api/v2/workspaces/{workspace_id}/jobs/{job_id}")
        assert last.status_code == 200, last.text
        body = last.json()
        if body["job"]["status"] in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.1)
    raise AssertionError(last.text if last is not None else "job did not start")


def main() -> None:
    clean_runtime()
    run_migrations()
    database.init_db()

    with TestClient(app) as owner:
        setup = owner.post(
            "/api/v2/auth/setup",
            json={"email": "owner@example.com", "display_name": "Owner", "password": "0123456789ab"},
        )
        assert_ok(setup)

        workspace = assert_ok(owner.post("/api/v2/workspaces", json={"name": "Hardening", "slug": "hardening"}), 201)
        workspace_id = workspace["id"]
        matter = assert_ok(owner.post(f"/api/v2/workspaces/{workspace_id}/matters", json={"name": "Permission Matter"}), 201)
        matter_id = matter["id"]

        member = assert_ok(
            owner.post(
                f"/api/v2/workspaces/{workspace_id}/members",
                json={
                    "email": "member@example.com",
                    "display_name": "Member",
                    "password": "abcdefgh1234",
                    "role": "member",
                },
            ),
            201,
        )
        assert member["role"] == "member"

        uploads = []
        for name, content in [
            ("alpha.txt", b"Alpha contract has indemnity and liability language."),
            ("beta.txt", b"Beta research note covers termination and notice clauses."),
        ]:
            upload = assert_ok(
                owner.post(
                    f"/api/v2/workspaces/{workspace_id}/documents/upload",
                    data={"matter_id": matter_id, "scope": "matter"},
                    files={"file": (name, content, "text/plain")},
                ),
                201,
            )
            uploads.append(upload)
        for upload in uploads:
            job = wait_job(owner, workspace_id, upload["job"]["id"])
            assert job["job"]["status"] == "completed", job

        scoped_chat = assert_ok(
            owner.post(
                "/api/chats",
                json={
                    "doc_context": "all",
                    "v2_workspace_id": workspace_id,
                    "v2_matter_id": matter_id,
                    "v2_document_ids": [uploads[0]["id"]],
                },
            )
        )
        archive = assert_ok(owner.post(f"/api/chats/{scoped_chat['id']}/archive"))
        assert archive["ok"] is True
        archived_chats = assert_ok(owner.get("/api/chats?archived=true"))
        assert any(chat["id"] == scoped_chat["id"] for chat in archived_chats)
        restore = assert_ok(owner.post(f"/api/chats/{scoped_chat['id']}/restore"))
        assert restore["ok"] is True
        active_chats = assert_ok(owner.get("/api/chats"))
        assert any(chat["id"] == scoped_chat["id"] for chat in active_chats)

        extra_chat = assert_ok(owner.post("/api/chats", json={"doc_context": "none"}))
        bulk = assert_ok(owner.post("/api/chats/bulk-delete", json={"ids": [extra_chat["id"]]}))
        assert bulk["deleted"] == 1
        assert all(chat["id"] != extra_chat["id"] for chat in assert_ok(owner.get("/api/chats")))

        with TestClient(app) as anonymous:
            hidden = anonymous.get("/api/chats")
            assert hidden.status_code == 401, hidden.text
            denied = anonymous.get(f"/api/chats/{scoped_chat['id']}/messages")
            assert denied.status_code == 401, denied.text

        with TestClient(app) as member_client:
            login = member_client.post(
                "/api/v2/auth/login",
                json={"email": "member@example.com", "password": "abcdefgh1234"},
            )
            assert_ok(login)
            visible = assert_ok(member_client.get("/api/chats"))
            assert any(chat["id"] == scoped_chat["id"] for chat in visible)
            delete_denied = member_client.delete(f"/api/v2/workspaces/{workspace_id}")
            assert delete_denied.status_code == 403, delete_denied.text

        deleted = assert_ok(owner.delete(f"/api/v2/workspaces/{workspace_id}"))
        assert deleted["ok"] is True
        deleted_matter = owner.get(f"/api/v2/workspaces/{workspace_id}/matters/{matter_id}")
        assert deleted_matter.status_code == 404, deleted_matter.text
        hidden_after_delete = assert_ok(owner.get("/api/chats"))
        assert all(chat["id"] != scoped_chat["id"] for chat in hidden_after_delete)


if __name__ == "__main__":
    main()
