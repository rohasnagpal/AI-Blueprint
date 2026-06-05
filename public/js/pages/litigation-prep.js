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
  renderLitigationPrepScopeSelector();
  renderLitigationPrepSourceDocuments();
  await loadLitigationPrepHistory();
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
  renderLitigationPrepScopeSelector();
  renderLitigationPrepSourceDocuments();
  await loadLitigationPrepHistory();
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
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
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
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs?page_size=8`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.litigationPrep.history = data.items || [];
    card.style.display = App.litigationPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.litigationPrep.history.map(run => `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Litigation prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.court ? ' · ' + esc(run.court) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions"><button class="btn-secondary" type="button" onclick="openLitigationPrepRun('${esc(run.id)}')">Open</button></div>
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
  const snapshotRows = Object.entries(result.case_snapshot || {}).map(([key, value]) => `<tr><td>${esc(key.replace(/_/g, ' '))}</td><td>${esc(litigationDisplayValue(value))}</td></tr>`).join('');
  preview.innerHTML = sanitizeDraftHtml(`
    <article class="draft-document">
      <h1>${esc(result.title || 'Litigation Prep')}</h1>
      <section><h2>Team Summary</h2><p>${esc(litigationDisplayValue(result.client_or_team_summary))}</p></section>
      <section><h2>Case Snapshot</h2><table><tbody>${snapshotRows || '<tr><td>No case snapshot returned.</td></tr>'}</tbody></table></section>
      ${renderLitigationSection('Claims and Defenses', result.claims_and_defenses || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.title || item.claim || 'Claim or defense'))}</strong><span>${esc(litigationDisplayValue(item.missing_proof || item.defenses || 'Requires review'))}</span></div>`)}
      ${renderLitigationSection('Issues and Proof Elements', result.issues || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(litigationDisplayValue(item.summary || item.missing_proof || 'Requires review'))}</span></div>`)}
      ${renderLitigationSection('Chronology', result.chronology || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(litigationDisplayValue(item.description))}</span></div>`)}
      ${renderLitigationSection('Evidence Matrix', result.evidence_matrix || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.issue || 'Issue'))}</strong><span>${esc(litigationDisplayValue(item.gaps || item.supporting_evidence || 'Evidence requires review'))}</span></div>`)}
      ${renderLitigationSection('Discovery', result.discovery_analysis || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.item_type || 'Discovery'))}</strong><span>${esc(litigationDisplayValue(item.description || item.status || 'Requires review'))}</span></div>`)}
      ${renderLitigationSection('Witness Prep', result.witness_prep || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.name || 'Witness'))}</strong><span>${esc(litigationDisplayValue(item.topics || item.prep_questions || 'Topics require review'))}</span></div>`)}
      ${renderLitigationSection('Depositions', result.deposition_prep || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.witness || 'Witness'))}</strong><span>${esc(litigationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderLitigationSection('Cross-Examination', result.cross_examination || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.witness || 'Witness'))}</strong><span>${esc(litigationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderLitigationSection('Procedural Tasks', result.procedural_tasks || [], item => `<div class="contract-finding-item"><strong>${esc(litigationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(litigationDisplayValue(item.description || item.compliance_risk))}</span></div>`)}
      <section><h2>Motion Strategy</h2><p>${esc(litigationDisplayValue(result.motion_strategy))}</p></section>
      <section><h2>Trial Prep</h2><p>${esc(litigationDisplayValue(result.trial_prep))}</p></section>
      <section><h2>Argument Themes</h2><p>${esc(litigationDisplayValue(result.argument_strategy))}</p></section>
      <section><h2>Damages and Remedies</h2><p>${esc(litigationDisplayValue(result.damages_and_remedies))}</p></section>
      ${renderLitigationSection('Risks and Gaps', result.risks_and_gaps || [], item => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(item.risk_level || 'medium')}">${esc(item.risk_level || 'medium')}</span><span>${esc(litigationDisplayValue(item.summary || item.decision_point))}</span></div>`)}
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(litigationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function litigationPrepMarkdown(result = App.litigationPrep.result) {
  if (!result) return '';
  const section = (title, items) => `## ${title}\n${items && items.length ? items.map(item => `- ${litigationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
  return `# ${result.title || 'Litigation Prep'}\n\n## Team Summary\n${litigationDisplayValue(result.client_or_team_summary)}\n\n${section('Claims and Defenses', result.claims_and_defenses)}${section('Issues', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Discovery', result.discovery_analysis)}${section('Witness Prep', result.witness_prep)}${section('Depositions', result.deposition_prep)}${section('Cross-Examination', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}## Motion Strategy\n${litigationDisplayValue(result.motion_strategy)}\n\n## Trial Prep\n${litigationDisplayValue(result.trial_prep)}\n\n## Damages and Remedies\n${litigationDisplayValue(result.damages_and_remedies)}\n\n${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
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

function resetLitigationPrep() {
  App.litigationPrep.result = null;
  ['litigation-prep-title', 'litigation-prep-court', 'litigation-prep-jurisdiction', 'litigation-prep-venue', 'litigation-prep-stage', 'litigation-prep-dates', 'litigation-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('litigation-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
