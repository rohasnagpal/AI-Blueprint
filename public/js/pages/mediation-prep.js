// ── MEDIATION PREP ─────────────────────────────────────────────────────
function mediationPrepWorkspaceId() {
  const selectValue = document.getElementById('mediation-prep-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedMediationPrepMatterId() {
  const value = document.getElementById('mediation-prep-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(mediationPrepWorkspaceId())[0]?.id || null;
}

async function renderMediationPrep() {
  if (!App.v2.user && typeof initV2 === 'function') {
    await initV2().catch(() => {});
  }
  renderMediationPrepScopeSelector();
  await syncMediationPrepScope();
  renderMediationPrepScopeSelector();
  renderMediationPrepSourceDocuments();
  await loadMediationPrepHistory();
}

async function syncMediationPrepScope(options = {}) {
  const matterSelect = document.getElementById('mediation-prep-matter-select');
  await syncV2WorkspaceMatterDocuments(mediationPrepWorkspaceId(), matterSelect?.value || '', matterSelect, options);
}

function renderMediationPrepScopeSelector() {
  const workspaceSelect = document.getElementById('mediation-prep-workspace-select');
  const matterSelect = document.getElementById('mediation-prep-matter-select');
  const card = document.getElementById('mediation-prep-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = mediationPrepWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderMediationPrepScopeSelector).catch(() => {});
}

async function onMediationPrepWorkspaceChange() {
  const matterSelect = document.getElementById('mediation-prep-matter-select');
  if (matterSelect) matterSelect.value = '';
  await syncMediationPrepScope({resetMatter: true});
  renderMediationPrepScopeSelector();
  renderMediationPrepSourceDocuments();
  await loadMediationPrepHistory();
}

async function onMediationPrepMatterChange() {
  await syncMediationPrepScope();
  renderMediationPrepSourceDocuments();
}

function renderMediationPrepSourceDocuments() {
  const field = document.getElementById('mediation-prep-source-documents-field');
  const select = document.getElementById('mediation-prep-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = mediationPrepWorkspaceId();
  const selectedMatter = selectedMediationPrepMatterId();
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

function selectedMediationPrepDocumentIds() {
  const select = document.getElementById('mediation-prep-source-documents');
  if (!select) return [];
  const selected = [...select.selectedOptions].map(option => option.value).filter(Boolean);
  if (selected.length) return selected;
  return [...select.options].map(option => option.value).filter(Boolean);
}

function collectMediationPrepPayload() {
  const workspaceId = mediationPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const dates = (document.getElementById('mediation-prep-dates')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
  return {
    workspaceId,
    payload: {
      title: document.getElementById('mediation-prep-title')?.value.trim() || 'Mediator Prep Report',
      matter_id: selectedMediationPrepMatterId(),
      document_ids: selectedMediationPrepDocumentIds(),
      party_role: document.getElementById('mediation-prep-party-role')?.value || 'neutral mediator',
      court: document.getElementById('mediation-prep-court')?.value.trim() || null,
      jurisdiction: document.getElementById('mediation-prep-jurisdiction')?.value.trim() || null,
      venue: document.getElementById('mediation-prep-venue')?.value.trim() || null,
      procedural_stage: document.getElementById('mediation-prep-stage')?.value.trim() || null,
      hearing_dates: dates,
      mediation_focus: document.getElementById('mediation-prep-focus')?.value || 'full prep',
      instructions: document.getElementById('mediation-prep-instructions')?.value.trim() || null,
    },
  };
}

async function loadMediationPrepHistory() {
  const workspaceId = mediationPrepWorkspaceId();
  const card = document.getElementById('mediation-prep-history-card');
  const list = document.getElementById('mediation-prep-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/mediation-prep/runs?page_size=8`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.mediationPrep.history = data.items || [];
    card.style.display = App.mediationPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.mediationPrep.history.map(run => `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Mediation prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.court ? ' · ' + esc(run.court) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions"><button class="btn-secondary" type="button" onclick="openMediationPrepRun('${esc(run.id)}')">Open</button></div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openMediationPrepRun(runId) {
  const workspaceId = mediationPrepWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/mediation-prep/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.mediationPrep.result = await r.json();
    renderMediationPrepResult();
    showToast('Mediation prep loaded.');
  } catch(e) {
    showToast('Failed to load mediation prep: ' + e.message, 'error');
  }
}

async function runMediationPrep() {
  if (App.mediationPrep.isRunning) return;
  const btn = document.getElementById('mediation-prep-run-btn');
  const status = document.getElementById('mediation-prep-status');
  try {
    const {workspaceId, payload} = collectMediationPrepPayload();
    App.mediationPrep.isRunning = true;
    App.mediationPrep.result = null;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Queuing prep...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/mediation-prep/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startMediationPrepJobStream(workspaceId, data.job);
      showToast('Mediation prep queued.');
      return;
    }
    App.mediationPrep.result = data;
    renderMediationPrepResult();
    showToast('Mediation prep complete.');
  } catch(e) {
    showToast('Mediation prep failed: ' + e.message, 'error');
    App.mediationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  } finally {
    if (App.mediationPrep.job) return;
    App.mediationPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function stopMediationPrepStream() {
  App.mediationPrep.stream?.close();
  App.mediationPrep.stream = null;
}

function renderMediationPrepProgress() {
  const status = document.getElementById('mediation-prep-status');
  const job = App.mediationPrep.job;
  if (!status || !job) return;
  const latest = [...(App.mediationPrep.events || [])].reverse().find(e => e.content)?.content || job.status || 'running';
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  status.textContent = `${latest} · ${progress}%`;
}

async function loadMediationPrepResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/mediation-prep/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.mediationPrep.result = await r.json();
  renderMediationPrepResult();
  return true;
}

function startMediationPrepJobStream(workspaceId, job) {
  stopMediationPrepStream();
  App.mediationPrep.job = job;
  App.mediationPrep.events = [{type:'status', content:'Mediation prep queued', metadata:{progress:0}}];
  renderMediationPrepProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.mediationPrep.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.mediationPrep.job = data.metadata;
    if (data.type && data.type !== 'status') App.mediationPrep.events.push(data);
    App.mediationPrep.events = App.mediationPrep.events.slice(-24);
    renderMediationPrepProgress();
    if (data.type === 'done') {
      stopMediationPrepStream();
      App.mediationPrep.job = data.metadata || App.mediationPrep.job;
      try {
        if (data.content === 'completed') {
          await loadMediationPrepResultFromJob(workspaceId, App.mediationPrep.job);
          await loadMediationPrepHistory();
          showToast('Mediation prep complete.');
        } else {
          showToast('Mediation prep ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Prep completed but result load failed: ' + e.message, 'error');
      } finally {
        App.mediationPrep.isRunning = false;
        App.mediationPrep.job = null;
        const btn = document.getElementById('mediation-prep-run-btn');
        const status = document.getElementById('mediation-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      }
    }
  };
  source.onerror = () => {
    stopMediationPrepStream();
    App.mediationPrep.isRunning = false;
    App.mediationPrep.job = null;
    const btn = document.getElementById('mediation-prep-run-btn');
    const status = document.getElementById('mediation-prep-status');
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
    showToast('Mediation prep event stream disconnected.', 'error');
  };
}

function mediationDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(mediationDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'description', 'title', 'theme', 'name', 'issue', 'excerpt']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return mediationDisplayValue(value[key]);
    }
    return Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '').map(([key, item]) => `${key.replace(/_/g, ' ')}: ${mediationDisplayValue(item)}`).join('; ');
  }
  return String(value);
}

function mediationSourceLabel(source) {
  if (!source || typeof source !== 'object') return mediationDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : Number(source.chunk_index || 0) + 1;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function renderMediationSection(title, items, renderer, emptyText) {
  return `<section><h2>${esc(title)}</h2>${items && items.length ? items.map(renderer).join('') : `<p>${esc(emptyText || 'No supported items returned.')}</p>`}</section>`;
}

function mediationReportRows(value) {
  if (!value || typeof value !== 'object') return `<p>${esc(mediationDisplayValue(value))}</p>`;
  return `<table><tbody>${Object.entries(value).map(([key, item]) => `<tr><th>${esc(key.replace(/_/g, ' '))}</th><td>${esc(mediationDisplayValue(item))}</td></tr>`).join('')}</tbody></table>`;
}

function mediationReportList(items, renderer, emptyText = 'No supported items returned.') {
  return items && items.length ? items.map(renderer).join('') : `<p class="muted">${esc(emptyText)}</p>`;
}

function mediationReportSection(title, body, opts = {}) {
  return `<section class="${opts.pageBreak ? 'page-break' : ''}"><h2>${esc(title)}</h2>${body}</section>`;
}

function mediationReportStyles() {
  return `<style>
    :root { color: #172026; background: #f4f1ea; font-family: Arial, Helvetica, sans-serif; }
    body { margin: 0; background: #f4f1ea; color: #172026; }
    .mediator-report { max-width: 920px; margin: 0 auto; background: #fff; padding: 48px 56px; box-sizing: border-box; }
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
      .mediator-report { max-width: none; margin: 0; padding: 0; }
      .page-break { break-before: page; }
      h2, .item, tr { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>`;
}

function mediationPrepReportHtml(result = App.mediationPrep.result, standalone = false) {
  if (!result) return '';
  const config = result.config || {};
  const generated = result.completed_at ? new Date(result.completed_at).toLocaleString() : new Date().toLocaleString();
  const sources = result.sources || [];
  const warnings = result.warnings || [];
  const body = `
    <article class="mediator-report">
      <div class="report-kicker">Private mediator preparation</div>
      <h1>${esc(result.title || 'Mediator Prep Report')}</h1>
      <div class="report-notice">This report is a neutral preparation aid for the mediator. It does not decide the dispute, provide legal advice, predict the outcome, or replace mediator judgment. Inferences, settlement ranges, and bridge options must be tested in session.</div>
      <div class="report-meta">
        <div><strong>Perspective:</strong> ${esc(config.party_role || 'neutral mediator')}</div>
        <div><strong>Generated:</strong> ${esc(generated)}</div>
        <div><strong>Provider / court:</strong> ${esc(config.court || 'Not provided')}</div>
        <div><strong>Jurisdiction / venue:</strong> ${esc([config.jurisdiction, config.venue].filter(Boolean).join(' / ') || 'Not provided')}</div>
        <div><strong>Stage:</strong> ${esc(config.procedural_stage || 'Not provided')}</div>
        <div><strong>Mediation dates:</strong> ${esc(mediationDisplayValue(config.hearing_dates || []))}</div>
      </div>
      ${mediationReportSection('Table of Contents', `<ol class="toc"><li>Neutral Case Summary</li><li>Factual Chronology</li><li>Key Issues</li><li>Party Positions vs Underlying Interests</li><li>BATNA / WATNA / ZOPA</li><li>Strengths, Weaknesses, and Uncertainties</li><li>Risk Allocation</li><li>Settlement Levers</li><li>Information Gaps</li><li>Caucus Questions</li><li>Likely Impasse Points</li><li>Bridge Proposals</li><li>Mediator Private Prep Note</li><li>One-Page Session Plan</li><li>Source Basis</li></ol>`)}
      ${mediationReportSection('Neutral Case Summary', `<p>${esc(mediationDisplayValue(result.client_or_team_summary))}</p>${mediationReportRows(result.case_snapshot || {})}`)}
      ${mediationReportSection('Factual Chronology', mediationReportList(result.chronology || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(mediationDisplayValue(item.description))}</span></div>`))}
      ${mediationReportSection('Key Legal, Factual, Commercial, and Emotional Issues', mediationReportList(result.issues || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(mediationDisplayValue(item.category || 'Unclassified'))}: ${esc(mediationDisplayValue(item.summary || item.missing_proof || item.emotional_or_commercial_dimension || 'Requires review'))}</span></div>`))}
      ${mediationReportSection('Party Positions vs Underlying Interests', mediationReportList(result.positions_and_interests || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.party || 'Party'))}</strong>${mediationReportRows({stated_positions: item.stated_positions, possible_underlying_interests: item.possible_underlying_interests, emotional_drivers: item.emotional_drivers, commercial_drivers: item.commercial_drivers, inference_caveats: item.inference_caveats})}</div>`), 'No party interest analysis returned.')}
      ${mediationReportSection('BATNA / WATNA / Possible ZOPA', mediationReportRows(result.batna_watna_zopa || {}), {pageBreak: true})}
      ${mediationReportSection('Strengths, Weaknesses, and Uncertainty Points', mediationReportList(result.risks_and_gaps || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.risk_level || 'Risk'))}</strong><span>${esc(mediationDisplayValue(item.summary || item.decision_point || item.leverage))}</span></div>`))}
      ${mediationReportSection('Risk Allocation Between Parties', mediationReportList(result.risk_allocation || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.risk || 'Risk'))}</strong>${mediationReportRows({allocation: item.allocation, affected_parties: item.affected_parties, rationale: item.rationale, uncertainty: item.uncertainty, mediator_note: item.mediator_note})}</div>`))}
      ${mediationReportSection('Settlement Levers', mediationReportList(result.settlement_levers || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.lever || 'Lever'))}</strong>${mediationReportRows({why_it_may_matter: item.why_it_may_matter, possible_shapes: item.possible_shapes, parties_affected: item.parties_affected, caveats: item.caveats})}</div>`))}
      ${mediationReportSection('Information Gaps to Clarify', mediationReportList(result.discovery_analysis || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.item_type || 'Information gap'))}</strong><span>${esc(mediationDisplayValue(item.description || item.status || 'Requires review'))}</span></div>`))}
      ${mediationReportSection('Suggested Caucus Questions', mediationReportList(result.caucus_questions || result.cross_examination || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.party || item.witness || 'Party'))}</strong><span>${esc(mediationDisplayValue(item.question || item.questions || item.topics))}</span><p class="muted">${esc(mediationDisplayValue(item.purpose || item.caveats || ''))}</p></div>`, 'No caucus questions returned.'), {pageBreak: true})}
      ${mediationReportSection('Likely Impasse Points', mediationReportList(result.impasse_points || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.issue || 'Impasse point'))}</strong>${mediationReportRows({why_it_may_block_settlement: item.why_it_may_block_settlement, early_warning_signs: item.early_warning_signs, mediator_options: item.mediator_options})}</div>`))}
      ${mediationReportSection('Possible Bridge Proposals', mediationReportList(result.bridge_proposals || [], item => `<div class="item"><strong>${esc(mediationDisplayValue(item.label || 'Bridge proposal'))}</strong>${mediationReportRows({structure: item.structure, parties_helped: item.parties_helped, tradeoffs: item.tradeoffs, prerequisites: item.prerequisites, risks: item.risks, neutrality_caveat: item.neutrality_caveat})}</div>`))}
      ${mediationReportSection('Mediator Private Prep Note', mediationReportRows(result.mediator_private_prep_note || {}), {pageBreak: true})}
      ${mediationReportSection('One-Page Session Plan', mediationReportRows(result.one_page_session_plan || {}))}
      ${mediationReportSection('Source Basis and Audit Notes', `<h3>Warnings</h3>${renderTranslationList(warnings, 'No warnings returned.')}<h3>Sources</h3>${renderTranslationList(sources.map(mediationSourceLabel), 'No source documents returned.')}<h3>Agent Trace</h3>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}`, {pageBreak: true})}
      <footer>Private mediator preparation report. Generated from indexed matter documents. Verify all source references, assumptions, authority, and confidentiality constraints before use.</footer>
    </article>`;
  if (!standalone) return body;
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(result.title || 'Mediator Prep Report')}</title>${mediationReportStyles()}</head><body>${body}</body></html>`;
}

function renderMediationPrepResult() {
  const result = App.mediationPrep.result;
  const grid = document.getElementById('mediation-prep-result-grid');
  const preview = document.getElementById('mediation-prep-preview');
  const meta = document.getElementById('mediation-prep-result-meta');
  const side = document.getElementById('mediation-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${config.party_role || 'neutral mediator'}${config.court ? ' · ' + config.court : ''}${config.jurisdiction ? ' · ' + config.jurisdiction : ''}`;
  preview.innerHTML = sanitizeDraftHtml(mediationReportStyles() + mediationPrepReportHtml(result, false));
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(mediationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function mediationPrepMarkdown(result = App.mediationPrep.result) {
  if (!result) return '';
  const section = (title, value) => {
    if (Array.isArray(value)) return `## ${title}\n${value.length ? value.map(item => `- ${mediationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
    return `## ${title}\n${mediationDisplayValue(value)}\n\n`;
  };
  return `# ${result.title || 'Mediator Prep Report'}\n\nPrivate mediator preparation. This does not decide the dispute, predict the outcome, or replace mediator judgment.\n\n## Neutral Case Summary\n${mediationDisplayValue(result.client_or_team_summary)}\n\n${section('Factual Chronology', result.chronology)}${section('Key Issues', result.issues)}${section('Party Positions vs Underlying Interests', result.positions_and_interests)}${section('BATNA / WATNA / Possible ZOPA', result.batna_watna_zopa)}${section('Strengths, Weaknesses, and Uncertainties', result.risks_and_gaps)}${section('Risk Allocation', result.risk_allocation)}${section('Settlement Levers', result.settlement_levers)}${section('Information Gaps', result.discovery_analysis)}${section('Caucus Questions', result.caucus_questions || result.cross_examination)}${section('Likely Impasse Points', result.impasse_points)}${section('Bridge Proposals', result.bridge_proposals)}${section('Mediator Private Prep Note', result.mediator_private_prep_note)}${section('One-Page Session Plan', result.one_page_session_plan)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
}

async function copyMediationPrep() {
  const text = mediationPrepMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Mediation prep copied.');
}

function downloadMediationPrep() {
  const text = mediationPrepMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `mediation-prep-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function mediationPrepHtmlFilename() {
  const title = (App.mediationPrep.result?.title || 'mediator-prep-report').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'mediator-prep-report';
  return `${title}-${Date.now()}.html`;
}

function downloadMediationPrepHtml() {
  const html = mediationPrepReportHtml(App.mediationPrep.result, true);
  if (!html) return;
  const blob = new Blob([html], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = mediationPrepHtmlFilename();
  a.click();
  URL.revokeObjectURL(a.href);
}

function printMediationPrepReport() {
  const html = mediationPrepReportHtml(App.mediationPrep.result, true);
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

function resetMediationPrep() {
  App.mediationPrep.result = null;
  ['mediation-prep-title', 'mediation-prep-court', 'mediation-prep-jurisdiction', 'mediation-prep-venue', 'mediation-prep-stage', 'mediation-prep-dates', 'mediation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('mediation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
