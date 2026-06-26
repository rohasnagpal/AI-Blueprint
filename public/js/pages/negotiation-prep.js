// ── NEGOTIATION PREP ─────────────────────────────────────────────────────
function negotiationPrepWorkspaceId() {
  const selectValue = document.getElementById('negotiation-prep-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedNegotiationPrepMatterId() {
  const value = document.getElementById('negotiation-prep-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(negotiationPrepWorkspaceId())[0]?.id || null;
}

async function renderNegotiationPrep() {
  if (!App.v2.user && typeof initV2 === 'function') {
    await initV2().catch(() => {});
  }
  renderNegotiationPrepScopeSelector();
  await syncNegotiationPrepScope();
  renderNegotiationPrepScopeSelector();
  renderNegotiationPrepSourceDocuments();
  await loadNegotiationPrepHistory();
}

async function syncNegotiationPrepScope(options = {}) {
  const matterSelect = document.getElementById('negotiation-prep-matter-select');
  await syncV2WorkspaceMatterDocuments(negotiationPrepWorkspaceId(), matterSelect?.value || '', matterSelect, options);
}

function renderNegotiationPrepScopeSelector() {
  const workspaceSelect = document.getElementById('negotiation-prep-workspace-select');
  const matterSelect = document.getElementById('negotiation-prep-matter-select');
  const card = document.getElementById('negotiation-prep-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = negotiationPrepWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderNegotiationPrepScopeSelector).catch(() => {});
}

async function onNegotiationPrepWorkspaceChange() {
  const matterSelect = document.getElementById('negotiation-prep-matter-select');
  if (matterSelect) matterSelect.value = '';
  await syncNegotiationPrepScope({resetMatter: true});
  renderNegotiationPrepScopeSelector();
  renderNegotiationPrepSourceDocuments();
  await loadNegotiationPrepHistory();
}

async function onNegotiationPrepMatterChange() {
  await syncNegotiationPrepScope();
  renderNegotiationPrepSourceDocuments();
}

function renderNegotiationPrepSourceDocuments() {
  const field = document.getElementById('negotiation-prep-source-documents-field');
  const select = document.getElementById('negotiation-prep-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = negotiationPrepWorkspaceId();
  const selectedMatter = selectedNegotiationPrepMatterId();
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

function selectedNegotiationPrepDocumentIds() {
  const select = document.getElementById('negotiation-prep-source-documents');
  if (!select) return [];
  const selected = [...select.selectedOptions].map(option => option.value).filter(Boolean);
  if (selected.length) return selected;
  return [...select.options].map(option => option.value).filter(Boolean);
}

function collectNegotiationPrepPayload() {
  const workspaceId = negotiationPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const dates = (document.getElementById('negotiation-prep-dates')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
  return {
    workspaceId,
    payload: {
      title: document.getElementById('negotiation-prep-title')?.value.trim() || 'Negotiation Prep',
      matter_id: selectedNegotiationPrepMatterId(),
      document_ids: selectedNegotiationPrepDocumentIds(),
      party_role: document.getElementById('negotiation-prep-party-role')?.value || 'neutral analysis',
      court: document.getElementById('negotiation-prep-court')?.value.trim() || null,
      jurisdiction: document.getElementById('negotiation-prep-jurisdiction')?.value.trim() || null,
      venue: document.getElementById('negotiation-prep-venue')?.value.trim() || null,
      procedural_stage: document.getElementById('negotiation-prep-stage')?.value.trim() || null,
      hearing_dates: dates,
      negotiation_focus: document.getElementById('negotiation-prep-focus')?.value || 'full prep',
      instructions: document.getElementById('negotiation-prep-instructions')?.value.trim() || null,
    },
  };
}

async function loadNegotiationPrepHistory() {
  const workspaceId = negotiationPrepWorkspaceId();
  const card = document.getElementById('negotiation-prep-history-card');
  const list = document.getElementById('negotiation-prep-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/negotiation-prep/runs?page_size=8`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.negotiationPrep.history = data.items || [];
    card.style.display = App.negotiationPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.negotiationPrep.history.map(run => `<div class="council-row negotiation-prep-history-row">
      <div class="council-row-head negotiation-prep-history-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Negotiation prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.court ? ' · ' + esc(run.court) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions negotiation-prep-history-actions">
        <button class="btn-secondary" type="button" onclick="openNegotiationPrepRun('${esc(run.id)}')">Open</button>
        <button class="btn-secondary danger" type="button" onclick="deleteNegotiationPrepRun('${esc(run.id)}')">Delete</button>
      </div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openNegotiationPrepRun(runId) {
  const workspaceId = negotiationPrepWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/negotiation-prep/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.negotiationPrep.result = await r.json();
    renderNegotiationPrepResult();
    showToast('Negotiation prep loaded.');
  } catch(e) {
    showToast('Failed to load negotiation prep: ' + e.message, 'error');
  }
}

async function deleteNegotiationPrepRun(runId) {
  const workspaceId = negotiationPrepWorkspaceId();
  if (!workspaceId || !runId) return;
  const run = (App.negotiationPrep.history || []).find(item => item.id === runId);
  const title = run?.title || 'Negotiation prep';
  if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/negotiation-prep/runs/${encodeURIComponent(runId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.negotiationPrep.result?.id === runId) {
      App.negotiationPrep.result = null;
      const grid = document.getElementById('negotiation-prep-result-grid');
      if (grid) grid.style.display = 'none';
    }
    await loadNegotiationPrepHistory();
    showToast('Negotiation prep deleted.');
  } catch(e) {
    showToast('Failed to delete negotiation prep: ' + e.message, 'error');
  }
}

async function runNegotiationPrep() {
  if (App.negotiationPrep.isRunning) return;
  const btn = document.getElementById('negotiation-prep-run-btn');
  const status = document.getElementById('negotiation-prep-status');
  try {
    const {workspaceId, payload} = collectNegotiationPrepPayload();
    App.negotiationPrep.isRunning = true;
    App.negotiationPrep.result = null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Queuing prep...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/negotiation-prep/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startNegotiationPrepJobStream(workspaceId, data.job);
      showToast('Negotiation prep queued.');
      return;
    }
    App.negotiationPrep.result = data;
    renderNegotiationPrepResult();
    showToast('Negotiation prep complete.');
  } catch(e) {
    showToast('Negotiation prep failed: ' + e.message, 'error');
    App.negotiationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  } finally {
    if (App.negotiationPrep.job) return;
    App.negotiationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function stopNegotiationPrepStream() {
  App.negotiationPrep.stream?.close();
  App.negotiationPrep.stream = null;
}

function renderNegotiationPrepProgress() {
  const status = document.getElementById('negotiation-prep-status');
  const job = App.negotiationPrep.job;
  if (!status || !job) return;
  const latest = [...(App.negotiationPrep.events || [])].reverse().find(e => e.content)?.content || job.status || 'running';
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  status.textContent = `${latest} · ${progress}%`;
}

async function loadNegotiationPrepResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/negotiation-prep/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.negotiationPrep.result = await r.json();
  renderNegotiationPrepResult();
  return true;
}

function startNegotiationPrepJobStream(workspaceId, job) {
  stopNegotiationPrepStream();
  App.negotiationPrep.job = job;
  App.negotiationPrep.events = [{type:'status', content:'Negotiation prep queued', metadata:{progress:0}}];
  renderNegotiationPrepProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.negotiationPrep.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.negotiationPrep.job = data.metadata;
    if (data.type && data.type !== 'status') App.negotiationPrep.events.push(data);
    App.negotiationPrep.events = App.negotiationPrep.events.slice(-24);
    renderNegotiationPrepProgress();
    if (data.type === 'done') {
      stopNegotiationPrepStream();
      App.negotiationPrep.job = data.metadata || App.negotiationPrep.job;
      try {
        if (data.content === 'completed') {
          await loadNegotiationPrepResultFromJob(workspaceId, App.negotiationPrep.job);
          await loadNegotiationPrepHistory();
          showToast('Negotiation prep complete.');
        } else {
          showToast('Negotiation prep ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Prep completed but result load failed: ' + e.message, 'error');
      } finally {
        App.negotiationPrep.isRunning = false;
        App.negotiationPrep.job = null;
        const btn = document.getElementById('negotiation-prep-run-btn');
        const status = document.getElementById('negotiation-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      }
    }
  };
  source.onerror = () => {
    stopNegotiationPrepStream();
    App.negotiationPrep.isRunning = false;
    App.negotiationPrep.job = null;
    const btn = document.getElementById('negotiation-prep-run-btn');
    const status = document.getElementById('negotiation-prep-status');
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
    showToast('Negotiation prep event stream disconnected.', 'error');
  };
}

function negotiationDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(negotiationDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'description', 'title', 'theme', 'name', 'issue', 'excerpt']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return negotiationDisplayValue(value[key]);
    }
    return Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '').map(([key, item]) => `${key.replace(/_/g, ' ')}: ${negotiationDisplayValue(item)}`).join('; ');
  }
  return String(value);
}

function negotiationSourceLabel(source) {
  if (!source || typeof source !== 'object') return negotiationDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : Number(source.chunk_index || 0) + 1;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function renderNegotiationSection(title, items, renderer, emptyText) {
  return `<section><h2>${esc(title)}</h2>${items && items.length ? items.map(renderer).join('') : `<p>${esc(emptyText || 'No supported items returned.')}</p>`}</section>`;
}

function negotiationReportRows(value) {
  if (!value || typeof value !== 'object') return `<p>${esc(negotiationDisplayValue(value))}</p>`;
  return `<table><tbody>${Object.entries(value).map(([key, item]) => `<tr><th>${esc(key.replace(/_/g, ' '))}</th><td>${esc(negotiationDisplayValue(item))}</td></tr>`).join('')}</tbody></table>`;
}

function negotiationReportList(items, renderer, emptyText = 'No supported items returned.') {
  return items && items.length ? items.map(renderer).join('') : `<p class="muted">${esc(emptyText)}</p>`;
}

function negotiationReportSection(title, body, opts = {}) {
  return `<section class="${opts.pageBreak ? 'page-break' : ''}"><h2>${esc(title)}</h2>${body}</section>`;
}

function negotiationReportStyles() {
  return `<style>
    :root { color: #172026; background: #f3f1ea; font-family: Arial, Helvetica, sans-serif; }
    body { margin: 0; background: #f3f1ea; color: #172026; }
    .negotiation-report { max-width: 920px; margin: 0 auto; background: #fff; padding: 48px 56px; box-sizing: border-box; }
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
      .negotiation-report { max-width: none; margin: 0; padding: 0; }
      .page-break { break-before: page; }
      h2, .item, tr { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>`;
}

function negotiationPrepReportHtml(result = App.negotiationPrep.result, standalone = false) {
  if (!result) return '';
  const config = result.config || {};
  const generated = result.completed_at ? new Date(result.completed_at).toLocaleString() : new Date().toLocaleString();
  const sources = result.sources || [];
  const warnings = result.warnings || [];
  const body = `
    <article class="negotiation-report">
      <div class="report-kicker">Negotiation preparation</div>
      <h1>${esc(result.title || 'Negotiation Prep')}</h1>
      <div class="report-notice">This report is a negotiation preparation aid for lawyer review. It does not recommend settlement, decide the dispute, predict outcomes, or replace counsel judgment.</div>
      <div class="report-meta">
        <div><strong>Perspective:</strong> ${esc(config.party_role || 'neutral analysis')}</div>
        <div><strong>Generated:</strong> ${esc(generated)}</div>
        <div><strong>Counterparty / forum:</strong> ${esc(config.court || 'Not provided')}</div>
        <div><strong>Jurisdiction / market:</strong> ${esc(config.jurisdiction || 'Not provided')}</div>
        <div><strong>Context:</strong> ${esc(config.venue || 'Not provided')}</div>
        <div><strong>Stage:</strong> ${esc(config.procedural_stage || 'Not provided')}</div>
        <div><strong>Dates:</strong> ${esc(negotiationDisplayValue(config.hearing_dates || []))}</div>
        <div><strong>Focus:</strong> ${esc(config.negotiation_focus || 'full prep')}</div>
      </div>
      ${negotiationReportSection('Table of Contents', `<ol class="toc"><li>Negotiation Snapshot</li><li>Positions and Concessions</li><li>Issues and Proof Points</li><li>Chronology</li><li>Evidence Matrix</li><li>Information Gaps</li><li>Participant Prep</li><li>Authority and Caucus Prep</li><li>Reality-Testing Questions</li><li>Offer and Session Strategy</li><li>Value, Damages, and Remedies</li><li>Risks, Leverage, BATNA/WATNA</li><li>One-Page Negotiation Plan</li><li>Source Basis</li></ol>`)}
      ${negotiationReportSection('Negotiation Snapshot', `<p>${esc(negotiationDisplayValue(result.client_or_team_summary))}</p>${negotiationReportRows(result.case_snapshot || {})}`)}
      ${negotiationReportSection('Positions and Concessions', negotiationReportList(result.claims_and_defenses || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.title || item.claim_type || 'Position'))}</strong>${negotiationReportRows({elements: item.elements, defenses: item.defenses, admissions: item.admissions, settlement_relevance: item.settlement_relevance, missing_proof: item.missing_proof})}</div>`))}
      ${negotiationReportSection('Issues and Proof Points', negotiationReportList(result.issues || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.title || item.issue || 'Issue'))}</strong>${negotiationReportRows({proof_elements: item.proof_elements, disputed_facts: item.disputed_facts, admissions: item.admissions, missing_proof: item.missing_proof})}</div>`))}
      ${negotiationReportSection('Chronology', negotiationReportList(result.chronology || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(negotiationDisplayValue(item.description))}</span></div>`))}
      ${negotiationReportSection('Evidence Matrix', negotiationReportList(result.evidence_matrix || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.issue || 'Issue'))}</strong>${negotiationReportRows({supporting_evidence: item.supporting_evidence, adverse_evidence: item.adverse_evidence, gaps: item.gaps})}</div>`), {pageBreak: true})}
      ${negotiationReportSection('Information Gaps', negotiationReportList(result.discovery_analysis || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.item_type || 'Information gap'))}</strong>${negotiationReportRows({description: item.description, status: item.status, confidence_score: item.confidence_score})}</div>`))}
      ${negotiationReportSection('Participant Preparation', negotiationReportList(result.witness_prep || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.name || 'Participant'))}</strong>${negotiationReportRows({role: item.role, topics: item.topics, admissions: item.admissions, contradictions: item.contradictions, prep_questions: item.prep_questions})}</div>`))}
      ${negotiationReportSection('Authority and Caucus Preparation', negotiationReportList(result.deposition_prep || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.witness || 'Participant'))}</strong>${negotiationReportRows({topics: item.topics, questions: item.questions, caveats: item.caveats})}</div>`))}
      ${negotiationReportSection('Reality-Testing Questions', negotiationReportList(result.cross_examination || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.witness || 'Participant'))}</strong>${negotiationReportRows({topics: item.topics, questions: item.questions, caveats: item.caveats})}</div>`))}
      ${negotiationReportSection('Offer and Session Strategy', `${negotiationReportRows({position_brief: result.motion_strategy || {}, session_plan: result.trial_prep || {}, negotiation_themes: result.argument_strategy || {}})}`, {pageBreak: true})}
      ${negotiationReportSection('Procedural Tasks', negotiationReportList(result.procedural_tasks || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(negotiationDisplayValue(item.description || item.compliance_risk))}</span></div>`))}
      ${negotiationReportSection('Value, Damages, and Remedies', negotiationReportRows(result.damages_and_remedies || {}))}
      ${negotiationReportSection('Risks, Leverage, BATNA/WATNA', negotiationReportList(result.risks_and_gaps || [], item => `<div class="item"><strong>${esc(negotiationDisplayValue(item.risk_level || 'Risk'))}</strong><span>${esc(negotiationDisplayValue(item.summary || item.decision_point || item.leverage))}</span></div>`))}
      ${negotiationReportSection('One-Page Negotiation Plan', negotiationReportRows({opening_focus: 'Confirm posture, objectives, authority, red lines, and evidence-backed points.', information_focus: result.discovery_analysis || [], leverage_focus: result.risks_and_gaps || [], offer_framing: result.argument_strategy || {}, participant_focus: result.witness_prep || [], deadlines: result.procedural_tasks || []}), {pageBreak: true})}
      ${negotiationReportSection('Source Basis and Audit Notes', `<h3>Warnings</h3>${renderTranslationList(warnings, 'No warnings returned.')}<h3>Sources</h3>${renderTranslationList(sources.map(negotiationSourceLabel), 'No source documents returned.')}<h3>Agent Trace</h3>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}`, {pageBreak: true})}
      <footer>Negotiation preparation report. Generated from indexed matter documents. Verify all source references, authority assumptions, deadlines, and legal conclusions before use.</footer>
    </article>`;
  if (!standalone) return body;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(result.title || 'Negotiation Prep')}</title>${negotiationReportStyles()}</head><body>${body}</body></html>`;
}

function renderNegotiationPrepResult() {
  const result = App.negotiationPrep.result;
  const grid = document.getElementById('negotiation-prep-result-grid');
  const preview = document.getElementById('negotiation-prep-preview');
  const meta = document.getElementById('negotiation-prep-result-meta');
  const side = document.getElementById('negotiation-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${config.party_role || 'neutral analysis'}${config.court ? ' · ' + config.court : ''}${config.jurisdiction ? ' · ' + config.jurisdiction : ''}`;
  preview.innerHTML = sanitizeDraftHtml(negotiationReportStyles() + negotiationPrepReportHtml(result, false));
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(negotiationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function negotiationPrepMarkdown(result = App.negotiationPrep.result) {
  if (!result) return '';
  const section = (title, value) => {
    if (Array.isArray(value)) return `## ${title}\n${value.length ? value.map(item => `- ${negotiationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
    return `## ${title}\n${negotiationDisplayValue(value)}\n\n`;
  };
  return `# ${result.title || 'Negotiation Prep'}\n\nNegotiation preparation aid. This does not recommend settlement, decide the dispute, or predict outcomes.\n\n## Case Summary\n${negotiationDisplayValue(result.client_or_team_summary)}\n\n${section('Positions and Concessions', result.claims_and_defenses)}${section('Issues', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Information Gaps', result.discovery_analysis)}${section('Participant Prep', result.witness_prep)}${section('Authority and Caucus Prep', result.deposition_prep)}${section('Reality-Testing Questions', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}${section('Position Brief Strategy', result.motion_strategy)}${section('Session Plan', result.trial_prep)}${section('Negotiation Themes', result.argument_strategy)}${section('Damages and Remedies', result.damages_and_remedies)}${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
}

async function copyNegotiationPrep() {
  const text = negotiationPrepMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Negotiation prep copied.');
}

function downloadNegotiationPrep() {
  const text = negotiationPrepMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `negotiation-prep-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function negotiationPrepHtmlFilename() {
  const title = (App.negotiationPrep.result?.title || 'negotiation-prep').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'negotiation-prep';
  return `${title}-${Date.now()}.html`;
}

function downloadNegotiationPrepHtml() {
  const html = negotiationPrepReportHtml(App.negotiationPrep.result, true);
  if (!html) return;
  const blob = new Blob([html], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = negotiationPrepHtmlFilename();
  a.click();
  URL.revokeObjectURL(a.href);
}

function printNegotiationPrepReport() {
  const html = negotiationPrepReportHtml(App.negotiationPrep.result, true);
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

function resetNegotiationPrep() {
  App.negotiationPrep.result = null;
  ['negotiation-prep-title', 'negotiation-prep-court', 'negotiation-prep-jurisdiction', 'negotiation-prep-venue', 'negotiation-prep-stage', 'negotiation-prep-dates', 'negotiation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('negotiation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
