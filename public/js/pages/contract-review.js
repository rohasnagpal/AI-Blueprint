// ── STANDALONE CONTRACT REVIEW ───────────────────────────────────────────
function contractReviewWorkspaceId() {
  const selectValue = document.getElementById('contract-review-workspace-select')?.value || '';
  const workspaces = App.v2.workspaces || [];
  if (selectValue && workspaces.some(w => w.workspace_id === selectValue)) return selectValue;
  return App.v2.workspaceId || workspaces[0]?.workspace_id || null;
}

function selectedContractReviewMatterId() {
  const value = document.getElementById('contract-review-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(contractReviewWorkspaceId())[0]?.id || null;
}

async function renderStandaloneContractReview() {
  renderContractReviewScopeSelector();
  await loadStandaloneContractPlaybooks();
  renderContractReviewSourceDocuments();
}

function renderContractReviewScopeSelector() {
  const workspaceSelect = document.getElementById('contract-review-workspace-select');
  const matterSelect = document.getElementById('contract-review-matter-select');
  const card = document.getElementById('contract-review-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = contractReviewWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderContractReviewScopeSelector).catch(() => {});
}

async function onContractReviewWorkspaceChange() {
  const matterSelect = document.getElementById('contract-review-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderContractReviewScopeSelector();
  await loadStandaloneContractPlaybooks();
  renderContractReviewSourceDocuments();
}

async function loadStandaloneContractPlaybooks() {
  const workspaceId = contractReviewWorkspaceId();
  const select = document.getElementById('contract-review-playbook');
  if (!select) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    select.innerHTML = '<option value="">Sign in to load playbooks</option>';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/playbooks`);
    if (!r.ok) throw new Error(await apiError(r));
    App.contractReview.playbooks = await r.json();
    select.innerHTML = '<option value="">Auto-select / no playbook</option>' + App.contractReview.playbooks.map(p => `<option value="${esc(p.id)}">${esc(p.name)}${p.contract_category ? ' · ' + esc(p.contract_category.toUpperCase()) : ''}</option>`).join('');
  } catch(e) {
    select.innerHTML = '<option value="">Playbooks unavailable</option>';
  }
}

function renderContractReviewSourceDocuments() {
  const field = document.getElementById('contract-review-source-documents-field');
  const select = document.getElementById('contract-review-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = contractReviewWorkspaceId();
  const selectedMatter = selectedContractReviewMatterId();
  if (!App.v2.enabled || !App.v2.user || !selectedWorkspace || selectedWorkspace !== App.v2.workspaceId) {
    field.style.display = 'none';
    select.innerHTML = '';
    return;
  }
  const docs = (App.v2.documents || []).filter(doc => {
    if (doc.status && doc.status !== 'indexed') return false;
    return doc.matter_id === selectedMatter;
  });
  field.style.display = 'block';
  select.innerHTML = docs.length
    ? docs.map(doc => `<option value="${esc(doc.id)}">${esc(doc.original_name || 'Document')}</option>`).join('')
    : '<option value="">No indexed documents available</option>';
}

function selectedContractReviewDocumentIds() {
  const select = document.getElementById('contract-review-source-documents');
  if (!select) return [];
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
}

function collectStandaloneContractReviewPayload() {
  const workspaceId = contractReviewWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const payload = {
    title: document.getElementById('contract-review-title')?.value.trim() || 'Contract Review',
    matter_id: selectedContractReviewMatterId(),
    document_ids: selectedContractReviewDocumentIds(),
    playbook_id: document.getElementById('contract-review-playbook')?.value || null,
    review_depth: document.getElementById('contract-review-depth')?.value || 'standard',
    instructions: document.getElementById('contract-review-instructions')?.value.trim() || null,
  };
  return {workspaceId, payload};
}

async function runStandaloneContractReview() {
  if (App.contractReview.isRunning) return;
  const btn = document.getElementById('contract-review-run-btn');
  const status = document.getElementById('contract-review-status');
  try {
    const {workspaceId, payload} = collectStandaloneContractReviewPayload();
    App.contractReview.isRunning = true;
    App.contractReview.result = null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Reviewing...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    App.contractReview.result = await r.json();
    renderStandaloneContractReviewResult();
    showToast('Contract review complete.');
  } catch(e) {
    showToast('Contract review failed: ' + e.message, 'error');
  } finally {
    App.contractReview.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function contractReviewDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(contractReviewDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'text', 'finding', 'answer', 'name', 'description']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return contractReviewDisplayValue(value[key]);
    }
    return Object.entries(value)
      .filter(([, item]) => item !== null && item !== undefined && item !== '')
      .map(([key, item]) => `${key.replace(/_/g, ' ')}: ${contractReviewDisplayValue(item)}`)
      .join('; ');
  }
  return String(value);
}

function contractReviewSourceLabel(source) {
  if (!source || typeof source !== 'object') return contractReviewDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : null;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function standaloneClauseSourceLabel(source) {
  if (!source || typeof source !== 'object') return 'source';
  const rawChunk = source.chunk_index !== undefined && source.chunk_index !== null ? Number(source.chunk_index) + 1 : null;
  return `${source.filename || 'source'}${rawChunk ? ' · chunk ' + rawChunk : ''}`;
}

function standaloneRiskRank(level) {
  return {critical:4, high:3, medium:2, low:1}[level] || 0;
}

function renderStandaloneRiskHeatmap(clauses) {
  const levels = ['critical', 'high', 'medium', 'low'];
  const types = Array.from(new Set((clauses || []).map(item => item.clause?.clause_type).filter(Boolean))).sort();
  if (!types.length) return '';
  const count = (type, level) => clauses.filter(item => item.clause?.clause_type === type && (item.risks || []).some(r => r.risk_level === level)).length;
  return `<div class="contract-heatmap">
    <div class="council-card-title">Risk Heatmap</div>
    <div class="contract-heatmap-grid" style="grid-template-columns:minmax(140px,1fr) repeat(${levels.length}, minmax(70px, 0.45fr))">
      <div class="heatmap-head">Clause</div>${levels.map(level => `<div class="heatmap-head">${esc(level)}</div>`).join('')}
      ${types.map(type => `<div class="heatmap-label">${esc(type.replace(/_/g, ' '))}</div>${levels.map(level => {
        const value = count(type, level);
        return `<div class="heatmap-cell risk-${esc(level)} ${value ? 'has-risk' : ''}">${value || ''}</div>`;
      }).join('')}`).join('')}
    </div>
  </div>`;
}

function renderStandaloneWorkflowReview(workflow) {
  if (!workflow) return '';
  const clauses = [...(workflow.clauses || [])].sort((a, b) => {
    const ar = Math.max(0, ...(a.risks || []).map(r => standaloneRiskRank(r.risk_level)));
    const br = Math.max(0, ...(b.risks || []).map(r => standaloneRiskRank(r.risk_level)));
    return br - ar || String(a.clause?.clause_type || '').localeCompare(String(b.clause?.clause_type || ''));
  });
  const stats = workflow.stats || {};
  const summaries = workflow.summaries || [];
  const escalations = workflow.escalations || [];
  return `<section class="contract-review-workspace">
    <div class="contract-review-page-head">
      <div>
        <div class="settings-section-desc">Structured workflow review</div>
        <div class="contract-dashboard-title">${esc(workflow.intake?.contract_type || 'Contract')}</div>
        <div class="council-card-meta">${esc(workflow.intake?.contract_category || 'general')}${workflow.coverage_score !== null && workflow.coverage_score !== undefined ? ' · coverage ' + esc(String(workflow.coverage_score)) : ''}</div>
      </div>
    </div>
    <div class="contract-review-stats">
      <div class="stat-pill"><strong>${esc(String(stats.clauses ?? clauses.length))}</strong> clauses</div>
      <div class="stat-pill"><strong>${esc(String(stats.review_needed ?? 0))}</strong> need review</div>
      <div class="stat-pill"><strong>${esc(String(stats.high ?? 0))}</strong> high</div>
      <div class="stat-pill"><strong>${esc(String(stats.critical ?? 0))}</strong> critical</div>
      <div class="stat-pill"><strong>${esc(String(stats.escalations ?? escalations.length))}</strong> escalations</div>
      <div class="stat-pill"><strong>${esc(String((workflow.trace || []).length))}</strong> trace steps</div>
    </div>
    ${renderContractSummaries(summaries)}
    ${renderStandaloneRiskHeatmap(clauses)}
    ${escalations.length ? `<div class="contract-escalations">
      <div class="council-row-head"><div><div class="council-card-title">Escalations</div><div class="council-card-meta">Items requiring human review before external delivery</div></div></div>
      <div class="contract-escalation-list">${escalations.map(e => `<div class="contract-escalation-item"><span class="risk-badge risk-${esc(e.severity || 'high')}">${esc(e.severity || 'high')}</span><span><strong>${esc(e.reason || 'Escalation')}</strong><small>${esc(e.required_action || '')}</small></span></div>`).join('')}</div>
    </div>` : ''}
    <div class="contract-filter-panel">
      <div><div class="council-card-title">Clause Review</div><div class="council-card-meta">${clauses.length} extracted clause areas</div></div>
    </div>
    <div class="contract-review-grid">
      <div class="contract-review-list">
        ${clauses.length ? clauses.map(item => renderStandaloneClauseRow(item)).join('') : '<div class="council-row"><div class="council-card-desc">No clauses were extracted from the indexed text.</div></div>'}
      </div>
      <div class="contract-review-detail">
        ${clauses.length ? renderStandaloneClauseDetail(clauses[0]) : renderContractSummaries(summaries)}
      </div>
    </div>
  </section>`;
}

function renderStandaloneClauseRow(item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  const topRisk = [...risks].sort((a,b) => standaloneRiskRank(b.risk_level) - standaloneRiskRank(a.risk_level))[0];
  const risk = topRisk?.risk_level || 'low';
  return `<div class="contract-clause-row">
    <span>
      <strong>${esc(clause.title || clause.clause_type || 'Clause')}</strong>
      <small>${esc(standaloneClauseSourceLabel(clause.source))}</small>
    </span>
    <span class="risk-badge risk-${esc(risk)}">${esc(risk)}</span>
    <span class="council-status ${esc(clause.review_status || 'pending')}">${esc(clause.review_status || 'pending')}</span>
  </div>`;
}

function renderStandaloneClauseDetail(item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  const findings = item.playbook_findings || [];
  const redlines = item.redline_suggestions || [];
  return `<div class="contract-clause-detail-card">
    <div class="council-row-head">
      <div>
        <div class="council-card-title">${esc(clause.title || clause.clause_type || 'Clause')}</div>
        <div class="council-card-meta">${esc(standaloneClauseSourceLabel(clause.source))} · confidence ${esc(String(clause.confidence_score ?? 'n/a'))}</div>
      </div>
      <span class="council-status ${esc(clause.review_status || 'pending')}">${esc(clause.review_status || 'pending')}</span>
    </div>
    <div class="contract-clause-text">${esc(clause.text || '')}</div>
    ${risks.length ? `<div class="contract-risk-list">${risks.map(r => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(r.risk_level)}">${esc(r.risk_level)}</span><span>${esc(r.reasoning || '')}</span></div>`).join('')}</div>` : ''}
    ${(findings.length || redlines.length) ? `<div class="contract-detail-section"><div class="council-card-title">Playbook & Redline Notes</div>
      ${findings.map(f => `<div class="contract-finding-item"><strong>${esc(f.status || 'finding')}</strong><span>${esc(f.deviation_summary || '')}</span></div>`).join('')}
      ${redlines.map(r => `<div class="contract-finding-item"><strong>Suggested fallback</strong><span>${esc(r.fallback_language || r.suggestion_text || '')}</span></div>`).join('')}
    </div>` : ''}
  </div>`;
}

function contractReviewMarkdown(result = App.contractReview.result) {
  if (!result) return '';
  const workflow = result.workflow || {};
  const workflowSummary = workflow.stats ? `## Workflow Dashboard\n- Clauses: ${workflow.stats.clauses ?? 0}\n- Need review: ${workflow.stats.review_needed ?? 0}\n- High risk: ${workflow.stats.high ?? 0}\n- Critical risk: ${workflow.stats.critical ?? 0}\n- Escalations: ${workflow.stats.escalations ?? 0}\n\n` : '';
  const workflowClauses = (workflow.clauses || []).map(item => {
    const clause = item.clause || {};
    const risks = (item.risks || []).map(r => `${r.risk_level}: ${r.reasoning}`).join('; ');
    const redlines = (item.redline_suggestions || []).map(r => r.fallback_language || r.suggestion_text).filter(Boolean).join('; ');
    return `- **${clause.title || clause.clause_type || 'Clause'}** (${standaloneClauseSourceLabel(clause.source)}): ${risks || 'No workflow risk.'}${redlines ? ` Fallback: ${redlines}` : ''}`;
  }).join('\n');
  const risks = (result.risk_matrix || []).map(r => `- **${contractReviewDisplayValue(r.issue || 'Issue')}** (${contractReviewDisplayValue(r.severity || r.risk_level || 'n/a')}): ${contractReviewDisplayValue(r.finding || r.reasoning || '')}`).join('\n');
  const extraction = Object.entries(result.extraction || {}).map(([key, value]) => `- **${key.replace(/_/g, ' ')}**: ${contractReviewDisplayValue(value)}`).join('\n');
  const sources = (result.sources || []).map(s => `- ${contractReviewSourceLabel(s)}: ${contractReviewDisplayValue(s?.excerpt || '')}`).join('\n');
  return `# ${result.title || 'Contract Review'}\n\n${workflowSummary}${workflowClauses ? `## Workflow Clauses\n${workflowClauses}\n\n` : ''}## Client Summary\n${contractReviewDisplayValue(result.client_summary)}\n\n## Structured Extraction\n${extraction || 'No extraction returned.'}\n\n## Risk Matrix\n${risks || 'No risks returned.'}\n\n## Negotiation Memo\n${contractReviewDisplayValue(result.negotiation_memo)}\n\n## Sources\n${sources || 'No sources returned.'}\n\n## Review Notice\nHuman legal review is required before use or circulation.\n`;
}

function renderStandaloneContractReviewResult() {
  const result = App.contractReview.result;
  const grid = document.getElementById('contract-review-result-grid');
  const preview = document.getElementById('contract-review-preview');
  const meta = document.getElementById('contract-review-result-meta');
  const side = document.getElementById('contract-review-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  if (meta) meta.textContent = `${result.review_depth || 'standard'}${result.playbook?.name ? ' · ' + result.playbook.name : ''}${result.provider ? ' · ' + result.provider : ' · fallback'}`;
  const riskRows = (result.risk_matrix || []).map(r => `<tr><td>${esc(contractReviewDisplayValue(r.issue || 'Issue'))}</td><td>${esc(contractReviewDisplayValue(r.severity || r.risk_level || 'n/a'))}</td><td>${esc(contractReviewDisplayValue(r.finding || r.reasoning || ''))}</td></tr>`).join('');
  const extractionRows = Object.entries(result.extraction || {}).map(([key, value]) => `<tr><td>${esc(key.replace(/_/g, ' '))}</td><td>${esc(contractReviewDisplayValue(value))}</td></tr>`).join('');
  preview.innerHTML = sanitizeDraftHtml(`
    ${renderStandaloneWorkflowReview(result.workflow)}
    <article class="draft-document">
      <h1>${esc(result.title || 'Contract Review')}</h1>
      <section><h2>Client Summary</h2><p>${esc(contractReviewDisplayValue(result.client_summary))}</p></section>
      <section><h2>Structured Extraction</h2><table><tbody>${extractionRows || '<tr><td>No extraction returned.</td></tr>'}</tbody></table></section>
      <section><h2>Risk Matrix</h2><table><thead><tr><th>Issue</th><th>Severity</th><th>Finding</th></tr></thead><tbody>${riskRows || '<tr><td colspan="3">No risks returned.</td></tr>'}</tbody></table></section>
      <section><h2>Negotiation Memo</h2><p>${esc(contractReviewDisplayValue(result.negotiation_memo)).replace(/\\n/g, '<br>')}</p></section>
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.review_warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(contractReviewSourceLabel), 'No source documents returned.')}</div>
  `;
}

async function copyStandaloneContractReview() {
  const text = contractReviewMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Contract review copied.');
}

function downloadStandaloneContractReview() {
  const text = contractReviewMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `contract-review-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function resetStandaloneContractReview() {
  App.contractReview.result = null;
  const ids = ['contract-review-title', 'contract-review-instructions'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('contract-review-result-grid').style.display = 'none';
}
