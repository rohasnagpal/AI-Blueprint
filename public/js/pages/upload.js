// ── UPLOAD ────────────────────────────────────────────────────────────────
function initUpload() {
  const zone = document.getElementById('upload-zone');
  const input = document.getElementById('file-input');
  if (!zone || !input) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor='var(--accent)'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor=''; });
  zone.addEventListener('drop', e => { e.preventDefault(); zone.style.borderColor=''; handleFiles(e.dataTransfer.files); });
  input.addEventListener('change', () => { handleFiles(input.files); input.value=''; });
}

function updateUploadQueueVisibility() {
  const title = document.getElementById('upload-queue-title');
  const list = document.getElementById('upload-queue-list');
  if (title) title.style.display = list && list.children.length ? 'block' : 'none';
}

function handleFiles(files) {
  const allowed = ['.pdf','.docx','.txt','.csv','.xlsx','.md','.json','.html','.htm'];
  const maxMb = parseInt(App.settings.max_file_size_mb || 25);
  for (const f of files) {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) { showToast(`${f.name}: File type not supported.`, 'error'); continue; }
    if (f.size > maxMb * 1024 * 1024) { showToast(`${f.name}: Exceeds ${maxMb} MB limit.`, 'error'); continue; }
    uploadFile(f);
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

async function uploadFile(file) {
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
  const iv = setInterval(() => { pct = Math.min(pct + Math.random() * 12, 85); fill.style.width = pct + '%'; }, 300);
  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('original_name', displayName);
    const matterId = selectedUploadMatterId();
    fd.append('scope', 'matter');
    if (matterId) fd.append('matter_id', matterId);
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(uploadWorkspaceId())}/documents/upload`, {method:'POST', body:fd});
    clearInterval(iv);
    if (!r.ok) {
      const err = await r.json();
      fill.style.width='100%'; fill.style.background='var(--danger)';
      status.className='upload-item-status'; status.textContent='✕'; status.style.color='var(--danger)';
      showToast(err.detail || 'Upload failed.', 'error');
    } else {
      const uploaded = await r.json();
      fill.style.width='100%';
      status.className='upload-item-status status-done';
      status.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
      showToast(`${displayName} uploaded.`);
      await loadDocuments();
      if (!App.currentChatId && !App.isStreaming && uploaded.id) {
        App.chatMode = 'documents';
        App.selectedDocIds = [uploaded.id];
        if (uploaded.matter_id) App.v2.activeMatterId = uploaded.matter_id;
        updateChatModeUI();
      }
    }
  } catch(e) { clearInterval(iv); showToast('Upload failed: ' + e.message, 'error'); }
  setTimeout(() => {
    item.remove();
    updateUploadQueueVisibility();
  }, 4000);
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
