import os
import time
import unittest
from pathlib import Path


ROOT = Path("/tmp/ai_blueprint_launch_tests")
DB_PATH = ROOT / "v2.db"
LEGACY_DB_PATH = ROOT / "legacy.db"
UPLOADS_PATH = ROOT / "uploads"
SECRET_PATH = ROOT / "secret.key"
LEGACY_SECRET_PATH = ROOT / "legacy_secret.key"

os.environ["AI_BLUEPRINT_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["AI_BLUEPRINT_LEGACY_DATABASE_PATH"] = str(LEGACY_DB_PATH)
os.environ["AI_BLUEPRINT_UPLOADS_DIR"] = str(UPLOADS_PATH)
os.environ["AI_BLUEPRINT_SECRET_KEY_FILE"] = str(SECRET_PATH)
os.environ["AI_BLUEPRINT_LEGACY_SECRET_KEY_FILE"] = str(LEGACY_SECRET_PATH)
os.environ["AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS"] = "100"

from fastapi.testclient import TestClient

from main import app


def _clean_runtime() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for path in ROOT.glob("*"):
        if path.is_file():
            path.unlink()
    if UPLOADS_PATH.exists():
        for child in sorted(UPLOADS_PATH.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()


class LaunchReadinessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _clean_runtime()
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def wait_for_job(self, workspace_id: str, job_id: str) -> dict:
        last = None
        for _ in range(30):
            last = self.client.get(f"/api/v2/workspaces/{workspace_id}/jobs/{job_id}")
            self.assertEqual(last.status_code, 200, last.text)
            body = last.json()
            if body["job"]["status"] in {"completed", "failed", "cancelled"}:
                return body
            time.sleep(0.1)
        self.fail(last.text if last is not None else "job did not finish")

    def test_public_launch_flow_and_guardrails(self) -> None:
        health = self.client.get("/api/v2/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["database"]["migration_revision"], "0016_contract_review_reports")
        self.assertTrue(health.json()["secrets"]["key_configured"])
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertEqual(health.headers["x-frame-options"], "DENY")

        setup_state = self.client.get("/api/v2/auth/setup-state")
        self.assertEqual(setup_state.json(), {"setup_required": True})

        setup = self.client.post(
            "/api/v2/auth/setup",
            json={"email": "admin@example.com", "display_name": "Admin", "password": "0123456789ab"},
        )
        self.assertEqual(setup.status_code, 200, setup.text)
        self.assertFalse(setup.json()["user"]["must_change_credentials"])

        duplicate_setup = self.client.post(
            "/api/v2/auth/setup",
            json={"email": "other@example.com", "display_name": "Other", "password": "0123456789ab"},
        )
        self.assertEqual(duplicate_setup.status_code, 409, duplicate_setup.text)

        workspace = self.client.post("/api/v2/workspaces", json={"name": "Launch Workspace", "slug": "launch"})
        self.assertEqual(workspace.status_code, 201, workspace.text)
        workspace_id = workspace.json()["id"]

        matter = self.client.post(f"/api/v2/workspaces/{workspace_id}/matters", json={"name": "Launch Matter"})
        self.assertEqual(matter.status_code, 201, matter.text)
        matter_id = matter.json()["id"]

        rejected_upload = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/documents/upload",
            files={"file": ("malware.exe", b"not really malware", "application/octet-stream")},
        )
        self.assertEqual(rejected_upload.status_code, 400, rejected_upload.text)

        upload = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/documents/upload",
            data={"matter_id": matter_id, "scope": "matter"},
            files={"file": ("contract.txt", b"termination liability indemnity", "text/plain")},
        )
        self.assertEqual(upload.status_code, 201, upload.text)
        job = self.wait_for_job(workspace_id, upload.json()["job"]["id"])
        self.assertEqual(job["job"]["status"], "completed", job)

        secret = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/secrets",
            json={"name": "OPENAI_API_KEY", "value": "sk-public-launch-test", "scope": "workspace"},
        )
        self.assertEqual(secret.status_code, 201, secret.text)
        self.assertNotIn("sk-public-launch-test", secret.text)
        self.assertNotIn("encrypted_value", secret.text)

        member = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/members",
            json={
                "email": "member@example.com",
                "display_name": "Member",
                "password": "abcdefgh1234",
                "role": "member",
            },
        )
        self.assertEqual(member.status_code, 201, member.text)

        with TestClient(app) as member_client:
            login = member_client.post(
                "/api/v2/auth/login",
                json={"identifier": "member@example.com", "password": "abcdefgh1234"},
            )
            self.assertEqual(login.status_code, 200, login.text)
            members_denied = member_client.get(f"/api/v2/workspaces/{workspace_id}/members")
            self.assertEqual(members_denied.status_code, 403, members_denied.text)

        chat = self.client.post(
            "/api/chats",
            json={
                "doc_context": "all",
                "v2_workspace_id": workspace_id,
                "v2_matter_id": matter_id,
                "v2_document_ids": [upload.json()["id"]],
            },
        )
        self.assertEqual(chat.status_code, 200, chat.text)
        self.assertEqual(chat.json()["v2_document_ids"], [upload.json()["id"]])

        enable_contract_review = self.client.put(f"/api/v2/workspaces/{workspace_id}/plugins/contract_review", json={"enabled": True})
        self.assertEqual(enable_contract_review.status_code, 200, enable_contract_review.text)
        blueprint = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints",
            json={"name": "Contract Review", "plugin_id": "contract_review", "matter_id": matter_id},
        )
        self.assertEqual(blueprint.status_code, 201, blueprint.text)
        blueprint_id = blueprint.json()["id"]
        link = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/documents/{upload.json()['id']}/links",
            json={"blueprint_id": blueprint_id},
        )
        self.assertEqual(link.status_code, 201, link.text)
        contract_run = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs",
            json={"title": "Launch Contract Review"},
        )
        self.assertEqual(contract_run.status_code, 201, contract_run.text)
        contract_job = self.wait_for_job(workspace_id, contract_run.json()["job"]["id"])
        self.assertEqual(contract_job["job"]["status"], "completed", contract_job)
        self.assertGreaterEqual(len(contract_job["events"]), 5)
        export = self.client.get(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{contract_run.json()['id']}/export"
        )
        self.assertEqual(export.status_code, 200, export.text)
        self.assertIn("# Launch Contract Review", export.text)


if __name__ == "__main__":
    unittest.main()
