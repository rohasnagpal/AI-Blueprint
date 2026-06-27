import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path("/tmp/ai_blueprint_mediation_tests")
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
from app.core.mediation_agents.orchestrator import run_agentic_mediation_prep
from app.core.mediation_agents.tools import SUPPORTED_TOOLS, run_mediation_agent_tools
from app.core.database import SessionLocal
from app.core.models import (
    MediationAgentStepOutput,
    MediationChronologyEvent,
    MediationClaim,
    MediationDepositionTopic,
    MediationDiscoveryItem,
    MediationEvidenceItem,
    MediationIssue,
    MediationMotion,
    MediationPrepOutput,
    MediationPrepRun,
    MediationProceduralTask,
    MediationWitness,
    KnowledgeChunk,
    KnowledgeDocument,
    User,
    Workspace,
    WorkspaceMember,
    utcnow,
)
from app.core.security import hash_password


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


class MediationPrepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _configure_runtime()
        _clean_runtime()
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        setup = cls.client.post("/api/v2/auth/setup", json={"email": "admin@example.com", "display_name": "Admin", "password": "0123456789ab"})
        assert setup.status_code == 200, setup.text
        cls.user_id = setup.json()["user"]["id"]
        workspace = cls.client.post("/api/v2/workspaces", json={"name": "Mediation Workspace", "slug": "lit"})
        assert workspace.status_code == 201, workspace.text
        cls.workspace_id = workspace.json()["id"]
        matter = cls.client.post(f"/api/v2/workspaces/{cls.workspace_id}/matters", json={"name": "Mediation Matter"})
        assert matter.status_code == 201, matter.text
        cls.matter_id = matter.json()["id"]
        other_matter = cls.client.post(f"/api/v2/workspaces/{cls.workspace_id}/matters", json={"name": "Other Matter"})
        assert other_matter.status_code == 201, other_matter.text
        cls.other_matter_id = other_matter.json()["id"]
        cls.indexed_doc_id = cls._insert_document(cls.matter_id, "pleading.txt", "indexed", "On 12 Jan 2026 Alpha Corp filed a claim for USD 100,000 damages. Jane Smith sent notice of breach. Defendant asserted an affirmative defense. Interrogatory responses and request for production objections remain incomplete. Procedural Order No. 1 sets a filing deadline of 2026-07-15. Confidential settlement communication may be privileged.")
        cls.other_doc_id = cls._insert_document(cls.other_matter_id, "other.txt", "indexed", "Other matter content.")
        cls.unindexed_doc_id = cls._insert_document(cls.matter_id, "draft.txt", "registered", "Unindexed content.")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    @classmethod
    def _insert_document(cls, matter_id: str, filename: str, status: str, content: str) -> str:
        document_id = str(uuid.uuid4())
        chunk_id = str(uuid.uuid4())
        with SessionLocal() as db:
            db.add(
                KnowledgeDocument(
                    id=document_id,
                    workspace_id=cls.workspace_id,
                    matter_id=matter_id,
                    original_name=filename,
                    storage_key=None,
                    content_hash=str(uuid.uuid4()),
                    mime_type="text/plain",
                    size_bytes=len(content),
                    scope="matter",
                    status=status,
                    created_by_user_id=cls.user_id,
                )
            )
            db.flush()
            if status == "indexed":
                db.add(
                    KnowledgeChunk(
                        id=chunk_id,
                        workspace_id=cls.workspace_id,
                        document_id=document_id,
                        chunk_index=0,
                        content=content,
                        metadata_json=json.dumps({"page": 1, "start_offset": 0, "end_offset": len(content), "filename": filename, "source_anchor_version": "1"}),
                    )
                )
            db.commit()
        return document_id

    def wait_for_job(self, workspace_id: str, job_id: str) -> dict:
        last = None
        for _ in range(40):
            last = self.client.get(f"/api/v2/workspaces/{workspace_id}/jobs/{job_id}")
            self.assertEqual(last.status_code, 200, last.text)
            body = last.json()
            if body["job"]["status"] in {"completed", "failed", "cancelled"}:
                return body
            time.sleep(0.1)
        self.fail(last.text if last is not None else "job did not finish")

    def test_mediation_prep_run_persists_outputs_and_endpoints(self) -> None:
        response = self.client.post(
            f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs",
            json={
                "title": "Mediation Prep",
                "matter_id": self.matter_id,
                "document_ids": [self.indexed_doc_id],
                "party_role": "requesting party",
                "court": "Mediation Center",
                "jurisdiction": "Confidential",
                "venue": "Confidential County",
                "procedural_stage": "discovery",
                "hearing_dates": ["2026-07-15"],
                "mediation_focus": "full prep",
                "instructions": "Focus on chronology, witnesses, damages, and procedural deadlines.",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        queued = response.json()
        self.assertEqual(queued["status"], "queued")
        self.assertTrue(queued["run_id"])
        job = self.wait_for_job(self.workspace_id, queued["job"]["id"])
        self.assertEqual(job["job"]["status"], "completed", job)

        result = self.client.get(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs/{queued['run_id']}")
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(body["title"], "Mediation Prep")
        self.assertIn("case_snapshot", body)
        self.assertTrue(body["claims_and_defenses"])
        self.assertTrue(body["issues"])
        self.assertTrue(body["evidence_matrix"])
        self.assertTrue(body["discovery_analysis"])
        self.assertIn("agentic_review", body)
        self.assertTrue(body["agentic_review"]["autonomous_loop"]["enabled"])
        self.assertTrue(body["agentic_review"]["autonomous_loop"]["steps"])
        self.assertIn("working_memory", body["agentic_review"])
        self.assertTrue(body["agentic_review"]["human_review_gates"])
        self.assertTrue(body["warnings"])

        endpoints = ["claims", "issues", "chronology", "evidence", "witnesses", "depositions", "discovery", "motions", "procedural-tasks", "audit-package"]
        for endpoint in endpoints:
            item = self.client.get(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs/{queued['run_id']}/{endpoint}")
            self.assertEqual(item.status_code, 200, f"{endpoint}: {item.text}")

        with SessionLocal() as db:
            self.assertIsNotNone(db.get(MediationPrepRun, queued["run_id"]))
            self.assertEqual(db.query(MediationPrepOutput).filter(MediationPrepOutput.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationClaim).filter(MediationClaim.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationIssue).filter(MediationIssue.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationEvidenceItem).filter(MediationEvidenceItem.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationAgentStepOutput).filter(MediationAgentStepOutput.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationChronologyEvent).filter(MediationChronologyEvent.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationWitness).filter(MediationWitness.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationDepositionTopic).filter(MediationDepositionTopic.run_id == queued["run_id"]).count(), 0)
            self.assertGreaterEqual(db.query(MediationDiscoveryItem).filter(MediationDiscoveryItem.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationMotion).filter(MediationMotion.run_id == queued["run_id"]).count(), 1)
            self.assertGreaterEqual(db.query(MediationProceduralTask).filter(MediationProceduralTask.run_id == queued["run_id"]).count(), 1)

    def test_validation_rejects_bad_sources_and_access(self) -> None:
        no_docs = self.client.post(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs", json={"matter_id": self.matter_id, "document_ids": []})
        self.assertEqual(no_docs.status_code, 400, no_docs.text)
        outside_matter = self.client.post(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs", json={"matter_id": self.matter_id, "document_ids": [self.other_doc_id]})
        self.assertEqual(outside_matter.status_code, 400, outside_matter.text)
        unindexed = self.client.post(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs", json={"matter_id": self.matter_id, "document_ids": [self.unindexed_doc_id]})
        self.assertEqual(unindexed.status_code, 409, unindexed.text)

        other_user_id = str(uuid.uuid4())
        other_workspace_id = str(uuid.uuid4())
        with SessionLocal() as db:
            db.add(User(id=other_user_id, username=None, email="outsider@example.com", display_name="Outsider", password_hash=hash_password("abcdefgh1234"), is_active=True))
            db.add(Workspace(id=other_workspace_id, name="Other Workspace", slug="other-lit", created_by_user_id=other_user_id))
            db.add(WorkspaceMember(id=str(uuid.uuid4()), workspace_id=other_workspace_id, user_id=other_user_id, role="admin"))
            db.commit()
        with TestClient(app) as outsider:
            login = outsider.post("/api/v2/auth/login", json={"identifier": "outsider@example.com", "password": "abcdefgh1234"})
            self.assertEqual(login.status_code, 200, login.text)
            denied = outsider.get(f"/api/v2/workspaces/{self.workspace_id}/mediation-prep/runs")
            self.assertEqual(denied.status_code, 403, denied.text)

    def test_each_tool_returns_expected_structure_and_verifies_anchors(self) -> None:
        source_bundle = [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "filename": "bundle.txt",
                "chunk_index": 0,
                "content": "On 12 Jan 2026 Jane Smith sent notice. Plaintiff seeks USD 100,000 damages. Defendant raised a defense. Interrogatory responses are deficient. Confidential settlement email. Filing deadline 2026-07-15.",
                "page": 1,
                "start_offset": 0,
                "end_offset": 140,
            }
        ]
        requests = [{"tool": tool, "query": "Jane damages deadline"} for tool in sorted(SUPPORTED_TOOLS)]
        result = run_mediation_agent_tools(requests=requests, source_bundle=source_bundle, run_context={"party_role": "requesting party", "hearing_dates": ["2026-07-15"]}, existing_outputs={"draft": {"source": {"excerpt": "On 12 Jan 2026 Jane Smith sent notice."}}})
        self.assertEqual(len(result["tool_results"]), len(SUPPORTED_TOOLS))
        outputs = {item["tool"]: item["output"] for item in result["tool_results"]}
        self.assertTrue(outputs["targeted_document_retrieval"])
        self.assertTrue(outputs["claim_defense_mapper"])
        self.assertTrue(outputs["chronology_builder"])
        self.assertTrue(outputs["witness_mapper"])
        self.assertTrue(outputs["discovery_gap_analyzer"])
        self.assertTrue(outputs["procedural_deadline_tool"])
        self.assertTrue(outputs["damages_extractor"]["claimed_relief"])
        self.assertTrue(outputs["privilege_sensitivity_scanner"])
        self.assertIn("motions", outputs["motion_argument_outline_tool"])
        self.assertIn("themes", outputs["trial_theme_builder"])
        self.assertIn("required_sections", outputs["mediation_audit_package_tool"])
        verifier = run_mediation_agent_tools(
            requests=[{"tool": "evidence_anchor_verifier"}],
            source_bundle=source_bundle,
            run_context={},
            existing_outputs={"supported": {"excerpt": "On 12 Jan 2026 Jane Smith sent notice."}, "unsupported": {"excerpt": "This quote does not exist."}},
        )
        verified = verifier["tool_results"][0]["output"]
        self.assertTrue(any(item["supported"] for item in verified))
        self.assertTrue(any(not item["supported"] for item in verified))

    def test_qc_flags_trigger_revision_and_clean_outputs_are_not_rerun(self) -> None:
        source_bundle = [{"document_id": "doc-1", "chunk_id": "chunk-1", "filename": "a.txt", "chunk_index": 0, "content": "Claim filed on 12 Jan 2026.", "page": 1}]
        settings = {"chat_model": "mock-model"}
        responses = [
            {"strategy": "plan", "required_agents": [], "tool_requests": [{"tool": "targeted_document_retrieval", "query": "claim"}], "evidence_gaps": [], "stop_conditions": []},
            {"case_snapshot": {"court": "Mediation Center"}},
            {"client_or_team_summary": "Neutral summary for mediator review."},
            {"claims_and_defenses": []},
            {"positions_and_interests": []},
            {"issues": []},
            {"chronology": []},
            {"evidence_matrix": []},
            {"discovery_analysis": []},
            {"witness_prep": []},
            {"deposition_prep": []},
            {"motion_strategy": {"motions": []}},
            {"trial_prep": {"themes": []}},
            {"argument_strategy": {"themes": []}},
            {"procedural_tasks": []},
            {"damages_and_remedies": {}},
            {"batna_watna_zopa": {}},
            {"risk_allocation": []},
            {"settlement_levers": []},
            {"cross_examination": []},
            {"caucus_questions": [], "impasse_points": []},
            {"bridge_proposals": []},
            {"mediator_private_prep_note": {}, "one_page_session_plan": {}},
            {"risks_and_gaps": []},
            {"approved": False, "flagged_items": [{"output_key": "issues", "issue": "empty"}], "unsupported_claims": [], "privilege_flags": [], "warnings": [], "corrections": {}},
            {"revisions_made": {"issues": "filled"}, "revised_outputs": {"issues": [{"title": "Revised issue", "missing_proof": ["review"]}]}},
        ]
        with patch("app.core.mediation_agents.orchestrator.configured_llm_provider", return_value="mock"), patch("app.core.mediation_agents.orchestrator.complete_with_configured_llm", side_effect=[json.dumps(item) for item in responses]) as mocked:
            result = run_agentic_mediation_prep(sources=[], source_bundle=source_bundle, run_context={"court": "Mediation Center", "jurisdiction": "Confidential"}, settings=settings)
        self.assertEqual(result["issues"][0]["title"], "Revised issue")
        self.assertTrue(result["agentic_review"]["autonomous_loop"]["enabled"])
        self.assertTrue(result["agentic_review"]["working_memory"]["completed_steps"])
        self.assertIn("revision_controller_agent", [step["step_name"] for step in result["agent_trace"]])
        self.assertEqual(mocked.call_count, len(responses))

        clean_responses = responses[:-2] + [{"approved": True, "flagged_items": [], "unsupported_claims": [], "privilege_flags": [], "warnings": [], "corrections": {}}]
        with patch("app.core.mediation_agents.orchestrator.configured_llm_provider", return_value="mock"), patch("app.core.mediation_agents.orchestrator.complete_with_configured_llm", side_effect=[json.dumps(item) for item in clean_responses]) as clean_mock:
            clean = run_agentic_mediation_prep(sources=[], source_bundle=source_bundle, run_context={"court": "Mediation Center", "jurisdiction": "Confidential"}, settings=settings)
        self.assertNotIn("revision_controller_agent", [step["step_name"] for step in clean["agent_trace"]])
        self.assertEqual(clean_mock.call_count, len(clean_responses))

    def test_strict_planner_actions_drive_autonomous_loop(self) -> None:
        source_bundle = [{"document_id": "doc-1", "chunk_id": "chunk-1", "filename": "a.txt", "chunk_index": 0, "content": "Complaint filed on 12 Jan 2026. Jane Smith sent notice.", "page": 1}]
        settings = {"chat_model": "mock-model"}
        responses = [
            {"next_actions": [
                {"type": "run_tool", "name": "targeted_document_retrieval", "reason": "Find complaint evidence", "input": {"tool": "targeted_document_retrieval", "query": "complaint notice"}},
                {"type": "run_agent", "name": "chronology_agent", "reason": "Build mediation chronology", "input": {}},
                {"type": "finalize", "name": "finalize", "reason": "Bounded mediation test complete", "input": {}},
            ], "evidence_gaps": ["Confirm court order deadlines"]},
            {"chronology": [{"date": "12 Jan 2026", "description": "Complaint filed.", "source": {"excerpt": "Complaint filed on 12 Jan 2026."}}]},
            {"approved": True, "flagged_items": [], "unsupported_claims": [], "privilege_flags": [], "warnings": [], "corrections": {}},
        ]
        with patch("app.core.mediation_agents.orchestrator.configured_llm_provider", return_value="mock"), patch("app.core.mediation_agents.orchestrator.complete_with_configured_llm", side_effect=[json.dumps(item) for item in responses]) as mocked:
            result = run_agentic_mediation_prep(sources=[], source_bundle=source_bundle, run_context={"court": "Mediation Center", "jurisdiction": "Confidential"}, settings=settings)
        loop = result["agentic_review"]["autonomous_loop"]
        self.assertEqual(loop["stop_reason"], "Bounded mediation test complete")
        self.assertEqual([step["action"]["type"] for step in loop["steps"][:3]], ["run_tool", "run_agent", "finalize"])
        self.assertTrue(result["chronology"])
        self.assertEqual(mocked.call_count, len(responses))

    def test_frontend_javascript_syntax(self) -> None:
        import subprocess

        completed = subprocess.run(["node", "--check", "public/js/pages/mediation-prep.js"], cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
