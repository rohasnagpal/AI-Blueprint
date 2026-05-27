from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ContractWorkflowModule:
    id: str
    name: str
    stage: str
    order: int
    execution: str
    module_type: str
    input_schema: str
    output_schema: str
    configurable: bool = False
    enabled: bool = True


BUILTIN_CONTRACT_WORKFLOW_MODULES: tuple[ContractWorkflowModule, ...] = (
    ContractWorkflowModule("intake", "Intake", "classification", 10, "sequential", "hybrid", "raw_contract_text", "IntakeResult"),
    ContractWorkflowModule("clause_extraction", "Clause Extraction", "extraction", 20, "sequential", "hybrid", "raw_contract_text_with_source_anchors", "ExtractedClause[]"),
    ContractWorkflowModule("playbook_comparison", "Playbook Comparison", "comparison", 30, "parallel", "rules_first", "ContractClause[] + ContractPlaybook", "PlaybookFindingResult[]"),
    ContractWorkflowModule("risk_scoring", "Risk Scoring", "risk", 40, "parallel", "rules_first", "ContractClause[] + PlaybookFindingResult[]", "RiskFindingResult[]"),
    ContractWorkflowModule("conflict_detection", "Conflict Detection", "escalation", 50, "sequential", "deterministic", "ContractClause[]", "EscalationResult[]"),
    ContractWorkflowModule("redlining", "Redlining Suggestions", "suggestions", 60, "sequential", "hybrid", "Flagged ContractClause[] + ContractPlaybook", "RedlineSuggestionResult[]"),
    ContractWorkflowModule("summarization", "Summarization", "summary", 70, "sequential", "hybrid", "Full workflow context", "SummaryResult[]"),
    ContractWorkflowModule("escalation_detection", "Escalation Detection", "escalation", 80, "sequential", "rules_first", "RiskFindingResult[] + ConflictResult[]", "EscalationResult[]"),
)


def list_contract_workflow_modules() -> list[dict]:
    return [asdict(module) for module in sorted(BUILTIN_CONTRACT_WORKFLOW_MODULES, key=lambda item: item.order)]
