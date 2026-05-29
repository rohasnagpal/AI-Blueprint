// ── CHATS ──────────────────────────────────────────────────────────────────
async function loadChats() {
  try {
    const r = await fetch(`/api/chats${App.chatArchiveFilter ? '?archived=true' : ''}`);
    App.chats = await arrayOrEmpty(r);
    renderChatHistory();
  } catch(e) {}
}

function renderChatHistory() {
  const list = document.getElementById('chat-history-list');
  if (!list) return;
  el('chat-history-label', App.chatArchiveFilter ? 'Archived Chats' : 'Recent Chats');
  document.getElementById('chat-active-filter')?.classList.toggle('active', !App.chatArchiveFilter);
  document.getElementById('chat-archived-filter')?.classList.toggle('active', App.chatArchiveFilter);
  const bulk = document.getElementById('chat-bulk-actions');
  if (bulk) bulk.style.display = App.chatSelectMode ? 'flex' : 'none';
  list.innerHTML = '';
  const query = App.chatSearchQuery.trim().toLowerCase();
  const chats = query ? App.chats.filter(chat => (chat.title || 'New Chat').toLowerCase().includes(query)) : App.chats;
  if (!chats.length && query) {
    list.innerHTML = '<div data-csp-style="padding:10px 8px;color:var(--sidebar-text-muted);font-size:12px">No matching chats.</div>';
    return;
  }
  for (const chat of chats) {
    const item = document.createElement('div');
    item.className = 'chat-history-item' + (chat.id === App.currentChatId ? ' active' : '') + (chat.id === App.openChatMenuId ? ' menu-open' : '');
    const menu = chat.id === App.openChatMenuId ? `
      <div class="chat-row-menu" onclick="event.stopPropagation()">
        ${App.chatArchiveFilter ? `<button class="chat-menu-item" type="button" onclick="restoreChat('${chat.id}', event)">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/></svg>
          <span>Restore</span>
        </button>` : `<button class="chat-menu-item" type="button" onclick="archiveChat('${chat.id}', event)">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/></svg>
          <span>Archive</span>
        </button>`}
        <button class="chat-menu-item danger" type="button" onclick="deleteChat('${chat.id}', event)">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
          <span>Delete</span>
        </button>
      </div>` : '';
    const checked = App.selectedChatIds.has(chat.id) ? 'checked' : '';
    const selector = App.chatSelectMode ? `<input type="checkbox" ${checked} onclick="toggleSelectedChat('${chat.id}', event)" data-csp-style="margin:0 2px 0 0;accent-color:var(--accent)"/>` : '';
    item.innerHTML = `${selector}<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><span class="chat-history-title">${esc(chat.title || 'New Chat')}</span><button class="chat-menu-btn" type="button" title="Chat options" onclick="toggleChatMenu('${chat.id}', event)"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>${menu}`;
    item.onclick = () => App.chatSelectMode ? toggleSelectedChat(chat.id) : openChat(chat.id);
    list.appendChild(item);
  }
}

function setChatArchiveFilter(archived) {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before changing chat lists.', 'warning');
    return;
  }
  App.chatArchiveFilter = !!archived;
  App.chatSelectMode = false;
  App.selectedChatIds.clear();
  App.openChatMenuId = null;
  loadChats();
}

function toggleChatSelectMode(force) {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before selecting chats.', 'warning');
    return;
  }
  App.chatSelectMode = typeof force === 'boolean' ? force : !App.chatSelectMode;
  App.selectedChatIds.clear();
  App.openChatMenuId = null;
  renderChatHistory();
}

function toggleSelectedChat(chatId, event) {
  if (event) event.stopPropagation();
  if (App.selectedChatIds.has(chatId)) App.selectedChatIds.delete(chatId);
  else App.selectedChatIds.add(chatId);
  renderChatHistory();
}

function toggleChatSearch() {
  const wrap = document.getElementById('topbar-chat-search');
  const input = document.getElementById('chat-search-input');
  if (!wrap || !input) return;
  const open = !wrap.classList.contains('open');
  wrap.classList.toggle('open', open);
  if (open) {
    input.focus();
    input.select();
  } else {
    input.value = '';
    searchChats('');
  }
}

function searchChats(value) {
  App.chatSearchQuery = value || '';
  renderChatHistory();
}

function handleChatSearchKey(event) {
  if (event.key !== 'Escape') return;
  event.preventDefault();
  const input = document.getElementById('chat-search-input');
  if (input) input.value = '';
  searchChats('');
  document.getElementById('topbar-chat-search')?.classList.remove('open');
}

function toggleChatMenu(chatId, event) {
  event.stopPropagation();
  App.openChatMenuId = App.openChatMenuId === chatId ? null : chatId;
  renderChatHistory();
}

function closeChatMenus() {
  if (!App.openChatMenuId) return;
  App.openChatMenuId = null;
  renderChatHistory();
}

async function archiveChat(chatId, event) {
  event.stopPropagation();
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before archiving a chat.', 'warning');
    return;
  }
  try {
    const r = await fetch(`/api/chats/${chatId}/archive`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || err.error || 'Archive failed');
    }
    App.openChatMenuId = null;
    if (App.currentChatId === chatId) newChat();
    await loadChats();
    showToast('Chat archived.', 'success');
  } catch(e) {
    showToast('Failed to archive chat: ' + e.message, 'error');
  }
}

async function restoreChat(chatId, event) {
  event.stopPropagation();
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before restoring a chat.', 'warning');
    return;
  }
  try {
    const r = await fetch(`/api/chats/${chatId}/restore`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || err.error || 'Restore failed');
    }
    App.openChatMenuId = null;
    await loadChats();
    showToast('Chat restored.', 'success');
  } catch(e) {
    showToast('Failed to restore chat: ' + e.message, 'error');
  }
}

async function deleteChat(chatId, event) {
  event.stopPropagation();
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before deleting a chat.', 'warning');
    return;
  }
  const chat = App.chats.find(c => c.id === chatId);
  const title = chat?.title || 'New Chat';
  if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
  try {
    const r = await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || err.error || 'Delete failed');
    }
    App.openChatMenuId = null;
    if (App.currentChatId === chatId) newChat();
    await loadChats();
    showToast('Chat deleted.', 'success');
  } catch(e) {
    showToast('Failed to delete chat: ' + e.message, 'error');
  }
}

async function deleteSelectedChats() {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before deleting chats.', 'warning');
    return;
  }
  const ids = [...App.selectedChatIds];
  if (!ids.length) { showToast('Select at least one chat.', 'warning'); return; }
  if (!confirm(`Delete ${ids.length} selected chat${ids.length === 1 ? '' : 's'}? This cannot be undone.`)) return;
  try {
    const r = await fetch('/api/chats/bulk-delete', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ids})});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (ids.includes(App.currentChatId)) newChat();
    App.selectedChatIds.clear();
    App.chatSelectMode = false;
    await loadChats();
    showToast(`${data.deleted || 0} chat${data.deleted === 1 ? '' : 's'} deleted.`);
  } catch(e) { showToast('Delete failed: ' + e.message, 'error'); }
}

async function deleteAllVisibleChats() {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before deleting chats.', 'warning');
    return;
  }
  if (!App.chats.length) { showToast('No chats to delete.', 'warning'); return; }
  const label = App.chatArchiveFilter ? 'archived' : 'active';
  if (!confirm(`Delete all ${App.chats.length} ${label} chat${App.chats.length === 1 ? '' : 's'}? This cannot be undone.`)) return;
  try {
    const r = await fetch(`/api/chats${App.chatArchiveFilter ? '?archived=true' : ''}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (!App.chatArchiveFilter) newChat();
    App.selectedChatIds.clear();
    App.chatSelectMode = false;
    await loadChats();
    showToast(`${data.deleted || 0} chat${data.deleted === 1 ? '' : 's'} deleted.`);
  } catch(e) { showToast('Delete failed: ' + e.message, 'error'); }
}

async function openChat(chatId) {
  App.openChatMenuId = null;
  App.currentChatId = chatId;
  const chat = App.chats.find(c => c.id === chatId);
  const context = chat?.doc_context || 'all';
  App.chatMode = context === 'help' ? 'help' : context === 'none' ? 'general' : 'documents';
  App.selectedDocIds = ['none', 'help'].includes(context) ? 'all' : context === 'all' ? 'all' : context.split(',').filter(Boolean);
  App.selectedPersonaId = chat?.persona_id || '';
  if (chat?.v2_workspace_id) {
    App.v2.workspaceId = chat.v2_workspace_id;
    App.v2.activeMatterId = chat.v2_matter_id || 'all';
    App.v2.activeBlueprintId = chat.v2_blueprint_id || null;
  }
  updateChatModeUI();
  updatePersonaSelect();
  switchView('chat');
  const conv = document.getElementById('chat-conversation');
  conv.innerHTML = '';
  conv.style.display = 'block';
  document.getElementById('welcome-screen').style.display = 'none';
  renderChatHistory();
  try {
    const r = await fetch(`/api/chats/${chatId}/messages`);
    const msgs = await r.json();
    for (const m of msgs) conv.appendChild(m.role === 'user' ? mkUser(m.content) : mkAi(m.content, m.sources || [], m.id));
    scrollBottom();
  } catch(e) { showToast('Failed to load messages.', 'error'); }
}

function newChat() {
  App.openChatMenuId = null;
  App.currentChatId = null;
  App.chatMode = 'general';
  App.selectedDocIds = 'all';
  App.selectedPersonaId = '';
  updateChatModeUI();
  updatePersonaSelect();
  document.getElementById('chat-conversation').innerHTML = '';
  document.getElementById('chat-conversation').style.display = 'none';
  document.getElementById('welcome-screen').style.display = 'flex';
  document.getElementById('chat-input').value = '';
  renderChatHistory();
}
