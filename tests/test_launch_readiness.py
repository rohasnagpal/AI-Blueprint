import json
import os
import time
import unittest
import uuid
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

import database

database.DB_PATH = str(LEGACY_DB_PATH)
database.SECRET_KEY_FILE = str(LEGACY_SECRET_PATH)

from fastapi.testclient import TestClient

from main import app
from app.core.contract_agents.clause_extractor import extract_clauses
from app.core.contract_agents.conflict_detector import detect_conflicts
from app.core.contract_agents.intake import run_intake
from app.core.contract_agents.playbook_comparator import compare_to_playbook
from app.core.contract_agents.redliner import suggest_redlines
from app.core.contract_agents.risk_scorer import score_risks
from app.core.contract_agents.schemas import RiskFindingResult
from app.core.config import Settings, get_settings, validate_runtime_security
from app.core.database import SessionLocal
from app.core.document_indexer import _extract_chunks
from app.core.contract_review_workflow_runner import _select_playbook
from app.core.models import ContractClause, ContractPlaybook, ContractPlaybookClause, KnowledgeChunk, KnowledgeEmbedding, User, Workspace
from app.core.secrets import decrypt_secret


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
        self.assertEqual(health.json()["database"]["migration_revision"], "0023_translation_runs")
        self.assertTrue(health.json()["secrets"]["key_configured"])
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertEqual(health.headers["x-frame-options"], "DENY")
        csp = health.headers["content-security-policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertIn("script-src-attr 'none'", csp)
        self.assertIn("style-src-attr 'none'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

        public_translation = self.client.post(
            "/api/v2/translations/public/text",
            json={"text": "The agreement terminates on 31 December 2026.", "target_language": "Hindi", "mode": "legal"},
        )
        self.assertEqual(public_translation.status_code, 200, public_translation.text)
        self.assertEqual(public_translation.json()["source_type"], "text")
        self.assertEqual(public_translation.json()["target_language"], "Hindi")
        self.assertEqual(public_translation.json()["mode"], "legal")
        self.assertIn("translated_html", public_translation.json())

        index = self.client.get("/index.html")
        self.assertEqual(index.status_code, 200, index.text)
        self.assertIn("/js/csp-styles.js", index.text)
        self.assertIn("/js/csp-events.js", index.text)

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

        invalid_matter = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/matters",
            json={"name": "Invalid Matter", "status": "surprise"},
        )
        self.assertEqual(invalid_matter.status_code, 400, invalid_matter.text)

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
        documents = self.client.get(f"/api/v2/workspaces/{workspace_id}/documents?page=1&page_size=10")
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

        enable_contract_review = self.client.put(f"/api/v2/workspaces/{workspace_id}/plugins/contract_review", json={"enabled": True})
        self.assertEqual(enable_contract_review.status_code, 200, enable_contract_review.text)
        invalid_blueprint = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints",
            json={"name": "Invalid Blueprint", "plugin_id": "contract_review", "status": "surprise"},
        )
        self.assertEqual(invalid_blueprint.status_code, 400, invalid_blueprint.text)
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

        playbooks = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/playbooks")
        self.assertEqual(playbooks.status_code, 200, playbooks.text)
        self.assertGreaterEqual(len(playbooks.json()), 7)
        self.assertTrue(any(item["contract_category"] == "dpa" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "sow" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "saas" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "consulting" for item in playbooks.json()))
        self.assertTrue(any(item["contract_category"] == "reseller" for item in playbooks.json()))
        builtin_msa = next(item for item in playbooks.json() if item["id"] == "builtin-msa-v1")
        builtin_msa_detail = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/playbooks/{builtin_msa['id']}")
        self.assertEqual(builtin_msa_detail.status_code, 200, builtin_msa_detail.text)
        liability_standard = next(item for item in builtin_msa_detail.json()["clauses"] if item["clause_type"] == "limitation_of_liability")
        self.assertIn("Liability cap", liability_standard["approved_text"])
        self.assertIn("aggregate liability", liability_standard["fallback_text"])
        custom_playbook_payload = {
            "name": "Workspace Test MSA",
            "contract_category": "msa",
            "rules": {"review_posture": "balanced"},
            "clauses": [
                {
                    "clause_type": "limitation_of_liability",
                    "title": "Limitation of Liability",
                    "required": True,
                    "severity_default": "critical",
                    "prohibited_patterns": ["unlimited liability"],
                },
                {
                    "clause_type": "data_security",
                    "title": "Data Security",
                    "required": True,
                    "severity_default": "high",
                    "prohibited_patterns": [],
                },
            ],
        }
        custom_playbook = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/playbooks",
            json=custom_playbook_payload,
        )
        self.assertEqual(custom_playbook.status_code, 201, custom_playbook.text)
        self.assertFalse(custom_playbook.json()["is_builtin"])
        self.assertEqual(len(custom_playbook.json()["clauses"]), 2)
        custom_playbook_payload["name"] = "Workspace Test MSA v2"
        custom_playbook_payload["version"] = "1.1"
        updated_playbook = self.client.put(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/playbooks/{custom_playbook.json()['id']}",
            json=custom_playbook_payload,
        )
        self.assertEqual(updated_playbook.status_code, 200, updated_playbook.text)
        self.assertEqual(updated_playbook.json()["version"], "1.1")
        workflow_modules = self.client.get(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/workflow-modules"
        )
        self.assertEqual(workflow_modules.status_code, 200, workflow_modules.text)
        module_ids = [item["id"] for item in workflow_modules.json()["items"]]
        self.assertIn("clause_extraction", module_ids)
        self.assertIn("escalation_detection", module_ids)
        self.assertEqual(workflow_modules.json()["extension_contract"]["status"], "reserved")
        workflow_run = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs",
            json={"title": "Workflow Contract Review", "mode": "workflow", "config": {"playbook_id": custom_playbook.json()["id"]}},
        )
        self.assertEqual(workflow_run.status_code, 201, workflow_run.text)
        workflow_job = self.wait_for_job(workspace_id, workflow_run.json()["job"]["id"])
        self.assertEqual(workflow_job["job"]["status"], "completed", workflow_job)
        workflow_run_id = workflow_run.json()["id"]
        workflow_detail = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}")
        self.assertEqual(workflow_detail.status_code, 200, workflow_detail.text)
        self.assertEqual(workflow_detail.json()["run"]["mode"], "workflow")
        self.assertGreaterEqual(len(workflow_detail.json()["summaries"]), 1)
        trace = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/trace")
        self.assertEqual(trace.status_code, 200, trace.text)
        self.assertGreaterEqual(len(trace.json()), 5)
        clauses = self.client.get(f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/clauses")
        self.assertEqual(clauses.status_code, 200, clauses.text)
        self.assertGreaterEqual(len(clauses.json()), 1)
        self.assertTrue(clauses.json()[0]["clause"]["source"].get("excerpt"))
        escalations = self.client.get(f"/api/v2/workspaces/{workspace_id}/escalations/blueprints/{blueprint_id}")
        self.assertEqual(escalations.status_code, 200, escalations.text)
        workflow_escalations = [item for item in escalations.json()["items"] if item["source_id"] == workflow_run_id]
        self.assertGreaterEqual(len(workflow_escalations), 1)
        blocked_completion = self.client.put(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/complete"
        )
        self.assertEqual(blocked_completion.status_code, 409, blocked_completion.text)
        for escalation in workflow_escalations:
            dismissed = self.client.put(f"/api/v2/workspaces/{workspace_id}/escalations/{escalation['id']}/dismiss")
            self.assertEqual(dismissed.status_code, 200, dismissed.text)
            self.assertEqual(dismissed.json()["status"], "dismissed")
        clause_id = clauses.json()[0]["clause"]["id"]
        decision = self.client.post(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/clauses/{clause_id}/decisions",
            json={"decision": "approve", "note": "Reviewed in launch test."},
        )
        self.assertEqual(decision.status_code, 201, decision.text)
        clause_detail = self.client.get(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/clauses/{clause_id}"
        )
        self.assertEqual(clause_detail.status_code, 200, clause_detail.text)
        self.assertEqual(clause_detail.json()["decisions"][0]["decision"], "approve")
        self.assertIn("playbook_clauses", clause_detail.json())
        completed_review = self.client.put(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/complete"
        )
        self.assertEqual(completed_review.status_code, 200, completed_review.text)
        self.assertTrue(completed_review.json()["run"]["review_complete"])
        self.assertEqual(completed_review.json()["run"]["status_detail"], "Review complete")
        audit_package = self.client.get(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/audit-package"
        )
        self.assertEqual(audit_package.status_code, 200, audit_package.text)
        self.assertEqual(audit_package.json()["package_type"], "contract_review_workflow_audit")
        self.assertGreaterEqual(len(audit_package.json()["clauses"]), 1)
        self.assertGreaterEqual(len(audit_package.json()["step_trace"]), 5)
        self.assertGreaterEqual(len(audit_package.json()["escalations"]), 1)
        self.assertEqual(audit_package.json()["clauses"][0]["decisions"][0]["decision"], "approve")
        self.assertIn("not autonomous legal advice", audit_package.json()["human_oversight_notice"])
        workflow_export = self.client.get(
            f"/api/v2/workspaces/{workspace_id}/blueprints/{blueprint_id}/contract-review/runs/{workflow_run_id}/export"
        )
        self.assertEqual(workflow_export.status_code, 200, workflow_export.text)
        self.assertIn("## Clause Review", workflow_export.text)
        self.assertIn("AI-assisted workflow draft", workflow_export.text)
        self.assertIn("Completion: Human review complete", workflow_export.text)
        self.assertIn("Open escalations: 0", workflow_export.text)
        self.assertIn("Human decisions recorded: 1", workflow_export.text)

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

            selected = _select_playbook(db, {"playbook_id": foreign_playbook.id}, "nda", workspace_b.id)
            self.assertIsNotNone(selected)
            self.assertNotEqual(selected.id, foreign_playbook.id)
            self.assertIsNone(selected.workspace_id)
            self.assertEqual(selected.contract_category, "nda")

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

    def test_builtin_insurance_policy_explainer_persona(self) -> None:
        personas = {persona["id"]: persona for persona in database._builtin_personas()}
        persona = personas["insurance-policy-explainer-india"]
        self.assertEqual(persona["name"], "Insurance Policy Explainer")
        self.assertEqual(persona["category"], "Insurance")
        self.assertIn("global insurance policy explainer", persona["system_prompt"])
        self.assertIn("default to India", persona["system_prompt"])
        self.assertIn("health insurance", persona["tags"])
        self.assertTrue(any("country or jurisdiction is unclear" in item for item in persona["constraints"]))

    def test_builtin_consumer_document_personas(self) -> None:
        personas = {persona["id"]: persona for persona in database._builtin_personas()}
        expected = {
            "medical-bill-decoder": ("Medical Bill Decoder", "Healthcare"),
            "lease-agreement-reviewer": ("Lease Agreement Reviewer", "Housing"),
            "employment-offer-explainer": ("Employment Offer Explainer", "Work & Career"),
            "loan-mortgage-explainer": ("Loan / Mortgage Explainer", "Finance"),
            "warranty-explainer": ("Warranty Explainer", "Consumer"),
        }
        for persona_id, (name, category) in expected.items():
            with self.subTest(persona_id=persona_id):
                persona = personas[persona_id]
                self.assertEqual(persona["name"], name)
                self.assertEqual(persona["category"], category)
                self.assertIn("default to India", persona["system_prompt"])
                self.assertIn("india default", persona["tags"])
                self.assertTrue(any("unclear" in item and "default to India" in item for item in persona["constraints"]))

    def test_runtime_security_rejects_insecure_production_cookies(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_runtime_security(Settings(environment="production", secure_cookies=False))

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
