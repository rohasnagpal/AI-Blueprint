function toggleWebSearch() {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before changing web search.', 'warning');
    return;
  }
  App.webSearchEnabled = !App.webSearchEnabled;
  document.getElementById('web-search-btn')?.classList.toggle('active', App.webSearchEnabled);
}

function toggleChatModeMenu(event) {
  event?.stopPropagation();
  const menu = document.getElementById('input-mode-menu');
  if (!menu) return;
  const trigger = event?.currentTarget;
  const isTopbar = trigger?.id === 'doc-selector';
  menu.classList.toggle('topbar-mode-menu', isTopbar);
  if (isTopbar) {
    const rect = trigger.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top = (rect.bottom + 8) + 'px';
    menu.style.bottom = 'auto';
  } else {
    menu.style.left = '';
    menu.style.top = '';
    menu.style.bottom = '';
  }
  menu.classList.toggle('open');
}

function setChatMode(mode) {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before changing modes.', 'warning');
    return;
  }
  if (mode === 'documents' && !App.documents.length && !App.v2.documents.length) {
    App.chatMode = 'general';
    updateChatModeUI();
    document.getElementById('input-mode-menu')?.classList.remove('open');
    return;
  }
  document.getElementById('input-mode-menu')?.classList.remove('open');
  if (App.currentChatId && App.chatMode !== mode) {
    const draft = document.getElementById('chat-input')?.value || '';
    newChat();
    const input = document.getElementById('chat-input');
    if (input) {
      input.value = draft;
      autoResize(input);
    }
  }
  App.chatMode = mode;
  if (mode === 'documents' && App.selectedDocIds === 'none') App.selectedDocIds = 'all';
  updateChatModeUI();
}

function activateHelpChat() {
  switchView('chat');
  setChatMode('help');
  const input = document.getElementById('chat-input');
  if (input) input.focus();
}

function updateChatModeUI() {
  if (App.chatMode === 'documents' && !App.documents.length && !App.v2.documents.length) App.chatMode = 'general';
  const label = document.getElementById('input-mode-label');
  const icon = document.getElementById('input-mode-icon');
  const input = document.getElementById('chat-input');
  const docOpt = document.getElementById('mode-option-documents');
  const generalOpt = document.getElementById('mode-option-general');
  const helpOpt = document.getElementById('mode-option-help');
  if (label) label.textContent = App.chatMode === 'help' ? 'Help' : App.chatMode === 'general' ? 'General' : 'Documents';
  if (icon) icon.innerHTML = App.chatMode === 'help'
    ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 1 1 5.82 1c0 2-3 2-3 4"/><path d="M12 17h.01"/></svg>'
    : App.chatMode === 'general'
      ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
      : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>';
  if (input) input.placeholder = App.chatMode === 'help' ? 'Ask how to use AI Blueprint...' : App.chatMode === 'general' ? 'Ask anything...' : 'Ask anything about your documents...';
  docOpt?.classList.toggle('active', App.chatMode === 'documents');
  generalOpt?.classList.toggle('active', App.chatMode === 'general');
  helpOpt?.classList.toggle('active', App.chatMode === 'help');
  updateDocSelector();
  updateChatScopeControls();
}

function updateDocSelector() {
  const badge = document.getElementById('input-doc-badge');
  const topbarLabel = document.getElementById('topbar-doc-label');
  if (!badge && !topbarLabel) return;
  if (App.chatMode === 'help') {
    if (badge) {
      badge.textContent = 'AI Blueprint help';
      badge.style.display = 'inline-flex';
    }
    if (topbarLabel) topbarLabel.textContent = 'Help';
    return;
  }
  if (App.chatMode === 'general') {
    const scopeLabel = v2ChatScopeLabel();
    if (badge) {
      badge.textContent = scopeLabel ? `${scopeLabel} · No document search` : 'No document search';
      badge.style.display = 'inline-flex';
    }
    if (topbarLabel) topbarLabel.textContent = scopeLabel || 'General';
    return;
  }
  const v2Label = v2ChatScopeLabel();
  const docText = v2Label || (App.selectedDocIds === 'all' ? `All Documents (${App.documents.length})` : `${App.selectedDocIds.length} selected`);
  if (badge) {
    badge.textContent = docText;
    badge.style.display = 'inline-flex';
  }
  if (topbarLabel) topbarLabel.textContent = docText;
}

function updateChatScopeControls() {
  const workspaceSelect = document.getElementById('chat-workspace-select');
  const matterSelect = document.getElementById('chat-matter-select');
  if (!workspaceSelect || !matterSelect) return;
  const show = !!(App.v2.enabled && App.v2.workspaces.length);
  workspaceSelect.style.display = show ? 'block' : 'none';
  matterSelect.style.display = show ? 'block' : 'none';
  if (!show) return;
  workspaceSelect.innerHTML = App.v2.workspaces
    .map(w => `<option value="${esc(w.workspace_id)}">${esc(w.workspace_name || w.name || 'Workspace')}</option>`)
    .join('');
  workspaceSelect.value = App.v2.workspaceId || '';
  matterSelect.innerHTML = `<option value="all">All matters</option>` +
    App.v2.matters.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  matterSelect.value = App.v2.activeMatterId && App.v2.activeMatterId !== '' ? App.v2.activeMatterId : 'all';
}

function prepareNewChatForScopeChange() {
  if (!App.currentChatId) return;
  const draft = document.getElementById('chat-input')?.value || '';
  newChat();
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = draft;
    autoResize(input);
  }
}

async function setChatWorkspaceFromInput(workspaceId) {
  if (!workspaceId || workspaceId === App.v2.workspaceId) return;
  prepareNewChatForScopeChange();
  await setV2Workspace(workspaceId);
  updateChatModeUI();
}

function setChatMatterFromInput(matterId) {
  prepareNewChatForScopeChange();
  App.v2.activeMatterId = matterId || '';
  App.v2.activeBlueprintId = null;
  renderV2Shell();
  updateChatModeUI();
}

function v2ChatScopeLabel() {
  if (!App.v2.enabled || !App.v2.workspaceId) return '';
  const blueprint = App.v2.activeBlueprintId ? App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId) : null;
  if (blueprint) return `Blueprint: ${blueprint.name}`;
  const matterId = App.v2.activeMatterId;
  if (matterId && matterId !== 'all') {
    const matter = App.v2.matters.find(m => m.id === matterId);
    return matter ? `Matter: ${matter.name}` : 'Matter documents';
  }
  const workspace = App.v2.workspaces.find(w => w.workspace_id === App.v2.workspaceId);
  return workspace ? `Workspace: ${workspace.workspace_name || workspace.name}` : 'Workspace';
}

function v2ChatScopePayload() {
  if (!App.v2.enabled || !App.v2.workspaceId) return {};
  let v2DocIds = [];
  if (App.chatMode === 'documents' && Array.isArray(App.selectedDocIds)) {
    v2DocIds = App.selectedDocIds
      .filter(id => (App.v2.documents || []).some(doc => doc.id === id));
  }
  return {
    v2_workspace_id: App.v2.workspaceId,
    v2_matter_id: App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : null,
    v2_blueprint_id: App.v2.activeBlueprintId || null,
    v2_document_ids: v2DocIds
  };
}
