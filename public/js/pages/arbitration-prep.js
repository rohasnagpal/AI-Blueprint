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
  renderArbitrationPrepScopeSelector();
  renderArbitrationPrepSourceDocuments();
  await loadArbitrationPrepHistory();
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
  renderArbitrationPrepScopeSelector();
  renderArbitrationPrepSourceDocuments();
  await loadArbitrationPrepHistory();
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
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
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
  const snapshotRows = Object.entries(result.case_snapshot || {}).map(([key, value]) => `<tr><td>${esc(key.replace(/_/g, ' '))}</td><td>${esc(arbitrationDisplayValue(value))}</td></tr>`).join('');
  preview.innerHTML = sanitizeDraftHtml(`
    <article class="draft-document">
      <h1>${esc(result.title || 'Arbitration Prep')}</h1>
      <section><h2>Team Summary</h2><p>${esc(arbitrationDisplayValue(result.client_or_team_summary))}</p></section>
      <section><h2>Case Snapshot</h2><table><tbody>${snapshotRows || '<tr><td>No case snapshot returned.</td></tr>'}</tbody></table></section>
      ${renderArbitrationSection('Issues and Proof Elements', result.issues || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.title || item.issue || 'Issue'))}</strong><span>${esc(arbitrationDisplayValue(item.summary || item.missing_proof || 'Requires review'))}</span></div>`)}
      ${renderArbitrationSection('Chronology', result.chronology || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.date || item.event_date || 'Date not found'))}</strong><span>${esc(arbitrationDisplayValue(item.description))}</span></div>`)}
      ${renderArbitrationSection('Evidence Matrix', result.evidence_matrix || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.issue || 'Issue'))}</strong><span>${esc(arbitrationDisplayValue(item.gaps || item.supporting_evidence || 'Evidence requires review'))}</span></div>`)}
      ${renderArbitrationSection('Witness Prep', result.witness_prep || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.name || 'Witness'))}</strong><span>${esc(arbitrationDisplayValue(item.topics || item.prep_questions || 'Topics require review'))}</span></div>`)}
      ${renderArbitrationSection('Cross-Examination', result.cross_examination || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.witness || 'Witness'))}</strong><span>${esc(arbitrationDisplayValue(item.questions || item.topics || 'Questions require review'))}</span></div>`)}
      ${renderArbitrationSection('Procedural Tasks', result.procedural_tasks || [], item => `<div class="contract-finding-item"><strong>${esc(arbitrationDisplayValue(item.due_date || item.task_type || 'Task'))}</strong><span>${esc(arbitrationDisplayValue(item.description || item.compliance_risk))}</span></div>`)}
      <section><h2>Argument Themes</h2><p>${esc(arbitrationDisplayValue(result.argument_strategy))}</p></section>
      <section><h2>Damages and Remedies</h2><p>${esc(arbitrationDisplayValue(result.damages_and_remedies))}</p></section>
      ${renderArbitrationSection('Risks and Gaps', result.risks_and_gaps || [], item => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(item.risk_level || 'medium')}">${esc(item.risk_level || 'medium')}</span><span>${esc(arbitrationDisplayValue(item.summary || item.decision_point))}</span></div>`)}
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(arbitrationSourceLabel), 'No source documents returned.')}</div>
  `;
}

function arbitrationPrepMarkdown(result = App.arbitrationPrep.result) {
  if (!result) return '';
  const section = (title, items) => `## ${title}\n${items && items.length ? items.map(item => `- ${arbitrationDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
  return `# ${result.title || 'Arbitration Prep'}\n\n## Team Summary\n${arbitrationDisplayValue(result.client_or_team_summary)}\n\n${section('Issues', result.issues)}${section('Chronology', result.chronology)}${section('Evidence Matrix', result.evidence_matrix)}${section('Witness Prep', result.witness_prep)}${section('Cross-Examination', result.cross_examination)}${section('Procedural Tasks', result.procedural_tasks)}## Argument Strategy\n${arbitrationDisplayValue(result.argument_strategy)}\n\n## Damages and Remedies\n${arbitrationDisplayValue(result.damages_and_remedies)}\n\n${section('Risks and Gaps', result.risks_and_gaps)}## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
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

function resetArbitrationPrep() {
  App.arbitrationPrep.result = null;
  ['arbitration-prep-title', 'arbitration-prep-seat', 'arbitration-prep-stage', 'arbitration-prep-dates', 'arbitration-prep-instructions'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const grid = document.getElementById('arbitration-prep-result-grid');
  if (grid) grid.style.display = 'none';
}
