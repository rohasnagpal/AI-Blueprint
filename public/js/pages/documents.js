// ── DOCUMENTS ─────────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    if (App.v2.enabled) {
      await loadV2Documents();
      App.documents = (App.v2.documents || []).map(normalizeV2Document);
    } else {
      App.documents = [];
    }
    if (!App.documents.length && App.chatMode === 'documents') App.chatMode = 'general';
    renderDocsScopeSelector();
    renderDocuments();
    updateDocsBadge();
    updateDocSelector();
    renderEmailControls();
  } catch(e) {}
}

function normalizeV2Document(doc) {
  const name = doc.original_name || 'Document';
  const ext = (name.split('.').pop() || '').toUpperCase();
  return {
    ...doc,
    file_type: ext && ext !== name.toUpperCase() ? ext : (doc.mime_type || 'TXT').split('/').pop().toUpperCase(),
    uploaded_at: doc.created_at || doc.updated_at,
    page_count: doc.page_count || null,
  };
}

function docsMatterFilterValue() {
  const value = document.getElementById('docs-matter-select')?.value;
  if (value != null) return value;
  return App.v2.activeMatterId || 'all';
}

function scopedDocumentsForView() {
  const matterId = docsMatterFilterValue();
  const docs = App.documents || [];
  if (matterId === 'all') return docs;
  if (matterId === '') return docs.filter(doc => !doc.matter_id);
  return docs.filter(doc => doc.matter_id === matterId);
}

function renderDocsScopeSelector() {
  const card = document.getElementById('docs-scope-card');
  const workspaceSelect = document.getElementById('docs-workspace-select');
  const matterSelect = document.getElementById('docs-matter-select');
  if (!card || !workspaceSelect || !matterSelect) return;
  const show = !!(App.v2.enabled && App.v2.workspaces.length);
  card.style.display = show ? 'grid' : 'none';
  if (!show) return;
  workspaceSelect.innerHTML = App.v2.workspaces
    .map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === App.v2.workspaceId ? 'selected' : ''}>${esc(w.workspace_name || w.name || 'Workspace')}</option>`)
    .join('');
  const currentMatter = matterSelect.value || App.v2.activeMatterId || 'all';
  matterSelect.innerHTML = '<option value="all">All workspace documents</option><option value="">Workspace-level only</option>' +
    (App.v2.matters || []).map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  matterSelect.value = [...matterSelect.options].some(o => o.value === currentMatter) ? currentMatter : 'all';
}

async function onDocsWorkspaceChange(workspaceId) {
  if (!workspaceId || workspaceId === App.v2.workspaceId) return;
  await setV2Workspace(workspaceId);
  App.v2.activeMatterId = 'all';
  await loadDocuments();
}

function onDocsMatterChange(matterId) {
  App.v2.activeMatterId = matterId || 'all';
  renderDocuments(document.querySelector('.search-input')?.value || '');
  updateDocSelector();
}

async function loadConnectedFolders() {
  App.connectedFolders = [];
  renderConnectedFolders();
}

function renderConnectedFolders() {
  document.querySelectorAll('.connected-folders-panel').forEach(panel => {
    panel.style.display = App.v2.enabled ? 'none' : '';
  });
  const lists = document.querySelectorAll('.connected-folders-list');
  if (!lists.length) return;
  const importedFolders = mergedImportedFolders();
  const connectedRows = App.connectedFolders.map(folder => `
    <div class="connected-folder-row">
      <div class="connected-folder-main">
        <div class="connected-folder-path" title="${esc(folder.path)}">${esc(folder.path)}</div>
        <div class="connected-folder-meta">${folder.file_count || 0} synced file${folder.file_count === 1 ? '' : 's'} · Connected folder${folder.last_synced_at ? ' · Last sync ' + esc(formatDate(folder.last_synced_at)) : ''}</div>
      </div>
      <div class="connected-folder-actions">
        <button class="btn-secondary" type="button" onclick="syncConnectedFolder('${esc(folder.id)}')">Sync</button>
        <button class="danger-btn" type="button" onclick="removeConnectedFolder('${esc(folder.id)}')">Remove</button>
      </div>
    </div>
  `);
  const importedRows = importedFolders.map(folder => `
    <div class="connected-folder-row">
      <div class="connected-folder-main">
        <div class="connected-folder-path" title="${esc(folder.name)}">${esc(folder.name)}</div>
        <div class="connected-folder-meta">${folder.file_count || 0} imported file${folder.file_count === 1 ? '' : 's'} · One-time browse import${folder.imported_at ? ' · Last import ' + esc(formatDate(folder.imported_at)) : ''}</div>
      </div>
      <div class="connected-folder-actions">
        <button class="btn-secondary" type="button" onclick="reimportFolderSource('${esc(folder.id)}')">Re-import</button>
        <button class="danger-btn" type="button" onclick="removeImportedFolder('${esc(folder.id)}')">Remove</button>
      </div>
    </div>
  `);
  const html = connectedRows.concat(importedRows).join('') || '<div class="connected-folder-empty">No folder sources yet.</div>';
  lists.forEach(list => { list.innerHTML = html; });
}

function mergedImportedFolders() {
  const inferred = new Map();
  scopedDocumentsForView().forEach(doc => {
    const originalName = doc.original_name || '';
    if (!originalName.includes('/')) return;
    const rootName = originalName.split('/')[0];
    if (!rootName) return;
    const id = rootName.toLowerCase().replace(/[^a-z0-9._-]+/g, '-');
    const existing = inferred.get(id) || {id, name: rootName, file_count: 0, imported_at: doc.uploaded_at || ''};
    existing.file_count += 1;
    if (doc.uploaded_at && (!existing.imported_at || new Date(doc.uploaded_at) > new Date(existing.imported_at))) {
      existing.imported_at = doc.uploaded_at;
    }
    inferred.set(id, existing);
  });
  App.importedFolders.forEach(folder => {
    const existing = inferred.get(folder.id);
    if (existing) {
      inferred.set(folder.id, {...folder, file_count: Math.max(folder.file_count || 0, existing.file_count || 0)});
    } else {
      inferred.set(folder.id, folder);
    }
  });
  return Array.from(inferred.values()).sort((a, b) => new Date(b.imported_at || 0) - new Date(a.imported_at || 0));
}

function saveImportedFolders() {
  localStorage.setItem('aibp_imported_folders', JSON.stringify(App.importedFolders));
}

function rememberImportedFolder(files) {
  const allowed = ['.pdf','.docx','.txt','.csv','.xlsx','.md','.json','.html','.htm'];
  const selected = Array.from(files || []);
  const firstRelativePath = selected.find(f => f.webkitRelativePath)?.webkitRelativePath || '';
  const rootName = firstRelativePath.split('/')[0];
  if (!rootName) return;
  const fileCount = selected.filter(f => allowed.includes('.' + f.name.split('.').pop().toLowerCase())).length;
  if (!fileCount) return;
  const imported = {
    id: rootName.toLowerCase().replace(/[^a-z0-9._-]+/g, '-'),
    name: rootName,
    file_count: fileCount,
    imported_at: new Date().toISOString()
  };
  App.importedFolders = [imported, ...App.importedFolders.filter(f => f.id !== imported.id)].slice(0, 20);
  saveImportedFolders();
  renderConnectedFolders();
}

async function removeImportedFolder(folderId) {
  const folder = mergedImportedFolders().find(f => f.id === folderId);
  if (!folder || !confirm(`Remove imported folder "${folder.name}" and its imported documents?`)) return;
  const prefix = `${folder.name}/`;
  const docs = App.documents.filter(doc => (doc.original_name || '').startsWith(prefix));
  try {
    for (const doc of docs) {
      const r = await v2Fetch(`/documents/${encodeURIComponent(doc.id)}`, {method:'DELETE'});
      if (!r.ok) throw new Error(await apiError(r));
    }
    App.importedFolders = App.importedFolders.filter(f => f.id !== folderId);
    saveImportedFolders();
    await loadDocuments();
    renderConnectedFolders();
    showToast(`Imported folder removed${docs.length ? `: ${docs.length} document${docs.length === 1 ? '' : 's'} deleted.` : '.'}`);
  } catch(e) {
    showToast('Could not remove imported folder: ' + e.message, 'error');
  }
}

function reimportFolderSource(folderId) {
  const folder = mergedImportedFolders().find(f => f.id === folderId);
  showToast(folder ? `Select "${folder.name}" again to re-import it.` : 'Select the folder again to re-import it.');
  browseConnectedFolder();
}

async function addConnectedFolder() {
  showToast('Connected folder sync has been removed. Upload files directly into the selected workspace/matter.', 'warning');
}

async function browseConnectedFolder() {
  const input = document.getElementById('folder-input');
  if (!input) {
    showToast('Folder browser is not available.', 'error');
    return;
  }
  input.click();
}

async function syncConnectedFolder(folderId) {
  showToast('Connected folder sync has been removed. Upload files directly into the selected workspace/matter.', 'warning');
}

async function removeConnectedFolder(folderId) {
  App.connectedFolders = App.connectedFolders.filter(folder => folder.id !== folderId);
  renderConnectedFolders();
}

function renderDocuments(filter = '') {
  const grid = document.getElementById('docs-grid');
  if (!grid) return;
  const scopedDocs = scopedDocumentsForView();
  const docs = filter ? scopedDocs.filter(d => d.original_name.toLowerCase().includes(filter.toLowerCase())) : scopedDocs;
  if (!docs.length) { grid.innerHTML = '<div data-csp-style="grid-column:1/-1;text-align:center;padding:48px;color:var(--text-subtle)">No documents yet. Upload one to get started.</div>'; }
  else grid.innerHTML = docs.map(d => docCard(d)).join('');
  const total = scopedDocs.reduce((s,d) => s+(d.size_bytes||0), 0);
  const types = new Set(scopedDocs.map(d=>d.file_type)).size;
  el('stat-docs-count', scopedDocs.length);
  el('stat-total-size', fmtBytes(total));
  el('stat-file-types', types);
  renderConnectedFolders();
}

function docCard(d) {
  const ext = (d.file_type||'TXT').toUpperCase();
  const cls = {PDF:'icon-pdf',DOCX:'icon-docx',TXT:'icon-txt',CSV:'icon-csv',XLSX:'icon-csv',MD:'icon-txt',JSON:'icon-txt',HTML:'icon-html',HTM:'icon-html',URL:'icon-html'}[ext]||'icon-txt';
  const date = d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '';
  const pages = d.page_count ? `<div class="dot"></div><span>${d.page_count} pages</span>` : '';
  const matter = d.matter_id ? (App.v2.matters || []).find(m => m.id === d.matter_id) : null;
  const scope = matter ? `Matter: ${matter.name}` : 'Workspace-level';
  return `<div class="doc-card">
    <div class="doc-card-header"><div class="doc-card-icon ${cls}">${ext}</div><div class="doc-card-title" title="${esc(d.original_name)}">${esc(d.original_name)}</div></div>
    <div class="doc-card-meta"><span>${esc(scope)}</span><div class="dot"></div><span>${fmtBytes(d.size_bytes||0)}</span>${date?`<div class="dot"></div><span>${date}</span>`:''}${pages}</div>
    <div class="doc-card-actions">
      <button class="doc-action-btn" onclick="chatWithDoc('${d.id}','${esc(d.original_name).replace(/'/g,"\\'")}')">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>Chat
      </button>
      <button class="doc-action-btn danger" onclick="deleteDocument('${d.id}')">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>Delete
      </button>
    </div>
  </div>`;
}

function updateDocsBadge() { el('docs-count-badge', App.documents.length); }

async function deleteDocument(id) {
  if (!confirm('Delete this document?')) return;
  try {
    const r = await v2Fetch(`/documents/${encodeURIComponent(id)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    showToast('Document deleted.');
    await loadDocuments();
  } catch(e) { showToast('Delete failed.', 'error'); }
}

async function deleteAllDocuments() {
  if (!confirm('Delete ALL documents? This cannot be undone.')) return;
  try {
    const r = await v2Fetch('/documents', {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    App.v2.documents = [];
    showToast('All documents deleted.');
    await loadDocuments();
  } catch(e) { showToast('Delete failed.', 'error'); }
}

function chatWithDoc(id) {
  App.chatMode = 'documents';
  App.selectedDocIds = [id];
  updateChatModeUI();
  switchView('chat');
  newChat();
  App.chatMode = 'documents';
  App.selectedDocIds = [id];
  updateChatModeUI();
}

function searchDocs(q) { renderDocuments(q); }
