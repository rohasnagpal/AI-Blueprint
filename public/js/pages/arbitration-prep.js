// ── ARBITRATION PREP ─────────────────────────────────────────────────────
function arbitrationPrepWorkspaceId() {
  const selectValue = document.getElementById('arbitration-prep-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedArbitrationPrepMatterId() {
  const value = document.getElementById('arbitration-prep-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(arbitrationPrepWorkspaceId())[0]?.id || null;
}

async function renderArbitrationPrep() {
  if (!App.v2.user && typeof initV2 === 'function') {
    await initV2().catch(() => {});
  }
  renderArbitrationPrepScopeSelector();
  await syncArbitrationPrepScope();
  renderArbitrationPrepScopeSelector();
  renderArbitrationPrepSourceDocuments();
  await loadArbitrationPrepHistory();
}

async function syncArbitrationPrepScope(options = {}) {
  const matterSelect = document.getElementById('arbitration-prep-matter-select');
  await syncV2WorkspaceMatterDocuments(arbitrationPrepWorkspaceId(), matterSelect?.value || '', matterSelect, options);
}

function renderArbitrationPrepScopeSelector() {
  const workspaceSelect = document.getElementById('arbitration-prep-workspace-select');
  const matterSelect = document.getElementById('arbitration-prep-matter-select');
  const card = document.getElementById('arbitration-prep-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = arbitrationPrepWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderArbitrationPrepScopeSelector).catch(() => {});
}

async function onArbitrationPrepWorkspaceChange() {
  const matterSelect = document.getElementById('arbitration-prep-matter-select');
  if (matterSelect) matterSelect.value = '';
  await syncArbitrationPrepScope({resetMatter: true});
  renderArbitrationPrepScopeSelector();
  renderArbitrationPrepSourceDocuments();
  await loadArbitrationPrepHistory();
}

async function onArbitrationPrepMatterChange() {
  await syncArbitrationPrepScope();
  renderArbitrationPrepSourceDocuments();
}

function renderArbitrationPrepSourceDocuments() {
  const field = document.getElementById('arbitration-prep-source-documents-field');
  const select = document.getElementById('arbitration-prep-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = arbitrationPrepWorkspaceId();
  const selectedMatter = selectedArbitrationPrepMatterId();
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

function selectedArbitrationPrepDocumentIds() {
  const select = document.getElementById('arbitration-prep-source-documents');
  if (!select) return [];
  const selected = [...select.selectedOptions].map(option => option.value).filter(Boolean);
  if (selected.length) return selected;
  return [...select.options].map(option => option.value).filter(Boolean);
}

function collectArbitrationPrepPayload() {
  const workspaceId = arbitrationPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const dates = (document.getElementById('arbitration-prep-dates')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
  return {
    workspaceId,
    payload: {
      title: document.getElementById('arbitration-prep-title')?.value.trim() || 'Arbitration Prep',
      matter_id: selectedArbitrationPrepMatterId(),
      document_ids: selectedArbitrationPrepDocumentIds(),
      party_role: document.getElementById('arbitration-prep-party-role')?.value || 'neutral analysis',
      forum_rules: document.getElementById('arbitration-prep-forum-rules')?.value || null,
      seat: document.getElementById('arbitration-prep-seat')?.value.trim() || null,
      procedural_stage: document.getElementById('arbitration-prep-stage')?.value.trim() || null,
      hearing_dates: dates,
      instructions: document.getElementById('arbitration-prep-instructions')?.value.trim() || null,
    },
  };
}

async function loadArbitrationPrepHistory() {
  const workspaceId = arbitrationPrepWorkspaceId();
  const card = document.getElementById('arbitration-prep-history-card');
  const list = document.getElementById('arbitration-prep-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/arbitration-prep/runs?page_size=8`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.arbitrationPrep.history = data.items || [];
    card.style.display = App.arbitrationPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.arbitrationPrep.history.map(run => `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Arbitration prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.forum_rules ? ' · ' + esc(run.forum_rules) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions"><button class="btn-secondary" type="button" onclick="openArbitrationPrepRun('${esc(run.id)}')">Open</button></div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openArbitrationPrepRun(runId) {
  const workspaceId = arbitrationPrepWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/arbitration-prep/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.arbitrationPrep.result = await r.json();
    renderArbitrationPrepResult();
    showToast('Arbitration prep loaded.');
  } catch(e) {
    showToast('Failed to load arbitration prep: ' + e.message, 'error');
  }
}

async function runArbitrationPrep() {
  if (App.arbitrationPrep.isRunning) return;
  const btn = document.getElementById('arbitration-prep-run-btn');
  const status = document.getElementById('arbitration-prep-status');
  try {
    const {workspaceId, payload} = collectArbitrationPrepPayload();
    App.arbitrationPrep.isRunning = true;
    App.arbitrationPrep.result = null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Queuing prep...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/arbitration-prep/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startArbitrationPrepJobStream(workspaceId, data.job);
      showToast('Arbitration prep queued.');
      return;
    }
    App.arbitrationPrep.result = data;
    renderArbitrationPrepResult();
    showToast('Arbitration prep complete.');
  } catch(e) {
    showToast('Arbitration prep failed: ' + e.message, 'error');
    App.arbitrationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  } finally {
    if (App.arbitrationPrep.job) return;
    App.arbitrationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function stopArbitrationPrepStream() {
  App.arbitrationPrep.stream?.close();
  App.arbitrationPrep.stream = null;
}

function renderArbitrationPrepProgress() {
  const status = document.getElementById('arbitration-prep-status');
  const job = App.arbitrationPrep.job;
  if (!status || !job) return;
  const latest = [...(App.arbitrationPrep.events || [])].reverse().find(e => e.content)?.content || job.status || 'running';
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  status.textContent = `${latest} · ${progress}%`;
}

async function loadArbitrationPrepResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/arbitration-prep/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.arbitrationPrep.result = await r.json();
  renderArbitrationPrepResult();
  return true;
}

function startArbitrationPrepJobStream(workspaceId, job) {
  stopArbitrationPrepStream();
  App.arbitrationPrep.job = job;
  App.arbitrationPrep.events = [{type:'status', content:'Arbitration prep queued', metadata:{progress:0}}];
  renderArbitrationPrepProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.arbitrationPrep.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.arbitrationPrep.job = data.metadata;
    if (data.type && data.type !== 'status') App.arbitrationPrep.events.push(data);
    App.arbitrationPrep.events = App.arbitrationPrep.events.slice(-24);
    renderArbitrationPrepProgress();
    if (data.type === 'done') {
      stopArbitrationPrepStream();
      App.arbitrationPrep.job = data.metadata || App.arbitrationPrep.job;
      try {
        if (data.content === 'completed') {
          await loadArbitrationPrepResultFromJob(workspaceId, App.arbitrationPrep.job);
          await loadArbitrationPrepHistory();
          showToast('Arbitration prep complete.');
        } else {
          showToast('Arbitration prep ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Prep completed but result load failed: ' + e.message, 'error');
      } finally {
        App.arbitrationPrep.isRunning = false;
        App.arbitrationPrep.job = null;
        const btn = document.getElementById('arbitration-prep-run-btn');
        const status = document.getElementById('arbitration-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      }
    }
  };
  source.onerror = () => {
    stopArbitrationPrepStream();
    App.arbitrationPrep.isRunning = false;
    App.arbitrationPrep.job = null;
    const btn = document.getElementById('arbitration-prep-run-btn');
    const status = document.getElementById('arbitration-prep-status');
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
    showToast('Arbitration prep event stream disconnected.', 'error');
  };
}

function arbitrationDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(arbitrationDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'description', 'title', 'theme', 'name', 'issue', 'excerpt']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return arbitrationDisplayValue(value[key]);
    }
    return Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '').map(([key, item]) => `${key.replace(/_/g, ' ')}: ${arbitrationDisplayValue(item)}`).join('; ');
  }
  return String(value);
}

function arbitrationSourceLabel(source) {
  if (!source || typeof source !== 'object') return arbitrationDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : Number(source.chunk_index || 0) + 1;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function renderArbitrationSection(title, items, renderer, emptyText) {
  return `<section><h2>${esc(title)}</h2>${items && items.length ? items.map(renderer).join('') : `<p>${esc(emptyText || 'No supported items returned.')}</p>`}</section>`;
}

function arbitrationReportRows(value) {
  if (!value || typeof value !== 'object') return `<p>${esc(arbitrationDisplayValue(value))}</p>`;
  return `<table><tbody>${Object.entries(value).map(([key, item]) => `<tr><th>${esc(key.replace(/_/g, ' '))}</th><td>${esc(arbitrationDisplayValue(item))}</td></tr>`).join('')}</tbody></table>`;
}

function arbitrationReportList(items, renderer, emptyText = 'No supported items returned.') {
  return items && items.length ? items.map(renderer).join('') : `<p class="muted">${esc(emptyText)}</p>`;
}

function arbitrationReportSection(title, body, opts = {}) {
  return `<section class="${opts.pageBreak ? 'page-break' : ''}"><h2>${esc(title)}</h2>${body}</section>`;
}

function arbitrationReportStyles() {
  return `<style>
    :root { color: #172026; background: #f4f1ea; font-family: Arial, Helvetica, sans-serif; }
    body { margin: 0; background: #f4f1ea; color: #172026; }
    .arbitration-report { max-width: 920px; margin: 0 auto; background: #fff; padding: 48px 56px; box-sizing: border-box; }
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
      .arbitration-report { max-width: none; margin: 0; padding: 0; }
      .page-break { break-before: page; }
      h2, .item, tr { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>`;
}

function arbitrationPrepReportHtml(result = App.arbitrationPrep.result, standalone = false) {
  if (!result) return '';
  const config = result.config || {};
  const generated = result.completed_at ? new Date(result.completed_at).toLocaleString() : new Date().toLocaleString();
  const sources = result.sources || [];
  const warnings = result.warnings || [];
  const body = `
    <article class="arbitration-report">
      <div class="report-kicker">Arbitration preparation</div>
      <h1>${esc(result.title || 'Arbitration Prep')}</h1>
      <div class="report-notice">This report is an arbitration preparation aid for legal review. It does not decide the dispute, provide legal advice, predict the award, or replace counsel judgment.</div>
      <div class="report-meta">
        <div><strong>Perspective:</strong> ${esc(config.party_role || 'neutral analysis')}</div>
        <div><strong>Generated:</strong> ${esc(generated)}</div>
        <div><strong>Forum / rules:</strong> ${esc(config.forum_rules || 'Not provided')}</div>
        <div><strong>Seat / jurisdiction:</strong> ${esc(config.seat || 'Not provided')}</div>
        <div><strong>Stage:</strong> ${esc(config.procedural_stage || 'Not provided')}</div>
        <div><strong>Hearing dates:</strong> ${esc(arbitrationDisplayValue(config.hearing_dates || []))}</div>
      </div>
      ${arbitrationReportSection('Table of Contents', `<ol class="toc"><li>Case Snapshot</li><li>Procedural Posture</li><li>Issues for Determination</li><li>Factual Chronology</li><li>Evidence Matrix</li><li>Witness Preparation</li><li>Cross-Examination Topics</li><li>Procedural Tasks</li><li>Damages and Remedies</li><li>Strengths, Weaknesses, and Uncertainties</li><li>Argument Themes</li><li>One-Page Hearing Preparation Plan</li><li>Source Basis</li></ol>`)}
      ${arbitrationReportSection('Case Snapshot', `<p>${esc(arbitrationDisplayValue(result.client_or_team_summary))}</p>${arbitrationReportRows(result.case_snapshot || {})}`)}
      ${arbitrationReportSection('Procedural Posture', arbitrationReportRows({forum_rules: config.forum_rules || result.case_snapshot?.forum_rules, seat: config.seat || result.case_snapshot?.seat, procedural_stage: config.procedural_stage || result.case_snapshot?.procedural_stage, key_dates: config.hearing_dates || result.case_snapshot?.key_dates}))}
      ${arbitrationReportSection('Issues for Determination', arbitrationReportList(result.issues || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(arbitrationDisplayValue(item.summary || item.missing_proof || item.proof_elements || 'Requires review'))}</span></div>`))}
      ${arbitrationReportSection('Factual Chronology', arbitrationReportList(result.chronology || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(arbitrationDisplayValue(item.description))}</span></div>`))}
      ${arbitrationReportSection('Evidence Matrix', arbitrationReportList(result.evidence_matrix || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.issue || 'Issue'))}</strong>${arbitrationReportRows({supporting_evidence: item.supporting_evidence, adverse_evidence: item.adverse_evidence, gaps: item.gaps})}</div>`), {pageBreak: true})}
      ${arbitrationReportSection('Witness Preparation', arbitrationReportList(result.witness_prep || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.name || 'Witness'))}</strong>${arbitrationReportRows({role: item.role, topics: item.topics, admissions: item.admissions, contradictions: item.contradictions, prep_questions: item.prep_questions})}</div>`))}
      ${arbitrationReportSection('Cross-Examination Topics', arbitrationReportList(result.cross_examination || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.witness || 'Witness'))}</strong>${arbitrationReportRows({topics: item.topics, questions: item.questions, caveats: item.caveats})}</div>`))}
      ${arbitrationReportSection('Procedural Tasks and Hearing Deadlines', arbitrationReportList(result.procedural_tasks || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(arbitrationDisplayValue(item.description || item.compliance_risk))}</span></div>`))}
      ${arbitrationReportSection('Damages and Remedies', arbitrationReportRows(result.damages_and_remedies || {}), {pageBreak: true})}
      ${arbitrationReportSection('Strengths, Weaknesses, and Uncertainty Points', arbitrationReportList(result.risks_and_gaps || [], item => `<div class="item"><strong>${esc(arbitrationDisplayValue(item.risk_level || 'Risk'))}</strong><span>${esc(arbitrationDisplayValue(item.summary || item.decision_point || item.leverage))}</span></div>`))}
      ${arbitrationReportSection('Argument Themes', arbitrationReportRows(result.argument_strategy || {}))}
      ${arbitrationReportSection('One-Page Hearing Preparation Plan', arbitrationReportRows({opening_focus: 'Confirm procedural posture, relief sought, tribunal issues, and agreed facts.', evidence_focus: 'Use the evidence matrix to separate supported facts, adverse evidence, and gaps.', witness_focus: 'Prepare admissions, contradictions, exhibit references, and cross-examination topics.', deadlines: result.procedural_tasks || [], review_points: result.risks_and_gaps || []}), {pageBreak: true})}
      ${arbitrationReportSection('Source Basis and Audit Notes', `<h3>Warnings</h3>${renderTranslationList(warnings, 'No warnings returned.')}<h3>Sources</h3>${renderTranslationList(sources.map(arbitrationSourceLabel), 'No source documents returned.')}<h3>Agent Trace</h3>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}`, {pageBreak: true})}
      <footer>Arbitration preparation report. Generated from indexed matter documents. Verify all source references, procedural assumptions, deadlines, and legal conclusions before use.</footer>
    </article>`;
  if (!standalone) return body;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(result.title || 'Arbitration Prep')}</title>${arbitrationReportStyles()}</head><body>${body}</body></html>`;
}

function renderArbitrationPrepResult() {
  const result = App.arbitrationPrep.result;
  const grid = document.getElementById('arbitration-prep-result-grid');
  const preview = document.getElementById('arbitration-prep-preview');
  const meta = document.getElementById('arbitration-prep-result-meta');
  const side = document.getElementById('arbitration-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${config.party_role || 'neutral analysis'}${config.forum_rules ? ' · ' + config.forum_rules : ''}${config.seat ? ' · ' + config.seat : ''}`;
  preview.innerHTML = sanitizeDraftHtml(arbitrationReportStyles() + arbitrationPrepReportHtml(result, false));
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(arbitrationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function arbitrationPrepMarkdown(result = App.arbitrationPrep.result) {
  if (!result) return '';
  const section = (title, value) => {
    if (Array.isArray(value)) return `## ${title}\n${value.length ? value.map(item => `- ${arbitrationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
    return `## ${title}\n${arbitrationDisplayValue(value)}\n\n`;
  };
  return `# ${result.title || 'Arbitration Prep'}\n\nArbitration preparation aid. This does not decide the dispute, provide legal advice, or predict the award.\n\n## Case Summary\n${arbitrationDisplayValue(result.client_or_team_summary)}\n\n${section('Issues for Determination', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Witness Prep', result.witness_prep)}${section('Cross-Examination', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}${section('Damages and Remedies', result.damages_and_remedies)}${section('Risks and Gaps', result.risks_and_gaps)}${section('Argument Strategy', result.argument_strategy)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
}

async function copyArbitrationPrep() {
  const text = arbitrationPrepMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Arbitration prep copied.');
}

function downloadArbitrationPrep() {
  const text = arbitrationPrepMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `arbitration-prep-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function arbitrationPrepHtmlFilename() {
  const title = (App.arbitrationPrep.result?.title || 'arbitration-prep').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'arbitration-prep';
  return `${title}-${Date.now()}.html`;
}

function downloadArbitrationPrepHtml() {
  const html = arbitrationPrepReportHtml(App.arbitrationPrep.result, true);
  if (!html) return;
  const blob = new Blob([html], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = arbitrationPrepHtmlFilename();
  a.click();
  URL.revokeObjectURL(a.href);
}

function printArbitrationPrepReport() {
  const html = arbitrationPrepReportHtml(App.arbitrationPrep.result, true);
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

function resetArbitrationPrep() {
  App.arbitrationPrep.result = null;
  ['arbitration-prep-title', 'arbitration-prep-seat', 'arbitration-prep-stage', 'arbitration-prep-dates', 'arbitration-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('arbitration-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
