// ── TRANSLATION ───────────────────────────────────────────────────────────
function setTranslateSourceType(value) {
  App.translation.sourceType = value === 'upload' ? 'upload' : 'text';
  const textCard = document.getElementById('translate-text-card');
  const uploadCard = document.getElementById('translate-upload-card');
  if (textCard) textCard.style.display = App.translation.sourceType === 'text' ? 'block' : 'none';
  if (uploadCard) uploadCard.style.display = App.translation.sourceType === 'upload' ? 'block' : 'none';
}

function initTranslationUpload() {
  const zone = document.getElementById('translate-upload-zone');
  const input = document.getElementById('translate-file-input');
  if (!zone || !input) return;
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor='var(--accent)'; });
  zone.addEventListener('dragleave', () => { zone.style.borderColor=''; });
  zone.addEventListener('drop', e => { e.preventDefault(); zone.style.borderColor=''; selectTranslationFile(e.dataTransfer.files?.[0]); });
  input.addEventListener('change', () => { selectTranslationFile(input.files?.[0]); input.value=''; });
}

function selectTranslationFile(file) {
  if (!file) return;
  const allowed = ['.pdf','.txt','.csv','.md','.json','.html','.htm'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  const maxMb = parseInt(App.settings.max_file_size_mb || 25);
  if (!allowed.includes(ext)) {
    showToast(`${file.name}: File type not supported for translation.`, 'error');
    return;
  }
  if (file.size > maxMb * 1024 * 1024) {
    showToast(`${file.name}: Exceeds ${maxMb} MB limit.`, 'error');
    return;
  }
  App.translation.file = file;
  renderTranslationFile();
}

function renderTranslationFile() {
  const title = document.getElementById('translate-file-title');
  const list = document.getElementById('translate-file-list');
  if (!title || !list) return;
  const file = App.translation.file;
  title.style.display = file ? 'block' : 'none';
  if (!file) {
    list.innerHTML = '';
    return;
  }
  const ext = file.name.split('.').pop().toUpperCase();
  const cls = {PDF:'icon-pdf',TXT:'icon-txt',CSV:'icon-csv',MD:'icon-txt',JSON:'icon-txt',HTML:'icon-html',HTM:'icon-html'}[ext]||'icon-txt';
  list.innerHTML = `<div class="upload-item"><div class="upload-item-icon ${cls}">${esc(ext)}</div><div class="upload-item-info"><div class="upload-item-name">${esc(file.name)}</div><div class="translate-file-note">Ready to translate</div></div><div class="upload-item-size">${fmtBytes(file.size)}</div><button class="icon-btn" type="button" title="Remove file" onclick="clearTranslationFile()">×</button></div>`;
}

function clearTranslationFile() {
  App.translation.file = null;
  renderTranslationFile();
}

function collectTranslationPayload() {
  const sourceLanguage = document.getElementById('translate-source-language')?.value || 'auto';
  const targetLanguage = document.getElementById('translate-target-language')?.value.trim() || '';
  const mode = document.getElementById('translate-mode')?.value || 'legal';
  const context = document.getElementById('translate-context')?.value.trim() || '';
  if (!targetLanguage) throw new Error('Target language is required.');
  return {sourceLanguage, targetLanguage, mode, context};
}

async function runTranslation() {
  if (App.translation.isRunning) return;
  const btn = document.getElementById('translate-run-btn');
  const status = document.getElementById('translate-status');
  try {
    const payload = collectTranslationPayload();
    App.translation.isRunning = true;
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Translating...';
    let r;
    const signedIn = !!(App.v2.enabled && App.v2.user && translateWorkspaceId());
    if (App.translation.sourceType === 'upload') {
      if (!App.translation.file) throw new Error('Choose one document to translate.');
      const fd = new FormData();
      fd.append('file', App.translation.file);
      fd.append('source_language', payload.sourceLanguage);
      fd.append('target_language', payload.targetLanguage);
      fd.append('mode', payload.mode);
      if (payload.context) fd.append('context', payload.context);
      if (signedIn && selectedTranslateMatterId()) fd.append('matter_id', selectedTranslateMatterId());
      const url = signedIn
        ? `/api/v2/workspaces/${encodeURIComponent(translateWorkspaceId())}/translations/upload`
        : '/api/v2/translations/public/upload';
      r = await fetch(url, {method:'POST', body:fd});
    } else {
      const text = document.getElementById('translate-source-text')?.value.trim() || '';
      if (!text) throw new Error('Paste text to translate.');
      const body = {
        text,
        source_language: payload.sourceLanguage,
        target_language: payload.targetLanguage,
        mode: payload.mode,
        context: payload.context || null,
      };
      if (signedIn && selectedTranslateMatterId()) body.matter_id = selectedTranslateMatterId();
      const url = signedIn
        ? `/api/v2/workspaces/${encodeURIComponent(translateWorkspaceId())}/translations/text`
        : '/api/v2/translations/public/text';
      r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    }
    if (!r.ok) throw new Error(await apiError(r));
    App.translation.result = await r.json();
    renderTranslationResult();
    showToast('Translation complete.');
  } catch(e) {
    showToast('Translation failed: ' + e.message, 'error');
  } finally {
    App.translation.isRunning = false;
    if (btn) btn.disabled = false;
    if (status) status.textContent = '';
  }
}

function sanitizeTranslationHtml(htmlText) {
  const template = document.createElement('template');
  template.innerHTML = htmlText || '';
  template.content.querySelectorAll('script,style,iframe,object,embed,link,meta').forEach(node => node.remove());
  template.content.querySelectorAll('*').forEach(node => {
    [...node.attributes].forEach(attr => {
      const name = attr.name.toLowerCase();
      const value = attr.value || '';
      if (name.startsWith('on') || value.toLowerCase().startsWith('javascript:')) node.removeAttribute(attr.name);
    });
  });
  return template.innerHTML;
}

function renderTranslationResult() {
  const result = App.translation.result;
  const grid = document.getElementById('translate-result-grid');
  const preview = document.getElementById('translate-html-preview');
  const meta = document.getElementById('translate-result-meta');
  const review = document.getElementById('translate-review-list');
  if (!result || !grid || !preview || !review) return;
  grid.style.display = 'grid';
  preview.innerHTML = sanitizeTranslationHtml(result.translated_html || `<p>${esc(result.translated_text || '')}</p>`);
  if (meta) meta.textContent = `${result.mode || 'translation'} to ${result.target_language || ''}${result.persisted ? ' · saved to workspace' : ' · local result'}`;
  const warnings = result.warnings || [];
  const notes = result.translator_notes || [];
  const preserved = result.preserved_terms || [];
  const quality = result.quality_check || {};
  review.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(warnings, 'No warnings returned.')}</div>
    <div class="translate-review-section"><strong>Translator notes</strong>${renderTranslationList(notes, 'No notes returned.')}</div>
    <div class="translate-review-section"><strong>Preserved terms</strong>${renderTranslationList(preserved, 'No preserved terms returned.')}</div>
    <div class="translate-review-section"><strong>Quality check</strong><pre>${esc(JSON.stringify(quality, null, 2))}</pre></div>
  `;
}

function renderTranslationList(items, emptyText) {
  if (!Array.isArray(items) || !items.length) return `<p>${esc(emptyText)}</p>`;
  return `<ul>${items.map(item => `<li>${esc(typeof item === 'string' ? item : JSON.stringify(item))}</li>`).join('')}</ul>`;
}

async function copyTranslationHtml() {
  const result = App.translation.result;
  if (!result) return;
  await navigator.clipboard.writeText(result.translated_html || result.translated_text || '');
  showToast('Translation copied.');
}

function downloadTranslationHtml() {
  const result = App.translation.result;
  if (!result) return;
  const htmlDoc = `<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Translation</title></head><body>${result.translated_html || `<pre>${esc(result.translated_text || '')}</pre>`}</body></html>`;
  const blob = new Blob([htmlDoc], {type:'text/html;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `translation-${Date.now()}.html`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function resetTranslation() {
  App.translation.file = null;
  App.translation.result = null;
  document.getElementById('translate-source-text').value = '';
  document.getElementById('translate-context').value = '';
  document.getElementById('translate-target-language').value = '';
  document.getElementById('translate-result-grid').style.display = 'none';
  renderTranslationFile();
}
