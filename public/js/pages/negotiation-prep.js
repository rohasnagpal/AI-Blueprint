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
  renderNegotiationPrepScopeSelector();
  renderNegotiationPrepSourceDocuments();
  await loadNegotiationPrepHistory();
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
  renderNegotiationPrepScopeSelector();
  renderNegotiationPrepSourceDocuments();
  await loadNegotiationPrepHistory();
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
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
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
    list.innerHTML = App.negotiationPrep.history.map(run => `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Negotiation prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.court ? ' · ' + esc(run.court) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions"><button class="btn-secondary" type="button" onclick="openNegotiationPrepRun('${esc(run.id)}')">Open</button></div>
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
  const snapshotRows = Object.entries(result.case_snapshot || {}).map(([key, value]) => `<tr><td>${esc(key.replace(/_/g, ' '))}</td><td>${esc(negotiationDisplayValue(value))}</td></tr>`).join('');
  preview.innerHTML = sanitizeDraftHtml(`
    <article class="draft-document">
      <h1>${esc(result.title || 'Negotiation Prep')}</h1>
      <section><h2>Team Summary</h2><p>${esc(negotiationDisplayValue(result.client_or_team_summary))}</p></section>
      <section><h2>Case Snapshot</h2><table><tbody>${snapshotRows || '<tr><td>No case snapshot returned.</td></tr>'}</tbody></table></section>
      ${renderNegotiationSection('Positions and Concessions', result.claims_and_defenses || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.title || item.claim || 'Position'))}</strong><span>${esc(negotiationDisplayValue(item.missing_proof || item.defenses || 'Requires review'))}</span></div>`)}
      ${renderNegotiationSection('Issues and Proof Elements', result.issues || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(negotiationDisplayValue(item.summary || item.missing_proof || 'Requires review'))}</span></div>`)}
      ${renderNegotiationSection('Chronology', result.chronology || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(negotiationDisplayValue(item.description))}</span></div>`)}
      ${renderNegotiationSection('Evidence Matrix', result.evidence_matrix || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.issue || 'Issue'))}</strong><span>${esc(negotiationDisplayValue(item.gaps || item.supporting_evidence || 'Evidence requires review'))}</span></div>`)}
      ${renderNegotiationSection('Information Gaps', result.discovery_analysis || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.item_type || 'Information gap'))}</strong><span>${esc(negotiationDisplayValue(item.description || item.status || 'Requires review'))}</span></div>`)}
      ${renderNegotiationSection('Participant Prep', result.witness_prep || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.name || 'Participant'))}</strong><span>${esc(negotiationDisplayValue(item.topics || item.prep_questions || 'Topics require review'))}</span></div>`)}
      ${renderNegotiationSection('Authority and Caucus Prep', result.deposition_prep || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.witness || 'Participant'))}</strong><span>${esc(negotiationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderNegotiationSection('Reality-Testing Questions', result.cross_examination || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.witness || 'Participant'))}</strong><span>${esc(negotiationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderNegotiationSection('Procedural Tasks', result.procedural_tasks || [], item => `<div class="contract-finding-item"><strong>${esc(negotiationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(negotiationDisplayValue(item.description || item.compliance_risk))}</span></div>`)}
      <section><h2>Mediator Brief Strategy</h2><p>${esc(negotiationDisplayValue(result.motion_strategy))}</p></section>
      <section><h2>Session Plan</h2><p>${esc(negotiationDisplayValue(result.trial_prep))}</p></section>
      <section><h2>Negotiation Themes</h2><p>${esc(negotiationDisplayValue(result.argument_strategy))}</p></section>
      <section><h2>Damages and Remedies</h2><p>${esc(negotiationDisplayValue(result.damages_and_remedies))}</p></section>
      ${renderNegotiationSection('Risks and Gaps', result.risks_and_gaps || [], item => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(item.risk_level || 'medium')}">${esc(item.risk_level || 'medium')}</span><span>${esc(negotiationDisplayValue(item.summary || item.decision_point))}</span></div>`)}
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(negotiationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function negotiationPrepMarkdown(result = App.negotiationPrep.result) {
  if (!result) return '';
  const section = (title, items) => `## ${title}\n${items && items.length ? items.map(item => `- ${negotiationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
  return `# ${result.title || 'Negotiation Prep'}\n\n## Team Summary\n${negotiationDisplayValue(result.client_or_team_summary)}\n\n${section('Positions and Concessions', result.claims_and_defenses)}${section('Issues', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Information Gaps', result.discovery_analysis)}${section('Participant Prep', result.witness_prep)}${section('Authority and Caucus Prep', result.deposition_prep)}${section('Reality-Testing Questions', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}## Mediator Brief Strategy\n${negotiationDisplayValue(result.motion_strategy)}\n\n## Session Plan\n${negotiationDisplayValue(result.trial_prep)}\n\n## Damages and Remedies\n${negotiationDisplayValue(result.damages_and_remedies)}\n\n${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
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

function resetNegotiationPrep() {
  App.negotiationPrep.result = null;
  ['negotiation-prep-title', 'negotiation-prep-court', 'negotiation-prep-jurisdiction', 'negotiation-prep-venue', 'negotiation-prep-stage', 'negotiation-prep-dates', 'negotiation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('negotiation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
