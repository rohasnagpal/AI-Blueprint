// ── PERSONAS ─────────────────────────────────────────────────────────────
async function loadPersonas() {
  try {
    const r = await fetch('/api/personas');
    App.personas = await arrayOrEmpty(r);
    renderPersonaSelect();
    renderPersonas();
    renderEmailControls();
  } catch(e) {}
}

function renderPersonaSelect() {
  const sel = document.getElementById('persona-select');
  if (!sel) return;
  const groups = {};
  for (const p of App.personas) {
    if (!groups[p.category]) groups[p.category] = [];
    groups[p.category].push(p);
  }
  const html = ['<option value="">No persona</option>'];
  for (const category of Object.keys(groups).sort()) {
    html.push(`<optgroup label="${esc(category)}">`);
    html.push(...groups[category].map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`));
    html.push('</optgroup>');
  }
  sel.innerHTML = html.join('');
  updatePersonaSelect();
}

function updatePersonaSelect() {
  const sel = document.getElementById('persona-select');
  if (sel) sel.value = App.selectedPersonaId || '';
}

function setPersona(personaId) {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before changing personas.', 'warning');
    updatePersonaSelect();
    return;
  }
  if (App.currentChatId && App.selectedPersonaId !== personaId) {
    const draft = document.getElementById('chat-input')?.value || '';
    newChat();
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = draft;
      autoResize(input);
    }
  }
  App.selectedPersonaId = personaId || '';
  updatePersonaSelect();
}

function renderPersonas() {
  const grid = document.getElementById('personas-grid');
  const pills = document.getElementById('persona-category-pills');
  if (!grid || !pills) return;
  const categories = [...new Set(App.personas.map(p => p.category))];
  if (!App.personas.length) {
    pills.innerHTML = '';
    grid.innerHTML = '<div data-csp-style="grid-column:1/-1;text-align:center;padding:48px;color:var(--text-subtle)">No personas yet.</div>';
    return;
  }
  if (!App.selectedPersonaCategory || !categories.includes(App.selectedPersonaCategory)) {
    App.selectedPersonaCategory = categories[0] || '';
  }
  pills.innerHTML = categories.map(c => `
    <button class="stat-pill selectable ${c === App.selectedPersonaCategory ? 'active' : ''}" type="button" onclick="setPersonaCategory('${esc(c)}')">
      <strong>${esc(c)}</strong>
    </button>
  `).join('');
  const visible = App.personas.filter(p => p.category === App.selectedPersonaCategory);
  grid.innerHTML = visible.map(p => `
    <div class="doc-card">
      <div class="doc-card-header">
        <div class="doc-card-icon icon-txt">${esc(p.name.split(' ').map(x => x[0]).join('').slice(0, 2).toUpperCase())}</div>
        <div class="doc-card-title" title="${esc(p.name)}">${esc(p.name)}</div>
      </div>
      <div class="doc-card-meta"><span>${esc(p.category)}</span>${p.is_builtin ? '<div class="dot"></div><span>Built-in</span>' : ''}</div>
      <div class="settings-row-desc">${esc(p.description || '')}</div>
      <div class="doc-card-actions">
        <button class="doc-action-btn" onclick="showPersonaDetails('${esc(p.id)}')">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>Details
        </button>
        ${p.is_builtin ? '' : `<button class="doc-action-btn" onclick="openPersonaEditor('${esc(p.id)}')">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>Edit
        </button>`}
        <button class="doc-action-btn" onclick="usePersona('${esc(p.id)}')">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4Z"/></svg>Use
        </button>
      </div>
    </div>
  `).join('');
}

function setPersonaCategory(category) {
  App.selectedPersonaCategory = category;
  renderPersonas();
}

function usePersona(personaId) {
  setPersona(personaId);
  switchView('chat');
}

function showPersonaDetails(personaId) {
  const p = App.personas.find(x => x.id === personaId);
  if (!p) return;
  el('persona-detail-name', p.name);
  el('persona-detail-category', `${p.category}${p.is_builtin ? ' · Built-in' : ''}`);
  const body = document.getElementById('persona-detail-body');
  const constraints = (p.constraints || []).length
    ? `<ul class="detail-list">${p.constraints.map(c => `<li>${esc(c)}</li>`).join('')}</ul>`
    : '<div class="detail-text">None</div>';
  const tags = (p.tags || []).length
    ? `<div class="tag-row">${p.tags.map(t => `<span class="stat-pill">${esc(t)}</span>`).join('')}</div>`
    : '<div class="detail-text">None</div>';
  body.innerHTML = `
    <div class="detail-block">
      <div class="detail-label">Description</div>
      <div class="detail-text">${esc(p.description || '')}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">System Prompt</div>
      <div class="detail-text">${esc(p.system_prompt || '')}</div>
    </div>
    <div class="detail-block">
      <div class="detail-label">Constraints</div>
      ${constraints}
    </div>
    <div class="detail-block">
      <div class="detail-label">Tags</div>
      ${tags}
    </div>
  `;
  document.getElementById('persona-detail-modal')?.classList.add('open');
}

function closePersonaDetails(event) {
  if (event && event.target.id !== 'persona-detail-modal') return;
  document.getElementById('persona-detail-modal')?.classList.remove('open');
}

function openPersonaEditor(personaId = null) {
  const persona = personaId ? App.personas.find(p => p.id === personaId) : null;
  if (persona?.is_builtin) {
    showToast('Built-in personas cannot be edited.', 'warning');
    return;
  }
  App.editingPersonaId = persona?.id || null;
  el('persona-editor-title', persona ? 'Edit Persona' : 'Create Persona');
  el('persona-editor-subtitle', persona ? 'Update this custom persona for future chats.' : 'Create a reusable role, style, and instruction set.');
  setInputValue('persona-editor-name', persona?.name || '');
  setInputValue('persona-editor-category', persona?.category || 'Custom');
  setInputValue('persona-editor-description', persona?.description || '');
  setInputValue('persona-editor-system-prompt', persona?.system_prompt || '');
  setInputValue('persona-editor-constraints', (persona?.constraints || []).join('\n'));
  setInputValue('persona-editor-tags', (persona?.tags || []).join(', '));
  const deleteBtn = document.getElementById('persona-editor-delete');
  if (deleteBtn) deleteBtn.style.display = persona ? 'inline-flex' : 'none';
  document.getElementById('persona-editor-modal')?.classList.add('open');
}

function closePersonaEditor(event) {
  if (event && event.target.id !== 'persona-editor-modal') return;
  document.getElementById('persona-editor-modal')?.classList.remove('open');
}

function setInputValue(id, value) {
  const input = document.getElementById(id);
  if (input) input.value = value;
}

function personaEditorPayload() {
  const constraints = (document.getElementById('persona-editor-constraints')?.value || '')
    .split('\n')
    .map(v => v.trim())
    .filter(Boolean);
  const tags = (document.getElementById('persona-editor-tags')?.value || '')
    .split(',')
    .map(v => v.trim())
    .filter(Boolean);
  return {
    name: document.getElementById('persona-editor-name')?.value.trim() || '',
    category: document.getElementById('persona-editor-category')?.value.trim() || 'Custom',
    description: document.getElementById('persona-editor-description')?.value.trim() || '',
    system_prompt: document.getElementById('persona-editor-system-prompt')?.value.trim() || '',
    constraints,
    output_format: {},
    tags,
    is_enabled: true
  };
}

async function savePersona() {
  const payload = personaEditorPayload();
  if (!payload.name) {
    showToast('Persona name is required.', 'error');
    return;
  }
  if (!payload.system_prompt) {
    showToast('System prompt is required.', 'error');
    return;
  }
  const personaId = App.editingPersonaId;
  const url = personaId ? `/api/personas/${encodeURIComponent(personaId)}` : '/api/personas';
  const method = personaId ? 'PUT' : 'POST';
  try {
    const r = await fetch(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const saved = await r.json();
    App.selectedPersonaCategory = saved.category;
    closePersonaEditor();
    await loadPersonas();
    showToast(personaId ? 'Persona saved.' : 'Persona created.');
  } catch(e) {
    showToast('Failed to save persona: ' + e.message, 'error');
  }
}

async function deletePersonaFromEditor() {
  const personaId = App.editingPersonaId;
  const persona = App.personas.find(p => p.id === personaId);
  if (!persona || persona.is_builtin) return;
  if (!confirm(`Delete persona "${persona.name}"?`)) return;
  try {
    const r = await fetch(`/api/personas/${encodeURIComponent(personaId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.selectedPersonaId === personaId) App.selectedPersonaId = '';
    closePersonaEditor();
    await loadPersonas();
    showToast('Persona deleted.');
  } catch(e) {
    showToast('Failed to delete persona: ' + e.message, 'error');
  }
}
