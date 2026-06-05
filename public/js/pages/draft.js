// ── DRAFTING ─────────────────────────────────────────────────────────────
function renderDraftScopeSelector() {
  const workspaceSelect = document.getElementById('draft-workspace-select');
  const matterSelect = document.getElementById('draft-matter-select');
  const card = document.getElementById('draft-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    renderDraftSourceDocuments();
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = draftWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderDraftScopeSelector).catch(() => {});
  renderDraftSourceDocuments();
}

function draftWorkspaceId() {
  const selectValue = document.getElementById('draft-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function onDraftWorkspaceChange() {
  const matterSelect = document.getElementById('draft-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderDraftScopeSelector();
  loadDraftHistory();
}

function selectedDraftMatterId() {
  const value = document.getElementById('draft-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(draftWorkspaceId())[0]?.id || null;
}

function renderDraftSourceDocuments() {
  const field = document.getElementById('draft-source-documents-field');
  const select = document.getElementById('draft-source-documents');
  if (!field || !select) return;
  const signedIn = !!(App.v2.enabled && App.v2.user && draftWorkspaceId());
  const selectedWorkspace = draftWorkspaceId();
  const selectedMatter = selectedDraftMatterId();
  if (!signedIn || selectedWorkspace !== App.v2.workspaceId) {
    field.style.display = 'none';
    select.innerHTML = '';
    return;
  }
  const docs = (App.v2.documents || []).filter(doc => {
    if (doc.status && doc.status !== 'indexed') return false;
    return doc.matter_id === selectedMatter;
  });
  if (!docs.length) {
    field.style.display = 'none';
    select.innerHTML = '';
    return;
  }
  field.style.display = 'block';
  select.innerHTML = docs.map(doc => `<option value="${esc(doc.id)}">${esc(doc.original_name || 'Document')}</option>`).join('');
}

function selectedDraftSourceDocumentIds() {
  const select = document.getElementById('draft-source-documents');
  if (!select) return [];
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
}

function collectDraftPayload() {
  const documentType = document.getElementById('draft-document-type')?.value.trim() || '';
  const facts = document.getElementById('draft-facts')?.value.trim() || '';
  if (!documentType) throw new Error('Document type is required.');
  if (!facts) throw new Error('Facts and background are required.');
  const payload = {
    title: document.getElementById('draft-title')?.value.trim() || null,
    document_type: documentType,
    jurisdiction: document.getElementById('draft-jurisdiction')?.value.trim() || null,
    tone: document.getElementById('draft-tone')?.value || 'formal',
    audience: document.getElementById('draft-audience')?.value.trim() || null,
    parties: document.getElementById('draft-parties')?.value.trim() || null,
    facts,
    key_terms: document.getElementById('draft-key-terms')?.value.trim() || null,
    instructions: document.getElementById('draft-instructions')?.value.trim() || null,
    source_document_ids: selectedDraftSourceDocumentIds(),
  };
  if (App.v2.enabled && App.v2.user) payload.matter_id = selectedDraftMatterId();
  return payload;
}

async function runDraft() {
  if (App.drafting.isRunning) return;
  const btn = document.getElementById('draft-run-btn');
  const status = document.getElementById('draft-status');
  try {
    const payload = collectDraftPayload();
    App.drafting.isRunning = true;
    App.drafting.result = null;
    App.drafting.job = null;
    App.drafting.events = [];
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Starting...';
    renderDraftProgress();
    const signedIn = !!(App.v2.enabled && App.v2.user && draftWorkspaceId());
    const url = signedIn
      ? `/api/v2/workspaces/${encodeURIComponent(draftWorkspaceId())}/drafts`
      : '/api/v2/drafts/public';
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (signedIn && data.job) {
      if (status) status.textContent = 'Generating...';
      startDraftJobStream(data.job);
    } else {
      App.drafting.result = data;
      renderDraftResult();
      showToast('Draft generated.');
      App.drafting.isRunning = false;
      if (btn) btn.disabled = false;
      if (status) status.textContent = '';
    }
  } catch(e) {
    showToast('Draft failed: ' + e.message, 'error');
    App.drafting.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
    renderDraftProgress();
  }
}

function sanitizeDraftHtml(htmlText) {
  return sanitizeTranslationHtml(htmlText);
}

function renderDraftResult() {
  const result = App.drafting.result;
  const grid = document.getElementById('draft-result-grid');
  const preview = document.getElementById('draft-html-preview');
  const meta = document.getElementById('draft-result-meta');
  const review = document.getElementById('draft-review-list');
  if (!result || !grid || !preview || !review) return;
  grid.style.display = 'grid';
  preview.innerHTML = sanitizeDraftHtml(result.draft_html || `<p>${esc(result.draft_text || '')}</p>`);
  if (meta) meta.textContent = `${result.document_type || 'draft'}${result.jurisdiction ? ' · ' + result.jurisdiction : ''}${result.persisted ? ' · saved to workspace' : ' · local result'}`;
  review.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.review_warnings || [], 'No warnings returned.')}</div>
    <div class="translate-review-section"><strong>Missing information</strong>${renderTranslationList(result.missing_information || [], 'No missing information returned.')}</div>
    <div class="translate-review-section"><strong>Assumptions</strong>${renderTranslationList(result.assumptions || [], 'No assumptions returned.')}</div>
    <div class="translate-review-section"><strong>Sources</strong>${renderTranslationList((result.sources || []).map(source => source.filename ? `${source.filename}${source.chunk !== undefined ? ' · chunk ' + source.chunk : ''}` : source), 'No source documents used.')}</div>
  `;
}

async function loadDraftHistory() {
  const card = document.getElementById('draft-history-card');
  const list = document.getElementById('draft-history-list');
  const meta = document.getElementById('draft-history-meta');
  const workspaceId = draftWorkspaceId();
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    App.drafting.history = [];
    return;
  }
  card.style.display = 'block';
  App.drafting.historyLoading = true;
  if (meta) meta.textContent = 'Loading saved workspace drafts';
  list.innerHTML = '<div class="draft-history-empty">Loading drafts...</div>';
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/drafts?page_size=25`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.drafting.history = data.items || [];
    if (meta) meta.textContent = `${data.total || App.drafting.history.length || 0} saved draft${(data.total || App.drafting.history.length) === 1 ? '' : 's'}`;
    renderDraftHistory();
  } catch(e) {
    list.innerHTML = `<div class="draft-history-empty">Could not load draft history: ${esc(e.message)}</div>`;
  } finally {
    App.drafting.historyLoading = false;
  }
}

function renderDraftHistory() {
  const list = document.getElementById('draft-history-list');
  if (!list) return;
  const items = App.drafting.history || [];
  if (!items.length) {
    list.innerHTML = '<div class="draft-history-empty">No saved drafts yet. Generate a draft while signed in to save it here.</div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const title = item.title || item.document_type || 'Untitled draft';
    const date = item.completed_at || item.created_at;
    const tokens = item.config?.drafting_trace?.token_usage || item.config?.token_usage || {};
    const tokenText = tokens.total_tokens ? ` · ~${tokens.total_tokens} tokens` : '';
    const meta = [
      item.document_type || 'Draft',
      item.jurisdiction || '',
      date ? formatDate(date) : '',
    ].filter(Boolean).join(' · ');
    return `<div class="draft-history-row">
      <div>
        <div class="draft-history-title">${esc(title)}</div>
        <div class="draft-history-meta-line">${esc(meta)}${esc(tokenText)}</div>
      </div>
      <div class="draft-history-actions">
        <button class="btn-secondary" type="button" onclick="openDraftHistoryItem('${esc(item.id)}')">Open</button>
        <button class="btn-secondary" type="button" onclick="downloadDraftHistoryItem('${esc(item.id)}')">Download</button>
      </div>
    </div>`;
  }).join('');
}

async function fetchDraftHistoryItem(draftId) {
  const workspaceId = draftWorkspaceId();
  if (!workspaceId) throw new Error('No workspace selected.');
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/drafts/${encodeURIComponent(draftId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  const result = await r.json();
  result.persisted = true;
  return result;
}

async function openDraftHistoryItem(draftId) {
  try {
    App.drafting.result = await fetchDraftHistoryItem(draftId);
    renderDraftResult();
    document.getElementById('draft-result-grid')?.scrollIntoView({behavior:'smooth', block:'start'});
  } catch(e) {
    showToast('Draft load failed: ' + e.message, 'error');
  }
}

async function downloadDraftHistoryItem(draftId) {
  try {
    const result = await fetchDraftHistoryItem(draftId);
    downloadDraftResult(result);
  } catch(e) {
    showToast('Draft download failed: ' + e.message, 'error');
  }
}

function renderDraftProgress() {
  const card = document.getElementById('draft-progress-card');
  const list = document.getElementById('draft-progress-list');
  const meta = document.getElementById('draft-progress-meta');
  if (!card || !list) return;
  const events = App.drafting.events || [];
  const job = App.drafting.job;
  if (!job && !events.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'block';
  const progress = Math.max(0, Math.min(100, Number(job?.progress || 0)));
  const elapsed = App.drafting.startedAt ? `${Math.max(0, Math.floor((Date.now() - App.drafting.startedAt) / 1000))}s` : '0s';
  const latestTokens = [...events].reverse().map(e => e.metadata?.tokens).find(Boolean) || job?.metadata?.token_usage || {};
  const tokenText = latestTokens.total_tokens ? `~${latestTokens.total_tokens} tokens` : 'tokens pending';
  if (meta) meta.textContent = `${job?.status || 'running'} · ${progress}% · ${elapsed} elapsed · ${tokenText}`;
  const rows = events.length ? events : [{content:'Draft generation queued', metadata:{progress:0}}];
  list.innerHTML = rows.slice(-10).map((event, index) => {
    const tokens = event.metadata?.tokens;
    const tokenPill = tokens?.total_tokens ? `<div class="draft-token-pill">~${esc(tokens.total_tokens)} tokens</div>` : '';
    const detail = event.metadata?.stage ? `${event.metadata.stage}${event.metadata.exact_tokens === false || tokens?.exact === false ? ' · estimated' : ''}` : '';
    return `<div class="draft-progress-item ${index < rows.length - 1 ? 'muted' : ''}">
      <div class="draft-progress-dot"></div>
      <div><strong>${esc(event.content || event.type || 'Working')}</strong>${detail ? `<span>${esc(detail)}</span>` : ''}</div>
      ${tokenPill}
    </div>`;
  }).join('');
}

function stopDraftStream() {
  App.drafting.stream?.close();
  App.drafting.stream = null;
}

async function loadDraftResultFromJob(job) {
  const draftId = job?.metadata?.draft_id;
  if (!draftId || !draftWorkspaceId()) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(draftWorkspaceId())}/drafts/${encodeURIComponent(draftId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.drafting.result = await r.json();
  App.drafting.result.persisted = true;
  renderDraftResult();
  await loadDraftHistory();
  return true;
}

function startDraftJobStream(job) {
  stopDraftStream();
  if (!job?.id || !draftWorkspaceId()) return;
  App.drafting.job = job;
  App.drafting.events = [{type:'status', content:'Draft generation queued', metadata:{progress:0}}];
  App.drafting.startedAt = Date.now();
  renderDraftProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(draftWorkspaceId())}/jobs/${encodeURIComponent(job.id)}/events`);
  App.drafting.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.drafting.job = data.metadata;
    if (data.type && data.type !== 'status') App.drafting.events.push(data);
    App.drafting.events = App.drafting.events.slice(-24);
    renderDraftProgress();
    if (data.type === 'done') {
      stopDraftStream();
      App.drafting.job = data.metadata || App.drafting.job;
      try {
        if (data.content === 'completed') {
          await loadDraftResultFromJob(App.drafting.job);
          showToast('Draft generated.');
        } else {
          showToast('Draft ended: ' + data.content, data.content === 'failed' ? 'error' : 'warning');
        }
      } catch(e) {
        showToast('Draft completed but result load failed: ' + e.message, 'error');
      } finally {
        App.drafting.isRunning = false;
        const btn = document.getElementById('draft-run-btn');
        const status = document.getElementById('draft-status');
        if (btn) btn.disabled = false;
        if (status) status.textContent = '';
        renderDraftProgress();
      }
    }
  };
  source.onerror = () => {
    stopDraftStream();
    renderDraftProgress();
  };
}

function printableDraftDocumentFor(result) {
  if (!result) return '';
  const body = result.draft_html || `<pre>${esc(result.draft_text || '')}</pre>`;
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${esc(result.title || 'Draft')}</title><style>
    @page { margin: 22mm 18mm; }
    body { font-family: Georgia, 'Times New Roman', serif; color: #111; line-height: 1.55; font-size: 12pt; }
    article { max-width: 760px; margin: 0 auto; }
    h1 { font-size: 20pt; text-align: center; margin: 0 0 18pt; }
    h2 { font-size: 14pt; margin: 18pt 0 8pt; }
    h3 { font-size: 12.5pt; margin: 14pt 0 6pt; }
    p { margin: 0 0 9pt; }
    table { width: 100%; border-collapse: collapse; margin: 12pt 0; }
    th, td { border: 1px solid #777; padding: 6pt; vertical-align: top; }
    aside { border-left: 3px solid #888; padding-left: 10pt; color: #333; }
  </style></head><body>${body}</body></html>`;
}

function printableDraftDocument() {
  return printableDraftDocumentFor(App.drafting.result);
}

async function copyDraftHtml() {
  const result = App.drafting.result;
  if (!result) return;
  await navigator.clipboard.writeText(result.draft_html || result.draft_text || '');
  showToast('Draft HTML copied.');
}

async function copyDraftText() {
  const result = App.drafting.result;
  if (!result) return;
  await navigator.clipboard.writeText(result.draft_text || '');
  showToast('Draft text copied.');
}

function downloadDraftHtml() {
  const result = App.drafting.result;
  if (!result) return;
  downloadDraftResult(result);
}

function downloadDraftResult(result) {
  const blob = new Blob([printableDraftDocumentFor(result)], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${slugify(result.title || result.document_type || 'draft')}.html`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function printDraftHtml() {
  const htmlDoc = printableDraftDocument();
  if (!htmlDoc) return;
  const win = window.open('', '_blank');
  if (!win) {
    showToast('Pop-up blocked. Use Download HTML instead.', 'error');
    return;
  }
  win.document.open();
  win.document.write(htmlDoc);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 250);
}

function resetDraft() {
  stopDraftStream();
  App.drafting.result = null;
  App.drafting.job = null;
  App.drafting.events = [];
  App.drafting.startedAt = null;
  ['draft-document-type','draft-title','draft-jurisdiction','draft-audience','draft-parties','draft-facts','draft-key-terms','draft-instructions'].forEach(id => {
    const node = document.getElementById(id);
    if (node) node.value = '';
  });
  const grid = document.getElementById('draft-result-grid');
  if (grid) grid.style.display = 'none';
  const progress = document.getElementById('draft-progress-card');
  if (progress) progress.style.display = 'none';
  const sourceSelect = document.getElementById('draft-source-documents');
  if (sourceSelect) [...sourceSelect.options].forEach(option => { option.selected = false; });
}
