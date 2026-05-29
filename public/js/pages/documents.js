// ── DOCUMENTS ─────────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    if (App.v2.enabled) await loadV2Documents();
    const r = await fetch('/api/documents');
    App.documents = await arrayOrEmpty(r);
    if (!App.documents.length && App.chatMode === 'documents') App.chatMode = 'general';
    renderDocuments();
    updateDocsBadge();
    updateDocSelector();
    renderCouncilDocOptions();
    renderEmailControls();
  } catch(e) {}
}

async function loadConnectedFolders() {
  try {
    const r = await fetch('/api/connected-folders');
    App.connectedFolders = await arrayOrEmpty(r);
    renderConnectedFolders();
  } catch(e) {
    App.connectedFolders = [];
    renderConnectedFolders();
  }
}

function renderConnectedFolders() {
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
  App.documents.forEach(doc => {
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
      const r = await fetch(`/api/documents/${encodeURIComponent(doc.id)}`, {method:'DELETE'});
      if (!r.ok) throw new Error(await apiError(r));
      await deleteV2DocumentForLegacyDoc(doc);
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
  const input = document.getElementById('connected-folder-path');
  const path = input?.value.trim() || '';
  if (!path) {
    showToast('Folder path is required.', 'error');
    return;
  }
  try {
    const r = await fetch('/api/connected-folders', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path})
    });
    if (!r.ok) throw new Error(await apiError(r));
    if (input) input.value = '';
    await loadConnectedFolders();
    showToast('Folder connected.');
  } catch(e) {
    showToast('Could not connect folder: ' + e.message, 'error');
  }
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
  try {
    const r = await fetch(`/api/connected-folders/${encodeURIComponent(folderId)}/sync`, {method:'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    const result = await r.json();
    await Promise.all([loadConnectedFolders(), loadDocuments()]);
    showToast(`Folder synced: ${result.added || 0} added, ${result.updated || 0} updated, ${result.removed || 0} removed, ${result.skipped || 0} unchanged.`);
  } catch(e) {
    showToast('Folder sync failed: ' + e.message, 'error');
  }
}

async function removeConnectedFolder(folderId) {
  const folder = App.connectedFolders.find(f => f.id === folderId);
  if (!folder || !confirm(`Remove connected folder "${folder.path}"? Existing synced documents will remain.`)) return;
  try {
    const r = await fetch(`/api/connected-folders/${encodeURIComponent(folderId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadConnectedFolders();
    showToast('Connected folder removed.');
  } catch(e) {
    showToast('Could not remove folder: ' + e.message, 'error');
  }
}

function renderDocuments(filter = '') {
  const grid = document.getElementById('docs-grid');
  if (!grid) return;
  const docs = filter ? App.documents.filter(d => d.original_name.toLowerCase().includes(filter.toLowerCase())) : App.documents;
  if (!docs.length) { grid.innerHTML = '<div data-csp-style="grid-column:1/-1;text-align:center;padding:48px;color:var(--text-subtle)">No documents yet. Upload one to get started.</div>'; }
  else grid.innerHTML = docs.map(d => docCard(d)).join('');
  const total = App.documents.reduce((s,d) => s+(d.size_bytes||0), 0);
  const types = new Set(App.documents.map(d=>d.file_type)).size;
  el('stat-docs-count', App.documents.length);
  el('stat-total-size', fmtBytes(total));
  el('stat-file-types', types);
}

function docCard(d) {
  const ext = (d.file_type||'TXT').toUpperCase();
  const cls = {PDF:'icon-pdf',DOCX:'icon-docx',TXT:'icon-txt',CSV:'icon-csv',XLSX:'icon-csv',MD:'icon-txt',JSON:'icon-txt',HTML:'icon-html',HTM:'icon-html',URL:'icon-html'}[ext]||'icon-txt';
  const date = d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '';
  const pages = d.page_count ? `<div class="dot"></div><span>${d.page_count} pages</span>` : '';
  return `<div class="doc-card">
    <div class="doc-card-header"><div class="doc-card-icon ${cls}">${ext}</div><div class="doc-card-title" title="${esc(d.original_name)}">${esc(d.original_name)}</div></div>
    <div class="doc-card-meta"><span>${fmtBytes(d.size_bytes||0)}</span>${date?`<div class="dot"></div><span>${date}</span>`:''}${pages}</div>
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
    const doc = App.documents.find(d => d.id === id);
    await fetch(`/api/documents/${id}`, {method:'DELETE'});
    await deleteV2DocumentForLegacyDoc(doc);
    showToast('Document deleted.');
    await loadDocuments();
  } catch(e) { showToast('Delete failed.', 'error'); }
}

async function deleteAllDocuments() {
  if (!confirm('Delete ALL documents? This cannot be undone.')) return;
  try {
    await fetch('/api/documents', {method:'DELETE'});
    await deleteAllV2Documents();
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
