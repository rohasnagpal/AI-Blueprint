// ── UPLOAD ────────────────────────────────────────────────────────────────
function initUpload() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  const folderInput = document.getElementById('folder-input');
  if (!zone || !input) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor='var(--accent)'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor=''; });
  zone.addEventListener('drop', e => { e.preventDefault(); zone.style.borderColor=''; handleFiles(e.dataTransfer.files); });
  input.addEventListener('change', () => { handleFiles(input.files); input.value=''; });
  if (folderInput) {
    folderInput.addEventListener('change', async () => {
      const forcedSourceId = App.pendingBrowserFolderSourceId || null;
      App.pendingBrowserFolderSourceId = null;
      await syncBrowserFolder(folderInput.files, forcedSourceId);
      folderInput.value = '';
    });
  }
  loadFolderSources();
}

function updateUploadQueueVisibility() {
  const title = document.getElementById('upload-queue-title');
  const list = document.getElementById('upload-queue-list');
  if (title) title.style.display = list && list.children.length ? 'block' : 'none';
}

function handleFiles(files, options = {}) {
  const allowed = ['.pdf','.docx','.txt','.csv','.xlsx','.md','.json','.html','.htm'];
  const maxMb = parseInt(App.settings.max_file_size_mb || 25);
  for (const f of files) {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) { showToast(`${f.name}: File type not supported.`, 'error'); continue; }
    if (f.size > maxMb * 1024 * 1024) { showToast(`${f.name}: Exceeds ${maxMb} MB limit.`, 'error'); continue; }
    uploadFile(f, options);
  }
}

function openChatUpload() {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before uploading.', 'warning');
    return;
  }
  const input = document.getElementById('file-input');
  if (!input) {
    showToast('Upload control is not available.', 'error');
    return;
  }
  input.click();
}

async function uploadFile(file, options = {}) {
  if (!App.v2.enabled || !uploadWorkspaceId()) {
    showToast('Choose or sign in to a workspace before uploading documents.', 'error');
    return;
  }
  const queueEl = document.getElementById('upload-queue-list');
  if (!queueEl) return;
  const displayName = file.webkitRelativePath || file.name;
  const ext = file.name.split('.').pop().toUpperCase();
  const cls = {PDF:'icon-pdf',DOCX:'icon-docx',TXT:'icon-txt',CSV:'icon-csv',XLSX:'icon-csv',MD:'icon-txt',JSON:'icon-txt',HTML:'icon-html',HTM:'icon-html'}[ext]||'icon-txt';
  const item = document.createElement('div');
  item.className = 'upload-item';
  item.innerHTML = `<div class="upload-item-icon ${cls}">${ext}</div><div class="upload-item-info"><div class="upload-item-name">${esc(displayName)}</div><div class="progress-bar"><div class="progress-fill" data-csp-style="width:5%"></div></div></div><div class="upload-item-size">${fmtBytes(file.size)}</div><div class="upload-item-status status-loading"></div>`;
  queueEl.appendChild(item);
  updateUploadQueueVisibility();
  const fill = item.querySelector('.progress-fill');
  const status = item.querySelector('.upload-item-status');
  let pct = 5;
  let result = null;
  const iv = setInterval(() => { pct = Math.min(pct + Math.random() * 12, 85); fill.style.width = pct + '%'; }, 300);
  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('original_name', displayName);
    const matterId = selectedUploadMatterId();
    fd.append('scope', 'matter');
    if (matterId) fd.append('matter_id', matterId);
    if (options.folderSourceId) fd.append('folder_source_id', options.folderSourceId);
    if (options.sourcePath) fd.append('source_path', options.sourcePath);
    if (options.sourceMtime != null) fd.append('source_mtime', String(options.sourceMtime));
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(uploadWorkspaceId())}/documents/upload`, {method:'POST', body:fd});
    clearInterval(iv);
    if (!r.ok) {
      const err = await apiError(r);
      fill.style.width='100%'; fill.style.background='var(--danger)';
      status.className='upload-item-status'; status.textContent='✕'; status.style.color='var(--danger)';
      showToast(err || 'Upload failed.', 'error');
    } else {
      const uploaded = await r.json();
      fill.style.width='100%';
      status.className='upload-item-status status-done';
      status.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      if (!options.quiet) showToast(`${displayName} uploaded.`);
      await loadDocuments();
      if (options.folderSourceId) await loadFolderSources();
      if (!App.currentChatId && !App.isStreaming && uploaded.id) {
        App.chatMode = 'documents';
        App.selectedDocIds = [uploaded.id];
        if (uploaded.matter_id) App.v2.activeMatterId = uploaded.matter_id;
        updateChatModeUI();
      }
      result = uploaded;
    }
  } catch(e) { clearInterval(iv); showToast('Upload failed: ' + e.message, 'error'); }
  setTimeout(() => {
    item.remove();
    updateUploadQueueVisibility();
  }, 4000);
  return result;
}

function folderImportRoot(files) {
  const selected = Array.from(files || []);
  const firstRelativePath = selected.find(f => f.webkitRelativePath)?.webkitRelativePath || '';
  return firstRelativePath.split('/')[0] || '';
}

function folderSourceApi(path = '') {
  const workspaceId = uploadWorkspaceId();
  return workspaceId ? `/api/v2/workspaces/${encodeURIComponent(workspaceId)}/documents/folders${path}` : null;
}

async function loadFolderSources() {
  const list = document.getElementById('folder-source-list');
  if (!list || !App.v2.enabled || !uploadWorkspaceId()) {
    if (list) list.innerHTML = '';
    return;
  }
  const matterId = selectedUploadMatterId();
  if (!matterId) {
    list.innerHTML = '<div class="folder-empty">Choose or create a matter before connecting folders.</div>';
    return;
  }
  try {
    const r = await fetch(`${folderSourceApi()}?matter_id=${encodeURIComponent(matterId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.folderSources = data.items || [];
    renderFolderSources();
  } catch(e) {
    list.innerHTML = `<div class="folder-empty">Folder sources could not be loaded.</div>`;
  }
}

function renderFolderSources() {
  const list = document.getElementById('folder-source-list');
  if (!list) return;
  const sources = App.folderSources || [];
  if (!sources.length) {
    list.innerHTML = '<div class="folder-empty">No folder sources connected yet.</div>';
    return;
  }
  list.innerHTML = sources.map(source => {
    const synced = source.last_synced_at ? new Date(source.last_synced_at).toLocaleString() : 'Never synced';
    const typeLabel = source.source_type === 'browser' ? 'Selected folder' : 'Local path';
    const syncLabel = source.source_type === 'browser' ? 'Reselect to Sync' : 'Sync Files';
    return `<div class="folder-source-row">
      <div class="folder-source-main">
        <div class="folder-source-title">${esc(source.display_name || source.path)}</div>
        <div class="folder-source-meta"><span>${esc(typeLabel)}</span><span>${esc(source.path)}</span><span>${source.file_count || 0} files</span><span>${esc(synced)}</span></div>
      </div>
      <div class="folder-source-actions">
        <button type="button" onclick="syncFolderSource('${esc(source.id)}')">${syncLabel}</button>
        <button type="button" class="danger" onclick="deleteFolderSource('${esc(source.id)}')">Remove</button>
      </div>
    </div>`;
  }).join('');
}

function browseConnectedFolder(folderSourceId = null) {
  const input = document.getElementById('folder-input');
  if (!input) {
    showToast('Folder picker is not available.', 'error');
    return;
  }
  App.pendingBrowserFolderSourceId = folderSourceId;
  input.click();
}

async function connectLocalFolder() {
  if (!App.v2.enabled || !uploadWorkspaceId()) {
    showToast('Choose or sign in to a workspace before connecting folders.', 'error');
    return;
  }
  const matterId = selectedUploadMatterId();
  const path = document.getElementById('connected-folder-path')?.value.trim();
  if (!matterId) { showToast('Choose a matter before connecting a folder.', 'error'); return; }
  if (!path) { showToast('Enter a local folder path.', 'error'); return; }
  try {
    const r = await fetch(folderSourceApi(), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({matter_id: matterId, path})
    });
    if (!r.ok) throw new Error(await apiError(r));
    const source = await r.json();
    showToast('Folder connected. Syncing files...', 'warning');
    await syncLocalFolder(source.id);
  } catch(e) {
    showToast('Folder connect failed: ' + e.message, 'error');
  }
}

async function syncFolderSource(folderSourceId) {
  const source = (App.folderSources || []).find(item => item.id === folderSourceId);
  if (!source) return;
  if (source.source_type === 'browser') {
    browseConnectedFolder(folderSourceId);
    return;
  }
  await syncLocalFolder(folderSourceId);
}

async function syncLocalFolder(folderSourceId) {
  try {
    const r = await fetch(folderSourceApi(`/${encodeURIComponent(folderSourceId)}/sync`), {method: 'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    showToast(`Folder sync complete: ${data.added || 0} added, ${data.updated || 0} updated, ${data.removed || 0} removed.`);
    await loadDocuments();
    await loadFolderSources();
  } catch(e) {
    showToast('Folder sync failed: ' + e.message, 'error');
  }
}

async function syncBrowserFolder(files, forcedSourceId = null) {
  const selected = Array.from(files || []);
  if (!selected.length) return;
  if (!App.v2.enabled || !uploadWorkspaceId()) {
    showToast('Choose or sign in to a workspace before syncing folders.', 'error');
    return;
  }
  const matterId = selectedUploadMatterId();
  if (!matterId) { showToast('Choose a matter before syncing a folder.', 'error'); return; }
  const rootName = folderImportRoot(selected);
  if (!rootName) { showToast('This browser did not provide folder paths.', 'error'); return; }
  let source = forcedSourceId ? (App.folderSources || []).find(item => item.id === forcedSourceId) : null;
  if (source && source.path !== rootName) {
    showToast(`Select the same folder again: ${source.path}`, 'error');
    return;
  }
  try {
    if (!source) {
      const r = await fetch(folderSourceApi('/browser'), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({matter_id: matterId, root_name: rootName})
      });
      if (!r.ok) throw new Error(await apiError(r));
      source = await r.json();
    }
    const sourcePaths = selected.map(file => file.webkitRelativePath || file.name);
    const start = await fetch(folderSourceApi(`/${encodeURIComponent(source.id)}/browser-sync-start`), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({source_paths: sourcePaths})
    });
    if (!start.ok) throw new Error(await apiError(start));
    let uploaded = 0;
    for (const file of selected) {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      if (!['.pdf','.docx','.txt','.csv','.xlsx','.md','.json','.html','.htm'].includes(ext)) continue;
      await uploadFile(file, {
        folderSourceId: source.id,
        sourcePath: file.webkitRelativePath || file.name,
        sourceMtime: file.lastModified ? file.lastModified / 1000 : null,
        quiet: true,
      });
      uploaded += 1;
    }
    showToast(`Folder sync complete: ${uploaded} file${uploaded === 1 ? '' : 's'} processed.`);
    await loadDocuments();
    await loadFolderSources();
  } catch(e) {
    showToast('Folder sync failed: ' + e.message, 'error');
  }
}

async function deleteFolderSource(folderSourceId) {
  if (!confirm('Remove this folder source? Synced documents will remain.')) return;
  try {
    const r = await fetch(folderSourceApi(`/${encodeURIComponent(folderSourceId)}`), {method: 'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    showToast('Folder source removed.');
    await loadFolderSources();
  } catch(e) {
    showToast('Remove failed: ' + e.message, 'error');
  }
}

async function ingestUrl() {
  if (!App.v2.enabled || !uploadWorkspaceId()) {
    showToast('Choose or sign in to a workspace before adding a URL.', 'error');
    return;
  }
  const input = document.getElementById('url-ingest-input');
  const url = input?.value.trim();
  if (!url) return;
  const queueEl = document.getElementById('upload-queue-list');
  const item = document.createElement('div');
  item.className = 'upload-item';
  item.innerHTML = `<div class="upload-item-icon icon-html">URL</div><div class="upload-item-info"><div class="upload-item-name">${esc(url)}</div><div class="progress-bar"><div class="progress-fill" data-csp-style="width:20%"></div></div></div><div class="upload-item-size">Web</div><div class="upload-item-status status-loading"></div>`;
  queueEl.appendChild(item);
  updateUploadQueueVisibility();
  const fill = item.querySelector('.progress-fill');
  const status = item.querySelector('.upload-item-status');
  try {
    const matterId = selectedUploadMatterId();
    const params = new URLSearchParams({scope: 'matter'});
    if (matterId) params.set('matter_id', matterId);
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(uploadWorkspaceId())}/documents/ingest-url?${params.toString()}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
    if (!r.ok) throw new Error(await apiError(r));
    fill.style.width='100%';
    status.className='upload-item-status status-done';
    status.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    input.value = '';
    showToast('URL added to documents.');
    await loadDocuments();
  } catch(e) {
    fill.style.width='100%'; fill.style.background='var(--danger)';
    status.className='upload-item-status'; status.textContent='x'; status.style.color='var(--danger)';
    showToast('URL ingest failed: ' + e.message, 'error');
  }
  setTimeout(() => {
    item.remove();
    updateUploadQueueVisibility();
  }, 5000);
}
