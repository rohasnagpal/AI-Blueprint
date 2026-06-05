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
  renderMediationPrepScopeSelector();
  renderMediationPrepSourceDocuments();
  await loadMediationPrepHistory();
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
  renderMediationPrepScopeSelector();
  renderMediationPrepSourceDocuments();
  await loadMediationPrepHistory();
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
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
}

function collectMediationPrepPayload() {
  const workspaceId = mediationPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const dates = (document.getElementById('mediation-prep-dates')?.value || '').split(',').map(item => item.trim()).filter(Boolean);
  return {
    workspaceId,
    payload: {
      title: document.getElementById('mediation-prep-title')?.value.trim() || 'Mediation Prep',
      matter_id: selectedMediationPrepMatterId(),
      document_ids: selectedMediationPrepDocumentIds(),
      party_role: document.getElementById('mediation-prep-party-role')?.value || 'neutral analysis',
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

function renderMediationPrepResult() {
  const result = App.mediationPrep.result;
  const grid = document.getElementById('mediation-prep-result-grid');
  const preview = document.getElementById('mediation-prep-preview');
  const meta = document.getElementById('mediation-prep-result-meta');
  const side = document.getElementById('mediation-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${config.party_role || 'neutral analysis'}${config.court ? ' · ' + config.court : ''}${config.jurisdiction ? ' · ' + config.jurisdiction : ''}`;
  const snapshotRows = Object.entries(result.case_snapshot || {}).map(([key, value]) => `<tr><td>${esc(key.replace(/_/g, ' '))}</td><td>${esc(mediationDisplayValue(value))}</td></tr>`).join('');
  preview.innerHTML = sanitizeDraftHtml(`
    <article class="draft-document">
      <h1>${esc(result.title || 'Mediation Prep')}</h1>
      <section><h2>Team Summary</h2><p>${esc(mediationDisplayValue(result.client_or_team_summary))}</p></section>
      <section><h2>Case Snapshot</h2><table><tbody>${snapshotRows || '<tr><td>No case snapshot returned.</td></tr>'}</tbody></table></section>
      ${renderMediationSection('Positions and Concessions', result.claims_and_defenses || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.title || item.claim || 'Position'))}</strong><span>${esc(mediationDisplayValue(item.missing_proof || item.defenses || 'Requires review'))}</span></div>`)}
      ${renderMediationSection('Issues and Proof Elements', result.issues || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(mediationDisplayValue(item.summary || item.missing_proof || 'Requires review'))}</span></div>`)}
      ${renderMediationSection('Chronology', result.chronology || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(mediationDisplayValue(item.description))}</span></div>`)}
      ${renderMediationSection('Evidence Matrix', result.evidence_matrix || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.issue || 'Issue'))}</strong><span>${esc(mediationDisplayValue(item.gaps || item.supporting_evidence || 'Evidence requires review'))}</span></div>`)}
      ${renderMediationSection('Information Gaps', result.discovery_analysis || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.item_type || 'Information gap'))}</strong><span>${esc(mediationDisplayValue(item.description || item.status || 'Requires review'))}</span></div>`)}
      ${renderMediationSection('Participant Prep', result.witness_prep || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.name || 'Participant'))}</strong><span>${esc(mediationDisplayValue(item.topics || item.prep_questions || 'Topics require review'))}</span></div>`)}
      ${renderMediationSection('Authority and Caucus Prep', result.deposition_prep || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.witness || 'Participant'))}</strong><span>${esc(mediationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderMediationSection('Reality-Testing Questions', result.cross_examination || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.witness || 'Participant'))}</strong><span>${esc(mediationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderMediationSection('Procedural Tasks', result.procedural_tasks || [], item => `<div class="contract-finding-item"><strong>${esc(mediationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(mediationDisplayValue(item.description || item.compliance_risk))}</span></div>`)}
      <section><h2>Mediator Brief Strategy</h2><p>${esc(mediationDisplayValue(result.motion_strategy))}</p></section>
      <section><h2>Session Plan</h2><p>${esc(mediationDisplayValue(result.trial_prep))}</p></section>
      <section><h2>Negotiation Themes</h2><p>${esc(mediationDisplayValue(result.argument_strategy))}</p></section>
      <section><h2>Damages and Remedies</h2><p>${esc(mediationDisplayValue(result.damages_and_remedies))}</p></section>
      ${renderMediationSection('Risks and Gaps', result.risks_and_gaps || [], item => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(item.risk_level || 'medium')}">${esc(item.risk_level || 'medium')}</span><span>${esc(mediationDisplayValue(item.summary || item.decision_point))}</span></div>`)}
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(mediationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function mediationPrepMarkdown(result = App.mediationPrep.result) {
  if (!result) return '';
  const section = (title, items) => `## ${title}\n${items && items.length ? items.map(item => `- ${mediationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
  return `# ${result.title || 'Mediation Prep'}\n\n## Team Summary\n${mediationDisplayValue(result.client_or_team_summary)}\n\n${section('Positions and Concessions', result.claims_and_defenses)}${section('Issues', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Information Gaps', result.discovery_analysis)}${section('Participant Prep', result.witness_prep)}${section('Authority and Caucus Prep', result.deposition_prep)}${section('Reality-Testing Questions', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}## Mediator Brief Strategy\n${mediationDisplayValue(result.motion_strategy)}\n\n## Session Plan\n${mediationDisplayValue(result.trial_prep)}\n\n## Damages and Remedies\n${mediationDisplayValue(result.damages_and_remedies)}\n\n${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
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

function resetMediationPrep() {
  App.mediationPrep.result = null;
  ['mediation-prep-title', 'mediation-prep-court', 'mediation-prep-jurisdiction', 'mediation-prep-venue', 'mediation-prep-stage', 'mediation-prep-dates', 'mediation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('mediation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
