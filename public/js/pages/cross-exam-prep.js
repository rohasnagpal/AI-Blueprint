// ── CROSS-EXAMINATION PREP ────────────────────────────────────────────────
function crossExamPrepWorkspaceId() {
  const selectValue = document.getElementById('cross-exam-prep-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedCrossExamPrepMatterId() {
  const value = document.getElementById('cross-exam-prep-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(crossExamPrepWorkspaceId())[0]?.id || null;
}

async function renderCrossExamPrep() {
  if (!App.v2.user && typeof initV2 === 'function') {
    await initV2().catch(() => {});
  }
  renderCrossExamPrepScopeSelector();
  await syncCrossExamPrepScope();
  renderCrossExamPrepScopeSelector();
  renderCrossExamPrepDocumentSummary();
  await loadCrossExamPrepHistory();
}

async function syncCrossExamPrepScope(options = {}) {
  const matterSelect = document.getElementById('cross-exam-prep-matter-select');
  await syncV2WorkspaceMatterDocuments(crossExamPrepWorkspaceId(), matterSelect?.value || '', matterSelect, options);
}

function renderCrossExamPrepScopeSelector() {
  const workspaceSelect = document.getElementById('cross-exam-prep-workspace-select');
  const matterSelect = document.getElementById('cross-exam-prep-matter-select');
  const card = document.getElementById('cross-exam-prep-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = crossExamPrepWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderCrossExamPrepScopeSelector).catch(() => {});
}

async function onCrossExamPrepWorkspaceChange() {
  const matterSelect = document.getElementById('cross-exam-prep-matter-select');
  if (matterSelect) matterSelect.value = '';
  await syncCrossExamPrepScope({resetMatter: true});
  renderCrossExamPrepScopeSelector();
  renderCrossExamPrepDocumentSummary();
  await loadCrossExamPrepHistory();
}

async function onCrossExamPrepMatterChange() {
  await syncCrossExamPrepScope();
  renderCrossExamPrepDocumentSummary();
}

function crossExamPrepDocumentIds() {
  const selectedMatter = selectedCrossExamPrepMatterId();
  return (App.v2.documents || [])
    .filter(doc => (!doc.status || doc.status === 'indexed') && doc.matter_id === selectedMatter)
    .map(doc => doc.id)
    .filter(Boolean);
}

function renderCrossExamPrepDocumentSummary() {
  const summary = document.getElementById('cross-exam-prep-doc-summary');
  if (!summary) return;
  const count = crossExamPrepDocumentIds().length;
  summary.textContent = count
    ? `${count} indexed matter document${count === 1 ? '' : 's'} will be read automatically.`
    : 'No indexed documents found for this matter.';
}

function collectCrossExamPrepPayload() {
  const workspaceId = crossExamPrepWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const matterId = selectedCrossExamPrepMatterId();
  if (!matterId) throw new Error('Choose a matter first.');
  const documentIds = crossExamPrepDocumentIds();
  if (!documentIds.length) throw new Error('Add and index matter documents before preparing cross-examination.');
  const witness = document.getElementById('cross-exam-prep-witness')?.value.trim() || '';
  if (!witness) throw new Error('Enter the witness to cross-examine.');
  const objective = document.getElementById('cross-exam-prep-objective')?.value || 'Prepare full cross';
  const side = document.getElementById('cross-exam-prep-side')?.value || 'defence / accused';
  const risk = document.getElementById('cross-exam-prep-risk')?.value || 'balanced';
  const language = document.getElementById('cross-exam-prep-language')?.value || 'English';
  const redLines = document.getElementById('cross-exam-prep-red-lines')?.value.trim() || '';
  const focus = document.getElementById('cross-exam-prep-focus')?.value.trim() || '';
  return {
    workspaceId,
    payload: {
      title: `Cross-Examination Prep: ${witness}`,
      matter_id: matterId,
      document_ids: documentIds,
      party_role: side,
      court: null,
      jurisdiction: null,
      venue: null,
      procedural_stage: 'trial prep',
      hearing_dates: [],
      litigation_focus: 'trial prep',
      workflow_mode: 'cross_exam_prep',
      target_witness: witness,
      cross_objective: objective,
      risk_level: risk,
      output_language: language,
      red_lines: redLines || null,
      focus_notes: focus || null,
    },
  };
}

async function loadCrossExamPrepHistory() {
  const workspaceId = crossExamPrepWorkspaceId();
  const card = document.getElementById('cross-exam-prep-history-card');
  const list = document.getElementById('cross-exam-prep-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs?page_size=8&workflow_mode=cross_exam_prep`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.crossExamPrep.history = (data.items || []).slice(0, 8);
    card.style.display = App.crossExamPrep.history.length ? 'block' : 'none';
    list.innerHTML = App.crossExamPrep.history.map(run => `<div class="council-row cross-exam-history-row">
      <div class="council-row-head cross-exam-history-row-head">
        <div>
          <div class="council-card-title">${esc(run.title || 'Cross-examination prep')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions cross-exam-history-actions">
        <button class="btn-secondary" type="button" onclick="openCrossExamPrepRun('${esc(run.id)}')">Open</button>
        <button class="btn-secondary danger" type="button" onclick="deleteCrossExamPrepRun('${esc(run.id)}', '${esc(run.title || 'Cross-examination prep')}')">Delete</button>
      </div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openCrossExamPrepRun(runId) {
  const workspaceId = crossExamPrepWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.crossExamPrep.result = await r.json();
    renderCrossExamPrepResult();
    showToast('Cross-examination prep loaded.');
  } catch(e) {
    showToast('Failed to load cross-examination prep: ' + e.message, 'error');
  }
}

async function deleteCrossExamPrepRun(runId, title) {
  const workspaceId = crossExamPrepWorkspaceId();
  if (!workspaceId || !runId) return;
  if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.crossExamPrep.result?.id === runId) {
      App.crossExamPrep.result = null;
      const grid = document.getElementById('cross-exam-prep-result-grid');
      if (grid) grid.style.display = 'none';
    }
    await loadCrossExamPrepHistory();
    showToast('Cross-examination prep deleted.');
  } catch(e) {
    showToast('Failed to delete cross-examination prep: ' + e.message, 'error');
  }
}

async function runCrossExamPrep() {
  if (App.crossExamPrep.isRunning) return;
  const btn = document.getElementById('cross-exam-prep-run-btn');
  const status = document.getElementById('cross-exam-prep-status');
  try {
    const {workspaceId, payload} = collectCrossExamPrepPayload();
    App.crossExamPrep.isRunning = true;
    App.crossExamPrep.result = null;
    App.crossExamPrep.events = [];
    renderCrossExamPrepProgressList();
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Queuing cross prep...';
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startCrossExamPrepJobStream(workspaceId, data.job);
      showToast('Cross-examination prep queued.');
      return;
    }
    App.crossExamPrep.result = data;
    renderCrossExamPrepResult();
    showToast('Cross-examination prep complete.');
  } catch(e) {
    showToast('Cross-examination prep failed: ' + e.message, 'error');
    App.crossExamPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  } finally {
    if (App.crossExamPrep.job) return;
    App.crossExamPrep.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function stopCrossExamPrepStream() {
  App.crossExamPrep.stream?.close();
  App.crossExamPrep.stream = null;
}

function renderCrossExamPrepProgress() {
  const status = document.getElementById('cross-exam-prep-status');
  const job = App.crossExamPrep.job;
  if (!status || !job) return;
  const latest = [...(App.crossExamPrep.events || [])].reverse().find(e => e.content)?.content || job.status || 'running';
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  status.textContent = `${latest} · ${progress}%`;
  renderCrossExamPrepProgressList();
}

function renderCrossExamPrepProgressList() {
  const card = document.getElementById('cross-exam-prep-progress-card');
  const list = document.getElementById('cross-exam-prep-progress-list');
  if (!card || !list) return;
  const events = App.crossExamPrep.events || [];
  card.style.display = events.length || App.crossExamPrep.isRunning ? 'block' : 'none';
  list.innerHTML = events.length
    ? events.slice(-10).map(event => {
        const progress = event.metadata?.progress;
        return `<div class="translate-review-section"><strong>${esc(event.content || event.type || 'Progress')}</strong><p>${progress !== undefined ? esc(progress + '%') : esc(event.type || '')}</p></div>`;
      }).join('')
    : '<div class="translate-review-section"><strong>Starting</strong><p>Preparing the cross-examination run.</p></div>';
}

async function loadCrossExamPrepResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/litigation-prep/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.crossExamPrep.result = await r.json();
  renderCrossExamPrepResult();
  return true;
}

function startCrossExamPrepJobStream(workspaceId, job, attempt = 0) {
  stopCrossExamPrepStream();
  App.crossExamPrep.job = job;
  if (!attempt) App.crossExamPrep.events = [{type:'status', content:'Cross-examination prep queued', metadata:{progress:0}}];
  renderCrossExamPrepProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.crossExamPrep.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.crossExamPrep.job = data.metadata;
    if (data.metadata?.progress !== undefined && App.crossExamPrep.job) App.crossExamPrep.job.progress = data.metadata.progress;
    if (data.type && data.type !== 'status') App.crossExamPrep.events.push(data);
    App.crossExamPrep.events = App.crossExamPrep.events.slice(-24);
    renderCrossExamPrepProgress();
    if (data.type === 'done') {
      stopCrossExamPrepStream();
      App.crossExamPrep.job = data.metadata || App.crossExamPrep.job;
      try {
        if (data.content === 'completed') {
          await loadCrossExamPrepResultFromJob(workspaceId, App.crossExamPrep.job);
          await loadCrossExamPrepHistory();
          showToast('Cross-examination prep complete.');
        } else {
          showToast('Cross-examination prep ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Prep completed but result load failed: ' + e.message, 'error');
      } finally {
        App.crossExamPrep.isRunning = false;
        App.crossExamPrep.job = null;
        const btn = document.getElementById('cross-exam-prep-run-btn');
        const status = document.getElementById('cross-exam-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      }
    }
  };
  source.onerror = () => {
    stopCrossExamPrepStream();
    if (App.crossExamPrep.isRunning && attempt < 4) {
      const delay = Math.min(8000, 1000 * Math.pow(2, attempt));
      App.crossExamPrep.events.push({type:'progress', content:`Event stream disconnected. Reconnecting in ${Math.round(delay / 1000)}s`, metadata:{progress:App.crossExamPrep.job?.progress || 0}});
      renderCrossExamPrepProgress();
      setTimeout(() => {
        if (App.crossExamPrep.isRunning && App.crossExamPrep.job?.id === job.id) startCrossExamPrepJobStream(workspaceId, App.crossExamPrep.job, attempt + 1);
      }, delay);
      return;
    }
    loadCrossExamPrepResultFromJob(workspaceId, App.crossExamPrep.job || job)
      .then(found => {
        if (found) showToast('Cross-examination prep loaded after stream disconnect.', 'warning');
      })
      .catch(() => showToast('Cross-examination prep event stream disconnected.', 'error'))
      .finally(() => {
        App.crossExamPrep.isRunning = false;
        App.crossExamPrep.job = null;
        const btn = document.getElementById('cross-exam-prep-run-btn');
        const status = document.getElementById('cross-exam-prep-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
      });
  };
}

function crossExamDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(crossExamDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'description', 'title', 'theme', 'name', 'question', 'purpose', 'excerpt']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return crossExamDisplayValue(value[key]);
    }
    return Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '').map(([key, item]) => `${key.replace(/_/g, ' ')}: ${crossExamDisplayValue(item)}`).join('; ');
  }
  return String(value);
}

function crossExamList(items) {
  const list = Array.isArray(items) ? items.filter(item => item !== null && item !== undefined && String(crossExamDisplayValue(item)).trim()) : [];
  return list.length ? `<ul>${list.map(item => `<li>${esc(crossExamDisplayValue(item))}</li>`).join('')}</ul>` : '<p>Not found.</p>';
}

function crossExamPlan(result = App.crossExamPrep.result) {
  return result?.agentic_review?.cross_exam_plan || null;
}

function isLegacyCrossExamResult(result = App.crossExamPrep.result) {
  return !!result && String(result.title || '').startsWith('Cross-Examination Prep:') && !crossExamPlan(result);
}

function crossExamSourceLabel(source) {
  if (!source || typeof source !== 'object') return crossExamDisplayValue(source);
  const rawChunk = source.chunk !== undefined && source.chunk !== null ? Number(source.chunk) : Number(source.chunk_index || 0) + 1;
  const chunk = Number.isFinite(rawChunk) ? Math.max(1, rawChunk) : null;
  return `${source.filename || 'Source'}${chunk ? ' · chunk ' + chunk : ''}`;
}

function crossExamSourceDocumentLabel(source) {
  const label = crossExamSourceLabel(source);
  return label.replace(/\s+·\s+chunk\s+\d+$/i, '');
}

function crossExamKeySources(result, plan) {
  const fullSources = result.sources || [];
  const referenced = [];
  (plan.cross_tree || []).forEach(item => {
    if (item?.document_to_confront) referenced.push(item.document_to_confront);
  });
  (plan.contradiction_bundles || []).forEach(item => {
    if (item?.source_1) referenced.push(item.source_1);
    if (item?.source_2) referenced.push(item.source_2);
  });
  const cleaned = referenced
    .map(item => String(item || '').trim())
    .filter(item => item && item !== 'Not found' && item !== 'Relevant source document' && item !== 'Prior statement');
  const sourceDocs = fullSources.map(crossExamSourceDocumentLabel).filter(Boolean);
  return [...new Set([...cleaned, ...sourceDocs.slice(0, 5)])].slice(0, 8);
}

function renderCrossExamSection(title, items, emptyText) {
  const list = Array.isArray(items) ? items : (items ? [items] : []);
  return `<section><h2>${esc(title)}</h2>${list.length ? list.map(item => `<div class="contract-finding-item"><span>${esc(crossExamDisplayValue(item))}</span></div>`).join('') : `<p>${esc(emptyText || 'No supported items returned.')}</p>`}</section>`;
}

function renderCrossExamTree(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return '<p>No cross-examination tree returned.</p>';
  return `<div class="md-table-wrap"><table class="md-table"><thead><tr><th>Question</th><th>Purpose</th><th>Evasion / Denial</th><th>Confront</th><th>Stop</th></tr></thead><tbody>${rows.map(item => `<tr><td>${esc(item.question || '')}</td><td>${esc(item.purpose || '')}</td><td>${esc([item.if_evasive, item.if_denied].filter(Boolean).join(' / '))}</td><td>${esc(item.document_to_confront || '')}</td><td>${esc(item.stop_or_continue || '')}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderCrossExamBundles(items) {
  const rows = Array.isArray(items) ? items : [];
  if (!rows.length) return '<p>No contradiction bundles returned.</p>';
  return rows.map(item => {
    const questions = Array.isArray(item.questions) ? item.questions.filter(Boolean) : [];
    return `<div class="contract-finding-item">
      <strong>${esc(item.contradiction || 'Contradiction')}</strong>
      <p>${esc(item.why_it_matters || '')}</p>
      <p><strong>Sources:</strong> ${esc([item.source_1, item.source_2].filter(Boolean).join(' / ') || 'Not found')}</p>
      ${questions.length ? `<ol>${questions.map(q => `<li>${esc(q)}</li>`).join('')}</ol>` : ''}
    </div>`;
  }).join('');
}

function crossExamBundleMarkdown(item) {
  const questions = Array.isArray(item?.questions) ? item.questions.filter(Boolean) : [];
  return [
    `- ${crossExamDisplayValue(item?.contradiction || 'Contradiction')}`,
    item?.why_it_matters ? `  Why it matters: ${crossExamDisplayValue(item.why_it_matters)}` : '',
    item?.source_1 || item?.source_2 ? `  Sources: ${[item.source_1, item.source_2].filter(Boolean).map(crossExamDisplayValue).join(' / ')}` : '',
    ...questions.map(q => `  Question: ${crossExamDisplayValue(q)}`),
  ].filter(Boolean).join('\n');
}

function renderCrossExamPlan(plan) {
  return `
    <section><h2>Witness Role</h2><p>${esc(plan.witness_role || 'Not found.')}</p></section>
    <section><h2>Objective</h2><p>${esc(plan.objective || 'Prepare full cross')}</p></section>
    <section><h2>Opponent Uses This Witness To Prove</h2><p>${esc(plan.opponent_uses_witness_to_prove || 'Not found.')}</p></section>
    <section><h2>Do Not Contest</h2>${crossExamList(plan.do_not_contest)}</section>
    <section><h2>Contest</h2>${crossExamList(plan.contest)}</section>
    <section><h2>Core Attack</h2><p>${esc(plan.core_attack || 'Not found.')}</p></section>
    <section><h2>Admissions To Obtain</h2>${crossExamList(plan.admissions_to_obtain)}</section>
    <section><h2>Contradiction Bundles</h2>${renderCrossExamBundles(plan.contradiction_bundles)}</section>
    <section><h2>Cross-Examination Tree</h2>${renderCrossExamTree(plan.cross_tree)}</section>
    <section><h2>Questions To Avoid</h2>${crossExamList((plan.questions_to_avoid || []).map(item => `${item.question_or_area || ''}: ${item.reason || ''}${item.better ? ' Better: ' + item.better : ''}`))}</section>
    <section><h2>Likely Judge Questions</h2>${crossExamList((plan.judge_questions || []).map(item => `${item.question || ''} Best answer: ${item.best_answer || ''}`))}</section>
    <section><h2>Opponent Repair</h2>${crossExamList((plan.opponent_repair || []).map(item => `${item.repair || ''} Counter: ${item.counter || ''}`))}</section>
    <section><h2>Closing Use</h2><p>${esc(plan.closing_use || 'Not found.')}</p></section>
    <section><h2>Missing Material</h2>${crossExamList(plan.missing_material)}</section>
  `;
}

function renderCrossExamPrepResult() {
  const result = App.crossExamPrep.result;
  const grid = document.getElementById('cross-exam-prep-result-grid');
  const preview = document.getElementById('cross-exam-prep-preview');
  const meta = document.getElementById('cross-exam-prep-result-meta');
  const side = document.getElementById('cross-exam-prep-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const config = result.config || {};
  if (meta) meta.textContent = `${result.title || 'Cross-examination prep'}${config.litigation_focus ? ' · ' + config.litigation_focus : ''}`;
  const plan = crossExamPlan(result);
  if (isLegacyCrossExamResult(result)) {
    const html = `
      <article class="draft-document">
        <h1>${esc(result.title || 'Cross-Examination Prep')}</h1>
        <section><h2>Legacy Run</h2>
          <p>This run was created by the old generic litigation-prep workflow, not the dedicated cross-examination workflow. Re-run this witness after restarting the app server to generate the specialized cross plan.</p>
        </section>
      </article>
    `;
    preview.innerHTML = typeof sanitizeDraftHtml === 'function' ? sanitizeDraftHtml(html) : html;
    side.innerHTML = `
      <div class="translate-review-section"><strong>What happened</strong><p>The result has no dedicated cross-exam plan payload.</p></div>
      <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    `;
    return;
  }
  if (plan) {
    const html = `
      <article class="draft-document">
        <h1>${esc(result.title || 'Cross-Examination Prep')}</h1>
        <section><h2>Strategy Summary</h2><p>${esc(plan.strategy_summary || result.client_or_team_summary || '')}</p></section>
        ${renderCrossExamPlan(plan)}
      </article>
    `;
    preview.innerHTML = typeof sanitizeDraftHtml === 'function' ? sanitizeDraftHtml(html) : html;
    side.innerHTML = `
      <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
      <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
      <div class="translate-review-section"><strong>Key Sources</strong>${renderTranslationList(crossExamKeySources(result, plan), 'No key source documents returned.')}<p>${esc((result.sources || []).length)} indexed chunks were available for audit.</p></div>
    `;
    return;
  }
  const crossItems = result.cross_examination || [];
  const witnessItems = result.witness_prep || [];
  const depositionItems = result.deposition_prep || [];
  const riskItems = result.risks_and_gaps || [];
  const html = `
    <article class="draft-document">
      <h1>${esc(result.title || 'Cross-Examination Prep')}</h1>
      <section><h2>Strategy Summary</h2><p>${esc(crossExamDisplayValue(result.client_or_team_summary))}</p></section>
      ${renderCrossExamSection('Witness Role and Objective', witnessItems, 'No witness-specific role returned.')}
      ${renderCrossExamSection('Contradictions and Evidence Attacks', [...(result.evidence_matrix || []), ...(result.issues || [])], 'No contradictions or evidence attacks returned.')}
      ${renderCrossExamSection('Cross-Examination Tree', crossItems, 'No cross-examination tree returned.')}
      ${renderCrossExamSection('Question Lines and Follow-Ups', depositionItems, 'No follow-up questions returned.')}
      ${renderCrossExamSection('Questions to Avoid / Risk Filter', riskItems, 'No risk filter returned.')}
      <section><h2>Judge Concerns</h2><p>${esc(crossExamDisplayValue(result.trial_prep))}</p></section>
      <section><h2>Opponent Repair and Closing Use</h2><p>${esc(crossExamDisplayValue(result.argument_strategy))}</p></section>
    </article>
  `;
  preview.innerHTML = typeof sanitizeDraftHtml === 'function' ? sanitizeDraftHtml(html) : html;
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Agent Trace</strong>${renderTranslationList((result.agentic_review?.agent_trace || []).map(step => `${step.step_name || 'agent'}: ${step.status || 'unknown'}`), 'No agent trace returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(crossExamSourceLabel), 'No source documents returned.')}</div>
  `;
}

function crossExamPrepMarkdown(result = App.crossExamPrep.result) {
  if (!result) return '';
  const plan = crossExamPlan(result);
  if (isLegacyCrossExamResult(result)) {
    return `# ${result.title || 'Cross-Examination Prep'}\n\nThis is a legacy run created by the old generic litigation-prep workflow. Re-run the witness after restarting the app server to generate the dedicated cross-examination plan.\n`;
  }
  if (plan) {
    const lines = [
      `# ${result.title || 'Cross-Examination Prep'}`,
      '',
      `## Strategy Summary\n${plan.strategy_summary || result.client_or_team_summary || ''}`,
      `## Witness Role\n${plan.witness_role || ''}`,
      `## Objective\n${plan.objective || ''}`,
      `## Opponent Uses This Witness To Prove\n${plan.opponent_uses_witness_to_prove || ''}`,
      `## Do Not Contest\n${(plan.do_not_contest || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Contest\n${(plan.contest || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Core Attack\n${plan.core_attack || ''}`,
      `## Admissions To Obtain\n${(plan.admissions_to_obtain || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Contradiction Bundles\n${(plan.contradiction_bundles || []).map(crossExamBundleMarkdown).join('\n')}`,
      `## Cross-Examination Tree\n${(plan.cross_tree || []).map(item => `- Q: ${item.question || ''}\n  Purpose: ${item.purpose || ''}\n  Expected: ${item.expected_answer || ''}\n  If evasive: ${item.if_evasive || ''}\n  If denied: ${item.if_denied || ''}\n  Confront: ${item.document_to_confront || ''}\n  Stop/continue: ${item.stop_or_continue || ''}`).join('\n')}`,
      `## Questions To Avoid\n${(plan.questions_to_avoid || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Likely Judge Questions\n${(plan.judge_questions || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Opponent Repair\n${(plan.opponent_repair || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Closing Use\n${plan.closing_use || ''}`,
      `## Missing Material\n${(plan.missing_material || []).map(item => `- ${crossExamDisplayValue(item)}`).join('\n')}`,
      `## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}`,
    ];
    return lines.join('\n\n');
  }
  const section = (title, items) => {
    const list = Array.isArray(items) ? items : (items ? [items] : []);
    return `## ${title}\n${list.length ? list.map(item => `- ${crossExamDisplayValue(item)}`).join('\n') : 'No supported items returned.'}\n\n`;
  };
  return `# ${result.title || 'Cross-Examination Prep'}\n\n## Strategy Summary\n${crossExamDisplayValue(result.client_or_team_summary)}\n\n${section('Witness Role and Objective', result.witness_prep)}${section('Contradictions and Evidence Attacks', [...(result.evidence_matrix || []), ...(result.issues || [])])}${section('Cross-Examination Tree', result.cross_examination)}${section('Question Lines and Follow-Ups', result.deposition_prep)}${section('Questions to Avoid / Risk Filter', result.risks_and_gaps)}## Judge Concerns\n${crossExamDisplayValue(result.trial_prep)}\n\n## Opponent Repair and Closing Use\n${crossExamDisplayValue(result.argument_strategy)}\n\n## Warnings\n${(result.warnings || []).map(item => `- ${item}`).join('\n')}\n`;
}

async function copyCrossExamPrep() {
  const text = crossExamPrepMarkdown();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      fallbackCopyCrossExamText(text);
    }
    showToast('Cross-examination prep copied.');
  } catch(e) {
    try {
      fallbackCopyCrossExamText(text);
      showToast('Cross-examination prep copied.');
    } catch(_fallbackError) {
      showToast('Copy failed. Use Download Markdown instead.', 'error');
    }
  }
}

function fallbackCopyCrossExamText(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '0';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  const ok = document.execCommand('copy');
  textarea.remove();
  if (!ok) throw new Error('Fallback copy failed');
}

function downloadCrossExamPrep() {
  const text = crossExamPrepMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `cross-exam-prep-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function printCrossExamPrep() {
  if (!App.crossExamPrep.result) return;
  window.print();
}

function resetCrossExamPrep() {
  App.crossExamPrep.result = null;
  App.crossExamPrep.events = [];
  App.crossExamPrep.job = null;
  App.crossExamPrep.isRunning = false;
  stopCrossExamPrepStream();
  ['cross-exam-prep-witness', 'cross-exam-prep-red-lines', 'cross-exam-prep-focus'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const objective = document.getElementById('cross-exam-prep-objective');
  if (objective) objective.value = 'Prepare full cross';
  const side = document.getElementById('cross-exam-prep-side');
  if (side) side.value = 'defence / accused';
  const risk = document.getElementById('cross-exam-prep-risk');
  if (risk) risk.value = 'balanced';
  const language = document.getElementById('cross-exam-prep-language');
  if (language) language.value = 'English';
  const grid = document.getElementById('cross-exam-prep-result-grid');
  if (grid) grid.style.display = 'none';
  const status = document.getElementById('cross-exam-prep-status');
  if (status) status.textContent = '';
  const btn = document.getElementById('cross-exam-prep-run-btn');
  if (btn) btn.disabled = false;
  renderCrossExamPrepProgressList();
  showToast('Cross-examination prep cleared.');
}
