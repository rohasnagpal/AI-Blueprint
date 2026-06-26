// ── LITIGATION PREP ─────────────────────────────────────────────────────
function litigationPrepWorkspaceId() {
  const selectValue = document.getElementById('litigation-prep-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedLitigationPrepMatterId() {
  const value = document.getElementById('litigation-prep-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(litigationPrepWorkspaceId())[0]?.id || null;
}

async function renderLitigationPrep() {
  if (!App.v2.user && typeof initV2 === 'function') {
    await initV2().catch(() => {});
  }
  renderLitigationPrepScopeSelector();
  await syncLitigationPrepScope();
  renderLitigationPrepScopeSelector();
  renderLitigationPrepSourceDocuments();
  await loadLitigationPrepHistory();
}

async function syncLitigationPrepScope(options = {}) {
  const matterSelect = document.getElementById('litigation-prep-matter-select');
  await syncV2WorkspaceMatterDocuments(litigationPrepWorkspaceId(), matterSelect?.value || '', matterSelect, options);
}

function renderLitigationPrepScopeSelector() {
  const workspaceSelect = document.getElementById('litigation-prep-workspace-select');
  const matterSelect = document.getElementById('litigation-prep-matter-select');
  const card = document.getElementById('litigation-prep-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = litigationPrepWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderLitigationPrepScopeSelector).catch(() => {});
}

async function onLitigationPrepWorkspaceChange() {
  const matterSelect = document.getElementById('litigation-prep-matter-select');
  if (matterSelect) matterSelect.value = '';
  await syncLitigationPrepScope({resetMatter: true});
  renderLitigationPrepScopeSelector();
  renderLitigationPrepSourceDocuments();
  await loadLitigationPrepHistory();
}

async function onLitigationPrepMatterChange() {
  await syncLitigationPrepScope();
  renderLitigationPrepSourceDocuments();
}

function renderLitigationPrepSourceDocuments() {
  const field = document.getElementById('litigation-prep-source-documents-field');
  const select = document.getElementById('litigation-prep-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = litigationPrepWorkspaceId();
  const selectedMatter = selectedLitigationPrepMatterId();
  if (!App.v2.enabled || !App.v2.user || !selectedWorkspace || selectedWorkspace !== App.v2.workspaceId) {
    field.style.display = 'none';
    select.innerHTML = '';
    return;
  }
  const docs = (App.v2.documents || []).filter(doc => (!doc.status || doc.status === 'indexed') && doc.matter_id === selectedMatter);
  field.style.display = 'block';
  select.innerHTML = docs.length
    ? docs.map(doc => `<option value="${esc(doc.id)}">${esc(doc.original_name || 'Document')}</option>`).join('')
    : '<option value="">No indexed documents available</option>';
}

function selectedLitigationPrepDocumentIds() {
  const select = document.getElementById('litigation-prep-source-documents');
  if (!select) return [];
  const selected = [...select.selectedOptions].map(option => option.value).filter(Boolean);
  if (selected.length) return selected;
  return [...select.options].map(option => option.value).filter(Boolean);
}

function collectLitigationPrepPayload() {
  const workspaceId = litigationPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const dates = (document.getElementById('litigation-prep-dates')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
  return {
    workspaceId,
    payload: {
      title: document.getElementById('litigation-prep-title')?.value.trim() || 'Litigation Prep',
      matter_id: selectedLitigationPrepMatterId(),
      document_ids: selectedLitigationPrepDocumentIds(),
      party_role: document.getElementById('litigation-prep-party-role')?.value || 'neutral analysis',
      court: document.getElementById('litigation-prep-court')?.value.trim() || null,
      jurisdiction: document.getElementById('litigation-prep-jurisdiction')?.value.trim() || null,
      venue: document.getElementById('litigation-prep-venue')?.value.trim() || null,
      procedural_stage: document.getElementById('litigation-prep-stage')?.value.trim() || null,
      hearing_dates: dates,
      litigation_focus: document.getElementById('litigation-prep-focus')?.value || 'full prep',
      instructions: document.getElementById('litigation-prep-instructions')?.value.trim() || null,
    },
  };
}

async function loadLitigationPrepHistory() {
  const workspaceId = litigationPrepWorkspaceId();
  const card = document.getElementById('litigation-prep-history-card');
  const list = document.getElementById('litigation-prep-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs?page_size=8&workflow_mode=litigation_prep`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.litigationPrep.history = data.items || [];
    card.style.display = App.litigationPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.litigationPrep.history.map(run => `<div class="council-row litigation-prep-history-row">
      <div class="council-row-head litigation-prep-history-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Litigation prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.court ? ' · ' + esc(run.court) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions litigation-prep-history-actions">
        <button class="btn-secondary" type="button" onclick="openLitigationPrepRun('${esc(run.id)}')">Open</button>
        <button class="btn-secondary danger" type="button" onclick="deleteLitigationPrepRun('${esc(run.id)}')">Delete</button>
      </div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openLitigationPrepRun(runId) {
  const workspaceId = litigationPrepWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.litigationPrep.result = await r.json();
    renderLitigationPrepResult();
    showToast('Litigation prep loaded.');
  } catch(e) {
    showToast('Failed to load litigation prep: ' + e.message, 'error');
  }
}

async function deleteLitigationPrepRun(runId) {
  const workspaceId = litigationPrepWorkspaceId();
  if (!workspaceId || !runId) return;
  const run = (App.litigationPrep.history || []).find(item => item.id === runId);
  const title = run?.title || 'Litigation prep';
  if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.litigationPrep.result?.id === runId) {
      App.litigationPrep.result = null;
      const grid = document.getElementById('litigation-prep-result-grid');
      if (grid) grid.style.display = 'none';
    }
    await loadLitigationPrepHistory();
    showToast('Litigation prep deleted.');
  } catch(e) {
    showToast('Failed to delete litigation prep: ' + e.message, 'error');
  }
}

async function runLitigationPrep() {
  if (App.litigationPrep.isRunning) return;
  const btn = document.getElementById('litigation-prep-run-btn');
  const status = document.getElementById('litigation-prep-status');
  try {
    const {workspaceId, payload} = collectLitigationPrepPayload();
    App.litigationPrep.isRunning = true;
    App.litigationPrep.result = null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Queuing prep...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startLitigationPrepJobStream(workspaceId, data.job);
      showToast('Litigation prep queued.');
      return;
    }
    App.litigationPrep.result = data;
    renderLitigationPrepResult();
    showToast('Litigation prep complete.');
  } catch(e) {
    showToast('Litigation prep failed: ' + e.message, 'error');
    App.litigationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  } finally {
    if (App.litigationPrep.job) return;
    App.litigationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function stopLitigationPrepStream() {
  App.litigationPrep.stream?.close();
  App.litigationPrep.stream = null;
}

function renderLitigationPrepProgress() {
  const status = document.getElementById('litigation-prep-status');
  const job = App.litigationPrep.job;
  if (!status || !job) return;
  const latest = [...(App.litigationPrep.events || [])].reverse().find(e => e.content)?.content || job.status || 'running';
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  status.textContent = `${latest} · ${progress}%`;
}

async function loadLitigationPrepResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.litigationPrep.result = await r.json();
  renderLitigationPrepResult();
  return true;
}

function startLitigationPrepJobStream(workspaceId, job) {
  stopLitigationPrepStream();
  App.litigationPrep.job = job;
  App.litigationPrep.events = [{type:'status', content:'Litigation prep queued', metadata:{progress:0}}];
  renderLitigationPrepProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.litigationPrep.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.litigationPrep.job = data.metadata;
    if (data.type && data.type !== 'status') App.litigationPrep.events.push(data);
    App.litigationPrep.events = App.litigationPrep.events.slice(-24);
    renderLitigationPrepProgress();
    if (data.type === 'done') {
      stopLitigationPrepStream();
      App.litigationPrep.job = data.metadata || App.litigationPrep.job;
      try {
        if (data.content === 'completed') {
          await loadLitigationPrepResultFromJob(workspaceId, App.litigationPrep.job);
          await loadLitigationPrepHistory();
          showToast('Litigation prep complete.');
        } else {
          showToast('Litigation prep ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Prep completed but result load failed: ' + e.message, 'error');
      } finally {
        App.litigationPrep.isRunning = false;
        App.litigationPrep.job = null;
        const btn = document.getElementById('litigation-prep-run-btn');
        const status = document.getElementById('litigation-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      }
    }
  };
  source.onerror = () => {
    stopLitigationPrepStream();
    App.litigationPrep.isRunning = false;
    App.litigationPrep.job = null;
    const btn = document.getElementById('litigation-prep-run-btn');
    const status = document.getElementById('litigation-prep-status');
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
    showToast('Litigation prep event stream disconnected.', 'error');
  };
}

function litigationDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(litigationDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'description', 'title', 'theme', 'name', 'issue', 'excerpt']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return litigationDisplayValue(value[key]);
    }
    return Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '').map(([key, item]) => `${key.replace(/_/g, ' ')}: ${litigationDisplayValue(item)}`).join('; ');
  }
  return String(value);
}

function litigationSourceLabel(source) {
  if (!source || typeof source !== 'object') return litigationDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : Number(source.chunk_index || 0) + 1;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function renderLitigationSection(title, items, renderer, emptyText) {
  return `<section><h2>${esc(title)}</h2>${items && items.length ? items.map(renderer).join('') : `<p>${esc(emptyText || 'No supported items returned.')}</p>`}</section>`;
}

function litigationReportRows(value) {
  if (!value || typeof value !== 'object') return `<p>${esc(litigationDisplayValue(value))}</p>`;
  return `<table><tbody>${Object.entries(value).map(([key, item]) => `<tr><th>${esc(key.replace(/_/g, ' '))}</th><td>${esc(litigationDisplayValue(item))}</td></tr>`).join('')}</tbody></table>`;
}

function litigationReportList(items, renderer, emptyText = 'No supported items returned.') {
  return items && items.length ? items.map(renderer).join('') : `<p class="muted">${esc(emptyText)}</p>`;
}

function litigationReportSection(title, body, opts = {}) {
  return `<section class="${opts.pageBreak ? 'page-break' : ''}"><h2>${esc(title)}</h2>${body}</section>`;
}

function litigationReportStyles() {
  return `<style>
    :root { color: #172026; background: #f3f1ea; font-family: Arial, Helvetica, sans-serif; }
    body { margin: 0; background: #f3f1ea; color: #172026; }
    .litigation-report { max-width: 920px; margin: 0 auto; background: #fff; padding: 48px 56px; box-sizing: border-box; }
    .report-kicker { color: #687076; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    h1 { font-size: 32px; line-height: 1.15; margin: 10px 0 12px; letter-spacing: 0; }
    h2 { font-size: 18px; margin: 28px 0 12px; padding-bottom: 7px; border-bottom: 1px solid #d9dee2; letter-spacing: 0; }
    h3 { font-size: 14px; margin: 14px 0 6px; letter-spacing: 0; }
    p, li, td, th { font-size: 12.5px; line-height: 1.48; }
    .report-meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 20px; margin: 20px 0; font-size: 12px; }
    .report-notice { border: 1px solid #b8c2c9; border-left: 4px solid #31566f; padding: 12px 14px; margin: 18px 0 24px; background: #f7fafb; font-size: 12.5px; }
    .toc { columns: 2; padding-left: 20px; }
    .item { break-inside: avoid; border: 1px solid #e0e4e7; padding: 10px 12px; margin: 8px 0; border-radius: 6px; }
    .item strong { display: block; margin-bottom: 4px; }
    .muted { color: #687076; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; }
    th, td { text-align: left; vertical-align: top; border: 1px solid #dfe4e7; padding: 7px 8px; }
    th { width: 28%; background: #f4f6f7; font-weight: 700; }
    footer { margin-top: 32px; padding-top: 12px; border-top: 1px solid #d9dee2; font-size: 11px; color: #687076; }
    @media print {
      @page { size: letter; margin: 0.55in; }
      body { background: #fff; }
      .litigation-report { max-width: none; margin: 0; padding: 0; }
      .page-break { break-before: page; }
      h2, .item, tr { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>`;
}

function litigationPrepReportHtml(result = App.litigationPrep.result, standalone = false) {
  if (!result) return '';
  const config = result.config || {};
  const generated = result.completed_at ? new Date(result.completed_at).toLocaleString() : new Date().toLocaleString();
  const sources = result.sources || [];
  const warnings = result.warnings || [];
  const body = `
    <article class="litigation-report">
      <div class="report-kicker">Litigation preparation</div>
      <h1>${esc(result.title || 'Litigation Prep')}</h1>
      <div class="report-notice">This report is a litigation preparation aid for lawyer review. It does not decide the dispute, provide legal advice, predict outcomes, or replace counsel judgment.</div>
      <div class="report-meta">
        <div><strong>Perspective:</strong> ${esc(config.party_role || 'neutral analysis')}</div>
        <div><strong>Generated:</strong> ${esc(generated)}</div>
        <div><strong>Court:</strong> ${esc(config.court || 'Not provided')}</div>
        <div><strong>Jurisdiction:</strong> ${esc(config.jurisdiction || 'Not provided')}</div>
        <div><strong>Venue:</strong> ${esc(config.venue || 'Not provided')}</div>
        <div><strong>Stage:</strong> ${esc(config.procedural_stage || 'Not provided')}</div>
        <div><strong>Dates:</strong> ${esc(litigationDisplayValue(config.hearing_dates || []))}</div>
        <div><strong>Focus:</strong> ${esc(config.litigation_focus || 'full prep')}</div>
      </div>
      ${litigationReportSection('Table of Contents', `<ol class="toc"><li>Case Snapshot</li><li>Claims and Defenses</li><li>Issues and Proof Elements</li><li>Factual Chronology</li><li>Evidence Matrix</li><li>Discovery Analysis</li><li>Witness and Deposition Prep</li><li>Cross-Examination Topics</li><li>Procedural Tasks</li><li>Motion, Trial, and Argument Themes</li><li>Damages and Remedies</li><li>Risks and Gaps</li><li>One-Page Litigation Plan</li><li>Source Basis</li></ol>`)}
      ${litigationReportSection('Case Snapshot', `<p>${esc(litigationDisplayValue(result.client_or_team_summary))}</p>${litigationReportRows(result.case_snapshot || {})}`)}
      ${litigationReportSection('Claims and Defenses', litigationReportList(result.claims_and_defenses || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.title || item.claim_type || 'Claim or defense'))}</strong>${litigationReportRows({elements: item.elements, defenses: item.defenses, admissions: item.admissions, missing_proof: item.missing_proof})}</div>`))}
      ${litigationReportSection('Issues and Proof Elements', litigationReportList(result.issues || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.title || item.issue || 'Issue'))}</strong>${litigationReportRows({proof_elements: item.proof_elements, burdens: item.burdens, disputed_facts: item.disputed_facts, admissions: item.admissions, missing_proof: item.missing_proof})}</div>`))}
      ${litigationReportSection('Factual Chronology', litigationReportList(result.chronology || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(litigationDisplayValue(item.description))}</span></div>`))}
      ${litigationReportSection('Evidence Matrix', litigationReportList(result.evidence_matrix || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.issue || 'Issue'))}</strong>${litigationReportRows({element: item.element, supporting_evidence: item.supporting_evidence, adverse_evidence: item.adverse_evidence, gaps: item.gaps})}</div>`), {pageBreak: true})}
      ${litigationReportSection('Discovery Analysis', litigationReportList(result.discovery_analysis || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.item_type || 'Discovery'))}</strong>${litigationReportRows({description: item.description, status: item.status, confidence_score: item.confidence_score})}</div>`))}
      ${litigationReportSection('Witness Preparation', litigationReportList(result.witness_prep || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.name || 'Witness'))}</strong>${litigationReportRows({role: item.role, topics: item.topics, admissions: item.admissions, contradictions: item.contradictions, prep_questions: item.prep_questions})}</div>`))}
      ${litigationReportSection('Deposition Preparation', litigationReportList(result.deposition_prep || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.witness || 'Witness'))}</strong>${litigationReportRows({topics: item.topics, questions: item.questions, caveats: item.caveats})}</div>`))}
      ${litigationReportSection('Cross-Examination Topics', litigationReportList(result.cross_examination || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.witness || 'Witness'))}</strong>${litigationReportRows({topics: item.topics, questions: item.questions, caveats: item.caveats})}</div>`))}
      ${litigationReportSection('Procedural Tasks and Deadlines', litigationReportList(result.procedural_tasks || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(litigationDisplayValue(item.description || item.compliance_risk))}</span></div>`), {pageBreak: true})}
      ${litigationReportSection('Motion Strategy', litigationReportRows(result.motion_strategy || {}))}
      ${litigationReportSection('Trial Preparation', litigationReportRows(result.trial_prep || {}))}
      ${litigationReportSection('Argument Themes', litigationReportRows(result.argument_strategy || {}))}
      ${litigationReportSection('Damages and Remedies', litigationReportRows(result.damages_and_remedies || {}))}
      ${litigationReportSection('Risks and Gaps', litigationReportList(result.risks_and_gaps || [], item => `<div class="item"><strong>${esc(litigationDisplayValue(item.risk_level || 'Risk'))}</strong><span>${esc(litigationDisplayValue(item.summary || item.decision_point || item.leverage))}</span></div>`))}
      ${litigationReportSection('One-Page Litigation Plan', litigationReportRows({opening_focus: 'Confirm pleadings, relief sought, court posture, and agreed facts.', proof_focus: 'Use the evidence matrix to separate supported facts, adverse evidence, and missing proof.', discovery_focus: result.discovery_analysis || [], witness_focus: result.witness_prep || [], motion_and_trial_focus: {motions: result.motion_strategy || {}, trial: result.trial_prep || {}}, deadlines: result.procedural_tasks || [], review_points: result.risks_and_gaps || []}), {pageBreak: true})}
      ${litigationReportSection('Source Basis and Audit Notes', `<h3>Warnings</h3>${renderTranslationList(warnings, 'No warnings returned.')}<h3>Sources</h3>${renderTranslationList(sources.map(litigationSourceLabel), 'No source documents returned.')}<h3>Agent Trace</h3>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}`, {pageBreak: true})}
      <footer>Litigation preparation report. Generated from indexed matter documents. Verify all source references, procedural assumptions, deadlines, and legal conclusions before use.</footer>
    </article>`;
  if (!standalone) return body;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(result.title || 'Litigation Prep')}</title>${litigationReportStyles()}</head><body>${body}</body></html>`;
}

function renderLitigationPrepResult() {
  const result = App.litigationPrep.result;
  const grid = document.getElementById('litigation-prep-result-grid');
  const preview = document.getElementById('litigation-prep-preview');
  const meta = document.getElementById('litigation-prep-result-meta');
  const side = document.getElementById('litigation-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${config.party_role || 'neutral analysis'}${config.court ? ' · ' + config.court : ''}${config.jurisdiction ? ' · ' + config.jurisdiction : ''}`;
  preview.innerHTML = sanitizeDraftHtml(litigationReportStyles() + litigationPrepReportHtml(result, false));
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(litigationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function litigationPrepMarkdown(result = App.litigationPrep.result) {
  if (!result) return '';
  const section = (title, value) => {
    if (Array.isArray(value)) return `## ${title}\n${value.length ? value.map(item => `- ${litigationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
    return `## ${title}\n${litigationDisplayValue(value)}\n\n`;
  };
  return `# ${result.title || 'Litigation Prep'}\n\nLitigation preparation aid. This does not decide the dispute, provide legal advice, or predict outcomes.\n\n## Case Summary\n${litigationDisplayValue(result.client_or_team_summary)}\n\n${section('Claims and Defenses', result.claims_and_defenses)}${section('Issues and Proof Elements', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Discovery', result.discovery_analysis)}${section('Witness Prep', result.witness_prep)}${section('Depositions', result.deposition_prep)}${section('Cross-Examination', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}${section('Motion Strategy', result.motion_strategy)}${section('Trial Prep', result.trial_prep)}${section('Argument Strategy', result.argument_strategy)}${section('Damages and Remedies', result.damages_and_remedies)}${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
}

async function copyLitigationPrep() {
  const text = litigationPrepMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Litigation prep copied.');
}

function downloadLitigationPrep() {
  const text = litigationPrepMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `litigation-prep-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function litigationPrepHtmlFilename() {
  const title = (App.litigationPrep.result?.title || 'litigation-prep').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'litigation-prep';
  return `${title}-${Date.now()}.html`;
}

function downloadLitigationPrepHtml() {
  const html = litigationPrepReportHtml(App.litigationPrep.result, true);
  if (!html) return;
  const blob = new Blob([html], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = litigationPrepHtmlFilename();
  a.click();
  URL.revokeObjectURL(a.href);
}

function printLitigationPrepReport() {
  const html = litigationPrepReportHtml(App.litigationPrep.result, true);
  if (!html) return;
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    showToast('Pop-up blocked. Download the HTML report and print it from the browser.', 'warning');
    return;
  }
  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  setTimeout(() => printWindow.print(), 250);
}

function resetLitigationPrep() {
  App.litigationPrep.result = null;
  ['litigation-prep-title', 'litigation-prep-court', 'litigation-prep-jurisdiction', 'litigation-prep-venue', 'litigation-prep-stage', 'litigation-prep-dates', 'litigation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('litigation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
