import time
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.database import run_migrations
from main import app


def wait_for_job(client: TestClient, workspace_id: str, job_id: str) -> dict:
    job = None
    for _ in range(30):
        response = client.get(f"/api/v2/workspaces/{workspace_id}/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["job"]["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    assert job is not None
    assert job["job"]["status"] == "completed", job
    return job


def main() -> None:
    run_migrations()
    with TestClient(app) as client:
        health = client.get("/api/v2/health")
        assert health.status_code == 200, health.text
        assert health.headers["x-request-id"]
        expected_head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert health.json()["database"]["migration_revision"] == expected_head

        setup_state = client.get("/api/v2/auth/setup-state")
        assert setup_state.status_code == 200, setup_state.text
        assert setup_state.json()["setup_required"] is True
        setup = client.post(
            "/api/v2/auth/setup",
            json={"email": "admin@example.com", "display_name": "Admin", "password": "0123456789ab"},
        )
        assert setup.status_code == 200, setup.text

        workspace = client.post("/api/v2/workspaces", json={"name": "Firm Workspace", "slug": "firm"})
        assert workspace.status_code == 201, workspace.text
        workspace_id = workspace.json()["id"]
        navigation = client.get("/api/v2/me/navigation")
        assert navigation.status_code == 200, navigation.text
        assert navigation.json()["items"][0]["workspace_id"] == workspace_id

        matter = client.post(f"/api/v2/workspaces/{workspace_id}/matters", json={"name": "Test Matter"})
        assert matter.status_code == 201, matter.text
        matter_id = matter.json()["id"]

        retired_plugins = client.get(f"/api/v2/workspaces/{workspace_id}/plugins")
        assert retired_plugins.status_code == 404, retired_plugins.text
        retired_blueprints = client.get(f"/api/v2/workspaces/{workspace_id}/blueprints")
        assert retired_blueprints.status_code == 404, retired_blueprints.text

        upload = client.post(
            f"/api/v2/workspaces/{workspace_id}/documents/upload",
            data={"matter_id": matter_id, "scope": "matter"},
            files={"file": ("uploaded.txt", b"hello scoped upload with termination and liability clauses", "text/plain")},
        )
        assert upload.status_code == 201, upload.text
        upload_document_id = upload.json()["id"]
        wait_for_job(client, workspace_id, upload.json()["job"]["id"])
        indexed_document = client.get(f"/api/v2/workspaces/{workspace_id}/documents/{upload_document_id}")
        assert indexed_document.status_code == 200, indexed_document.text
        assert indexed_document.json()["status"] == "indexed"

        playbooks = client.get(f"/api/v2/workspaces/{workspace_id}/contract-review/playbooks")
        assert playbooks.status_code == 200, playbooks.text
        assert any(item["contract_category"] == "msa" for item in playbooks.json())

        skills = client.get("/api/v2/skills")
        assert skills.status_code == 200, skills.text
        assert any(item["id"] == "contract.extract_fields" for item in skills.json()["items"])

        member = client.post(
            f"/api/v2/workspaces/{workspace_id}/members",
            json={"email": "member@example.com", "display_name": "Member", "password": "abcdefgh1234", "role": "member"},
        )
        assert member.status_code == 201, member.text
        assert client.post("/api/v2/auth/logout").status_code == 200
        login = client.post("/api/v2/auth/login", json={"identifier": "member@example.com", "password": "abcdefgh1234"})
        assert login.status_code == 200, login.text
        members_denied = client.get(f"/api/v2/workspaces/{workspace_id}/members")
        assert members_denied.status_code == 403, members_denied.text

        assert client.post("/api/v2/auth/logout").status_code == 200
        assert client.post("/api/v2/auth/login", json={"identifier": "admin@example.com", "password": "0123456789ab"}).status_code == 200
        deleted_workspace = client.delete(f"/api/v2/workspaces/{workspace_id}")
        assert deleted_workspace.status_code == 200, deleted_workspace.text
        hidden_workspace = client.get(f"/api/v2/workspaces/{workspace_id}")
        assert hidden_workspace.status_code == 404, hidden_workspace.text


if __name__ == "__main__":
    main()
