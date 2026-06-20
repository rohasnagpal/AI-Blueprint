import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

ROOT = Path("/tmp/ai_blueprint_launch_tests")
DB_PATH = ROOT / "v2.db"
APP_DB_PATH = ROOT / "application.db"
UPLOADS_PATH = ROOT / "uploads"
SECRET_PATH = ROOT / "secret.key"
APP_SECRET_PATH = ROOT / "application_secret.key"

os.environ["AI_BLUEPRINT_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["AI_BLUEPRINT_APP_DATABASE_PATH"] = str(APP_DB_PATH)
os.environ["AI_BLUEPRINT_UPLOADS_DIR"] = str(UPLOADS_PATH)
os.environ["AI_BLUEPRINT_SECRET_KEY_FILE"] = str(SECRET_PATH)
os.environ["AI_BLUEPRINT_APP_SECRET_KEY_FILE"] = str(APP_SECRET_PATH)
os.environ["AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS"] = "100"

import database

database.DB_PATH = str(APP_DB_PATH)
database.SECRET_KEY_FILE = str(APP_SECRET_PATH)

from fastapi.testclient import TestClient

from main import app
from app.core.contract_agents.clause_extractor import extract_clauses
from app.core.contract_agents.conflict_detector import detect_conflicts
from app.core.contract_agents.intake import run_intake
from app.core.contract_agents.agentic_review import ContractReviewAgentError, _parse_agent_json, run_agentic_contract_review
from app.core.contract_agents.playbook_comparator import compare_to_playbook
from app.core.contract_agents.redliner import suggest_redlines
from app.core.contract_agents.risk_scorer import score_risks
from app.core.contract_agents.schemas import RiskFindingResult
from app.core.contract_agents.tools import run_contract_agent_tools
from app.core.config import Settings, get_settings, validate_runtime_security
from app.core.database import SessionLocal
from app.core.document_indexer import _extract_chunks
from app.core.error_sanitizer import sanitize_provider_error
from app.api.contract_review_standalone import _deterministic_agentic_review_fallback, _is_agent_invalid_json_error, _runtime_settings_for_workspace, _select_playbook
from app.api.auth import _check_auth_rate_limit
from app.core.models import ContractClause, ContractPlaybook, ContractPlaybookClause, ContractReviewOutput, ContractReviewRun, ContractReviewStepOutput, KnowledgeChunk, KnowledgeEmbedding, Secret, User, Workspace, WorkspaceMember, utcnow
from app.core.secrets import decrypt_secret, encrypt_secret
from app.core.build_info import __version__


def _configure_runtime() -> None:
    os.environ["AI_BLUEPRINT_DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ["AI_BLUEPRINT_APP_DATABASE_PATH"] = str(APP_DB_PATH)
    os.environ["AI_BLUEPRINT_UPLOADS_DIR"] = str(UPLOADS_PATH)
    os.environ["AI_BLUEPRINT_SECRET_KEY_FILE"] = str(SECRET_PATH)
    os.environ["AI_BLUEPRINT_APP_SECRET_KEY_FILE"] = str(APP_SECRET_PATH)
    os.environ["AI_BLUEPRINT_AUTH_RATE_LIMIT_ATTEMPTS"] = "100"
    database.DB_PATH = str(APP_DB_PATH)
    database.SECRET_KEY_FILE = str(APP_SECRET_PATH)


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
        _configure_runtime()
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
        self.assertEqual(health.json()["version"], __version__)
        expected_head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        self.assertEqual(health.json()["database"]["migration_revision"], expected_head)
        self.assertTrue(health.json()["secrets"]["key_configured"])
        self.assertNotIn("uploads_dir", health.json()["storage"])
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertEqual(health.headers["x-frame-options"], "DENY")
        csp = health.headers["content-security-policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        self.assertIn("style-src-attr 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

        setup_state = self.client.get("/api/v2/auth/setup-state")
        self.assertEqual(setup_state.json(), {"setup_required": True})

        setup = self.client.post(
            "/api/v2/auth/setup",
            json={"email": "admin@example.com", "display_name": "Admin", "password": "0123456789ab"},
        )
        self.assertEqual(setup.status_code, 200, setup.text)
        self.assertFalse(setup.json()["user"]["must_change_credentials"])
        admin_user_id = setup.json()["user"]["id"]

        public_translation = self.client.post(
            "/api/v2/translations/public/text",
            json={"text": "The agreement terminates on 31 December 2026.", "target_language": "Hindi", "mode": "legal"},
        )
        self.assertEqual(public_translation.status_code, 200, public_translation.text)
        self.assertEqual(public_translation.json()["source_type"], "text")
        self.assertEqual(public_translation.json()["target_language"], "Hindi")
        self.assertEqual(public_translation.json()["mode"], "legal")
        self.assertIn("translated_html", public_translation.json())

        public_draft = self.client.post(
            "/api/v2/drafts/public",
            json={
                "document_type": "legal-notice",
                "jurisdiction": "India",
                "tone": "formal",
                "parties": "Sender: Example Pvt Ltd\nRecipient: Vendor LLP",
                "facts": "Vendor LLP failed to deliver services by 1 May 2026 despite repeated reminders.",
                "key_terms": "Demand cure within 7 days.",
            },
        )
        self.assertEqual(public_draft.status_code, 200, public_draft.text)
        self.assertEqual(public_draft.json()["document_type"], "legal-notice")
        self.assertIn("draft_html", public_draft.json())
        self.assertTrue(public_draft.json()["review_warnings"])

        index = self.client.get("/index.html")
        self.assertEqual(index.status_code, 200, index.text)
        self.assertIn("/js/csp-styles.js", index.text)
        self.assertIn("/js/csp-events.js", index.text)

        duplicate_setup = self.client.post(
            "/api/v2/auth/setup",
            json={"email": "other@example.com", "display_name": "Other", "password": "0123456789ab"},
        )
        self.assertEqual(duplicate_setup.status_code, 409, duplicate_setup.text)

        workspace = self.client.post("/api/v2/workspaces", json={"name": "Launch Workspace", "slug": "launch"})
        self.assertEqual(workspace.status_code, 201, workspace.text)
        workspace_id = workspace.json()["id"]

        invalid_matter = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/matters",
            json={"name": "Invalid Matter", "status": "surprise"},
        )
        self.assertEqual(invalid_matter.status_code, 400, invalid_matter.text)

        matter = self.client.post(f"/api/v2/workspaces/{workspace_id}/matters", json={"name": "Launch Matter"})
        self.assertEqual(matter.status_code, 201, matter.text)
        matter_id = matter.json()["id"]

        closed_matter = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/matters",
            json={"name": "Closed Matter", "status": "closed"},
        )
        self.assertEqual(closed_matter.status_code, 201, closed_matter.text)
        self.assertEqual(closed_matter.json()["status"], "closed")

        with SessionLocal() as db:
            stale_workspace = Workspace(
                id=f"stale-workspace-{uuid.uuid4().hex}",
                name="Stale Reuse",
                slug="stale-reuse",
                created_by_user_id=admin_user_id,
                deleted_at=utcnow(),
            )
            db.add(stale_workspace)
            db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=stale_workspace.id, user_id=admin_user_id, role="admin"))
            db.commit()
        reused = self.client.post("/api/v2/workspaces", json={"name": "Stale Reuse", "slug": "stale-reuse"})
        self.assertEqual(reused.status_code, 201, reused.text)
        self.assertEqual(reused.json()["slug"], "stale-reuse")

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
        with SessionLocal() as db:
            embeddings = db.query(KnowledgeEmbedding).filter(KnowledgeEmbedding.document_id == upload.json()["id"]).all()
            self.assertGreaterEqual(len(embeddings), 1)
            self.assertEqual(embeddings[0].provider, "local")
            self.assertEqual(embeddings[0].model, "hashing-ngrams-v1")
            chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == upload.json()["id"]).one()
            chunk_metadata = json.loads(chunk.metadata_json)
            self.assertEqual(chunk_metadata["source_anchor_version"], "1")
            self.assertEqual(chunk_metadata["filename"], "contract.txt")
            self.assertEqual(chunk_metadata["start_offset"], 0)
            self.assertGreater(chunk_metadata["end_offset"], chunk_metadata["start_offset"])
            self.assertIn("extraction_method", chunk_metadata)
            builtin_playbooks = db.query(ContractPlaybook).filter(ContractPlaybook.is_builtin.is_(True)).all()
            self.assertGreaterEqual(len(builtin_playbooks), 7)
            builtin_msa = next(playbook for playbook in builtin_playbooks if playbook.id == "builtin-msa-v1")
            self.assertEqual(builtin_msa.version, "1.1")
        documents = self.client.get(f"/api/v2/workspaces/{workspace_id}/documents?page=1&page_size=10&matter_id={matter_id}")
        self.assertEqual(documents.status_code, 200, documents.text)
        self.assertEqual(documents.json()["pages"], 1)
        self.assertFalse(documents.json()["has_next"])
        self.assertFalse(documents.json()["has_previous"])

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

        invalid_member = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/members",
            json={"email": "notanemail", "display_name": "Invalid", "password": "abcdefgh1234", "role": "member"},
        )
        self.assertEqual(invalid_member.status_code, 400, invalid_member.text)

        with TestClient(app) as member_client:
            login = member_client.post(
                "/api/v2/auth/login",
                json={"identifier": "member@example.com", "password": "abcdefgh1234"},
            )
            self.assertEqual(login.status_code, 200, login.text)
            members_denied = member_client.get(f"/api/v2/workspaces/{workspace_id}/members")
            self.assertEqual(members_denied.status_code, 403, members_denied.text)
            bulk_delete_denied = member_client.delete(f"/api/v2/workspaces/{workspace_id}/documents")
            self.assertEqual(bulk_delete_denied.status_code, 403, bulk_delete_denied.text)

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
        chat_activity = self.client.get("/api/v2/admin/activity?category=chat&page_size=10")
        self.assertEqual(chat_activity.status_code, 200, chat_activity.text)
        self.assertTrue(any(item["action"] == "chat.create" and item["workspace_id"] == workspace_id for item in chat_activity.json()["items"]))

        removed_plugins = self.client.get(f"/api/v2/workspaces/{workspace_id}/plugins")
        self.assertEqual(removed_plugins.status_code, 404, removed_plugins.text)
        removed_blueprints = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints")
        self.assertEqual(removed_blueprints.status_code, 404, removed_blueprints.text)

        playbooks = self.client.get(f"/api/v2/workspaces/{workspace_id}/contract-review/playbooks")
        self.assertEqual(playbooks.status_code, 200, playbooks.text)
        self.assertGreaterEqual(len(playbooks.json()), 7)
        self.assertTrue(any(item["contract_category"] == "dpa" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "sow" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "saas" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "consulting" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "reseller" for item in playbooks.json()))
        with patch("app.core.contract_agents.agentic_review.complete_with_configured_llm", return_value="not json"):
            review = self.client.post(
                f"/api/v2/workspaces/{workspace_id}/contract-review",
                json={
                    "title": "Standalone Contract Review",
                    "matter_id": matter_id,
                    "document_ids": [upload.json()["id"]],
                    "playbook_id": "builtin-msa-v1",
                    "review_depth": "detailed",
                },
            )
            self.assertEqual(review.status_code, 200, review.text)
            queued_review = review.json()
            self.assertEqual(queued_review["status"], "queued")
            review_job = self.wait_for_job(workspace_id, queued_review["job"]["id"])
        self.assertEqual(review_job["job"]["status"], "completed", review_job)
        review_result = self.client.get(f"/api/v2/workspaces/{workspace_id}/contract-review/runs/{queued_review['run_id']}")
        self.assertEqual(review_result.status_code, 200, review_result.text)
        review_json = review_result.json()
        self.assertEqual(review_json["mode"], "standalone")
        self.assertEqual(review_json["playbook"]["id"], "builtin-msa-v1")
        self.assertIn("workflow", review_json)
        self.assertGreaterEqual(review_json["workflow"]["stats"]["clauses"], 1)
        self.assertGreaterEqual(len(review_json["workflow"]["summaries"]), 1)
        self.assertGreaterEqual(len(review_json["workflow"]["trace"]), 5)
        self.assertTrue(review_json["workflow"]["clauses"][0]["clause"]["source"].get("excerpt"))
        self.assertIn("agentic_review", review_json)
        self.assertIn("persisted", review_json)
        with SessionLocal() as db:
            stored_run = db.get(ContractReviewRun, queued_review["run_id"])
            self.assertIsNotNone(stored_run)
            self.assertEqual(stored_run.mode, "agentic_standalone")
            self.assertEqual(
                db.query(ContractReviewOutput).filter(ContractReviewOutput.run_id == queued_review["run_id"]).count(),
                1,
            )
            self.assertGreaterEqual(
                db.query(ContractClause).filter(ContractClause.run_id == queued_review["run_id"]).count(),
                1,
            )
            self.assertGreaterEqual(
                db.query(ContractReviewStepOutput).filter(ContractReviewStepOutput.run_id == queued_review["run_id"]).count(),
                1,
            )
        review_activity = self.client.get("/api/v2/admin/activity?category=contract_review&page_size=10")
        self.assertEqual(review_activity.status_code, 200, review_activity.text)
        self.assertTrue(any(item["action"] == "contract_review_standalone.run" and item["workspace_id"] == workspace_id for item in review_activity.json()["items"]))
        activity_export = self.client.get("/api/v2/admin/activity/export.csv?category=chat")
        self.assertEqual(activity_export.status_code, 200, activity_export.text)
        self.assertIn("text/csv", activity_export.headers["content-type"])
        self.assertIn("chat.create", activity_export.text)

        stored_file = UPLOADS_PATH / upload.json()["storage_key"]
        self.assertTrue(stored_file.exists())
        delete_all = self.client.delete(f"/api/v2/workspaces/{workspace_id}/documents")
        self.assertEqual(delete_all.status_code, 200, delete_all.text)
        self.assertEqual(delete_all.json()["deleted"], 1)
        self.assertFalse(stored_file.exists())

    def test_malformed_secret_decrypts_to_empty_string(self) -> None:
        self.assertEqual(decrypt_secret("not encrypted"), "")

    def test_document_indexer_preserves_page_break_source_anchors(self) -> None:
        path = ROOT / "paged_contract.txt"
        path.write_text("Page one indemnity.\fPage two termination.", encoding="utf-8")
        chunks = _extract_chunks(path, "paged_contract.txt")
        self.assertEqual([chunk["page"] for chunk in chunks], [1, 2])
        self.assertEqual(chunks[0]["start_offset"], 0)
        self.assertIn("indemnity", chunks[0]["content"])
        self.assertIn("termination", chunks[1]["content"])

    def test_contract_agent_tools_return_evidence_and_playbook_context(self) -> None:
        playbook_clause = ContractPlaybookClause(
            id=str(uuid.uuid4()),
            playbook_id="playbook-1",
            clause_type="indemnity",
            title="Indemnity",
            approved_text="Mutual indemnity only.",
            fallback_text="Each party indemnifies the other for third-party claims caused by its breach.",
            prohibited_patterns_json=json.dumps(["uncapped indemnity"]),
            required=True,
            severity_default="high",
        )
        workflow = {
            "clauses": [
                {
                    "clause": {
                        "id": "clause-1",
                        "clause_type": "indemnity",
                        "text": "Supplier provides uncapped indemnity.",
                        "source": {"excerpt": "Supplier provides uncapped indemnity."},
                    },
                    "risks": [{"risk_level": "critical", "requires_review": True}],
                }
            ],
            "escalations": [],
            "trace": [],
        }
        result = run_contract_agent_tools(
            requests=[
                {"tool": "targeted_document_retrieval", "query": "uncapped indemnity"},
                {"tool": "playbook_lookup", "clause_types": ["indemnity"]},
                {"tool": "clause_evidence_verifier"},
            ],
            source_bundle=[{"content": "Supplier provides uncapped indemnity.", "filename": "contract.txt", "chunk_index": 0}],
            workflow=workflow,
            playbook=None,
            playbook_clauses=[playbook_clause],
        )
        outputs = {item["tool"]: item["output"] for item in result["tool_results"]}
        self.assertTrue(outputs["targeted_document_retrieval"][0]["excerpt"])
        self.assertEqual(outputs["playbook_lookup"]["clauses"][0]["fallback_text"], playbook_clause.fallback_text)
        self.assertTrue(outputs["clause_evidence_verifier"][0]["supported"])

    def test_clause_extractor_preserves_segment_offsets(self) -> None:
        text = "Intro text before clauses.\n1. Termination: Either party may terminate for breach after notice.\n2. Payment: Fees are due within 30 days."
        clauses = extract_clauses(
            [
                {
                    "content": text,
                    "filename": "contract.txt",
                    "chunk_index": 0,
                    "start_offset": 100,
                    "end_offset": 100 + len(text),
                }
            ]
        )
        by_type = {clause.clause_type: clause for clause in clauses}
        self.assertIn("termination", by_type)
        self.assertIn("payment", by_type)
        termination = by_type["termination"]
        expected_start = 100 + text.index("1. Termination")
        self.assertEqual(termination.source.start_offset, expected_start)
        self.assertGreater(termination.source.end_offset, termination.source.start_offset)
        self.assertIn("Termination", termination.source.excerpt)

    def test_clause_extractor_tracks_window_offsets_and_varies_confidence(self) -> None:
        prefix = "Background information. " * 430
        text = prefix + "\n1. Termination: Either party may terminate this agreement for material breach after notice and cure. Termination rights survive."
        clauses = extract_clauses(
            [
                {
                    "content": text,
                    "filename": "long-contract.txt",
                    "chunk_index": 0,
                    "start_offset": 200,
                    "end_offset": 200 + len(text),
                }
            ],
            window_size=800,
            overlap=50,
        )
        termination = next(clause for clause in clauses if clause.clause_type == "termination")
        self.assertEqual(termination.source.start_offset, 200 + text.index("1. Termination"))
        self.assertEqual(termination.source.end_offset, termination.source.start_offset + len(termination.text))

        varied = extract_clauses(
            [
                {"content": "Payment must be received within 30 days.", "filename": "a.txt", "chunk_index": 0, "start_offset": 0},
                {"content": "1. Termination: Either party may terminate for breach after notice and cure. Termination remedies survive.", "filename": "b.txt", "chunk_index": 1, "start_offset": 100},
            ]
        )
        scores = {clause.clause_type: clause.confidence_score for clause in varied}
        self.assertGreater(scores["termination"], scores["payment"])

    def test_clause_extractor_recognizes_commercial_playbook_terms(self) -> None:
        text = (
            "1. Subscription Scope: Customer may access the service for authorized users subject to usage limits.\n"
            "2. Availability: Provider will meet the SLA and uptime commitment.\n"
            "3. Marks: Supplier retains all trademarks and brand assets.\n"
            "4. Compliance: Reseller must comply with anti-bribery and export controls.\n"
            "5. Fees: Pricing, discounts, taxes, expenses, and chargebacks are stated."
        )
        clauses = extract_clauses([{"content": text, "filename": "commercial.txt", "chunk_index": 0, "start_offset": 0}])
        by_type = {clause.clause_type for clause in clauses}
        self.assertIn("scope", by_type)
        self.assertIn("warranties", by_type)
        self.assertIn("ip", by_type)
        self.assertIn("payment", by_type)

    def test_redliner_uses_playbook_fallback_language(self) -> None:
        clause = ContractClause(id="clause-1", clause_type="limitation_of_liability", text="Unlimited liability applies.", review_status="pending")
        playbook_clause = ContractPlaybookClause(
            id="playbook-clause-1",
            clause_type="limitation_of_liability",
            title="Limitation of Liability",
            approved_text="Liability cap is mutual.",
            fallback_text="Each party's aggregate liability is capped at fees paid in the prior 12 months.",
            required=True,
            severity_default="critical",
        )
        risk = RiskFindingResult(
            clause_id="clause-1",
            clause_type="limitation_of_liability",
            risk_level="critical",
            reasoning="Clause appears to contain prohibited language.",
        )
        suggestions = suggest_redlines([clause], [risk], [playbook_clause])
        self.assertEqual(len(suggestions), 1)
        self.assertIn("Liability cap is mutual", suggestions[0].suggestion_text)
        self.assertEqual(suggestions[0].fallback_language, playbook_clause.fallback_text)

    def test_redliner_suggests_generic_language_for_medium_unknown_clause(self) -> None:
        clause = ContractClause(id="clause-unknown", clause_type="non_compete", text="A non-compete applies.", review_status="pending")
        risk = RiskFindingResult(
            clause_id="clause-unknown",
            clause_type="non_compete",
            risk_level="medium",
            reasoning="Clause was extracted but has no matching playbook standard.",
        )
        suggestions = suggest_redlines([clause], [risk], [])
        self.assertEqual(len(suggestions), 1)
        self.assertIn("preferred position", suggestions[0].suggestion_text)

    def test_playbook_comparator_does_not_mark_deterministic_pass_as_approved(self) -> None:
        clause = ContractClause(id="clause-1", clause_type="payment", text="Customer pays undisputed invoices within 30 days.", review_status="pending")
        playbook_clause = ContractPlaybookClause(
            id="playbook-clause-1",
            clause_type="payment",
            title="Payment",
            approved_text="Customer pays undisputed invoices within 30 days.",
            fallback_text="Customer will pay undisputed invoices within 30 days.",
            prohibited_patterns_json=json.dumps(["payment due immediately"]),
            required=True,
            severity_default="medium",
        )
        findings = compare_to_playbook([clause], [playbook_clause])
        self.assertEqual(findings[0].status, "no_prohibited_match")
        self.assertIn("semantic alignment", findings[0].deviation_summary)
        risks = score_risks(findings)
        self.assertEqual(risks[0].risk_level, "low")

    def test_select_playbook_ignores_other_workspace_playbooks(self) -> None:
        unique = uuid.uuid4().hex
        with SessionLocal() as db:
            user = User(id=f"user-{unique}", email=f"{unique}@example.test", display_name="Scope Test", password_hash="x")
            workspace_a = Workspace(id=f"workspace-a-{unique}", name="Workspace A", slug=f"workspace-a-{unique}", created_by_user_id=user.id)
            workspace_b = Workspace(id=f"workspace-b-{unique}", name="Workspace B", slug=f"workspace-b-{unique}", created_by_user_id=user.id)
            db.add_all([user, workspace_a, workspace_b])
            db.commit()

            foreign_playbook = ContractPlaybook(
                id=f"foreign-playbook-{unique}",
                workspace_id=workspace_a.id,
                name="Foreign NDA",
                contract_category="nda",
                version="1.0",
                status="active",
                rules_json="{}",
                is_builtin=False,
                created_by_user_id=user.id,
            )
            db.add(foreign_playbook)
            db.commit()

            selected = _select_playbook(db, workspace_b.id, None, "nda")
            self.assertIsNotNone(selected)
            self.assertNotEqual(selected.id, foreign_playbook.id)
            self.assertIsNone(selected.workspace_id)
            self.assertEqual(selected.contract_category, "nda")

    def test_contract_intake_routes_supply_agreement_to_vendor_playbook(self) -> None:
        intake = run_intake(
            "Supply Agreement between Acme Buyer and Widget Supplier. "
            "Supplier will deliver products under purchase order terms with fees, warranties, and termination rights. "
            "The parties also agree to non-disclosure obligations for confidential information."
        )
        self.assertEqual(intake.contract_category, "msa")
        self.assertEqual(intake.contract_type, "Supply/Vendor Agreement")
        with SessionLocal() as db:
            selected = _select_playbook(db, "missing-workspace-for-builtins", None, intake.contract_category)
            self.assertIsNotNone(selected)
            self.assertEqual(selected.id, "builtin-msa-v1")

    def test_auto_select_does_not_fall_back_to_unrelated_playbook(self) -> None:
        with SessionLocal() as db:
            selected = _select_playbook(db, "missing-workspace-for-builtins", None, "general")
            self.assertIsNone(selected)

    def test_contract_review_does_not_publish_without_llm_provider(self) -> None:
        with self.assertRaisesRegex(ContractReviewAgentError, "no LLM provider is configured"):
            run_agentic_contract_review(
                text="termination liability indemnity",
                sources=[],
                config={},
                workflow={},
                deterministic_extraction={},
                deterministic_risks=[],
                deterministic_negotiation_memo="fallback memo",
                deterministic_client_summary="fallback summary",
                settings={},
            )

    def test_contract_review_does_not_publish_when_provider_rejects_large_request(self) -> None:
        error = (
            "Error code: 413 - {'error': {'message': 'Request too large for model `openai/gpt-oss-120b` "
            "on tokens per minute (TPM): Limit 8000, Requested 23427', 'type': 'tokens', "
            "'code': 'rate_limit_exceeded'}}"
        )
        with patch("app.core.contract_agents.agentic_review.complete_with_configured_llm", side_effect=Exception(error)):
            with self.assertRaisesRegex(ContractReviewAgentError, "Groq rejected the request as too large"):
                run_agentic_contract_review(
                    text="termination liability indemnity",
                    sources=[],
                    config={},
                    workflow={},
                    deterministic_extraction={},
                    deterministic_risks=[],
                    deterministic_negotiation_memo="fallback memo",
                    deterministic_client_summary="fallback summary",
                    settings={"local_llm_provider": "groq", "groq_api_key": "test", "chat_model": "openai/gpt-oss-120b"},
                )

    def test_contract_review_agent_json_parser_handles_common_model_wrappers(self) -> None:
        self.assertEqual(_parse_agent_json('```json\n{"strategy":"targeted"}\n```'), {"strategy": "targeted"})
        self.assertEqual(_parse_agent_json('Here is the JSON:\n{"strategy":"targeted","tool_requests":[]}\nDone.'), {"strategy": "targeted", "tool_requests": []})
        self.assertEqual(_parse_agent_json('{"strategy":"targeted","tool_requests":[],}'), {"strategy": "targeted", "tool_requests": []})

    def test_contract_review_uses_deterministic_fallback_when_agents_return_invalid_json(self) -> None:
        progress_events: list[tuple[str, int]] = []
        with patch("app.core.contract_agents.agentic_review.complete_with_configured_llm", return_value="I cannot return JSON for this request."):
            result = run_agentic_contract_review(
                text="termination liability indemnity",
                sources=[],
                config={},
                workflow={},
                deterministic_extraction={"parties": {"value": "Acme and Vendor", "supported": True}},
                deterministic_risks=[{"issue": "Liability", "severity": "medium"}],
                deterministic_negotiation_memo="fallback memo",
                deterministic_client_summary="fallback summary",
                settings={"local_llm_provider": "openai", "openai_api_key": "test", "chat_model": "gpt-test"},
                progress_callback=lambda message, progress: progress_events.append((message, progress)),
            )

        self.assertEqual(result["extraction"], {"parties": {"value": "Acme and Vendor", "supported": True}})
        self.assertEqual(result["risk_matrix"], [{"issue": "Liability", "severity": "medium"}])
        self.assertEqual(result["negotiation_memo"], "fallback memo")
        self.assertEqual(result["client_summary"], "fallback summary")
        self.assertTrue(any(step["status"] == "fallback" for step in result["agent_trace"]))
        self.assertTrue(any("malformed JSON" in message for message, _progress in progress_events))
        self.assertGreaterEqual(max(progress for _message, progress in progress_events), 84)

    def test_contract_review_runner_classifies_provider_invalid_json_as_fallback(self) -> None:
        error = "Contract review could not run because Anthropic returned an agent error: Agent returned invalid JSON."
        self.assertTrue(_is_agent_invalid_json_error(error))
        self.assertTrue(_is_agent_invalid_json_error("Contract review agent `risk_analysis_agent` did not return required list `risk_matrix`."))
        self.assertTrue(_is_agent_invalid_json_error("Contract review could not run because Openrouter returned an agent error: Expecting value: line 253 column 1 (char 1386)"))
        fallback = _deterministic_agentic_review_fallback(
            provider="anthropic",
            model="claude-test",
            error=error,
            extraction={"parties": {"value": "Acme and Vendor"}},
            risks=[{"issue": "Termination", "severity": "medium"}],
            negotiation_memo_text="fallback memo",
            client_summary_text="fallback summary",
        )
        self.assertEqual(fallback["negotiation_memo"], "fallback memo")
        self.assertEqual(fallback["agent_trace"][0]["status"], "fallback")
        self.assertEqual(fallback["agent_trace"][0]["provider"], "anthropic")

    def test_contract_review_uses_fallback_when_agents_return_wrong_json_shape(self) -> None:
        progress_events: list[tuple[str, int]] = []

        def fake_complete(_settings, system, _user, **_kwargs):
            if "review_planner_agent" in system:
                return json.dumps({"plan": "targeted"})
            if "intake_and_extraction_agent" in system:
                return json.dumps({"fields": "not an object"})
            if "risk_analysis_agent" in system:
                return json.dumps({"risk_matrix": {"items": "not a list"}, "risks": "also wrong"})
            if "negotiation_agent" in system:
                return json.dumps({"negotiation_memo": ["not", "text"]})
            if "client_summary_agent" in system:
                return json.dumps({"client_summary": {"text": "not plain text"}})
            if "quality_control_agent" in system:
                return json.dumps({"approved": "yes", "issues": {}, "corrections": []})
            return json.dumps({"revision_notes": "none"})

        with patch("app.core.contract_agents.agentic_review.complete_with_configured_llm", side_effect=fake_complete):
            result = run_agentic_contract_review(
                text="termination liability indemnity",
                sources=[],
                config={},
                workflow={},
                deterministic_extraction={"parties": {"value": "Acme and Vendor", "supported": True}},
                deterministic_risks=[{"issue": "Liability", "severity": "medium"}],
                deterministic_negotiation_memo="fallback memo",
                deterministic_client_summary="fallback summary",
                settings={"local_llm_provider": "openai", "openai_api_key": "test", "chat_model": "gpt-test"},
                progress_callback=lambda message, progress: progress_events.append((message, progress)),
            )

        self.assertEqual(result["extraction"], {"parties": {"value": "Acme and Vendor", "supported": True}})
        self.assertEqual(result["risk_matrix"], [{"issue": "Liability", "severity": "medium"}])
        self.assertEqual(result["negotiation_memo"], "fallback memo")
        self.assertEqual(result["client_summary"], "fallback summary")
        fallback_steps = [step["step_name"] for step in result["agent_trace"] if step["status"] == "fallback"]
        self.assertIn("risk_analysis_agent", fallback_steps)
        self.assertIn("negotiation_agent", fallback_steps)
        self.assertIn("client_summary_agent", fallback_steps)
        self.assertTrue(any("incomplete JSON" in message for message, _progress in progress_events))

    def test_contract_review_agent_payloads_are_task_scoped(self) -> None:
        captured_payloads: list[dict] = []

        def fake_complete(_settings, system, user, **_kwargs):
            captured_payloads.append(json.loads(user))
            if "review_planner_agent" in system:
                return json.dumps(
                    {
                        "strategy": "targeted",
                        "required_agents": [],
                        "tool_requests": [
                            {"tool": "targeted_document_retrieval", "query": "payment termination indemnity", "limit": 5},
                            {"tool": "risk_scoring"},
                            {"tool": "missing_clause_detector"},
                            {"tool": "redline_fallback_lookup", "clause_types": ["payment", "termination"]},
                        ],
                    }
                )
            if "intake_and_extraction_agent" in system:
                return json.dumps(
                    {
                        "extraction": {
                            "parties": {"value": "Supplier and Purchaser", "supported": True, "confidence_score": 0.9},
                            "renewal_term": {"value": "automatic renewal", "supported": True, "confidence_score": 0.2},
                            "governing_law": {"value": "New York", "supported": False, "confidence_score": 0.7},
                        }
                    }
                )
            if "risk_analysis_agent" in system:
                return json.dumps({"risk_matrix": [{"issue": "Payment timing", "severity": "medium", "finding": "Review payment timing.", "requires_review": True}]})
            if "negotiation_agent" in system:
                return json.dumps({"negotiation_memo": "Review payment timing and termination cure periods."})
            if "client_summary_agent" in system:
                return json.dumps({"client_summary": "The review found payment and termination points for lawyer review."})
            if "quality_control_agent" in system:
                return json.dumps({"approved": True, "issues": [], "corrections": {}})
            return json.dumps({"revision_notes": "none"})

        long_text = "Supplier shall provide deliverables. Payment termination indemnity confidentiality. " * 900
        workflow = {
            "version": "test",
            "intake": {"contract_category": "msa", "contract_type": "Supply Agreement"},
            "stats": {"clauses": 80, "review_needed": 20},
            "clauses": [
                {
                    "clause": {
                        "id": f"clause-{index}",
                        "clause_type": "payment" if index % 2 else "termination",
                        "title": "Payment" if index % 2 else "Termination",
                        "text": ("Long clause text " + str(index) + " ") * 240,
                        "source": {"filename": "supply.htm", "chunk_index": index, "excerpt": ("Long source excerpt " + str(index) + " ") * 120},
                        "confidence_score": 0.75,
                    },
                    "risks": [{"risk_level": "high" if index % 3 == 0 else "medium", "reasoning": ("Risk reasoning " + str(index) + " ") * 80, "requires_review": True}],
                    "playbook_findings": [{"status": "no_prohibited_match", "deviation_summary": ("Finding " + str(index) + " ") * 80}],
                    "redline_suggestions": [{"fallback_language": ("Fallback " + str(index) + " ") * 80}],
                }
                for index in range(80)
            ],
            "unattached_risk_findings": [{"clause_type": "governing_law", "risk_level": "high", "reasoning": "Missing governing law."}],
            "escalations": [{"severity": "high", "reason": ("Escalation reason " * 60), "required_action": "Review."}],
        }
        sources = [{"filename": "supply.htm", "chunk": index + 1, "excerpt": ("Source excerpt " + str(index) + " ") * 260} for index in range(30)]
        source_bundle = [{"filename": "supply.htm", "chunk_index": index, "content": ("Bundle content payment termination " + str(index) + " ") * 240} for index in range(30)]

        with patch("app.core.contract_agents.agentic_review.complete_with_configured_llm", side_effect=fake_complete):
            result = run_agentic_contract_review(
                text=long_text,
                sources=sources,
                config={"instructions": "Focus on payment and termination."},
                workflow=workflow,
                deterministic_extraction={"parties": {"value": None, "supported": False}},
                deterministic_risks=[],
                deterministic_negotiation_memo="fallback memo",
                deterministic_client_summary="fallback summary",
                settings={"local_llm_provider": "openai", "openai_api_key": "test", "chat_model": "gpt-test"},
                tool_context={"source_bundle": source_bundle, "playbook": None, "playbook_clauses": [], "supported_tools": []},
            )

        self.assertEqual(result["client_summary"], "The review found payment and termination points for lawyer review.")
        self.assertEqual(len(captured_payloads), 6)
        serialized_payloads = [json.dumps(payload, sort_keys=True) for payload in captured_payloads]
        self.assertTrue(all(len(payload) < 30000 for payload in serialized_payloads))
        self.assertTrue(all("workflow_clauses" not in payload for payload in serialized_payloads))
        self.assertTrue(all("text_excerpt" not in payload for payload in serialized_payloads))
        self.assertTrue(all("Bundle content payment termination" not in payload for payload in serialized_payloads))
        risk_payload = next(payload for payload in captured_payloads if payload.get("task", {}).get("clauses"))
        self.assertLessEqual(len(risk_payload["task"]["clauses"]), 12)
        self.assertLessEqual(len(risk_payload["task"]["clauses"][0]["text"]), 503)
        self.assertNotIn("renewal_term", risk_payload["task"]["extraction"])
        self.assertNotIn("governing_law", risk_payload["task"]["extraction"])
        self.assertEqual({item["field"] for item in risk_payload["task"]["uncertain_extraction_fields"]}, {"renewal_term", "governing_law"})
        negotiation_payload = next(payload for payload in captured_payloads if payload.get("task", {}).get("fallback_language") is not None)
        self.assertLessEqual(len(negotiation_payload["source_excerpts"]), 3)
        self.assertTrue(negotiation_payload["task"]["grounding_clause_excerpts"])

    def test_conflict_detector_flags_duplicate_governing_law(self) -> None:
        clauses = [
            ContractClause(id="clause-1", clause_type="governing_law", text="This agreement is governed by New York law.", review_status="pending"),
            ContractClause(id="clause-2", clause_type="governing_law", text="This agreement is governed by California law.", review_status="pending"),
        ]
        conflicts = detect_conflicts(clauses)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].severity, "high")
        self.assertEqual(conflicts[0].metadata["conflict_type"], "duplicate_unique_clause")

    def test_conflict_detector_flags_payment_ip_and_liability_conflicts(self) -> None:
        clauses = [
            ContractClause(id="pay-1", clause_type="payment", text="Invoices are payable within 30 days after receipt.", review_status="pending"),
            ContractClause(id="pay-2", clause_type="payment", text="Customer will pay net 60 days from invoice date.", review_status="pending"),
            ContractClause(id="ip-1", clause_type="ip", text="Customer shall own all work product and deliverables.", review_status="pending"),
            ContractClause(id="ip-2", clause_type="ip", text="Provider retains ownership of all intellectual property.", review_status="pending"),
            ContractClause(id="lol-1", clause_type="limitation_of_liability", text="All liability is capped at fees paid in the prior twelve months.", review_status="pending"),
            ContractClause(id="lol-2", clause_type="limitation_of_liability", text="Except for indemnity and confidentiality claims, the cap applies.", review_status="pending"),
        ]
        conflict_types = {item.metadata["conflict_type"] for item in detect_conflicts(clauses)}
        self.assertIn("payment_timing", conflict_types)
        self.assertIn("ip_ownership", conflict_types)
        self.assertIn("liability_carveouts", conflict_types)

    def test_conflict_detector_flags_breach_indemnity_and_renewal_conflicts(self) -> None:
        clauses = [
            ContractClause(id="breach-1", clause_type="data_breach_notice", text="Processor must notify controller within 24 hours of a security incident.", review_status="pending"),
            ContractClause(id="breach-2", clause_type="data_breach_notice", text="Processor may provide breach notification within 5 days.", review_status="pending"),
            ContractClause(id="indemnity-1", clause_type="indemnity", text="Each party shall indemnify the other for third-party claims.", review_status="pending"),
            ContractClause(id="indemnity-2", clause_type="indemnity", text="Only provider shall indemnify customer for losses.", review_status="pending"),
            ContractClause(id="term-1", clause_type="termination", text="The agreement automatically renews for successive one-year terms.", review_status="pending"),
            ContractClause(id="term-2", clause_type="termination", text="The agreement will not renew unless the parties sign a written amendment.", review_status="pending"),
        ]
        conflict_types = {item.metadata["conflict_type"] for item in detect_conflicts(clauses)}
        self.assertIn("data_breach_notice_timing", conflict_types)
        self.assertIn("indemnity_scope", conflict_types)
        self.assertIn("renewal_terms", conflict_types)

    def test_intake_routes_builtin_contract_categories(self) -> None:
        dpa = run_intake("This Data Processing Agreement is between controller and processor for personal data.")
        sow = run_intake("This Statement of Work describes deliverables, milestones, and acceptance criteria.")
        saas = run_intake("This SaaS subscription agreement covers access to the hosted software as a service.")
        consulting = run_intake("This consulting agreement covers professional services and deliverables.")
        reseller = run_intake("This reseller agreement appoints an authorized reseller for the products.")
        self.assertEqual(dpa.contract_category, "dpa")
        self.assertEqual(sow.contract_category, "sow")
        self.assertEqual(saas.contract_category, "saas")
        self.assertEqual(consulting.contract_category, "consulting")
        self.assertEqual(reseller.contract_category, "reseller")

    def test_builtin_personas_are_lawyer_focused(self) -> None:
        personas = {persona["id"]: persona for persona in database._builtin_personas()}
        self.assertEqual(
            set(personas),
            {
                "the-mediator",
                "the-arbitrator",
                "the-legal-explainer",
                "regulatory-compliance-analyst",
                "legal-researcher",
                "case-law-analyst",
                "litigation-drafting-assistant",
                "cross-examination-strategist",
                "due-diligence-reviewer",
                "client-intake-interviewer",
                "chronology-builder",
                "evidence-organizer",
                "settlement-evaluator",
                "the-contract-reviewer",
                "the-devils-advocate-legal",
                "the-legal-strategist",
                "the-courtroom-coach",
            },
        )
        expected_categories = {
            "the-mediator": "Dispute Resolution",
            "the-arbitrator": "Dispute Resolution",
            "settlement-evaluator": "Dispute Resolution",
            "litigation-drafting-assistant": "Litigation",
            "cross-examination-strategist": "Litigation",
            "the-devils-advocate-legal": "Litigation",
            "the-courtroom-coach": "Litigation",
            "the-legal-explainer": "Legal Research",
            "legal-researcher": "Legal Research",
            "case-law-analyst": "Legal Research",
            "the-contract-reviewer": "Contracts & Transactions",
            "due-diligence-reviewer": "Contracts & Transactions",
            "regulatory-compliance-analyst": "Compliance",
            "client-intake-interviewer": "Matter Management",
            "chronology-builder": "Matter Management",
            "evidence-organizer": "Matter Management",
            "the-legal-strategist": "Strategy",
        }
        self.assertEqual({persona_id: persona["category"] for persona_id, persona in personas.items()}, expected_categories)

    def test_retired_builtin_personas_are_removed_from_existing_database(self) -> None:
        conn = database.get_connection()
        now = "2026-06-20T00:00:00+00:00"
        conn.execute(
            """
            INSERT OR REPLACE INTO personas
            (id, name, category, description, system_prompt, constraints_json, output_format_json, tags_json, is_builtin, is_enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """,
            (
                "richard-feynman",
                "Richard Feynman",
                "Expert Explainers",
                "Retired built-in",
                "Retired built-in prompt",
                "[]",
                "{}",
                "[]",
                now,
                now,
            ),
        )
        conn.commit()
        conn.close()

        database.init_db()

        conn = database.get_connection()
        row = conn.execute("SELECT id FROM personas WHERE id = ?", ("richard-feynman",)).fetchone()
        conn.close()
        self.assertIsNone(row)

    def test_runtime_security_rejects_insecure_production_cookies(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_runtime_security(Settings(environment="production", secure_cookies=False))

    def test_packaged_runtime_rejects_lan_bind_with_insecure_cookies(self) -> None:
        with patch("app.core.config.sys.frozen", True, create=True):
            with self.assertRaisesRegex(RuntimeError, "cannot listen on all interfaces"):
                validate_runtime_security(Settings(host="0.0.0.0", secure_cookies=False))

    def test_local_binary_defaults_to_loopback_host(self) -> None:
        previous_host = os.environ.get("AI_BLUEPRINT_HOST")
        try:
            os.environ.pop("AI_BLUEPRINT_HOST", None)
            get_settings.cache_clear()
            self.assertEqual(get_settings().host, "127.0.0.1")
        finally:
            if previous_host is None:
                os.environ.pop("AI_BLUEPRINT_HOST", None)
            else:
                os.environ["AI_BLUEPRINT_HOST"] = previous_host
            get_settings.cache_clear()

    def test_auth_rate_limit_uses_epoch_timestamps(self) -> None:
        class Client:
            host = "127.0.0.1"

        class Request:
            headers = {}
            client = Client()

        with SessionLocal() as db:
            _check_auth_rate_limit(db, Request(), "epoch-check")
            attempted_at = db.execute(
                text("SELECT attempted_at FROM auth_rate_limit_attempts WHERE client_key LIKE :key ORDER BY attempted_at DESC LIMIT 1"),
                {"key": "%epoch-check"},
            ).scalar_one()
        self.assertGreater(attempted_at, 1_700_000_000)

    def test_provider_errors_are_sanitized_before_user_display(self) -> None:
        error = "AuthenticationError: api_key=sk-testsecret123456789 account acct_123"
        sanitized = sanitize_provider_error(error)
        self.assertNotIn("sk-testsecret", sanitized)
        self.assertIn("Check your API key", sanitized)

    def test_contract_review_runtime_reads_workspace_api_key_secret(self) -> None:
        user_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        with SessionLocal() as db:
            user = User(
                id=user_id,
                username=f"secret-user-{user_id}@example.com",
                email=f"secret-user-{user_id}@example.com",
                display_name="Secret User",
                password_hash="test",
                is_system_admin=True,
            )
            workspace = Workspace(id=workspace_id, name="Secret Workspace", slug=f"secret-{workspace_id}", created_by_user_id=user.id)
            db.add(user)
            db.add(workspace)
            db.flush()
            db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=workspace.id, user_id=user.id, role="admin"))
            db.add(
                Secret(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace.id,
                    owner_user_id=None,
                    name="OPENAI_API_KEY",
                    encrypted_value=encrypt_secret("sk-workspace-secret-test"),
                    scope="workspace",
                    status="active",
                    created_by_user_id=user.id,
                )
            )
            db.flush()
            settings = _runtime_settings_for_workspace(db, workspace.id, user)
            db.rollback()
        self.assertEqual(settings["openai_api_key"], "sk-workspace-secret-test")

    def test_runtime_security_requires_bootstrap_password(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_runtime_security(Settings(bootstrap_default_admin=True, bootstrap_admin_password=None))

    def test_runtime_security_allows_explicit_bootstrap_password(self) -> None:
        validate_runtime_security(Settings(bootstrap_default_admin=True, bootstrap_admin_password="0123456789ab"))

    def test_production_disables_startup_migrations_by_default(self) -> None:
        previous = os.environ.get("AI_BLUEPRINT_ENV")
        previous_migrations = os.environ.get("AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP")
        try:
            os.environ["AI_BLUEPRINT_ENV"] = "production"
            os.environ.pop("AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP", None)
            get_settings.cache_clear()
            self.assertFalse(get_settings().run_migrations_on_startup)
        finally:
            if previous is None:
                os.environ.pop("AI_BLUEPRINT_ENV", None)
            else:
                os.environ["AI_BLUEPRINT_ENV"] = previous
            if previous_migrations is None:
                os.environ.pop("AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP", None)
            else:
                os.environ["AI_BLUEPRINT_RUN_MIGRATIONS_ON_STARTUP"] = previous_migrations
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
