// ── STATE ──────────────────────────────────────────────────────────────────
const App = { currentChatId: null, settings: {}, documents: [], connectedFolders: [], importedFolders: JSON.parse(localStorage.getItem('aibp_imported_folders') || '[]'), chats: [], personas: [], editingPersonaId: null, emailMessages: [], selectedPersonaId: '', selectedPersonaCategory: '', chatMode: 'general', selectedDocIds: 'all', webSearchEnabled: false, isStreaming: false, activeChatController: null, openChatMenuId: null, chatArchiveFilter: false, chatSelectMode: false, chatSearchQuery: '', selectedChatIds: new Set(), councilTemplates: [], councilRuns: [], councilBuilder: null, councilEditingTemplateId: null, models: [], editingModelId: null, activeCouncilRunId: null, councilPollTimer: null, councilRenderKey: '', adminUsers: [], adminWorkspaces: [], workspaceManager: { workspaces: [], selectedId: null, matters: [] }, v2: { enabled: false, user: null, workspaceId: null, workspaces: [], matters: [], blueprints: [], plugins: [], documents: [], personas: [], secrets: [], activeMatterId: 'all', activeBlueprintId: null, pluginConfig: null, pluginRuns: [], pluginJobs: {}, pluginJobEvents: {}, pluginJobStreams: {}, pluginJobTimers: {}, setupRequired: false, skipped: localStorage.getItem('aibp_v2_skip') === 'true' } };

// ── TOAST ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const c = document.getElementById('toast-container');
  const t = document.createElement('div');
  const bg = type === 'success' ? '#16a34a' : type === 'error' ? '#dc2626' : '#d97706';
  applyInlineStyles(t, {
    background: bg,
    color: 'white',
    padding: '10px 16px',
    borderRadius: '8px',
    fontSize: '13.5px',
    fontFamily: "'DM Sans', sans-serif",
    boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
    maxWidth: '340px',
    lineHeight: '1.4',
    animation: 'slideIn 0.2s ease',
    pointerEvents: 'auto',
  });
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function applyInlineStyles(element, styles) {
  Object.entries(styles || {}).forEach(([property, value]) => {
    element.style[property] = value;
  });
}

// ── INIT ───────────────────────────────────────────────────────────────────
async function init() {
  await Promise.all([loadSettings(), loadModels(), loadChats(), loadDocuments(), loadConnectedFolders(), loadPersonas()]);
  restoreSavedView();
  updateV2AuthSidebar();
  updateChatModeUI();
  renderEmailControls();
  checkFirstRun();
  runAfterFirstPaint(async () => {
    await initV2();
    updateV2AuthSidebar();
    updateChatModeUI();
    renderEmailControls();
  });
  runAfterFirstPaint(() => {
    loadCouncils();
    loadEmailMessages();
  });
}

function runAfterFirstPaint(task) {
  const run = () => Promise.resolve().then(task).catch(() => {});
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, {timeout: 1200});
  } else {
    setTimeout(run, 0);
  }
}

// ── V2 BACKEND BRIDGE ─────────────────────────────────────────────────────
async function initV2() {
  try {
    const me = await fetch('/api/v2/auth/me');
    if (!me.ok) {
      const setup = await fetch('/api/v2/auth/setup-state').then(r => r.ok ? r.json() : null).catch(() => null);
      App.v2.setupRequired = !!setup?.setup_required;
      updateV2AuthSidebar();
      if (!App.v2.skipped) showV2AuthModal(App.v2.setupRequired ? 'setup' : 'login');
      return;
    }
    const user = await me.json();
    App.v2.user = user.user || user;
    updateAdminNav();
    if (App.v2.user?.must_change_credentials) {
      showInitialCredentialReset();
      updateV2AuthSidebar();
      return;
    }
    await refreshV2Workspace();
  } catch(e) {
    App.v2.enabled = false;
    updateV2AuthSidebar();
  }
}

async function refreshV2Workspace(autoCreate = true) {
  try {
    const nav = await fetch('/api/v2/me/navigation');
    if (!nav.ok) {
      App.v2.enabled = false;
      return;
    }
    const navData = await nav.json();
    let workspaces = navData.items || [];
    if (autoCreate && !workspaces.length) {
      const created = await fetch('/api/v2/workspaces', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name:'My Workspace'})
      });
      if (created.ok) {
        const navAgain = await fetch('/api/v2/me/navigation');
        if (navAgain.ok) workspaces = (await navAgain.json()).items || [];
      }
    }
    App.v2 = {
      ...App.v2,
      enabled: !!workspaces.length,
      workspaceId: workspaces[0]?.workspace_id || null,
      workspaces
    };
    if (App.v2.enabled) await loadV2ShellData();
  } catch(e) {
    App.v2.enabled = false;
  }
}

function showV2AuthModal(mode) {
  App.v2.setupRequired = mode === 'setup';
  el('v2-auth-title', mode === 'setup' ? 'Set up multi-user access' : 'Sign in to multi-user access');
  el('v2-auth-subtitle', mode === 'setup' ? 'Create the local admin used by workspace and plugin features.' : 'Sign in to enable workspace and plugin features.');
  el('v2-auth-submit', mode === 'setup' ? 'Create admin' : 'Sign in');
  const nameField = document.getElementById('v2-auth-name-field');
  if (nameField) nameField.style.display = mode === 'setup' ? 'block' : 'none';
  const password = document.getElementById('v2-auth-password');
  if (password) password.setAttribute('autocomplete', mode === 'setup' ? 'new-password' : 'current-password');
  const error = document.getElementById('v2-auth-error');
  if (error) { error.style.display = 'none'; error.textContent = ''; }
  document.getElementById('v2-auth-modal')?.classList.add('open');
}

function updateV2AuthSidebar() {
  const label = document.getElementById('v2-auth-sidebar-label');
  const avatar = document.getElementById('v2-auth-avatar');
  const logout = document.getElementById('v2-logout-topbar');
  if (!label || !avatar) return;
  const name = App.v2.user?.display_name || App.v2.user?.username || App.v2.user?.email || '';
  label.textContent = name || (App.v2.setupRequired ? 'Set up access' : 'Sign in');
  avatar.textContent = name ? name.slice(0, 1).toUpperCase() : 'U';
  if (logout) logout.style.display = App.v2.user ? 'flex' : 'none';
  updateAdminNav();
}

async function logoutV2() {
  const btn = document.getElementById('v2-logout-topbar');
  try {
    if (btn) btn.disabled = true;
    const r = await fetch('/api/v2/auth/logout', {method:'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    App.v2 = {
      ...App.v2,
      enabled: false,
      user: null,
      workspaceId: null,
      workspaces: [],
      matters: [],
      blueprints: [],
      plugins: [],
      documents: [],
      personas: [],
      secrets: [],
      activeMatterId: 'all',
      activeBlueprintId: null,
      skipped: true
    };
    localStorage.setItem('aibp_v2_skip', 'true');
    App.workspaceManager = { workspaces: [], selectedId: null, matters: [] };
    updateV2AuthSidebar();
    renderWorkspaceManagerSignedOut();
    renderV2Shell();
    await Promise.all([loadDocuments(), loadPersonas()]);
    showToast('Logged out.');
  } catch(e) {
    showToast('Logout failed: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function openV2AuthFromSidebar() {
  if (App.v2.enabled && App.v2.user) {
    showToast(`Signed in as ${App.v2.user.display_name || App.v2.user.email}.`);
    return;
  }
  const setup = await fetch('/api/v2/auth/setup-state').then(r => r.ok ? r.json() : null).catch(() => null);
  App.v2.setupRequired = !!setup?.setup_required;
  App.v2.skipped = false;
  localStorage.removeItem('aibp_v2_skip');
  updateV2AuthSidebar();
  showV2AuthModal(App.v2.setupRequired ? 'setup' : 'login');
}

function closeV2AuthModal(event) {
  if (event && event.target.id !== 'v2-auth-modal') return;
  skipV2Auth();
}

function skipV2Auth() {
  App.v2.skipped = true;
  localStorage.setItem('aibp_v2_skip', 'true');
  document.getElementById('v2-auth-modal')?.classList.remove('open');
}

async function submitV2Auth() {
  const identifier = document.getElementById('v2-auth-email')?.value.trim();
  const password = document.getElementById('v2-auth-password')?.value || '';
  const displayName = document.getElementById('v2-auth-name')?.value.trim();
  const error = document.getElementById('v2-auth-error');
  const submit = document.getElementById('v2-auth-submit');
  if (error) { error.style.display = 'none'; error.textContent = ''; }
  if (!identifier || !password || (App.v2.setupRequired && !displayName)) {
    if (error) { error.textContent = 'Username, password, and name are required.'; error.style.display = 'block'; }
    return;
  }
  if (App.v2.setupRequired && password.length < 12) {
    if (error) { error.textContent = 'Password must be at least 12 characters.'; error.style.display = 'block'; }
    return;
  }
  try {
    if (submit) submit.disabled = true;
    const url = App.v2.setupRequired ? '/api/v2/auth/setup' : '/api/v2/auth/login';
    const payload = App.v2.setupRequired ? {email: identifier, password, display_name: displayName} : {identifier, password};
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.v2.user = data.user;
    App.v2.skipped = false;
    localStorage.removeItem('aibp_v2_skip');
    document.getElementById('v2-auth-modal')?.classList.remove('open');
    if (App.v2.user?.must_change_credentials) {
      showInitialCredentialReset();
      updateV2AuthSidebar();
      return;
    }
    await refreshV2Workspace();
    await Promise.all([loadDocuments(), loadPersonas()]);
    updateV2AuthSidebar();
    showToast('Multi-user access enabled.');
  } catch(e) {
    const message = e instanceof TypeError && e.message === 'Failed to fetch'
      ? 'Cannot reach AI Blueprint server. Start the app with python main.py and open http://127.0.0.1:8000.'
      : e.message;
    if (error) { error.textContent = message; error.style.display = 'block'; }
  } finally {
    if (submit) submit.disabled = false;
  }
}

function updateAdminNav() {
  const show = App.v2.user?.is_system_admin ? 'flex' : 'none';
  const workspaceShow = App.v2.user ? 'flex' : 'none';
  const workspaceNav = document.getElementById('settings-nav-workspaces');
  const settingsNav = document.getElementById('settings-nav-users');
  const mainNav = document.getElementById('nav-admin-users');
  if (workspaceNav) workspaceNav.style.display = workspaceShow;
  if (settingsNav) settingsNav.style.display = show;
  if (mainNav) mainNav.style.display = show;
}

function toggleSidebarMore(event) {
  event?.stopPropagation();
  document.getElementById('sidebar-more-menu')?.classList.toggle('open');
}

function closeSidebarMore() {
  document.getElementById('sidebar-more-menu')?.classList.remove('open');
}

function switchViewFromMore(name) {
  closeSidebarMore();
  switchView(name);
}

// ── WORKSPACE MANAGER ─────────────────────────────────────────────────────
function workspaceApi(workspaceId, path = '') {
  return `/api/v2/workspaces/${encodeURIComponent(workspaceId)}${path}`;
}

function workspaceManagerSelected() {
  return App.workspaceManager.workspaces.find(w => w.id === App.workspaceManager.selectedId) || null;
}

async function loadWorkspaceManager() {
  if (!App.v2.user) {
    renderWorkspaceManagerSignedOut();
    return;
  }
  try {
    const r = await fetch('/api/v2/workspaces?page_size=200');
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.workspaceManager.workspaces = data.items || [];
    if (!App.workspaceManager.workspaces.some(w => w.id === App.workspaceManager.selectedId)) {
      App.workspaceManager.selectedId = App.v2.workspaceId || App.workspaceManager.workspaces[0]?.id || null;
    }
    await loadWorkspaceManagerMatters();
    renderWorkspaceManager();
  } catch(e) {
    showToast('Failed to load workspaces: ' + e.message, 'error');
  }
}

function renderWorkspaceManagerSignedOut() {
  const empty = '<div class="council-row"><div class="council-card-desc">Sign in to manage workspaces and matters.</div></div>';
  const list = document.getElementById('workspace-manager-list');
  const detail = document.getElementById('workspace-manager-detail');
  const matters = document.getElementById('workspace-manager-matters');
  if (list) list.innerHTML = empty;
  if (detail) detail.innerHTML = empty;
  if (matters) matters.innerHTML = empty;
}

function renderWorkspaceManager() {
  renderWorkspaceManagerList();
  renderWorkspaceManagerDetail();
  renderWorkspaceManagerMatters();
}

function renderWorkspaceManagerList() {
  const list = document.getElementById('workspace-manager-list');
  if (!list) return;
  if (!App.workspaceManager.workspaces.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No workspaces yet.</div></div>';
    return;
  }
  list.innerHTML = App.workspaceManager.workspaces.map(w => {
    const selected = w.id === App.workspaceManager.selectedId;
    const canAdmin = w.role === 'admin' || App.v2.user?.is_system_admin;
    return `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${selected ? '✓ ' : ''}${esc(w.name)}</div>
          <div class="council-card-meta">${esc(w.slug || '')} · ${esc(w.role || 'member')}</div>
        </div>
        <span class="council-status ${canAdmin ? 'running' : 'completed'}">${esc(w.role || 'member')}</span>
      </div>
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="selectWorkspaceManagerWorkspace('${esc(w.id)}')">${selected ? 'Selected' : 'Open'}</button>
        ${canAdmin ? `<button class="danger-btn" type="button" onclick="deleteWorkspaceManagerWorkspace('${esc(w.id)}')">Delete</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

function renderWorkspaceManagerDetail() {
  const selected = workspaceManagerSelected();
  const detail = document.getElementById('workspace-manager-detail');
  el('workspace-manager-selected-title', selected ? selected.name : 'Selected Workspace');
  el('workspace-manager-selected-subtitle', selected ? `${selected.slug || 'no-slug'} · ${selected.role || 'member'}` : 'Select a workspace to manage its details and matters.');
  if (!detail) return;
  if (!selected) {
    detail.innerHTML = '<div class="council-row"><div class="council-card-desc">Select a workspace first.</div></div>';
    return;
  }
  const canAdmin = selected.role === 'admin' || App.v2.user?.is_system_admin;
  detail.innerHTML = `<div class="council-form-row">
      <div class="council-field"><label for="workspace-edit-name">Name</label><input class="council-input" id="workspace-edit-name" value="${esc(selected.name)}" ${canAdmin ? '' : 'disabled'}/></div>
      <div class="council-field"><label for="workspace-edit-slug">Slug</label><input class="council-input" id="workspace-edit-slug" value="${esc(selected.slug || '')}" ${canAdmin ? '' : 'disabled'}/></div>
    </div>
    <div class="council-actions">
      <button class="btn-secondary" type="button" onclick="setV2Workspace('${esc(selected.id)}')">Use in Blueprints</button>
      ${canAdmin ? '<button class="btn-primary" type="button" onclick="updateWorkspaceManagerWorkspace()">Save Workspace</button>' : '<span class="council-card-desc">Only workspace admins can edit workspace details.</span>'}
    </div>`;
}

async function loadWorkspaceManagerMatters() {
  App.workspaceManager.matters = [];
  if (!App.workspaceManager.selectedId) return;
  const r = await fetch(workspaceApi(App.workspaceManager.selectedId, '/matters?page_size=200'));
  if (!r.ok) throw new Error(await apiError(r));
  const data = await r.json();
  App.workspaceManager.matters = data.items || [];
}

function renderWorkspaceManagerMatters() {
  const list = document.getElementById('workspace-manager-matters');
  if (!list) return;
  const selected = workspaceManagerSelected();
  if (!selected) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">Select a workspace first.</div></div>';
    return;
  }
  if (!App.workspaceManager.matters.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No matters in this workspace yet.</div></div>';
    return;
  }
  list.innerHTML = App.workspaceManager.matters.map(m => `
    <div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(m.name)}</div>
          <div class="council-card-meta">${esc(m.status || 'active')}${m.client_name ? ' · ' + esc(m.client_name) : ''}</div>
        </div>
        <span class="council-status ${esc(m.status || 'active')}">${esc(m.status || 'active')}</span>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Name</label><input class="council-input matter-edit-name" data-id="${esc(m.id)}" value="${esc(m.name)}"/></div>
        <div class="council-field"><label>Client</label><input class="council-input matter-edit-client" data-id="${esc(m.id)}" value="${esc(m.client_name || '')}"/></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Status</label><select class="council-select matter-edit-status" data-id="${esc(m.id)}"><option value="active" ${m.status === 'active' ? 'selected' : ''}>Active</option><option value="paused" ${m.status === 'paused' ? 'selected' : ''}>Paused</option><option value="closed" ${m.status === 'closed' ? 'selected' : ''}>Closed</option></select></div>
        <div class="council-field"><label>Description</label><input class="council-input matter-edit-description" data-id="${esc(m.id)}" value="${esc(m.description || '')}"/></div>
      </div>
      <div class="council-actions">
        <button class="btn-primary" type="button" onclick="updateWorkspaceManagerMatter('${esc(m.id)}')">Save Matter</button>
        <button class="btn-secondary" type="button" onclick="focusWorkspaceManagerMatter('${esc(m.id)}')">Use Filter</button>
        <button class="danger-btn" type="button" onclick="deleteWorkspaceManagerMatter('${esc(m.id)}')">Delete</button>
      </div>
    </div>`).join('');
}

async function selectWorkspaceManagerWorkspace(workspaceId) {
  App.workspaceManager.selectedId = workspaceId;
  await loadWorkspaceManagerMatters();
  renderWorkspaceManager();
}

async function createWorkspaceManagerWorkspace() {
  const name = document.getElementById('workspace-name')?.value.trim();
  const slug = document.getElementById('workspace-slug')?.value.trim();
  if (!name) {
    showToast('Workspace name is required.', 'error');
    return;
  }
  try {
    const r = await fetch('/api/v2/workspaces', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, slug: slug || null})});
    if (!r.ok) throw new Error(await apiError(r));
    const workspace = await r.json();
    App.workspaceManager.selectedId = workspace.id;
    ['workspace-name','workspace-slug'].forEach(id => { const input = document.getElementById(id); if (input) input.value = ''; });
    await refreshV2Workspace(false);
    await loadWorkspaceManager();
    showToast('Workspace created.');
  } catch(e) {
    showToast('Failed to create workspace: ' + e.message, 'error');
  }
}

async function updateWorkspaceManagerWorkspace() {
  const selected = workspaceManagerSelected();
  if (!selected) return;
  const name = document.getElementById('workspace-edit-name')?.value.trim();
  const slug = document.getElementById('workspace-edit-slug')?.value.trim();
  if (!name) {
    showToast('Workspace name is required.', 'error');
    return;
  }
  try {
    const r = await fetch(workspaceApi(selected.id), {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, slug: slug || null})});
    if (!r.ok) throw new Error(await apiError(r));
    await refreshV2Workspace();
    await loadWorkspaceManager();
    showToast('Workspace saved.');
  } catch(e) {
    showToast('Failed to save workspace: ' + e.message, 'error');
  }
}

async function deleteWorkspaceManagerWorkspace(workspaceId) {
  const workspace = App.workspaceManager.workspaces.find(w => w.id === workspaceId);
  if (!workspace || !confirm(`Delete workspace "${workspace.name}"? This is a soft delete.`)) return;
  try {
    const r = await fetch(workspaceApi(workspaceId), {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.workspaceManager.selectedId === workspaceId) App.workspaceManager.selectedId = null;
    await refreshV2Workspace(false);
    await loadWorkspaceManager();
    showToast('Workspace deleted.');
  } catch(e) {
    showToast('Failed to delete workspace: ' + e.message, 'error');
  }
}

async function createWorkspaceManagerMatter() {
  const workspaceId = App.workspaceManager.selectedId;
  if (!workspaceId) {
    showToast('Select a workspace first.', 'error');
    return;
  }
  const payload = {
    name: document.getElementById('matter-name')?.value.trim(),
    client_name: document.getElementById('matter-client')?.value.trim() || null,
    status: document.getElementById('matter-status')?.value || 'active',
    description: document.getElementById('matter-description')?.value.trim() || null
  };
  if (!payload.name) {
    showToast('Matter name is required.', 'error');
    return;
  }
  try {
    const r = await fetch(workspaceApi(workspaceId, '/matters'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    ['matter-name','matter-client','matter-description'].forEach(id => { const input = document.getElementById(id); if (input) input.value = ''; });
    await loadWorkspaceManagerMatters();
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter created.');
  } catch(e) {
    showToast('Failed to create matter: ' + e.message, 'error');
  }
}

function matterManagerInput(selector, matterId) {
  return document.querySelector(`${selector}[data-id="${CSS.escape(matterId)}"]`);
}

async function updateWorkspaceManagerMatter(matterId) {
  const workspaceId = App.workspaceManager.selectedId;
  if (!workspaceId) return;
  const payload = {
    name: matterManagerInput('.matter-edit-name', matterId)?.value.trim(),
    client_name: matterManagerInput('.matter-edit-client', matterId)?.value.trim() || null,
    status: matterManagerInput('.matter-edit-status', matterId)?.value || 'active',
    description: matterManagerInput('.matter-edit-description', matterId)?.value.trim() || null
  };
  if (!payload.name) {
    showToast('Matter name is required.', 'error');
    return;
  }
  try {
    const r = await fetch(workspaceApi(workspaceId, `/matters/${encodeURIComponent(matterId)}`), {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    await loadWorkspaceManagerMatters();
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter saved.');
  } catch(e) {
    showToast('Failed to save matter: ' + e.message, 'error');
  }
}

async function deleteWorkspaceManagerMatter(matterId) {
  const workspaceId = App.workspaceManager.selectedId;
  const matter = App.workspaceManager.matters.find(m => m.id === matterId);
  if (!workspaceId || !matter || !confirm(`Delete matter "${matter.name}"? Linked blueprints and documents will be unassigned from this matter.`)) return;
  try {
    const r = await fetch(workspaceApi(workspaceId, `/matters/${encodeURIComponent(matterId)}`), {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadWorkspaceManagerMatters();
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter deleted.');
  } catch(e) {
    showToast('Failed to delete matter: ' + e.message, 'error');
  }
}

async function focusWorkspaceManagerMatter(matterId) {
  const workspaceId = App.workspaceManager.selectedId;
  if (!workspaceId) return;
  if (workspaceId !== App.v2.workspaceId) {
    await setV2Workspace(workspaceId);
  }
  App.v2.activeMatterId = matterId;
  renderV2MatterOptions();
  renderV2Blueprints();
  showToast('Matter filter updated.');
}

function showInitialCredentialReset() {
  document.getElementById('v2-auth-modal')?.classList.remove('open');
  const username = document.getElementById('v2-reset-username');
  const name = document.getElementById('v2-reset-name');
  if (username) username.value = App.v2.user?.username === 'rohas' ? '' : (App.v2.user?.username || '');
  if (name) name.value = App.v2.user?.display_name === 'Default Admin' ? '' : (App.v2.user?.display_name || '');
  const error = document.getElementById('v2-reset-error');
  if (error) { error.style.display = 'none'; error.textContent = ''; }
  document.getElementById('v2-reset-modal')?.classList.add('open');
}

async function submitInitialCredentialReset() {
  const username = document.getElementById('v2-reset-username')?.value.trim();
  const displayName = document.getElementById('v2-reset-name')?.value.trim();
  const password = document.getElementById('v2-reset-password')?.value || '';
  const confirm = document.getElementById('v2-reset-confirm')?.value || '';
  const error = document.getElementById('v2-reset-error');
  if (error) { error.style.display = 'none'; error.textContent = ''; }
  if (!username || !displayName || !password) {
    if (error) { error.textContent = 'Username, display name, and password are required.'; error.style.display = 'block'; }
    return;
  }
  if (password !== confirm) {
    if (error) { error.textContent = 'Passwords do not match.'; error.style.display = 'block'; }
    return;
  }
  if (password.length < 8) {
    if (error) { error.textContent = 'Password must be at least 8 characters.'; error.style.display = 'block'; }
    return;
  }
  try {
    const r = await fetch('/api/v2/auth/change-initial-credentials', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username, display_name: displayName, password})
    });
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.v2.user = data.user;
    document.getElementById('v2-reset-modal')?.classList.remove('open');
    await refreshV2Workspace();
    updateV2AuthSidebar();
    showToast('Admin credentials updated.');
  } catch(e) {
    if (error) { error.textContent = e.message; error.style.display = 'block'; }
  }
}

function v2WorkspacePath(path) {
  if (!App.v2.workspaceId) return null;
  return `/api/v2/workspaces/${encodeURIComponent(App.v2.workspaceId)}${path}`;
}

async function v2Fetch(path, options = {}) {
  if (!App.v2.enabled) return null;
  const url = path.startsWith('/api/v2/') ? path : v2WorkspacePath(path);
  if (!url) return null;
  const r = await fetch(url, options);
  if (r.status === 401 || r.status === 403) App.v2.enabled = false;
  return r;
}

async function loadV2Documents() {
  const r = await v2Fetch('/documents?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.documents = data.items || [];
}

async function loadAdminUsers() {
  if (!App.v2.user?.is_system_admin) return;
  try {
    const [usersRes, workspacesRes] = await Promise.all([
      fetch('/api/v2/admin/users?page_size=200'),
      fetch('/api/v2/admin/workspaces')
    ]);
    if (!usersRes.ok) throw new Error(await apiError(usersRes));
    if (!workspacesRes.ok) throw new Error(await apiError(workspacesRes));
    const users = await usersRes.json();
    const workspaces = await workspacesRes.json();
    App.adminUsers = users.items || [];
    App.adminWorkspaces = workspaces.items || [];
    renderAdminWorkspaceOptions();
    renderAdminUsers();
  } catch(e) {
    showToast('Failed to load users: ' + e.message, 'error');
  }
}

function renderAdminWorkspaceOptions() {
  const select = document.getElementById('admin-user-workspace');
  if (!select) return;
  select.innerHTML = '<option value="">No workspace</option>' + App.adminWorkspaces.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');
}

function renderAdminUsers() {
  const list = document.getElementById('admin-users-list');
  if (!list) return;
  if (!App.adminUsers.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No users found.</div></div>';
    return;
  }
  list.innerHTML = App.adminUsers.map(user => {
    const identityParts = [user.username, user.email].filter(Boolean);
    const identityMeta = Array.from(new Set(identityParts.map(part => part.trim()).filter(Boolean))).join(' · ');
    const memberships = (user.memberships || []).map(m => `
      <span class="stat-pill selectable" title="${esc(m.workspace_id)}">
        <strong>${esc(m.workspace_name)}</strong> ${esc(m.role)}
        <button class="mini-x" type="button" onclick="removeAdminUserMembership('${esc(user.id)}','${esc(m.workspace_id)}')">x</button>
      </span>
    `).join('') || '<span class="council-card-desc">No workspace access</span>';
    const workspaceOptions = ['<option value="">Add workspace</option>'].concat(App.adminWorkspaces.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`)).join('');
    return `
      <div class="council-row">
        <div class="council-row-head">
          <div>
            <div class="council-card-title">${esc(user.display_name)}</div>
            <div class="council-card-meta">${esc(identityMeta)}</div>
          </div>
          <div class="council-actions">
            <span class="council-status ${user.is_active ? 'completed' : 'error'}">${user.is_active ? 'active' : 'inactive'}</span>
            ${user.is_system_admin ? '<span class="council-status running">system admin</span>' : ''}
            ${user.must_change_credentials ? '<span class="council-status">reset required</span>' : ''}
          </div>
        </div>
        <div class="admin-user-fields">
          <input class="council-input admin-user-username" data-id="${esc(user.id)}" value="${esc(user.username || '')}" placeholder="Username"/>
          <input class="council-input admin-user-display" data-id="${esc(user.id)}" value="${esc(user.display_name || '')}" placeholder="Display name"/>
          <input class="council-input admin-user-email" data-id="${esc(user.id)}" value="${esc(user.email || '')}" placeholder="Email"/>
          <input class="council-input admin-user-password" data-id="${esc(user.id)}" type="password" value="" placeholder="New password" autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')"/>
        </div>
        <div class="admin-user-memberships">${memberships}</div>
        <div class="council-form-row">
          <div class="council-field"><select class="council-select admin-membership-workspace" data-id="${esc(user.id)}">${workspaceOptions}</select></div>
          <div class="council-field"><select class="council-select admin-membership-role" data-id="${esc(user.id)}"><option value="member">Member</option><option value="admin">Admin</option></select></div>
        </div>
        <div class="council-actions">
          <label class="admin-check"><input class="admin-user-active" data-id="${esc(user.id)}" type="checkbox" ${user.is_active ? 'checked' : ''}/> Active</label>
          <label class="admin-check"><input class="admin-user-system" data-id="${esc(user.id)}" type="checkbox" ${user.is_system_admin ? 'checked' : ''}/> System admin</label>
          <button class="btn-secondary" type="button" onclick="saveAdminUser('${esc(user.id)}')">Save</button>
          <button class="btn-secondary" type="button" onclick="resetAdminUserPassword('${esc(user.id)}')">Reset Password</button>
          <button class="btn-secondary" type="button" onclick="addAdminUserMembership('${esc(user.id)}')">Add Workspace</button>
          <button class="danger-btn" type="button" onclick="deleteAdminUser('${esc(user.id)}')">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

async function createAdminUser() {
  const payload = {
    username: document.getElementById('admin-user-username')?.value.trim(),
    display_name: document.getElementById('admin-user-display')?.value.trim(),
    email: document.getElementById('admin-user-email')?.value.trim() || null,
    password: document.getElementById('admin-user-password')?.value || '',
    workspace_id: document.getElementById('admin-user-workspace')?.value || null,
    workspace_role: document.getElementById('admin-user-role')?.value || 'member',
    is_system_admin: !!document.getElementById('admin-user-system-admin')?.checked
  };
  if (!payload.username || !payload.display_name || !payload.password) {
    showToast('Username, display name, and temporary password are required.', 'error');
    return;
  }
  try {
    const r = await fetch('/api/v2/admin/users', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    ['admin-user-username','admin-user-display','admin-user-email','admin-user-password'].forEach(id => { const input = document.getElementById(id); if (input) input.value = ''; });
    const adminToggle = document.getElementById('admin-user-system-admin'); if (adminToggle) adminToggle.checked = false;
    await loadAdminUsers();
    showToast('User created.');
  } catch(e) { showToast('Failed to create user: ' + e.message, 'error'); }
}

function adminInput(selector, userId) {
  return document.querySelector(`${selector}[data-id="${CSS.escape(userId)}"]`);
}

async function saveAdminUser(userId) {
  const payload = {
    username: adminInput('.admin-user-username', userId)?.value.trim(),
    display_name: adminInput('.admin-user-display', userId)?.value.trim(),
    email: adminInput('.admin-user-email', userId)?.value.trim() || null,
    is_active: !!adminInput('.admin-user-active', userId)?.checked,
    is_system_admin: !!adminInput('.admin-user-system', userId)?.checked
  };
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    await loadAdminUsers();
    showToast('User saved.');
  } catch(e) { showToast('Failed to save user: ' + e.message, 'error'); }
}

async function resetAdminUserPassword(userId) {
  const password = adminInput('.admin-user-password', userId)?.value || '';
  if (!password) {
    showToast('Enter a new password first.', 'error');
    return;
  }
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}/reset-password`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password, must_change_credentials:true})});
    if (!r.ok) throw new Error(await apiError(r));
    await loadAdminUsers();
    showToast('Password reset.');
  } catch(e) { showToast('Failed to reset password: ' + e.message, 'error'); }
}

async function deleteAdminUser(userId) {
  if (!confirm('Delete this user? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadAdminUsers();
    showToast('User deleted.');
  } catch(e) { showToast('Failed to delete user: ' + e.message, 'error'); }
}

async function addAdminUserMembership(userId) {
  const workspace = adminInput('.admin-membership-workspace', userId)?.value;
  const role = adminInput('.admin-membership-role', userId)?.value || 'member';
  if (!workspace) {
    showToast('Choose a workspace first.', 'error');
    return;
  }
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}/memberships`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({workspace_id:workspace, role})});
    if (!r.ok) throw new Error(await apiError(r));
    await loadAdminUsers();
    showToast('Workspace access added.');
  } catch(e) { showToast('Failed to add workspace: ' + e.message, 'error'); }
}

async function removeAdminUserMembership(userId, workspaceId) {
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}/memberships/${encodeURIComponent(workspaceId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadAdminUsers();
    showToast('Workspace access removed.');
  } catch(e) { showToast('Failed to remove workspace: ' + e.message, 'error'); }
}

async function loadV2Matters() {
  const r = await v2Fetch('/matters?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.matters = data.items || [];
}

async function loadV2Blueprints() {
  const r = await v2Fetch('/blueprints?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.blueprints = data.items || [];
}

async function loadV2Plugins() {
  const r = await v2Fetch('/plugins?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.plugins = data.items || [];
}

async function loadV2ShellData() {
  await Promise.all([loadV2Matters(), loadV2Blueprints(), loadV2Plugins(), loadV2Documents(), loadV2Personas(), loadV2Secrets()]);
  renderV2Shell();
  updateChatScopeControls();
}

function v2DocumentByNameAndSize(doc) {
  return App.v2.documents.find(v2 =>
    v2.original_name === doc.original_name &&
    (v2.size_bytes || 0) === (doc.size_bytes || 0)
  );
}

async function loadV2Personas() {
  const r = await v2Fetch('/personas?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.personas = data.items || [];
}

async function loadV2Secrets() {
  const r = await v2Fetch('/secrets?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.secrets = data.items || [];
}

async function mirrorUploadToV2(file) {
  if (!App.v2.enabled) return;
  try {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('scope', 'workspace');
    const r = await v2Fetch('/documents/upload', {method:'POST', body:fd});
    if (r && r.ok) await loadV2Documents();
  } catch(e) {}
}

async function deleteV2DocumentForLegacyDoc(doc) {
  if (!App.v2.enabled || !doc) return;
  try {
    await loadV2Documents();
    const v2Doc = v2DocumentByNameAndSize(doc);
    if (!v2Doc) return;
    const r = await v2Fetch(`/documents/${encodeURIComponent(v2Doc.id)}`, {method:'DELETE'});
    if (r && r.ok) await loadV2Documents();
  } catch(e) {}
}

async function deleteAllV2Documents() {
  if (!App.v2.enabled) return;
  try {
    const r = await v2Fetch('/documents', {method:'DELETE'});
    if (r && r.ok) App.v2.documents = [];
  } catch(e) {}
}

async function upsertV2Secret(name, value) {
  if (!App.v2.enabled || !value || value === '••••••••') return;
  try {
    await loadV2Secrets();
    const existing = App.v2.secrets.find(s => s.name === name);
    const payload = {name, value, scope:'workspace'};
    const r = existing
      ? await v2Fetch(`/secrets/${encodeURIComponent(existing.id)}/rotate`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)})
      : await v2Fetch('/secrets', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (r && r.ok) await loadV2Secrets();
  } catch(e) {}
}

async function updateV2Setting(key, value) {
  if (!App.v2.enabled) return;
  try {
    await v2Fetch(`/settings/${encodeURIComponent(key)}`, {
      method:'PUT',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({value})
    });
  } catch(e) {}
}

async function syncV2RuntimeSettings(settings) {
  if (!App.v2.enabled) return;
  if (settings.max_file_size_mb != null) {
    const maxUploadSize = parseInt(settings.max_file_size_mb, 10);
    if (!Number.isNaN(maxUploadSize)) await updateV2Setting('max_upload_size_mb', maxUploadSize);
  }
}

function v2PluginLabel(pluginId) {
  const labels = {contract_review:'Contract Review', ai_council:'AI Council', legal_research:'Legal Research'};
  return labels[pluginId] || pluginId;
}

function renderV2Shell() {
  const workspaceSelect = document.getElementById('v2-workspace-select');
  if (!workspaceSelect) return;
  if (!App.v2.enabled) {
    workspaceSelect.innerHTML = '<option>Sign in to multi-user access</option>';
    el('v2-stat-matters', '0');
    el('v2-stat-blueprints', '0');
    el('v2-stat-documents', '0');
    const empty = '<div class="council-row"><div class="council-card-desc">Sign in to use v2 workspaces, matters, and blueprints.</div></div>';
    const matters = document.getElementById('v2-matters-list');
    const blueprints = document.getElementById('v2-blueprints-list');
    const plugins = document.getElementById('v2-plugins-grid');
    if (matters) matters.innerHTML = empty;
    if (blueprints) blueprints.innerHTML = empty;
    if (plugins) plugins.innerHTML = empty;
    return;
  }
  workspaceSelect.innerHTML = App.v2.workspaces.map(w => `<option value="${esc(w.workspace_id)}">${esc(w.workspace_name || w.name || 'Workspace')}</option>`).join('');
  workspaceSelect.value = App.v2.workspaceId || '';
  el('v2-stat-matters', App.v2.matters.length);
  el('v2-stat-blueprints', App.v2.blueprints.length);
  el('v2-stat-documents', App.v2.documents.length);
  renderV2MatterOptions();
  renderV2Matters();
  renderV2Blueprints();
  renderV2Plugins();
}

function renderV2MatterOptions() {
  const filter = document.getElementById('v2-matter-filter');
  const blueprintMatter = document.getElementById('v2-blueprint-matter');
  const options = App.v2.matters.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  if (filter) {
    filter.innerHTML = `<option value="all">All matters</option>${options}`;
    filter.value = App.v2.activeMatterId && App.v2.activeMatterId !== '' ? App.v2.activeMatterId : 'all';
  }
  if (blueprintMatter) {
    blueprintMatter.innerHTML = options;
    const active = App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : '';
    blueprintMatter.value = active;
  }
  const pluginSelect = document.getElementById('v2-blueprint-plugin');
  if (pluginSelect) {
    const plugins = App.v2.plugins.filter(p => p.workspace_enabled);
    pluginSelect.innerHTML = plugins.length
      ? plugins.map(p => `<option value="${esc(p.id)}">${esc(v2PluginLabel(p.id))}</option>`).join('')
      : '<option value="">Enable a plugin first</option>';
  }
}

function renderV2Matters() {
  const list = document.getElementById('v2-matters-list');
  if (!list) return;
  if (!App.v2.matters.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No matters yet.</div></div>';
    return;
  }
  list.innerHTML = App.v2.matters.map(m => {
    const count = App.v2.blueprints.filter(b => b.matter_id === m.id).length;
    const client = m.client_name ? ` · ${esc(m.client_name)}` : '';
    return `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(m.name)}</div>
          <div class="council-card-meta">${esc(m.status || 'active')}${client} · ${count} blueprint${count === 1 ? '' : 's'}</div>
        </div>
        <span class="council-status ${esc(m.status || 'active')}">${esc(m.status || 'active')}</span>
      </div>
      ${m.description ? `<div class="council-card-desc">${esc(m.description)}</div>` : ''}
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="focusV2Matter('${m.id}')">Open</button>
        <button class="danger-btn" type="button" onclick="deleteV2Matter('${m.id}')">Delete</button>
      </div>
    </div>`;
  }).join('');
}

function renderV2Blueprints() {
  const list = document.getElementById('v2-blueprints-list');
  if (!list) return;
  const active = App.v2.activeMatterId || 'all';
  const rows = App.v2.blueprints.filter(b => active === 'all' || (active === '' ? !b.matter_id : b.matter_id === active));
  if (!rows.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No blueprints for this filter.</div></div>';
    renderV2PluginWorkspace();
    return;
  }
  list.innerHTML = rows.map(b => {
    const matter = App.v2.matters.find(m => m.id === b.matter_id);
    const metaParts = [v2PluginLabel(b.plugin_id), matter?.name, b.role || 'member'].filter(Boolean);
    return `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(b.name)}</div>
          <div class="council-card-meta">${esc(metaParts.join(' · '))}</div>
        </div>
        <span class="council-status ${esc(b.status || 'active')}">${esc(b.status || 'active')}</span>
      </div>
      ${b.description ? `<div class="council-card-desc">${esc(b.description)}</div>` : ''}
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="openV2Blueprint('${b.id}')">Open</button>
        <button class="danger-btn" type="button" onclick="deleteV2Blueprint('${b.id}')">Delete</button>
      </div>
    </div>`;
  }).join('');
  renderV2PluginWorkspace();
}

function renderV2Plugins() {
  const grid = document.getElementById('v2-plugins-grid');
  if (!grid) return;
  if (!App.v2.plugins.length) {
    grid.innerHTML = '<div class="council-card"><div class="council-card-desc">No v2 plugins available.</div></div>';
    return;
  }
  grid.innerHTML = App.v2.plugins.map(p => `<div class="council-card">
    <div class="council-card-title">${esc(p.name || v2PluginLabel(p.id))}</div>
    <div class="council-card-meta">${p.workspace_enabled ? 'Enabled' : 'Disabled'} · ${esc(p.id)}</div>
    <div class="council-card-desc">${esc(p.description || 'Plugin-backed blueprint workflow.')}</div>
    <div class="council-actions">
      <button class="${p.workspace_enabled ? 'btn-secondary' : 'btn-primary'}" type="button" onclick="setV2PluginEnabled('${p.id}', ${p.workspace_enabled ? 'false' : 'true'})">${p.workspace_enabled ? 'Disable' : 'Enable'}</button>
    </div>
  </div>`).join('');
}

function v2PluginApiSegment(pluginId) {
  return {contract_review:'contract-review', ai_council:'council', legal_research:'legal-research'}[pluginId] || pluginId;
}

function defaultV2PluginConfig(pluginId) {
  if (pluginId === 'ai_council') {
    return {
      name: 'AI Council',
      agents: [{id:'agent_1', name:'Reviewer', instructions:'Assess the issue and cite document evidence.', provider:'default', model:'default', temperature:0.2, max_tokens:1200, context_access:['documents','user_prompt'], output_type:'analysis', require_citations:true}],
      phases: [{id:'phase_1', name:'Review', mode:'sequential', agents:['agent_1'], instructions:'Produce a practical answer with citations.', retrieval_query:'objective'}]
    };
  }
  if (pluginId === 'legal_research') return {jurisdiction:'', memo_format:'IRAC', authorities_required:true};
  return {review_standard:'balanced', jurisdiction:'', risk_tolerance:'medium'};
}

function v2PluginRunFields(blueprint) {
  if (!blueprint) return '';
  if (blueprint.plugin_id === 'legal_research') {
    return '<div class="council-field"><label for="v2-plugin-run-title">Run title</label><input class="council-input" id="v2-plugin-run-title" placeholder="Research memo"/></div><div class="council-field"><label for="v2-plugin-run-question">Question</label><textarea class="council-textarea" id="v2-plugin-run-question" placeholder="What legal question should this research answer?"></textarea></div>';
  }
  if (blueprint.plugin_id === 'ai_council') {
    return '<div class="council-field"><label for="v2-plugin-run-title">Run title</label><input class="council-input" id="v2-plugin-run-title" placeholder="Council run"/></div><div class="council-field"><label for="v2-plugin-run-objective">Objective</label><textarea class="council-textarea" id="v2-plugin-run-objective" placeholder="What should the council decide or analyze?"></textarea></div>';
  }
  return '<div class="council-field"><label for="v2-plugin-run-title">Run title</label><input class="council-input" id="v2-plugin-run-title" placeholder="Contract review"/></div>';
}

function v2RunJob(runId) {
  return App.v2.pluginJobs?.[runId] || null;
}

function v2JobElapsed(job) {
  const started = Date.parse(job?.started_at || job?.created_at || '');
  if (!started) return '0s';
  return Math.max(0, Math.floor((Date.now() - started) / 1000)) + 's';
}

function renderV2RunProgress(run) {
  const job = v2RunJob(run.id);
  if (!job || !['pending','running'].includes(job.status || run.status)) return '';
  const events = App.v2.pluginJobEvents?.[job.id] || [];
  const latest = events.slice().reverse().find(e => e.content)?.content || job.status || run.status;
  const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
  return `<div class="run-progress" data-job-id="${esc(job.id)}">
    <div class="run-progress-head">
      <span>${esc(latest)}</span>
      <span>${v2JobElapsed(job)} elapsed · ${progress}%</span>
    </div>
    <div class="progress-bar"><div class="progress-fill" data-csp-style="width:${progress}%"></div></div>
  </div>`;
}

function renderV2RunActions(blueprint, run) {
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  const base = `/api/v2/workspaces/${encodeURIComponent(App.v2.workspaceId)}/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(run.id)}`;
  if (blueprint.plugin_id === 'contract_review') {
    return `
      <button class="btn-secondary" type="button" onclick="exportV2PluginRun('${esc(run.id)}')">Export</button>
      <button class="danger-btn" type="button" onclick="deleteV2PluginRun('${esc(run.id)}')">Delete</button>
    `;
  }
  return `
    <button class="btn-secondary" type="button" onclick="exportV2PluginRun('${esc(run.id)}')">Export</button>
    <button class="danger-btn" type="button" onclick="deleteV2PluginRun('${esc(run.id)}')">Delete</button>
  `;
}

function renderV2PluginWorkspace() {
  const host = document.getElementById('v2-plugin-workspace');
  if (!host) return;
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) {
    host.style.display = 'none';
    host.innerHTML = '';
    return;
  }
  host.style.display = 'block';
  const matter = App.v2.matters.find(m => m.id === blueprint.matter_id);
  const config = App.v2.pluginConfig || defaultV2PluginConfig(blueprint.plugin_id);
  const runs = App.v2.pluginRuns || [];
  host.innerHTML = `
    <div class="settings-card-header">
      <div><div class="settings-card-title">${esc(blueprint.name)}</div><div class="settings-card-subtitle">${esc(v2PluginLabel(blueprint.plugin_id))}${matter ? ' · ' + esc(matter.name) : ''}</div></div>
      <button class="btn-secondary" type="button" onclick="openV2BlueprintChat('${esc(blueprint.id)}')">Chat</button>
    </div>
    <div class="council-form v2-plugin-workspace-body">
      <div class="settings-section-desc">Plugin config</div>
      <div class="council-field"><textarea class="council-textarea" id="v2-plugin-config-json">${esc(JSON.stringify(config, null, 2))}</textarea></div>
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="saveV2PluginConfig()">Save Config</button>
        <button class="btn-secondary" type="button" onclick="loadV2PluginData()">Refresh</button>
      </div>
      <div class="settings-section-desc">New run</div>
      ${v2PluginRunFields(blueprint)}
      <div class="council-actions"><button class="btn-primary" type="button" onclick="runV2Plugin()">Run ${esc(v2PluginLabel(blueprint.plugin_id))}</button></div>
      <div class="settings-section-desc">Runs</div>
      <div class="council-list">
        ${runs.length ? runs.map(run => `<div class="council-row">
          <div class="council-row-head">
            <div><div class="council-card-title">${esc(run.title || 'Run')}</div><div class="council-card-meta">${esc(new Date(run.created_at).toLocaleString())}</div></div>
            <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
          </div>
          ${renderV2RunProgress(run)}
          ${run.error ? `<div class="council-card-desc" data-csp-style="color:var(--danger)">${esc(run.error)}</div>` : ''}
          <div class="council-actions">
            ${renderV2RunActions(blueprint, run)}
          </div>
        </div>`).join('') : '<div class="council-row"><div class="council-card-desc">No runs yet.</div></div>'}
      </div>
        </div>
  `;
}

async function loadV2PluginData() {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  App.v2.pluginConfig = null;
  App.v2.pluginRuns = [];
  const config = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/config`);
  App.v2.pluginConfig = config?.ok ? (await config.json()).config : defaultV2PluginConfig(blueprint.plugin_id);
  const runs = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs?page_size=50`);
  if (runs?.ok) App.v2.pluginRuns = (await runs.json()).items || [];
  await loadV2PluginJobs(blueprint);
  renderV2PluginWorkspace();
}

async function loadV2PluginJobs(blueprint) {
  const r = await v2Fetch('/jobs?page_size=100');
  if (!r?.ok) return;
  const jobs = (await r.json()).items || [];
  const next = {};
  jobs.forEach(job => {
    const meta = job.metadata || {};
    if (meta.blueprint_id === blueprint.id && meta.run_id) {
      next[meta.run_id] = job;
      if (['pending','running'].includes(job.status)) startV2JobStream(job);
    }
  });
  App.v2.pluginJobs = {...App.v2.pluginJobs, ...next};
}

async function saveV2PluginConfig() {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  let config;
  try { config = JSON.parse(document.getElementById('v2-plugin-config-json')?.value || '{}'); }
  catch(e) { showToast('Config must be valid JSON.', 'error'); return; }
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/config`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({config})});
    if (!r?.ok) throw new Error(await apiError(r));
    App.v2.pluginConfig = (await r.json()).config;
    renderV2PluginWorkspace();
    showToast('Config saved.');
  } catch(e) { showToast('Save failed: ' + e.message, 'error'); }
}

async function runV2Plugin() {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  const title = document.getElementById('v2-plugin-run-title')?.value.trim() || blueprint.name;
  const body = {title};
  if (blueprint.plugin_id === 'legal_research') {
    const question = document.getElementById('v2-plugin-run-question')?.value.trim();
    if (!question) { showToast('Question is required.', 'error'); return; }
    body.question = question;
  }
  if (blueprint.plugin_id === 'ai_council') {
    const objective = document.getElementById('v2-plugin-run-objective')?.value.trim();
    if (!objective) { showToast('Objective is required.', 'error'); return; }
    body.objective = objective;
  }
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!r?.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data?.job) {
      App.v2.pluginJobs[data.id] = data.job;
      startV2JobStream(data.job);
    }
    showToast('Run started.');
    await loadV2PluginData();
  } catch(e) { showToast('Run failed: ' + e.message, 'error'); }
}

async function deleteV2PluginRun(runId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint || !confirm('Delete this run?')) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}`, {method:'DELETE'});
    if (!r?.ok) throw new Error(await apiError(r));
    await loadV2PluginData();
    showToast('Run deleted.');
  } catch(e) { showToast('Delete failed: ' + e.message, 'error'); }
}

async function exportV2PluginRun(runId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}/export`);
    if (!r?.ok) throw new Error(await apiError(r));
    const text = await r.text();
    const w = window.open('', '_blank');
    if (w) {
      w.document.write(`<pre data-csp-style="white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;padding:20px">${esc(text)}</pre>`);
      w.document.close();
    }
  } catch(e) { showToast('Export failed: ' + e.message, 'error'); }
}

function startV2JobStream(job) {
  if (!job?.id || !App.v2.workspaceId || App.v2.pluginJobStreams[job.id]) return;
  const url = `/api/v2/workspaces/${encodeURIComponent(App.v2.workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`;
  const source = new EventSource(url);
  App.v2.pluginJobStreams[job.id] = source;
  App.v2.pluginJobEvents[job.id] = App.v2.pluginJobEvents[job.id] || [];
  App.v2.pluginJobTimers[job.id] = setInterval(renderV2PluginWorkspace, 1000);
  source.onmessage = event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    const meta = data.metadata || {};
    const currentJob = meta.id ? meta : (data.type === 'status' && meta.metadata ? meta : null);
    if (currentJob?.id) {
      const runId = currentJob.metadata?.run_id || job.metadata?.run_id;
      if (runId) App.v2.pluginJobs[runId] = currentJob;
    }
    if (data.type && data.type !== 'status') {
      App.v2.pluginJobEvents[job.id].push(data);
      App.v2.pluginJobEvents[job.id] = App.v2.pluginJobEvents[job.id].slice(-8);
    }
    if (data.type === 'done') {
      stopV2JobStream(job.id);
      loadV2PluginData();
    } else {
      renderV2PluginWorkspace();
    }
  };
  source.onerror = () => {
    stopV2JobStream(job.id);
  };
}

function stopV2JobStream(jobId) {
  App.v2.pluginJobStreams[jobId]?.close();
  delete App.v2.pluginJobStreams[jobId];
  if (App.v2.pluginJobTimers[jobId]) clearInterval(App.v2.pluginJobTimers[jobId]);
  delete App.v2.pluginJobTimers[jobId];
}

function openV2BlueprintChat(blueprintId) {
  const blueprint = App.v2.blueprints.find(b => b.id === blueprintId);
  if (!blueprint) return;
  App.v2.activeBlueprintId = blueprintId;
  App.v2.activeMatterId = blueprint.matter_id || '';
  App.chatMode = 'documents';
  App.selectedDocIds = 'all';
  switchView('chat');
  updateChatModeUI();
}

async function loadV2Shell() {
  if (!App.v2.enabled) {
    await initV2();
  } else {
    await loadV2ShellData();
  }
  renderV2Shell();
}

async function setV2Workspace(workspaceId) {
  if (!workspaceId || workspaceId === App.v2.workspaceId) return;
  App.v2.workspaceId = workspaceId;
  App.v2.activeMatterId = 'all';
  App.v2.activeBlueprintId = null;
  await loadV2ShellData();
}

function setV2MatterFilter(matterId) {
  App.v2.activeMatterId = matterId;
  App.v2.activeBlueprintId = null;
  renderV2Shell();
  updateDocSelector();
}

function focusV2Matter(matterId) {
  App.v2.activeMatterId = matterId;
  App.v2.activeBlueprintId = null;
  renderV2Shell();
  updateDocSelector();
  switchView('blueprints');
}

function switchBlueprintTab(tab, button) {
  document.querySelectorAll('[id^="blueprint-panel-"]').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('#view-blueprints .council-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('blueprint-panel-' + tab)?.classList.add('active');
  if (button) button.classList.add('active');
  else document.querySelector(`#view-blueprints .council-tab[onclick*="'${tab}'"]`)?.classList.add('active');
}

async function createV2Matter() {
  if (!App.v2.enabled) { showToast('Sign in to multi-user access first.', 'error'); return; }
  const name = document.getElementById('v2-matter-name')?.value.trim();
  const client = document.getElementById('v2-matter-client')?.value.trim();
  const description = document.getElementById('v2-matter-description')?.value.trim();
  if (!name) { showToast('Matter name is required.', 'error'); return; }
  try {
    const r = await v2Fetch('/matters', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, client_name:client || null, description:description || null})});
    if (!r || !r.ok) throw new Error(await apiError(r));
    document.getElementById('v2-matter-name').value = '';
    document.getElementById('v2-matter-client').value = '';
    document.getElementById('v2-matter-description').value = '';
    await loadV2ShellData();
    showToast('Matter created.');
  } catch(e) { showToast('Failed to create matter: ' + e.message, 'error'); }
}

async function deleteV2Matter(matterId) {
  if (!confirm('Delete this matter? Blueprints and documents will remain but lose the matter link.')) return;
  try {
    const r = await v2Fetch(`/matters/${encodeURIComponent(matterId)}`, {method:'DELETE'});
    if (!r || !r.ok) throw new Error(await apiError(r));
    if (App.v2.activeMatterId === matterId) App.v2.activeMatterId = 'all';
    await loadV2ShellData();
    showToast('Matter deleted.');
  } catch(e) { showToast('Failed to delete matter: ' + e.message, 'error'); }
}

async function createV2Blueprint() {
  if (!App.v2.enabled) { showToast('Sign in to multi-user access first.', 'error'); return; }
  const name = document.getElementById('v2-blueprint-name')?.value.trim();
  const pluginId = document.getElementById('v2-blueprint-plugin')?.value;
  const matterId = document.getElementById('v2-blueprint-matter')?.value || null;
  const status = document.getElementById('v2-blueprint-status')?.value || 'active';
  const description = document.getElementById('v2-blueprint-description')?.value.trim();
  if (!name || !pluginId) { showToast('Blueprint name and enabled plugin are required.', 'error'); return; }
  try {
    const body = {name, plugin_id:pluginId, matter_id:matterId, status, description:description || null};
    const r = await v2Fetch('/blueprints', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    if (!r || !r.ok) throw new Error(await apiError(r));
    document.getElementById('v2-blueprint-name').value = '';
    document.getElementById('v2-blueprint-description').value = '';
    await loadV2ShellData();
    showToast('Blueprint created.');
  } catch(e) { showToast('Failed to create blueprint: ' + e.message, 'error'); }
}

async function deleteV2Blueprint(blueprintId) {
  if (!confirm('Delete this blueprint and its plugin runs? This cannot be undone.')) return;
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprintId)}`, {method:'DELETE'});
    if (!r || !r.ok) throw new Error(await apiError(r));
    await loadV2ShellData();
    showToast('Blueprint deleted.');
  } catch(e) { showToast('Failed to delete blueprint: ' + e.message, 'error'); }
}

async function setV2PluginEnabled(pluginId, enabled) {
  try {
    const r = await v2Fetch(`/plugins/${encodeURIComponent(pluginId)}`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled})});
    if (!r || !r.ok) throw new Error(await apiError(r));
    await loadV2ShellData();
    showToast(enabled ? 'Plugin enabled.' : 'Plugin disabled.');
  } catch(e) { showToast('Failed to update plugin: ' + e.message, 'error'); }
}

async function openV2Blueprint(blueprintId) {
  const blueprint = App.v2.blueprints.find(b => b.id === blueprintId);
  if (!blueprint) return;
  App.v2.activeBlueprintId = blueprintId;
  App.v2.activeMatterId = blueprint.matter_id || '';
  App.chatMode = 'documents';
  App.selectedDocIds = 'all';
  switchView('blueprints');
  updateChatModeUI();
  renderV2Shell();
  await loadV2PluginData();
  showToast(`${blueprint.name} selected.`);
}

async function checkFirstRun() {
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    if (d.first_run) {
      const b = document.getElementById('first-run-banner');
      if (b) b.style.display = 'flex';
    }
  } catch(e) {}
}

// ── SETTINGS ───────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch('/api/settings');
    App.settings = await r.json();
    applySettings();
    populateSettingsUI();
  } catch(e) {}
}

function applySettings() {
  const s = App.settings;
  document.documentElement.setAttribute('data-theme', s.dark_mode === 'true' ? 'dark' : 'light');
  if (s.font_size) document.body.style.fontSize = s.font_size + 'px';
  if (s.app_name) {
    const title = document.getElementById('welcome-title');
    if (title) title.textContent = s.app_name;
    document.title = s.app_name;
  }
  if (s.app_intro) { const el = document.getElementById('welcome-intro'); if (el) el.textContent = s.app_intro; }
  if (s.suggested_questions) {
    try {
      const qs = JSON.parse(s.suggested_questions);
      const chips = document.getElementById('suggestion-chips-list');
      if (chips && Array.isArray(qs)) chips.innerHTML = qs.map(q => `<div class="chip" onclick="fillInput(this)">${esc(q)}</div>`).join('');
    } catch(e) {}
  }
  updateDocSelector();
}

function populateSettingsUI() {
  const s = App.settings;
  const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
  const tog = (id, on) => { const el = document.getElementById(id); if (el) { el.classList.toggle('on', !!on); } };
  const chatProvider = document.getElementById('sel-chat-provider');
  if (chatProvider) chatProvider.value = s.local_llm_provider || 'openai';
  renderChatModelOptions();
  set('sel-chat-model', s.chat_model);
  set('sel-max-tokens', s.max_tokens);
  set('sel-embedding-provider', s.embedding_provider || 'openai');
  set('sel-embedding-model', s.embedding_model);
  const tempEl = document.getElementById('sl-temperature');
  if (tempEl && s.temperature) { tempEl.value = Math.round(parseFloat(s.temperature) * 100); tempEl.nextElementSibling.textContent = parseFloat(s.temperature).toFixed(1); }
  const topkEl = document.getElementById('sl-top-k');
  if (topkEl && s.top_k) { topkEl.value = s.top_k; topkEl.nextElementSibling.textContent = s.top_k; }
  const simEl = document.getElementById('sl-similarity');
  if (simEl && s.similarity_threshold) { simEl.value = Math.round(parseFloat(s.similarity_threshold) * 100); simEl.nextElementSibling.textContent = parseFloat(s.similarity_threshold).toFixed(2); }
  const csEl = document.getElementById('sl-chunk-size');
  if (csEl && s.chunk_size) { csEl.value = s.chunk_size; csEl.nextElementSibling.textContent = s.chunk_size; }
  const coEl = document.getElementById('sl-chunk-overlap');
  if (coEl && s.chunk_overlap) { coEl.value = s.chunk_overlap; coEl.nextElementSibling.textContent = s.chunk_overlap; }
  set('sel-retrieval', s.retrieval_strategy);
  set('sel-response-length', s.response_length);
  set('sel-response-language', 'English');
  if (s.response_language) {
    const langSel = document.getElementById('sel-response-language');
    if (langSel) { for (let o of langSel.options) { if (o.value === s.response_language || o.text.startsWith(s.response_language)) { langSel.value = o.value; break; } } }
  }
  tog('tog-always-sources', s.always_show_sources === 'true');
  tog('tog-stream', s.stream_responses !== 'false');
  tog('tog-auto-detect', s.auto_detect_language === 'true');
  tog('appearance-dark-toggle', s.dark_mode === 'true');
  set('sel-font-size', s.font_size);
  set('inp-app-name', s.app_name);
  set('inp-app-intro', s.app_intro);
  renderQuestionsList(s.suggested_questions);
  set('sel-max-file-size', s.max_file_size_mb);
  set('sel-auto-delete', s.auto_delete_days);
  const ragSel = document.getElementById('rag-provider-select');
  if (ragSel && s.rag_provider) { ragSel.value = s.rag_provider; onRagProviderChange(s.rag_provider); }
  set('ollama-base-url-input', s.ollama_base_url || 'http://localhost:11434');
  set('ollama-api-key-input', s.ollama_api_key ? '••••••••' : '');
  renderEmailControls();
  // Show connected status for API keys
  document.querySelectorAll('.provider-card').forEach(card => {
    const name = card.querySelector('.provider-name')?.textContent?.trim();
    const keyMap = { 'OpenAI':'openai_api_key','OpenRouter':'openrouter_api_key','Anthropic':'anthropic_api_key','Google Gemini':'gemini_api_key','Mistral AI':'mistral_api_key','Cohere':'cohere_api_key','Groq':'groq_api_key','Ollama':'ollama_api_key','xAI (Grok)':'xai_api_key','Cloudflare Workers AI':'cloudflare_api_key','Together AI':'together_api_key','Brave Search':'brave_search_api_key','SearXNG':'searxng_base_url' };
    const k = keyMap[name];
    const status = card.querySelector('.provider-status');
    const input = card.querySelector('.key-input');
    const hasValue = !!(k && s[k] && s[k] !== '');
    if (k && status) {
      status.textContent = hasValue ? 'Connected' : (name === 'Ollama' ? 'Local default' : 'Not connected');
      status.className = hasValue ? 'provider-status connected' : 'provider-status not-connected';
    }
    if (input && k) input.value = hasValue ? '••••••••' : '';
  });
}

async function saveSettings(obj) {
  try {
    const r = await fetch('/api/settings', { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({settings:obj}) });
    const d = await r.json();
    if (d.ok) { showToast('Settings saved.'); await loadSettings(); }
    else showToast(d.error || 'Save failed.', 'error');
  } catch(e) { showToast('Save failed: ' + e.message, 'error'); }
}

async function loadModels() {
  try {
    const r = await fetch('/api/models');
    App.models = await r.json();
    renderChatProviderOptions();
    renderChatModelOptions();
    renderModelRegistry();
    renderCouncilBuilder();
  } catch(e) {}
}

function providerLabel(provider) {
  const labels = {
    openai:'OpenAI',
    openrouter:'OpenRouter',
    anthropic:'Anthropic',
    groq:'Groq',
    ollama:'Ollama',
    gemini:'Google Gemini',
    mistral:'Mistral AI',
    cohere:'Cohere',
    xai:'xAI',
    cloudflare:'Cloudflare Workers AI',
    together:'Together AI'
  };
  return labels[provider] || provider;
}

function runnableModelProviders() {
  const supported = ['openai', 'openrouter', 'anthropic', 'groq', 'ollama'];
  const providers = modelProviders().filter(p => supported.includes(p));
  return providers.length ? providers : ['openai', 'groq', 'ollama'];
}

function modelProviders() {
  const providers = [...new Set(App.models.map(m => m.provider))];
  return providers.length ? providers : ['openai', 'groq', 'ollama'];
}

function enabledModels(provider) {
  return App.models.filter(m => m.enabled && (!provider || m.provider === provider));
}

function renderChatProviderOptions() {
  const sel = document.getElementById('sel-chat-provider');
  if (!sel) return;
  const current = sel.value || App.settings.local_llm_provider || 'openai';
  const providers = runnableModelProviders();
  sel.innerHTML = providers.map(p => `<option value="${esc(p)}">${esc(providerLabel(p))}</option>`).join('');
  sel.value = providers.includes(current) ? current : (providers[0] || 'openai');
}

function renderChatModelOptions() {
  const sel = document.getElementById('sel-chat-model');
  const provider = document.getElementById('sel-chat-provider')?.value || 'openai';
  if (!sel) return;
  const current = sel.value || App.settings.chat_model || '';
  const models = enabledModels(provider);
  sel.innerHTML = models.map(m => `<option value="${esc(m.model_id)}">${esc(m.display_name)} (${esc(m.model_id)})</option>`).join('');
  if (models.some(m => m.model_id === current)) sel.value = current;
  else if (App.settings.chat_model && models.some(m => m.model_id === App.settings.chat_model)) sel.value = App.settings.chat_model;
}

function providerOptions(selected) {
  return runnableModelProviders().map(p => `<option value="${esc(p)}" ${p === selected ? 'selected' : ''}>${esc(providerLabel(p))}</option>`).join('');
}

function modelOptions(provider, selected, includeDefault = true) {
  const models = enabledModels(provider);
  const opts = includeDefault ? ['<option value="default">Default</option>'] : [];
  opts.push(...models.map(m => `<option value="${esc(m.model_id)}" ${m.model_id === selected ? 'selected' : ''}>${esc(m.display_name)} (${esc(m.model_id)})</option>`));
  if (selected && selected !== 'default' && !models.some(m => m.model_id === selected)) {
    opts.push(`<option value="${esc(selected)}" selected>${esc(selected)}</option>`);
  }
  return opts.join('');
}

function renderModelRegistry() {
  const list = document.getElementById('model-registry-list');
  if (!list) return;
  if (!App.models.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No models configured.</div></div>';
    return;
  }
  list.innerHTML = App.models.map(m => `
    <div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(m.display_name)}</div>
          <div class="council-card-meta">${esc(providerLabel(m.provider))} · ${esc(m.model_id)} · ${m.enabled ? 'Enabled' : 'Disabled'}</div>
        </div>
        <div class="council-actions">
          <button class="btn-secondary" onclick="editModelRegistryEntry('${m.id}')">Edit</button>
          <button class="danger-btn" onclick="deleteModelRegistryEntry('${m.id}')">Delete</button>
        </div>
      </div>
    </div>
  `).join('');
}

function editModelRegistryEntry(id) {
  const model = App.models.find(m => m.id === id);
  if (!model) return;
  App.editingModelId = id;
  document.getElementById('model-provider-input').value = model.provider;
  document.getElementById('model-name-input').value = model.display_name;
  document.getElementById('model-id-input').value = model.model_id;
  document.getElementById('model-enabled-toggle')?.classList.toggle('on', model.enabled);
}

function resetModelForm() {
  App.editingModelId = null;
  const provider = document.getElementById('model-provider-input');
  const name = document.getElementById('model-name-input');
  const modelId = document.getElementById('model-id-input');
  if (provider) provider.value = 'openai';
  if (name) name.value = '';
  if (modelId) modelId.value = '';
  document.getElementById('model-enabled-toggle')?.classList.add('on');
}

async function saveModelRegistryEntry() {
  const provider = document.getElementById('model-provider-input')?.value.trim().toLowerCase();
  const display_name = document.getElementById('model-name-input')?.value.trim();
  const model_id = document.getElementById('model-id-input')?.value.trim();
  const enabled = document.getElementById('model-enabled-toggle')?.classList.contains('on');
  if (!provider || !display_name || !model_id) {
    showToast('Provider, display name, and model ID are required.', 'error');
    return;
  }
  try {
    const url = App.editingModelId ? `/api/models/${App.editingModelId}` : '/api/models';
    const r = await fetch(url, {
      method: App.editingModelId ? 'PUT' : 'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({provider, display_name, model_id, enabled})
    });
    if (!r.ok) throw new Error(await apiError(r));
    resetModelForm();
    await loadModels();
    showToast('Model saved.');
  } catch(e) { showToast('Failed to save model: ' + e.message, 'error'); }
}

async function deleteModelRegistryEntry(id) {
  if (!confirm('Delete this model from the registry?')) return;
  try {
    const r = await fetch(`/api/models/${id}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadModels();
    showToast('Model deleted.');
  } catch(e) { showToast('Failed to delete model: ' + e.message, 'error'); }
}

function saveApiKey(btn) {
  const card = btn.closest('.provider-card');
  const input = card.querySelector('.key-input');
  const val = input.value.trim();
  if (!val || val === '••••••••') return;
  const name = card.querySelector('.provider-name')?.textContent?.trim();
  const keyMap = { 'OpenAI':'openai_api_key','OpenRouter':'openrouter_api_key','Anthropic':'anthropic_api_key','Google Gemini':'gemini_api_key','Mistral AI':'mistral_api_key','Cohere':'cohere_api_key','Groq':'groq_api_key','Ollama':'ollama_api_key','xAI (Grok)':'xai_api_key','Cloudflare Workers AI':'cloudflare_api_key','Together AI':'together_api_key','Brave Search':'brave_search_api_key','SearXNG':'searxng_base_url' };
  const k = keyMap[name];
  if (!k) { showToast('Unknown provider', 'error'); return; }
  saveSettings({[k]: val}).then(() => {
    upsertV2Secret(k.toUpperCase(), val);
    input.value = '••••••••';
  });
}

function saveOllamaSettings() {
  const keyInput = document.getElementById('ollama-api-key-input');
  const urlInput = document.getElementById('ollama-base-url-input');
  const key = keyInput?.value.trim() || '';
  let baseUrl = urlInput?.value.trim() || '';
  if (!baseUrl) {
    showToast('Ollama base URL is required.', 'error');
    return;
  }
  if (key && key !== '••••••••' && (baseUrl === 'http://localhost:11434' || baseUrl === 'http://127.0.0.1:11434')) {
    baseUrl = 'https://ollama.com';
    if (urlInput) urlInput.value = baseUrl;
  }
  const settings = { ollama_base_url: baseUrl };
  if (key && key !== '••••••••') settings.ollama_api_key = key;
  saveSettings(settings).then(() => {
    if (key && key !== '••••••••') upsertV2Secret('OLLAMA_API_KEY', key);
    if (keyInput && key && key !== '••••••••') keyInput.value = '••••••••';
  });
}

async function testConnection() {
  try {
    const r = await fetch('/api/settings/test-connection');
    const d = await r.json();
    if (d.ok) showToast(d.message, 'success'); else showToast(d.error, 'error');
  } catch(e) { showToast('Test failed: ' + e.message, 'error'); }
}

async function testOllamaConnection() {
  try {
    const r = await fetch('/api/settings/test-ollama');
    const d = await r.json();
    if (d.ok) showToast(d.message, 'success'); else showToast(d.error, 'error');
  } catch(e) { showToast('Ollama test failed: ' + e.message, 'error'); }
}

function saveChatModelSettings() {
  const p = document.getElementById('sel-chat-provider')?.value;
  const m = document.getElementById('sel-chat-model')?.value;
  const t = document.getElementById('sel-max-tokens')?.value;
  const temp = document.getElementById('sl-temperature')?.value;
  const s = {};
  if (p) s.local_llm_provider = p;
  if (m) s.chat_model = m;
  if (t) s.max_tokens = t;
  if (temp) s.temperature = (parseFloat(temp)/100).toFixed(2);
  saveSettings(s);
}

function saveEmbeddingModelSettings() {
  const ep = document.getElementById('sel-embedding-provider')?.value;
  const em = document.getElementById('sel-embedding-model')?.value;
  const s = {};
  if (ep) s.embedding_provider = ep;
  if (em) s.embedding_model = em;
  saveSettings(s);
}

function saveModelSettings() {
  const p = document.getElementById('sel-chat-provider')?.value;
  const m = document.getElementById('sel-chat-model')?.value;
  const t = document.getElementById('sel-max-tokens')?.value;
  const temp = document.getElementById('sl-temperature')?.value;
  const ep = document.getElementById('sel-embedding-provider')?.value;
  const em = document.getElementById('sel-embedding-model')?.value;
  const s = {};
  if (p) s.local_llm_provider = p;
  if (m) s.chat_model = m;
  if (t) s.max_tokens = t;
  if (temp) s.temperature = (parseFloat(temp)/100).toFixed(2);
  if (ep) s.embedding_provider = ep;
  if (em) s.embedding_model = em;
  saveSettings(s);
}

function saveRagSettings() {
  const k = document.getElementById('sl-top-k')?.value;
  const sim = document.getElementById('sl-similarity')?.value;
  const ret = document.getElementById('sel-retrieval')?.value;
  const cs = document.getElementById('sl-chunk-size')?.value;
  const co = document.getElementById('sl-chunk-overlap')?.value;
  const s = {};
  if (k) s.top_k = k;
  if (sim) s.similarity_threshold = (parseFloat(sim)/100).toFixed(2);
  if (ret) s.retrieval_strategy = ret;
  if (cs) s.chunk_size = cs;
  if (co) s.chunk_overlap = co;
  saveSettings(s);
}

function saveChatSettings() {
  const lang = document.getElementById('sel-response-language')?.value;
  const len = document.getElementById('sel-response-length')?.value;
  const src = document.getElementById('tog-always-sources')?.classList.contains('on');
  const str = document.getElementById('tog-stream')?.classList.contains('on');
  const auto = document.getElementById('tog-auto-detect')?.classList.contains('on');
  const s = {};
  if (lang) s.response_language = lang;
  if (len) s.response_length = len;
  s.always_show_sources = src ? 'true' : 'false';
  s.stream_responses = str ? 'true' : 'false';
  s.auto_detect_language = auto ? 'true' : 'false';
  saveSettings(s);
}

function saveDocsSettings() {
  const mf = document.getElementById('sel-max-file-size')?.value;
  const ad = document.getElementById('sel-auto-delete')?.value;
  const s = {};
  if (mf) s.max_file_size_mb = mf;
  if (ad != null) s.auto_delete_days = ad;
  saveSettings(s).then(() => syncV2RuntimeSettings(s));
}

function saveAppearanceSettings() {
  const fs = document.getElementById('sel-font-size')?.value;
  const dm = document.getElementById('appearance-dark-toggle')?.classList.contains('on');
  const s = { dark_mode: dm ? 'true' : 'false' };
  if (fs) { s.font_size = fs; document.body.style.fontSize = fs + 'px'; }
  const name = document.getElementById('inp-app-name')?.value.trim();
  const intro = document.getElementById('inp-app-intro')?.value.trim();
  if (name) s.app_name = name;
  if (intro != null) s.app_intro = intro;
  const qs = collectQuestions();
  s.suggested_questions = JSON.stringify(qs);
  saveSettings(s);
}

function renderQuestionsList(json) {
  const list = document.getElementById('questions-list');
  if (!list) return;
  let qs = [];
  try { qs = JSON.parse(json || '[]'); } catch(e) {}
  list.innerHTML = qs.map((q, i) => `
    <div data-csp-style="display:flex;gap:6px;align-items:center">
      <input type="text" value="${esc(q)}" data-q="${i}" data-csp-style="flex:1;padding:6px 10px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:13px;font-family:inherit"/>
      <button onclick="removeQuestion(${i})" data-csp-style="background:none;border:none;cursor:pointer;color:var(--text-subtle);font-size:18px;line-height:1;padding:0 4px" title="Remove">&times;</button>
    </div>`).join('');
}

function collectQuestions() {
  return [...document.querySelectorAll('#questions-list input[data-q]')]
    .map(el => el.value.trim()).filter(Boolean);
}

function addQuestion() {
  const qs = collectQuestions();
  qs.push('');
  renderQuestionsList(JSON.stringify(qs));
  const inputs = document.querySelectorAll('#questions-list input[data-q]');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

function removeQuestion(i) {
  const qs = collectQuestions();
  qs.splice(i, 1);
  renderQuestionsList(JSON.stringify(qs));
}

function saveRagProviderSettings() {
  const v = document.getElementById('rag-provider-select')?.value;
  if (v) saveSettings({ rag_provider: v });
}

async function resetAllSettings() {
  if (!confirm('Reset all settings to defaults? API keys will be cleared.')) return;
  try {
    const defaults = { rag_provider:'openai', chat_model:'gpt-5.2', openai_assistants_model:'gpt-4.1', temperature:'0.2', max_tokens:'2048', top_k:'5', similarity_threshold:'0.72', chunk_size:'512', chunk_overlap:'64', retrieval_strategy:'semantic', response_language:'English', auto_detect_language:'false', response_length:'balanced', always_show_sources:'false', stream_responses:'true', max_file_size_mb:'25', auto_delete_days:'0', dark_mode:'false', font_size:'14', openai_api_key:'', openrouter_api_key:'', anthropic_api_key:'', groq_api_key:'', gemini_api_key:'', mistral_api_key:'', cohere_api_key:'', xai_api_key:'', cloudflare_api_key:'', together_api_key:'', ollama_api_key:'', ollama_base_url:'http://localhost:11434', brave_search_api_key:'', searxng_base_url:'', app_name:'AI Blueprint by Rohas Nagpal', app_intro:'Build private AI workspaces where documents, specialist agents, and multi-agent workflows turn knowledge into answers and action.', suggested_questions:'["Summarize the key points","What are the main findings?","List all action items","Compare sections across documents"]' };
    await saveSettings(defaults);
  } catch(e) { showToast('Reset failed.', 'error'); }
}

// ── CHATS ──────────────────────────────────────────────────────────────────
async function loadChats() {
  try {
    const r = await fetch(`/api/chats${App.chatArchiveFilter ? '?archived=true' : ''}`);
    App.chats = await r.json();
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
  App.chatMode = context === 'none' ? 'general' : 'documents';
  App.selectedDocIds = context === 'none' ? 'all' : context === 'all' ? 'all' : context.split(',').filter(Boolean);
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

function toggleWebSearch() {
  if (App.isStreaming) {
    showToast('Wait for the current response to finish before changing web search.', 'warning');
    return;
  }
  App.webSearchEnabled = !App.webSearchEnabled;
  document.getElementById('web-search-btn')?.classList.toggle('active', App.webSearchEnabled);
}

// ── DOCUMENTS ─────────────────────────────────────────────────────────────
async function loadDocuments() {
  try {
    if (App.v2.enabled) await loadV2Documents();
    const r = await fetch('/api/documents');
    App.documents = await r.json();
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
    if (!r.ok) throw new Error(await apiError(r));
    App.connectedFolders = await r.json();
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

// ── PERSONAS ─────────────────────────────────────────────────────────────
async function loadPersonas() {
  try {
    const r = await fetch('/api/personas');
    App.personas = await r.json();
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

// ── EMAIL ────────────────────────────────────────────────────────────────
function toggleEmailSettingsAccordion(forceOpen) {
  const card = document.getElementById('email-settings-card');
  if (!card) return;
  const shouldOpen = forceOpen ?? card.classList.contains('collapsed');
  card.classList.toggle('collapsed', !shouldOpen);
  card.querySelector('.email-accordion-trigger')?.setAttribute('aria-expanded', String(shouldOpen));
}

async function loadEmailMessages() {
  try {
    const r = await fetch('/api/email/messages');
    App.emailMessages = await r.json();
    renderEmailList();
  } catch(e) {}
}

function renderEmailControls() {
  const personaSel = document.getElementById('email-persona-select');
  if (personaSel) {
    const current = App.settings.email_persona_id || '';
    personaSel.innerHTML = '<option value="">No persona</option>' + App.personas.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    personaSel.value = current;
  }
  const docSel = document.getElementById('email-doc-context');
  if (docSel) {
    const current = App.settings.email_doc_context || 'none';
    docSel.innerHTML = [
      '<option value="none">No document search</option>',
      `<option value="all">All documents (${App.documents.length})</option>`,
      ...App.documents.map(d => `<option value="${esc(d.id)}">${esc(d.original_name)}</option>`)
    ].join('');
    docSel.value = [...docSel.options].some(o => o.value === current) ? current : 'none';
  }
  const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
  set('email-imap-host', App.settings.email_imap_host || '');
  set('email-imap-port', App.settings.email_imap_port || '993');
  set('email-imap-username', App.settings.email_imap_username || '');
  set('email-imap-password', App.settings.email_imap_password ? '••••••••' : '');
  set('email-imap-folder', App.settings.email_imap_folder || 'INBOX');
  set('email-smtp-host', App.settings.email_smtp_host || 'mail.smtp2go.com');
  set('email-smtp-port', App.settings.email_smtp_port || '2525');
  set('email-smtp-verify-tls', App.settings.email_smtp_verify_tls || 'true');
  set('email-smtp-username', App.settings.email_smtp_username || '');
  set('email-smtp-password', App.settings.email_smtp_password ? '••••••••' : '');
  set('email-from-address', App.settings.email_from_address || '');
}

async function saveEmailSettings() {
  const val = id => document.getElementById(id)?.value.trim() || '';
  const settings = {
    email_imap_host: val('email-imap-host'),
    email_imap_port: val('email-imap-port') || '993',
    email_imap_username: val('email-imap-username'),
    email_imap_folder: val('email-imap-folder') || 'INBOX',
    email_smtp_host: val('email-smtp-host') || 'mail.smtp2go.com',
    email_smtp_port: val('email-smtp-port') || '2525',
    email_smtp_verify_tls: val('email-smtp-verify-tls') || 'true',
    email_smtp_username: val('email-smtp-username'),
    email_from_address: val('email-from-address'),
    email_persona_id: val('email-persona-select'),
    email_doc_context: val('email-doc-context') || 'none'
  };
  const imapPass = val('email-imap-password');
  const smtpPass = val('email-smtp-password');
  if (imapPass && imapPass !== '••••••••') settings.email_imap_password = imapPass;
  if (smtpPass && smtpPass !== '••••••••') settings.email_smtp_password = smtpPass;
  await saveSettings(settings);
  const ip = document.getElementById('email-imap-password'); if (ip && (imapPass || App.settings.email_imap_password)) ip.value = '••••••••';
  const sp = document.getElementById('email-smtp-password'); if (sp && (smtpPass || App.settings.email_smtp_password)) sp.value = '••••••••';
}

async function pollEmail() {
  try {
    const r = await fetch('/api/email/poll', {method:'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    const d = await r.json();
    showToast(`${d.imported || 0} new email${d.imported === 1 ? '' : 's'} imported.`);
    await loadEmailMessages();
  } catch(e) { showToast('Email check failed: ' + e.message, 'error'); }
}

function renderEmailList() {
  const list = document.getElementById('email-list');
  if (!list) return;
  if (!App.emailMessages.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No imported emails yet.</div></div>';
    return;
  }
  list.innerHTML = App.emailMessages.map(m => {
    const date = m.received_at ? new Date(m.received_at).toLocaleString() : '';
    return `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(m.subject || '(no subject)')}</div>
          <div class="council-card-meta">${esc(m.from_email || '')}${date ? ' · ' + esc(date) : ''}</div>
        </div>
        <span class="council-status ${esc(m.status || 'new')}">${esc(m.status || 'new')}</span>
      </div>
      <div class="detail-text" data-csp-style="max-height:120px;overflow:auto;margin:8px 0">${esc((m.body || '').slice(0, 1200))}</div>
      ${m.error ? `<div class="council-card-desc" data-csp-style="color:var(--danger)">${esc(m.error)}</div>` : ''}
      <div class="council-form-row">
        <div class="council-field"><label>Persona</label><select class="council-select email-row-persona" data-id="${m.id}"><option value="">No persona</option>${App.personas.map(p => `<option value="${esc(p.id)}" ${p.id === m.persona_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div>
        <div class="council-field"><label>RAG scope</label><select class="council-select email-row-docs" data-id="${m.id}"><option value="none">No document search</option><option value="all" ${m.doc_context === 'all' ? 'selected' : ''}>All documents (${App.documents.length})</option>${App.documents.map(d => `<option value="${esc(d.id)}" ${d.id === m.doc_context ? 'selected' : ''}>${esc(d.original_name)}</option>`).join('')}</select></div>
      </div>
      <div class="council-field"><label>Draft</label><textarea class="council-textarea email-draft" data-id="${m.id}" data-csp-style="min-height:150px">${esc(m.draft_body || '')}</textarea></div>
      <div class="council-actions">
        <button class="btn-secondary" onclick="draftEmail('${m.id}')">Generate Draft</button>
        <button class="btn-primary" onclick="sendEmailReply('${m.id}')">Send Approved Reply</button>
        <button class="danger-btn" onclick="deleteEmailMessage('${m.id}')">Delete</button>
      </div>
    </div>`;
  }).join('');
}

async function draftEmail(id) {
  const persona = document.querySelector(`.email-row-persona[data-id="${id}"]`)?.value || '';
  const docContext = document.querySelector(`.email-row-docs[data-id="${id}"]`)?.value || 'none';
  try {
    showToast('Generating email draft...', 'warning');
    const r = await fetch(`/api/email/messages/${id}/draft`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({persona_id: persona, doc_context: docContext})
    });
    if (!r.ok) throw new Error(await apiError(r));
    const d = await r.json();
    const ta = document.querySelector(`.email-draft[data-id="${id}"]`);
    if (ta) ta.value = d.draft_body || '';
    await loadEmailMessages();
    showToast('Draft generated.');
  } catch(e) { showToast('Draft failed: ' + e.message, 'error'); }
}

async function sendEmailReply(id) {
  if (!confirm('Send this email reply via SMTP2GO?')) return;
  const draft = document.querySelector(`.email-draft[data-id="${id}"]`)?.value || '';
  try {
    const r = await fetch(`/api/email/messages/${id}/send`, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({draft_body: draft, approved: true})
    });
    if (!r.ok) throw new Error(await apiError(r));
    await loadEmailMessages();
    showToast('Email sent.');
  } catch(e) { showToast('Send failed: ' + e.message, 'error'); }
}

async function deleteEmailMessage(id) {
  if (!confirm('Delete this email from the review queue?')) return;
  try {
    const r = await fetch(`/api/email/messages/${id}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadEmailMessages();
    showToast('Email deleted.');
  } catch(e) { showToast('Delete failed: ' + e.message, 'error'); }
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

function updateChatModeUI() {
  if (App.chatMode === 'documents' && !App.documents.length && !App.v2.documents.length) App.chatMode = 'general';
  const label = document.getElementById('input-mode-label');
  const icon = document.getElementById('input-mode-icon');
  const input = document.getElementById('chat-input');
  const docOpt = document.getElementById('mode-option-documents');
  const generalOpt = document.getElementById('mode-option-general');
  if (label) label.textContent = App.chatMode === 'general' ? 'General' : 'Documents';
  if (icon) icon.innerHTML = App.chatMode === 'general'
    ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>';
  if (input) input.placeholder = App.chatMode === 'general' ? 'Ask anything...' : 'Ask anything about your documents...';
  docOpt?.classList.toggle('active', App.chatMode === 'documents');
  generalOpt?.classList.toggle('active', App.chatMode === 'general');
  updateDocSelector();
  updateChatScopeControls();
}

function updateDocSelector() {
  const badge = document.getElementById('input-doc-badge');
  const topbarLabel = document.getElementById('topbar-doc-label');
  if (!badge && !topbarLabel) return;
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
      .map(id => App.documents.find(d => d.id === id))
      .map(doc => doc ? v2DocumentByNameAndSize(doc) : null)
      .filter(Boolean)
      .map(doc => doc.id);
  }
  return {
    v2_workspace_id: App.v2.workspaceId,
    v2_matter_id: App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : null,
    v2_blueprint_id: App.v2.activeBlueprintId || null,
    v2_document_ids: v2DocIds
  };
}

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

// ── COUNCILS ──────────────────────────────────────────────────────────────
async function loadCouncils() {
  try {
    const [templatesRes, runsRes] = await Promise.all([
      fetch('/api/council/templates'),
      fetch('/api/council/runs')
    ]);
    App.councilTemplates = await templatesRes.json();
    App.councilRuns = await runsRes.json();
    renderCouncilTemplates();
    renderCouncilRuns();
    renderCouncilTemplateOptions();
    renderCouncilDocOptions();
    if (!App.councilBuilder) resetCouncilBuilder();
  } catch(e) {}
}

function renderCouncilTemplateOptions() {
  const sel = document.getElementById('council-run-template');
  if (!sel) return;
  sel.innerHTML = App.councilTemplates.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
}

function renderCouncilDocOptions() {
  const sel = document.getElementById('council-run-docs');
  if (!sel) return;
  const opts = ['<option value="all">All documents</option>'].concat(
    App.documents.map(d => `<option value="${d.id}">${esc(d.original_name)}</option>`)
  );
  sel.innerHTML = opts.join('');
}

function renderCouncilTemplates() {
  const grid = document.getElementById('council-templates-grid');
  if (!grid) return;
  if (!App.councilTemplates.length) {
    grid.innerHTML = '<div class="council-card"><div class="council-card-desc">No templates yet.</div></div>';
    return;
  }
  grid.innerHTML = App.councilTemplates.map(t => `
    <div class="council-card">
      <div class="council-card-title">${esc(t.name)}</div>
      <div class="council-card-meta">${t.is_builtin ? 'Built-in template' : 'Custom template'} · ${(t.config.agents || []).length} AI${(t.config.agents || []).length === 1 ? '' : 's'} · ${(t.config.phases || []).length} phase${(t.config.phases || []).length === 1 ? '' : 's'}</div>
      <div class="council-card-desc">${esc(t.description || t.config.description || '')}</div>
      <div class="council-actions">
        <button class="btn-primary" type="button" onclick="useCouncilTemplate('${t.id}')">Use</button>
        <button class="btn-secondary" type="button" onclick="loadTemplateIntoBuilder('${t.id}')">Edit</button>
        <button class="danger-btn" type="button" onclick="deleteCouncilTemplate('${t.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function renderCouncilRuns() {
  const list = document.getElementById('council-runs-list');
  if (!list) return;
  if (!App.councilRuns.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No council runs yet.</div></div>';
    return;
  }
  list.innerHTML = App.councilRuns.map(r => `
    <div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(r.title || 'Council Run')}</div>
          <div class="council-card-meta">${esc((r.objective || '').slice(0, 120))}${(r.objective || '').length > 120 ? '…' : ''}</div>
        </div>
        <span class="council-status ${esc(r.status || 'pending')}">${esc(r.status || 'pending')}</span>
      </div>
      ${r.error ? `<div class="council-card-desc" data-csp-style="color:var(--danger)">${esc(r.error)}</div>` : ''}
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="openCouncilRun('${r.id}')">Open</button>
        ${r.status === 'pending' || r.status === 'error' ? `<button class="btn-primary" type="button" onclick="startExistingCouncilRun('${r.id}')">Run</button>` : ''}
        <button class="danger-btn" type="button" onclick="deleteCouncilRun('${r.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function useCouncilTemplate(templateId) {
  const sel = document.getElementById('council-run-template');
  if (sel) sel.value = templateId;
  switchCouncilTab('runs');
}

function switchCouncilTab(tab, el) {
  document.querySelectorAll('.council-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.council-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('council-panel-' + tab)?.classList.add('active');
  if (el) el.classList.add('active');
  else document.querySelector(`.council-tab[onclick*="'${tab}'"]`)?.classList.add('active');
}

async function startCouncilFromForm() {
  const templateId = document.getElementById('council-run-template')?.value;
  const title = document.getElementById('council-run-title')?.value.trim() || '';
  const objective = document.getElementById('council-run-objective')?.value.trim();
  const docContext = document.getElementById('council-run-docs')?.value || 'all';
  if (!templateId) { showToast('Choose a council template.', 'error'); return; }
  if (!objective) { showToast('Enter a council objective or submission.', 'error'); return; }
  showToast('Council run started. This may take a while.', 'warning');
  try {
    const createRes = await fetch('/api/council/runs', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({template_id:templateId, title, objective, doc_context:docContext})
    });
    if (!createRes.ok) throw new Error(await apiError(createRes));
    const run = await createRes.json();
    await startExistingCouncilRun(run.id);
    document.getElementById('council-run-title').value = '';
  } catch(e) {
    showToast('Council run failed: ' + e.message, 'error');
  }
}

async function startExistingCouncilRun(runId) {
  try {
    const r = await fetch(`/api/council/runs/${runId}/start`, {method:'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    await streamCouncilRun(runId);
  } catch(e) {
    await loadCouncils();
    showToast('Council run failed: ' + e.message, 'error');
  }
}

async function openCouncilRun(runId) {
  try {
    const [runRes, outRes] = await Promise.all([
      fetch(`/api/council/runs/${runId}`),
      fetch(`/api/council/runs/${runId}/outputs`)
    ]);
    if (!runRes.ok) throw new Error(await apiError(runRes));
    if (!outRes.ok) throw new Error(await apiError(outRes));
    const run = await runRes.json();
    const data = await outRes.json();
    renderCouncilRunResult(run, data.outputs || [], data.evidence || []);
    if (run.status === 'running') streamCouncilRun(runId, false);
  } catch(e) {
    showToast('Failed to open council run: ' + e.message, 'error');
  }
}

async function streamCouncilRun(runId, showStartedToast = true) {
  App.activeCouncilRunId = runId;
  App.councilRenderKey = '';
  if (App.councilPollTimer) clearTimeout(App.councilPollTimer);
  if (showStartedToast) showToast('Council run is streaming as each participant finishes.', 'warning');
  const poll = async () => {
    if (App.activeCouncilRunId !== runId) return;
    try {
      const [runRes, outRes] = await Promise.all([
        fetch(`/api/council/runs/${runId}`),
        fetch(`/api/council/runs/${runId}/outputs`)
      ]);
      if (!runRes.ok) throw new Error(await apiError(runRes));
      if (!outRes.ok) throw new Error(await apiError(outRes));
      const run = await runRes.json();
      const data = await outRes.json();
      const key = JSON.stringify({
        status: run.status,
        error: run.error,
        outputs: (data.outputs || []).map(o => [o.id, o.content?.length || 0]),
        evidence: (data.evidence || []).map(e => [e.id, e.sources?.length || 0])
      });
      if (key !== App.councilRenderKey) {
        App.councilRenderKey = key;
        renderCouncilRunResult(run, data.outputs || [], data.evidence || [], !document.getElementById('council-run-result')?.innerHTML);
      }
      if (run.status === 'running' || run.status === 'pending') {
        App.councilPollTimer = setTimeout(poll, 1200);
        return;
      }
      App.councilPollTimer = null;
      await loadCouncils();
      if (run.status === 'completed') showToast('Council run completed.', 'success');
      if (run.status === 'error') showToast('Council run failed: ' + (run.error || 'Unknown error'), 'error');
    } catch(e) {
      App.councilPollTimer = setTimeout(poll, 2000);
    }
  };
  await poll();
}

function renderCouncilRunResult(run, outputs, evidence, shouldScroll = true) {
  const box = document.getElementById('council-run-result');
  if (!box) return;
  const phases = [...new Set(outputs.map(o => o.phase_id))];
  const phaseHtml = phases.map(pid => {
    const phaseOutputs = outputs.filter(o => o.phase_id === pid);
    const phaseName = phaseOutputs[0]?.phase_name || pid;
    const ev = evidence.find(e => e.phase_id === pid);
    const evidenceHtml = ev && ev.sources?.length ? `<div class="sources" data-csp-style="margin-bottom:10px">${mkSources(ev.sources).innerHTML}</div>` : '';
    return `
      <div class="settings-card">
        <div class="settings-card-header">
          <div><div class="settings-card-title">${esc(phaseName)}</div><div class="settings-card-subtitle">${ev ? esc(ev.query || '') : ''}</div></div>
        </div>
        ${evidenceHtml}
        ${phaseOutputs.map(o => `
          <div class="council-output">
            <div class="council-output-role">${esc(o.role_name)}</div>
            <div class="council-output-phase">${esc(o.metadata?.model || '')} · ${esc(o.metadata?.output_type || 'output')}</div>
            <div>${mdRender(o.content || '')}</div>
            ${o.sources?.length ? `<div data-csp-style="margin-top:10px">${mkSources(o.sources).innerHTML}</div>` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }).join('');
  box.innerHTML = `
    <div class="settings-card">
      <div class="settings-card-header">
        <div><div class="settings-card-title">${esc(run.title || 'Council Run')}</div><div class="settings-card-subtitle">${esc(run.objective || '')}</div></div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
    </div>
    ${phaseHtml || '<div class="council-row"><div class="council-card-desc">No outputs yet.</div></div>'}
  `;
  if (shouldScroll) box.scrollIntoView({behavior:'smooth', block:'start'});
}

async function deleteCouncilRun(runId) {
  if (!confirm('Delete this council run? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/council/runs/${runId}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    document.getElementById('council-run-result').innerHTML = '';
    await loadCouncils();
    showToast('Council run deleted.');
  } catch(e) { showToast('Failed to delete run: ' + e.message, 'error'); }
}

function resetCouncilBuilder(render = true) {
  App.councilEditingTemplateId = null;
  App.councilBuilder = {
    agents: [
      {id:'agent_1', name:'AI Participant 1', instructions:'Analyze the documents and objective from this role.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt'], output_type:'argument', require_citations:true},
      {id:'agent_2', name:'AI Participant 2', instructions:'Critique and complement the other perspective.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt','prior_outputs'], output_type:'critique', require_citations:true}
    ],
    phases: [
      {id:'phase_1', name:'Initial Analysis', mode:'parallel', agents:['agent_1','agent_2'], instructions:'Produce initial council outputs.', retrieval_query:'objective'}
    ]
  };
  const name = document.getElementById('builder-name'); if (name) name.value = 'Custom Council';
  const desc = document.getElementById('builder-description'); if (desc) desc.value = '';
  const obj = document.getElementById('builder-objective'); if (obj) obj.value = 'Analyze the user objective using uploaded documents.';
  const out = document.getElementById('builder-output'); if (out) out.value = 'memo';
  if (render) renderCouncilBuilder();
}

function renderCouncilBuilder() {
  renderBuilderAgents();
  renderBuilderPhases();
}

function renderBuilderAgents() {
  const box = document.getElementById('builder-agents');
  if (!box || !App.councilBuilder) return;
  box.innerHTML = App.councilBuilder.agents.map((a, i) => `
    <div class="council-row">
      <div class="council-row-head">
        <div class="council-card-title">AI ${i + 1}</div>
        <button class="danger-btn" type="button" onclick="removeCouncilAgent(${i})">Remove</button>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Role name</label><input class="council-input builder-agent-name" data-i="${i}" value="${esc(a.name)}"/></div>
        <div class="council-field"><label>Output type</label><input class="council-input builder-agent-output" data-i="${i}" value="${esc(a.output_type || 'custom')}"/></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Provider</label><select class="council-select builder-agent-provider" data-i="${i}" onchange="renderBuilderAgentModelSelect(${i})"><option value="default">Default</option>${providerOptions(a.provider)}</select></div>
        <div class="council-field"><label>Model</label><select class="council-select builder-agent-model" data-i="${i}">${modelOptions(a.provider === 'default' ? (App.settings.local_llm_provider || 'openai') : a.provider, a.model || 'default')}</select></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Temperature</label><input class="council-input builder-agent-temp" data-i="${i}" type="number" min="0" max="1" step="0.1" value="${a.temperature ?? 0.2}"/></div>
        <div class="council-field"><label>Max tokens</label><input class="council-input builder-agent-tokens" data-i="${i}" type="number" min="256" step="128" value="${a.max_tokens || 1400}"/></div>
      </div>
      <div class="council-field"><label>Instructions</label><textarea class="council-textarea builder-agent-instructions" data-i="${i}">${esc(a.instructions || '')}</textarea></div>
      <div class="council-field"><label>Context access</label><input class="council-input builder-agent-context" data-i="${i}" value="${esc((a.context_access || []).join(','))}"/></div>
    </div>
  `).join('');
  App.councilBuilder.agents.forEach((a, i) => {
    const sel = box.querySelector(`.builder-agent-provider[data-i="${i}"]`);
    if (sel) sel.value = a.provider || 'default';
  });
}

function renderBuilderAgentModelSelect(i) {
  const providerSel = document.querySelector(`.builder-agent-provider[data-i="${i}"]`);
  const modelSel = document.querySelector(`.builder-agent-model[data-i="${i}"]`);
  if (!providerSel || !modelSel) return;
  const provider = providerSel.value === 'default' ? (App.settings.local_llm_provider || 'openai') : providerSel.value;
  modelSel.innerHTML = modelOptions(provider, modelSel.value || 'default');
}

function renderBuilderPhases() {
  const box = document.getElementById('builder-phases');
  if (!box || !App.councilBuilder) return;
  const agentOptions = App.councilBuilder.agents.map(a => `${a.id}:${a.name}`).join(', ');
  box.innerHTML = App.councilBuilder.phases.map((p, i) => `
    <div class="council-row">
      <div class="council-row-head">
        <div class="council-card-title">Phase ${i + 1}</div>
        <button class="danger-btn" type="button" onclick="removeCouncilPhase(${i})">Remove</button>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Phase name</label><input class="council-input builder-phase-name" data-i="${i}" value="${esc(p.name)}"/></div>
        <div class="council-field"><label>Mode</label><select class="council-select builder-phase-mode" data-i="${i}"><option value="sequential">Sequential</option><option value="parallel">Parallel</option></select></div>
      </div>
      <div class="council-field"><label>Agent ids (${esc(agentOptions)})</label><input class="council-input builder-phase-agents" data-i="${i}" value="${esc((p.agents || []).join(','))}"/></div>
      <div class="council-field"><label>Instructions</label><textarea class="council-textarea builder-phase-instructions" data-i="${i}">${esc(p.instructions || '')}</textarea></div>
    </div>
  `).join('');
  App.councilBuilder.phases.forEach((p, i) => {
    const sel = box.querySelector(`.builder-phase-mode[data-i="${i}"]`);
    if (sel) sel.value = p.mode || 'sequential';
  });
}

function collectCouncilBuilder() {
  const agents = [...document.querySelectorAll('.builder-agent-name')].map(input => {
    const i = input.dataset.i;
    const old = App.councilBuilder.agents[i];
    return {
      id: old.id,
      name: input.value.trim() || old.id,
      instructions: document.querySelector(`.builder-agent-instructions[data-i="${i}"]`)?.value.trim() || '',
      provider: document.querySelector(`.builder-agent-provider[data-i="${i}"]`)?.value || 'default',
      model: document.querySelector(`.builder-agent-model[data-i="${i}"]`)?.value || 'default',
      temperature: parseFloat(document.querySelector(`.builder-agent-temp[data-i="${i}"]`)?.value || '0.2'),
      max_tokens: parseInt(document.querySelector(`.builder-agent-tokens[data-i="${i}"]`)?.value || '1400'),
      context_access: (document.querySelector(`.builder-agent-context[data-i="${i}"]`)?.value || 'documents,user_prompt').split(',').map(v => v.trim()).filter(Boolean),
      output_type: document.querySelector(`.builder-agent-output[data-i="${i}"]`)?.value.trim() || 'custom',
      require_citations: true
    };
  });
  const phases = [...document.querySelectorAll('.builder-phase-name')].map(input => {
    const i = input.dataset.i;
    const old = App.councilBuilder.phases[i];
    return {
      id: old.id,
      name: input.value.trim() || old.id,
      mode: document.querySelector(`.builder-phase-mode[data-i="${i}"]`)?.value || 'sequential',
      agents: (document.querySelector(`.builder-phase-agents[data-i="${i}"]`)?.value || '').split(',').map(v => v.trim()).filter(Boolean),
      instructions: document.querySelector(`.builder-phase-instructions[data-i="${i}"]`)?.value.trim() || '',
      retrieval_query: 'objective'
    };
  });
  App.councilBuilder.agents = agents;
  App.councilBuilder.phases = phases;
  return {
    name: document.getElementById('builder-name')?.value.trim() || 'Custom Council',
    description: document.getElementById('builder-description')?.value.trim() || '',
    document_scope: 'run',
    objective_prompt: document.getElementById('builder-objective')?.value.trim() || '',
    output_format: document.getElementById('builder-output')?.value || 'memo',
    agents,
    phases
  };
}

function addCouncilAgent() {
  collectCouncilBuilder();
  const n = App.councilBuilder.agents.length + 1;
  App.councilBuilder.agents.push({id:`agent_${n}`, name:`AI Participant ${n}`, instructions:'Analyze the objective from this role.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt','prior_outputs'], output_type:'custom', require_citations:true});
  renderCouncilBuilder();
}

function removeCouncilAgent(i) {
  collectCouncilBuilder();
  App.councilBuilder.agents.splice(i, 1);
  renderCouncilBuilder();
}

function addCouncilPhase() {
  collectCouncilBuilder();
  const n = App.councilBuilder.phases.length + 1;
  App.councilBuilder.phases.push({id:`phase_${n}`, name:`Phase ${n}`, mode:'sequential', agents:App.councilBuilder.agents.map(a => a.id).slice(0,1), instructions:'Run this phase.', retrieval_query:'objective'});
  renderCouncilBuilder();
}

function removeCouncilPhase(i) {
  collectCouncilBuilder();
  App.councilBuilder.phases.splice(i, 1);
  renderCouncilBuilder();
}

async function saveCouncilTemplate() {
  const config = collectCouncilBuilder();
  try {
    const url = App.councilEditingTemplateId ? `/api/council/templates/${App.councilEditingTemplateId}` : '/api/council/templates';
    const r = await fetch(url, {
      method: App.councilEditingTemplateId ? 'PUT' : 'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:config.name, description:config.description, config})
    });
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    switchCouncilTab('templates');
    showToast('Council template saved.');
  } catch(e) { showToast('Failed to save template: ' + e.message, 'error'); }
}

function loadTemplateIntoBuilder(templateId) {
  const t = App.councilTemplates.find(x => x.id === templateId);
  if (!t) return;
  const config = JSON.parse(JSON.stringify(t.config || {}));
  App.councilEditingTemplateId = t.id;
  App.councilBuilder = {agents: config.agents || [], phases: config.phases || []};
  document.getElementById('builder-name').value = t.name;
  document.getElementById('builder-description').value = t.description || config.description || '';
  document.getElementById('builder-objective').value = config.objective_prompt || '';
  document.getElementById('builder-output').value = config.output_format || 'memo';
  renderCouncilBuilder();
  switchCouncilTab('builder');
}

async function deleteCouncilTemplate(templateId) {
  if (!confirm('Delete this council template?')) return;
  try {
    const r = await fetch(`/api/council/templates/${templateId}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    showToast('Council template deleted.');
  } catch(e) { showToast('Failed to delete template: ' + e.message, 'error'); }
}

async function apiError(response) {
  const data = await response.json().catch(() => ({}));
  return data.detail || data.error || response.statusText || 'Request failed';
}

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
      await removeStaleImportedFolderDocuments(folderInput.files);
      rememberImportedFolder(folderInput.files);
      handleFiles(folderInput.files);
      folderInput.value = '';
    });
  }
}

function updateUploadQueueVisibility() {
  const title = document.getElementById('upload-queue-title');
  const list = document.getElementById('upload-queue-list');
  if (title) title.style.display = list && list.children.length ? 'block' : 'none';
}

function folderImportRoot(files) {
  const selected = Array.from(files || []);
  const firstRelativePath = selected.find(f => f.webkitRelativePath)?.webkitRelativePath || '';
  return firstRelativePath.split('/')[0] || '';
}

async function removeStaleImportedFolderDocuments(files) {
  const rootName = folderImportRoot(files);
  if (!rootName) return;
  const docs = App.documents.filter(doc => (doc.original_name || '').startsWith(rootName + '/'));
  if (!docs.length) return;
  for (const doc of docs) {
    try {
      const r = await fetch(`/api/documents/${doc.id}`, {method:'DELETE'});
      if (!r.ok) throw new Error(await apiError(r));
      await deleteV2DocumentForLegacyDoc(doc);
    } catch(e) {
      showToast(`Could not remove stale folder file: ${doc.original_name || doc.id}`, 'error');
    }
  }
  await loadDocuments();
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
  const queueEl = document.getElementById('upload-queue-list');
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
    fd.append('original_path', displayName);
    const r = await fetch('/api/documents/upload', {method:'POST', body:fd});
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
      await mirrorUploadToV2(file);
      await loadDocuments();
      if (!App.currentChatId && !App.isStreaming && uploaded.id) {
        App.chatMode = 'documents';
        App.selectedDocIds = [uploaded.id];
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
    const r = await fetch('/api/web/ingest-url', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url})});
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

// ── CHAT ──────────────────────────────────────────────────────────────────
function chatPrimaryAction() {
  if (App.isStreaming) {
    stopChatResponse();
    return;
  }
  sendMessage();
}

function setChatStreaming(active) {
  App.isStreaming = active;
  const btn = document.getElementById('chat-send-btn');
  if (!btn) return;
  btn.title = active ? 'Stop response' : 'Send message';
  btn.setAttribute('aria-label', active ? 'Stop response' : 'Send message');
  btn.classList.toggle('stopping', active);
  btn.innerHTML = active
    ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
}

function stopChatResponse() {
  if (!App.isStreaming) return;
  App.activeChatController?.abort();
}

async function sendMessage() {
  if (App.isStreaming) {
    stopChatResponse();
    return;
  }
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = ''; input.style.height = 'auto';
  document.getElementById('welcome-screen').style.display = 'none';
  const conv = document.getElementById('chat-conversation');
  conv.style.display = 'block';
  if (!App.currentChatId) {
    try {
      const docCtx = App.chatMode === 'general' ? 'none' : App.selectedDocIds === 'all' ? 'all' : App.selectedDocIds.join(',');
      const r = await fetch('/api/chats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({doc_context:docCtx, persona_id:App.selectedPersonaId || null, ...v2ChatScopePayload()})});
      const chat = await r.json();
      if (!r.ok) throw new Error(chat.detail || chat.error || 'Chat creation failed');
      App.currentChatId = chat.id;
    } catch(e) { showToast('Failed to create chat.', 'error'); return; }
  }
  conv.appendChild(mkUser(text));
  const aiEl = mkAi('', []);
  const bubble = aiEl.querySelector('.bubble');
  conv.appendChild(aiEl);
  scrollBottom();
  const controller = new AbortController();
  App.activeChatController = controller;
  setChatStreaming(true);
  const statusState = startChatStatus(bubble);
  let content = '', sources = [], hadError = false, wasStopped = false;
  try {
    const r = await fetch(`/api/chats/${App.currentChatId}/message`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:text, web_search:App.webSearchEnabled}), signal: controller.signal});
    if (!r.ok) throw new Error(await apiError(r));
    if (!r.body) throw new Error('The chat stream did not start.');
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.type === 'token') {
            stopChatStatus(statusState);
            content += ev.content;
            bubble.innerHTML = renderAssistantBubble(content, false);
            scrollBottom();
          }
          else if (ev.type === 'status') {
            updateChatStatus(statusState, ev.content || 'Working…', ev.progress);
            scrollBottom();
          }
          else if (ev.type === 'source') sources.push(ev);
          else if (ev.type === 'error') {
            stopChatStatus(statusState);
            hadError = true;
            content = ev.content || 'Chat request failed.';
            bubble.textContent = content;
            showToast(content, 'error');
          }
          else if (ev.type === 'done' && sources.length) {
            const sp = mkSources(sources);
            aiEl.insertBefore(sp, aiEl.querySelector('.msg-actions'));
            if (App.settings.always_show_sources === 'true') sp.querySelector('.sources-panel').classList.add('open');
          }
        } catch(ex) {}
      }
    }
    stopChatStatus(statusState);
    if (content) bubble.innerHTML = renderAssistantBubble(content, true);
    if (!content && !hadError) bubble.textContent = 'No response was returned.';
  } catch(e) {
    stopChatStatus(statusState);
    if (e.name === 'AbortError') {
      wasStopped = true;
      if (!content) bubble.textContent = 'Response stopped.';
      showToast('Response stopped.', 'warning');
    } else {
      content = 'Stream error: ' + e.message;
      bubble.textContent = content;
      showToast(content, 'error');
    }
  }
  if (wasStopped && content) bubble.innerHTML = renderAssistantBubble(content, true);
  App.activeChatController = null;
  setChatStreaming(false);
  await loadChats();
}

function mkUser(text) {
  const d = document.createElement('div'); d.className = 'msg user';
  d.innerHTML = `<div class="msg-meta"><span>You</span><div class="avatar user-av">U</div></div><div class="bubble">${esc(text)}</div>`;
  return d;
}

function mkAi(content, sources, messageId = '') {
  const d = document.createElement('div'); d.className = 'msg ai';
  const docSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  d.dataset.messageId = messageId || '';
  const body = content ? renderAssistantBubble(content, true) : '<span data-csp-style="opacity:.4">Preparing response…</span>';
  d.innerHTML = `<div class="msg-meta"><div class="avatar ai-av">${docSvg}</div><span>AI Blueprint</span></div><div class="bubble">${body}</div><div class="msg-actions"><div class="msg-action-btn" title="Copy" onclick="copyMsg(this)"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></div></div>`;
  if (sources.length) d.insertBefore(mkSources(sources), d.querySelector('.msg-actions'));
  return d;
}

function startChatStatus(bubble) {
  const state = {bubble, startedAt: Date.now(), message: 'Preparing response', progress: 6, timer: null, active: true};
  state.timer = setInterval(() => renderChatStatus(state), 1000);
  renderChatStatus(state);
  return state;
}

function updateChatStatus(state, message, progress) {
  if (!state?.active) return;
  state.message = message || state.message;
  if (progress != null && !Number.isNaN(Number(progress))) state.progress = Math.max(0, Math.min(95, Number(progress)));
  renderChatStatus(state);
}

function stopChatStatus(state) {
  if (!state) return;
  state.active = false;
  if (state.timer) clearInterval(state.timer);
}

function renderChatStatus(state) {
  if (!state?.active || !state.bubble) return;
  const elapsed = Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
  const progress = Math.max(6, Math.min(95, Math.round(state.progress || 6)));
  state.bubble.innerHTML = `<div class="chat-status-card">
    <div class="chat-status-title">${esc(state.message)}</div>
    <div class="chat-status-meta">${elapsed}s elapsed · ${progress}%</div>
    <div class="progress-bar"><div class="progress-fill" data-csp-style="width:${progress}%"></div></div>
  </div>`;
}

function renderAssistantBubble(content, includeContinueAction = true) {
  const body = mdRender(content);
  if (!includeContinueAction || !needsContinueAction(content)) return body;
  return `${body}<div class="continue-card">
    <div>
      <div class="continue-title">More steps are available</div>
      <div class="continue-desc">Continue in this same chat to complete the remaining review sections.</div>
    </div>
    <button class="btn-secondary" type="button" onclick="continueChatReview()">Continue</button>
  </div>`;
}

function needsContinueAction(content) {
  const text = String(content || '');
  const upper = text.toUpperCase();
  if (/Remaining steps available/i.test(text) || /reply ['"]?continue['"]?/i.test(text)) return true;
  return upper.includes('STEP 0') && (upper.includes('STEP 1') || upper.includes('CUAD')) && !upper.includes('STEP 8');
}

function continueChatReview() {
  if (App.isStreaming) return;
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = 'continue';
  autoResize(input);
  sendMessage();
}

function mkSources(sources) {
  const d = document.createElement('div'); d.className = 'sources';
  const items = sources.map(s => {
    const icon = s.kind === 'web'
      ? '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 0 20"/><path d="M12 2a15.3 15.3 0 0 0 0 20"/>'
      : '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';
    const title = s.url ? `<a class="source-doc" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.filename||s.url)}</a>` : `<div class="source-doc">${esc(s.filename||'')}</div>`;
    return `<div class="source-item"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon}</svg><div>${title}${s.excerpt?`<div data-csp-style="font-size:11.5px;color:var(--text-subtle);margin-top:2px">${esc(s.excerpt.substring(0,120))}</div>`:''}</div>${s.page!=null?`<span class="source-page">Chunk ${s.page}</span>`:''}</div>`;
  }).join('');
  d.innerHTML = `<div class="sources-toggle" onclick="toggleSources(this)"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>${sources.length} source${sources.length>1?'s':''}<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-csp-style="transition:transform .2s"><polyline points="6 9 12 15 18 9"/></svg></div><div class="sources-panel">${items}</div>`;
  return d;
}

function copyMsg(btn) {
  const b = btn.closest('.msg').querySelector('.bubble');
  navigator.clipboard.writeText(b.innerText).then(() => showToast('Copied.'));
}

async function downloadChatMarkdown() {
  if (!App.currentChatId) {
    showToast('Open or start a chat before downloading.', 'warning');
    return;
  }
  try {
    const chat = App.chats.find(c => c.id === App.currentChatId);
    const r = await fetch(`/api/chats/${App.currentChatId}/messages`);
    if (!r.ok) throw new Error(await apiError(r));
    const messages = await r.json();
    if (!messages.length) {
      showToast('This chat has no messages to download.', 'warning');
      return;
    }
    const title = chat?.title || 'AI Blueprint chat';
    const lines = [`# ${title}`, '', `Exported: ${new Date().toLocaleString()}`, ''];
    for (const message of messages) {
      lines.push(`## ${message.role === 'user' ? 'User' : 'AI Blueprint'}`, '', message.content || '', '');
      if (message.sources?.length) {
        lines.push('Sources:', '');
        for (const source of message.sources) {
          const name = source.filename || source.url || 'Source';
          const page = source.page != null ? `, chunk ${source.page}` : '';
          const url = source.url ? ` - ${source.url}` : '';
          lines.push(`- ${name}${page}${url}`);
        }
        lines.push('');
      }
    }
    const blob = new Blob([lines.join('\n')], {type: 'text/markdown;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${slugify(title || 'chat')}.md`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(a.href);
    a.remove();
    showToast('Chat downloaded.');
  } catch(e) {
    showToast('Download failed: ' + e.message, 'error');
  }
}

// ── UTILS ─────────────────────────────────────────────────────────────────
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function slugify(s) { return String(s || 'chat').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').substring(0, 80) || 'chat'; }
function fmtBytes(b) { if(!b)return'0 B'; if(b<1024)return b+' B'; if(b<1048576)return(b/1024).toFixed(1)+' KB'; return(b/1048576).toFixed(1)+' MB'; }
function formatDate(value) { try { return new Date(value).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}); } catch(e) { return value || ''; } }
function mdRender(t) {
  const codeStyle = 'background:var(--badge-bg);padding:1px 4px;border-radius:3px;font-size:.9em';
  const lines = esc(t || '').split('\n');
  let html = '';
  let inList = false;
  const isTableSep = s => /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(s.trim());
  const isTableRow = s => {
    const trimmed = s.trim();
    return trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.split('|').length >= 4;
  };
  const cells = s => s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
  const inline = s => s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, `<code data-csp-style="${codeStyle}">$1</code>`);
  const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
  const renderTable = (tableLines) => {
    if (tableLines.length < 2 || !isTableSep(tableLines[1])) return null;
    const head = cells(tableLines[0]);
    const body = tableLines.slice(2).filter(isTableRow).map(cells);
    if (!head.length || !body.length) return null;
    const colCount = head.length;
    const thead = `<thead><tr>${head.map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead>`;
    const tbody = `<tbody>${body.map(row => {
      const normalized = row.slice(0, colCount);
      while (normalized.length < colCount) normalized.push('');
      return `<tr>${normalized.map(c => `<td>${inline(c)}</td>`).join('')}</tr>`;
    }).join('')}</tbody>`;
    return `<div class="md-table-wrap"><table class="md-table">${thead}${tbody}</table></div>`;
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { closeList(); html += '<br>'; continue; }
    if (isTableRow(trimmed) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      closeList();
      const tableLines = [trimmed, lines[i + 1].trim()];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) {
        tableLines.push(lines[i].trim());
        i++;
      }
      i--;
      const table = renderTable(tableLines);
      if (table) {
        html += table;
        continue;
      }
    }
    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      closeList();
      const tag = heading[1].length === 1 ? 'h3' : 'h4';
      html += `<${tag}>${inline(heading[2])}</${tag}>`;
      continue;
    }
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inline(bullet[1])}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inline(trimmed)}</p>`;
  }
  closeList();
  return html;
}
function scrollBottom() { const m=document.getElementById('chat-messages'); if(m) m.scrollTop=m.scrollHeight; }
function el(id, val) { const e=document.getElementById(id); if(e) e.textContent=val; }

document.addEventListener('click', () => {
  document.getElementById('input-mode-menu')?.classList.remove('open');
  closeSidebarMore();
});

// ── VIEW SWITCHING ────────────────────────────────────────────────────────
const VIEWS = {chat:'view-chat',blueprints:'view-blueprints',matters:'view-matters',plugins:'view-plugins',councils:'view-councils',personas:'view-personas',email:'view-email','add-doc':'view-add-doc','view-docs':'view-view-docs',workspaces:'view-settings',settings:'view-settings','admin-users':'view-settings'};
const NAVS = {chat:'nav-chat',blueprints:'more-blueprints',matters:'more-matters',plugins:'more-plugins',councils:'nav-councils',personas:'nav-personas',email:'more-email','add-doc':'more-add-doc','view-docs':'more-view-docs',workspaces:'more-workspaces',settings:'more-settings','admin-users':'nav-admin-users'};
const TITLES = {chat:'Chat',blueprints:'Blueprints',matters:'Matters',plugins:'Plugins',councils:'Councils',personas:'Personas',email:'Email','add-doc':'Add Document','view-docs':'View Documents',workspaces:'Workspaces',settings:'Settings','admin-users':'Admin Users'};
const LAST_VIEW_KEY = 'aibp_last_view';

function switchView(name) {
  if (!VIEWS[name]) name = 'chat';
  localStorage.setItem(LAST_VIEW_KEY, name);
  Object.values(VIEWS).forEach(id => document.getElementById(id)?.classList.remove('active'));
  Object.values(NAVS).forEach(id => document.getElementById(id)?.classList.remove('active'));
  document.getElementById(VIEWS[name])?.classList.add('active');
  document.getElementById(NAVS[name])?.classList.add('active');
  document.getElementById('view-settings')?.classList.toggle('workspace-standalone', name === 'workspaces');
  const moreViews = ['blueprints', 'matters', 'add-doc', 'view-docs', 'email', 'plugins', 'workspaces', 'settings', 'admin-users'];
  document.getElementById('nav-more')?.classList.toggle('active', moreViews.includes(name));
  document.querySelectorAll('.sidebar-more-menu button').forEach(b => b.classList.remove('active'));
  const moreActive = document.getElementById('more-' + name) || (name === 'admin-users' ? document.getElementById('nav-admin-users') : null);
  moreActive?.classList.add('active');
  document.getElementById('topbar-title').textContent = TITLES[name] || name;
  document.getElementById('doc-selector').style.display = name === 'chat' ? 'flex' : 'none';
  if (name === 'view-docs') { renderDocuments(); renderConnectedFolders(); }
  if (['blueprints', 'matters', 'plugins'].includes(name)) loadV2Shell();
  if (name === 'councils') loadCouncils();
  if (name === 'personas') renderPersonas();
  if (name === 'add-doc') renderConnectedFolders();
  if (name === 'email') { renderEmailControls(); loadEmailMessages(); }
  if (name === 'workspaces') {
    const workspaceNav = document.getElementById('settings-nav-workspaces');
    if (workspaceNav) switchSettingsTab('workspaces', workspaceNav);
    if (!App.v2.user) initV2().then(loadWorkspaceManager).catch(() => {});
  }
  if (name === 'admin-users') {
    const usersNav = document.getElementById('settings-nav-users');
    if (usersNav) switchSettingsTab('users', usersNav);
  }
  if (name === 'chat' && !App.currentChatId) {
    document.getElementById('welcome-screen').style.display = 'flex';
    document.getElementById('chat-conversation').style.display = 'none';
  }
}

function restoreSavedView() {
  const saved = localStorage.getItem(LAST_VIEW_KEY);
  if (saved && VIEWS[saved]) switchView(saved);
}

// ── SETTINGS TABS ─────────────────────────────────────────────────────────
function switchSettingsTab(tab, el) {
  document.querySelectorAll('.settings-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.settings-nav-item').forEach(s => s.classList.remove('active'));
  document.getElementById('stab-' + tab)?.classList.add('active');
  el.classList.add('active');
  if (tab === 'workspaces') loadWorkspaceManager();
  if (tab === 'users') loadAdminUsers();
}

// ── RAG PROVIDER ──────────────────────────────────────────────────────────
function onRagProviderChange(val) {
  const a=document.getElementById('rag-openai-info'), b=document.getElementById('rag-llamaindex-info');
  if(a) a.style.display = val==='openai'?'block':'none';
  if(b) b.style.display = val==='llamaindex'?'block':'none';
}

// ── THEME ─────────────────────────────────────────────────────────────────
function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const newDark = !isDark;
  document.documentElement.setAttribute('data-theme', newDark ? 'dark' : 'light');
  const appTog = document.getElementById('appearance-dark-toggle');
  if (appTog) appTog.classList.toggle('on', newDark);
  saveSettings({ dark_mode: newDark ? 'true' : 'false' });
}

function toggleThemeFromSettings(el) {
  el.classList.toggle('on');
  const isDark = el.classList.contains('on');
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  saveSettings({ dark_mode: isDark ? 'true' : 'false' });
}

// ── EXISTING HELPERS ──────────────────────────────────────────────────────
function toggleKey(btn) {
  const input = btn.previousElementSibling;
  const hide = input.type === 'password';
  input.type = hide ? 'text' : 'password';
  btn.innerHTML = hide
    ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
}

function toggleSources(btn) {
  const panel = btn.nextElementSibling;
  panel.classList.toggle('open');
  const chevron = btn.querySelector('svg:last-child');
  if (chevron) chevron.style.transform = panel.classList.contains('open') ? 'rotate(180deg)' : '';
}

function fillInput(chip) {
  const input = document.getElementById('chat-input');
  input.value = chip.textContent.trim();
  input.focus();
  autoResize(input);
}

function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px'; }

// ── START ─────────────────────────────────────────────────────────────────
document.addEventListener('click', closeChatMenus);
document.addEventListener('DOMContentLoaded', () => { init(); initUpload(); });
