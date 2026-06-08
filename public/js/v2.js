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
        body:JSON.stringify({name:'Default Workspace'})
      });
      if (created.ok) {
        const navAgain = await fetch('/api/v2/me/navigation');
        if (navAgain.ok) workspaces = (await navAgain.json()).items || [];
      }
    }
    const currentWorkspaceId = workspaces.some(w => w.workspace_id === App.v2.workspaceId)
      ? App.v2.workspaceId
      : workspaces[0]?.workspace_id || null;
    App.v2 = {
      ...App.v2,
      enabled: !!workspaces.length,
      workspaceId: currentWorkspaceId,
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
  el('v2-auth-subtitle', mode === 'setup' ? 'Create the local admin username used by workspace features.' : 'Sign in with your username to enable workspace features.');
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
      documents: [],
      personas: [],
      secrets: [],
      activeMatterId: '',
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
    if (error) { error.textContent = 'Username, password, and display name are required.'; error.style.display = 'block'; }
    return;
  }
  if (App.v2.setupRequired && password.length < 12) {
    if (error) { error.textContent = 'Password must be at least 12 characters.'; error.style.display = 'block'; }
    return;
  }
  try {
    if (submit) submit.disabled = true;
    const url = App.v2.setupRequired ? '/api/v2/auth/setup' : '/api/v2/auth/login';
    const payload = App.v2.setupRequired ? {username: identifier, password, display_name: displayName} : {identifier, password};
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
  const workspaceShow = 'flex';
  const workspaceNav = document.getElementById('settings-nav-workspaces');
  const mattersNav = document.getElementById('settings-nav-matters');
  const settingsNav = document.getElementById('settings-nav-users');
  const activityNav = document.getElementById('settings-nav-activity');
  const mainNav = document.getElementById('nav-admin-users');
  if (workspaceNav) workspaceNav.style.display = workspaceShow;
  if (mattersNav) mattersNav.style.display = workspaceShow;
  if (settingsNav) settingsNav.style.display = show;
  if (activityNav) activityNav.style.display = show;
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

function appPathForView(name) {
  return VIEW_ROUTES[name] || '/chat';
}

function viewForAppPath(pathname) {
  return ROUTE_VIEWS[pathname.replace(/\/+$/, '') || '/'] || null;
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

function v2ExistingWorkspaceId(selectValue = '') {
  const workspaces = App.v2.workspaces || [];
  if (selectValue && workspaces.some(w => w.workspace_id === selectValue)) return selectValue;
  if (App.v2.workspaceId && workspaces.some(w => w.workspace_id === App.v2.workspaceId)) return App.v2.workspaceId;
  return workspaces[0]?.workspace_id || null;
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
  const matterId = App.v2.activeMatterId || App.v2.matters[0]?.id || '';
  if (!matterId) {
    App.v2.documents = [];
    if (typeof normalizeV2Document === 'function') App.documents = [];
    return;
  }
  const r = await v2Fetch(`/documents?page_size=200&matter_id=${encodeURIComponent(matterId)}`);
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.documents = data.items || [];
  if (typeof normalizeV2Document === 'function') {
    App.documents = App.v2.documents.map(normalizeV2Document);
  }
}

async function loadV2Matters() {
  const r = await v2Fetch('/matters?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.matters = data.items || [];
  if (!App.v2.matters.some(m => m.id === App.v2.activeMatterId)) {
    App.v2.activeMatterId = App.v2.matters[0]?.id || '';
  }
}

async function loadV2ShellData() {
  await loadV2Matters();
  await Promise.all([loadV2Documents(), loadV2Personas(), loadV2Secrets()]);
  renderV2Shell();
  renderUploadMatterSelector();
  updateChatScopeControls();
  if (document.getElementById('view-view-docs')?.classList.contains('active')) {
    renderDocsScopeSelector();
    renderDocuments(document.querySelector('.search-input')?.value || '');
    updateDocsBadge();
  }
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

function renderUploadMatterSelector() {
  const workspaceSelect = document.getElementById('upload-workspace-select');
  const matterSelect = document.getElementById('upload-matter-select');
  const card = document.getElementById('upload-matter-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  card.style.display = 'grid';
  workspaceSelect.disabled = false;
  matterSelect.disabled = false;
  if (!App.v2.user) {
    workspaceSelect.innerHTML = '<option value="">Sign in to use workspaces</option>';
    matterSelect.innerHTML = '<option value="">Sign in to choose a matter</option>';
    workspaceSelect.disabled = true;
    matterSelect.disabled = true;
    return;
  }
  if (!App.v2.enabled || !workspaces.length) {
    workspaceSelect.innerHTML = '<option value="">No workspaces available</option>';
    matterSelect.innerHTML = '<option value="">Create a workspace first</option>';
    workspaceSelect.disabled = true;
    matterSelect.disabled = true;
    return;
  }
  const currentWorkspaceId = uploadWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || (App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : '');
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matters.length) {
    matterSelect.innerHTML = '<option value="">Create a matter first</option>';
    matterSelect.disabled = true;
  }
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId);
}

function uploadWorkspaceId() {
  const selectValue = document.getElementById('upload-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function uploadMattersForWorkspace(workspaceId) {
  if (!workspaceId) return [];
  if (workspaceId === App.v2.workspaceId) return App.v2.matters || [];
  return App.v2.uploadMattersByWorkspace?.[workspaceId] || [];
}

async function loadUploadMattersForWorkspace(workspaceId) {
  if (!workspaceId || App.v2.uploadMattersByWorkspace?.[workspaceId]) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/matters?page_size=200`);
    if (!r.ok) return;
    const data = await r.json();
    App.v2.uploadMattersByWorkspace = {...(App.v2.uploadMattersByWorkspace || {}), [workspaceId]: data.items || []};
    if (uploadWorkspaceId() === workspaceId) renderUploadMatterSelector();
  } catch(e) {}
}

function onUploadWorkspaceChange() {
  const matterSelect = document.getElementById('upload-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderUploadMatterSelector();
  if (typeof loadFolderSources === 'function') loadFolderSources();
}

function selectedUploadMatterId() {
  const value = document.getElementById('upload-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(uploadWorkspaceId())[0]?.id || null;
}

function renderTranslateScopeSelector() {
  const workspaceSelect = document.getElementById('translate-workspace-select');
  const matterSelect = document.getElementById('translate-matter-select');
  const card = document.getElementById('translate-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = translateWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || (App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : '');
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderTranslateScopeSelector).catch(() => {});
}

function translateWorkspaceId() {
  const selectValue = document.getElementById('translate-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function onTranslateWorkspaceChange() {
  const matterSelect = document.getElementById('translate-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderTranslateScopeSelector();
}

function selectedTranslateMatterId() {
  const value = document.getElementById('translate-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(translateWorkspaceId())[0]?.id || null;
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
  if (!App.v2.enabled) {
    if (workspaceSelect) workspaceSelect.innerHTML = '<option>Sign in to multi-user access</option>';
    el('v2-stat-matters', '0');
    el('v2-stat-documents', '0');
    const empty = '<div class="council-row"><div class="council-card-desc">Sign in to use workspaces and matters.</div></div>';
    const matters = document.getElementById('v2-matters-list');
    if (matters) matters.innerHTML = empty;
    return;
  }
  if (workspaceSelect) {
    workspaceSelect.innerHTML = App.v2.workspaces.map(w => `<option value="${esc(w.workspace_id)}">${esc(w.workspace_name || w.name || 'Workspace')}</option>`).join('');
    workspaceSelect.value = App.v2.workspaceId || '';
  }
  el('v2-stat-matters', App.v2.matters.length);
  el('v2-stat-documents', App.v2.documents.length);
  renderV2MatterOptions();
  renderV2Matters();
}

function renderV2MatterOptions() {
  const filter = document.getElementById('v2-matter-filter');
  const options = App.v2.matters.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  if (filter) {
    filter.innerHTML = options;
    filter.value = App.v2.activeMatterId || App.v2.matters[0]?.id || '';
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
    const client = m.client_name ? ` · ${esc(m.client_name)}` : '';
    return `<div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(m.name)}</div>
          <div class="council-card-meta">${esc(m.status || 'active')}${client}</div>
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
  const active = App.v2.activeMatterId || App.v2.matters[0]?.id || '';
  const rows = App.v2.blueprints.filter(b => b.matter_id === active);
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
        <button class="btn-secondary" type="button" onclick="openV2BlueprintInNewTab('${b.id}')">Open</button>
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
  return {ai_council:'council', legal_research:'legal-research'}[pluginId] || pluginId;
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
  if (pluginId === 'contract_review') return {};
  return {review_standard:'balanced', jurisdiction:'', risk_tolerance:'medium'};
}

function v2PluginRunFields(blueprint) {
  if (!blueprint) return '';
  if (blueprint.plugin_id === 'contract_review') {
    return `
      <div class="council-row">
        <div class="council-row-head">
          <div>
            <div class="council-card-title">Use Standalone Contract Review</div>
            <div class="council-card-desc">Blueprint-backed contract review is not enabled in this build. The standalone Contract Review workspace is the supported path.</div>
          </div>
          <button class="btn-primary" type="button" onclick="switchView('contract-review')">Open Contract Review</button>
        </div>
      </div>
    `;
  }
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
  if (blueprint.plugin_id === 'contract_review') {
    return '<button class="btn-primary" type="button" onclick="switchView(\'contract-review\')">Open Contract Review</button>';
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
  if (blueprint.plugin_id === 'contract_review') {
    host.innerHTML = renderContractReviewUnavailableWorkspace(blueprint, matter);
    return;
  }
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

function renderContractReviewUnavailableWorkspace(blueprint, matter) {
  return `
    <div class="settings-card-header contract-review-shell-header">
      <div>
        <div class="settings-card-title">${esc(blueprint.name)}</div>
        <div class="settings-card-subtitle">${esc(v2PluginLabel(blueprint.plugin_id))}${matter ? ' · ' + esc(matter.name) : ''}</div>
      </div>
      <div class="contract-shell-actions">
        <button class="btn-secondary" type="button" onclick="openV2BlueprintChat('${esc(blueprint.id)}')">Chat</button>
        <button class="btn-primary" type="button" onclick="switchView('contract-review')">Open Contract Review</button>
      </div>
    </div>
    <div class="council-form v2-plugin-workspace-body contract-review-shell">
      <div class="council-row">
        <div class="council-row-head">
          <div>
            <div class="council-card-title">Blueprint Contract Review Disabled</div>
            <div class="council-card-desc">This build only supports the standalone Contract Review workspace. Blueprint-specific contract review runs, playbooks, clause decisions, and audit packages are hidden until their backend routes exist.</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function blueprintWorkspaceUrl(blueprintId) {
  const params = new URLSearchParams();
  params.set('view', 'blueprints');
  if (App.v2.workspaceId) params.set('workspace', App.v2.workspaceId);
  params.set('blueprint', blueprintId);
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
}

function openV2BlueprintInNewTab(blueprintId) {
  const opened = window.open(blueprintWorkspaceUrl(blueprintId), '_blank', 'noopener');
  if (!opened) openV2Blueprint(blueprintId);
}

async function loadV2PluginData() {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  App.v2.pluginConfig = null;
  App.v2.pluginRuns = [];
  App.v2.contractReviewPlaybooks = [];
  App.v2.contractReviewModules = [];
  App.v2.activeContractRun = null;
  App.v2.activeContractClauses = [];
  App.v2.activeContractTrace = [];
  App.v2.activeContractEscalations = [];
  if (blueprint.plugin_id === 'contract_review') {
    App.v2.pluginConfig = defaultV2PluginConfig(blueprint.plugin_id);
    renderV2PluginWorkspace();
    return;
  }
  const config = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/config`);
  App.v2.pluginConfig = config?.ok ? (await config.json()).config : defaultV2PluginConfig(blueprint.plugin_id);
  const runs = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs?page_size=50`);
  if (runs?.ok) App.v2.pluginRuns = (await runs.json()).items || [];
  await loadV2PluginJobs(blueprint);
  renderV2PluginWorkspace();
}

async function openBlueprintDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const blueprintId = params.get('blueprint');
  const workspaceId = params.get('workspace');
  if (!blueprintId || !App.v2.enabled) return;
  applyBlueprintFocusMode();
  if (workspaceId && workspaceId !== App.v2.workspaceId && App.v2.workspaces.some(w => w.workspace_id === workspaceId)) {
    App.v2.workspaceId = workspaceId;
    await loadV2ShellData();
  }
  const blueprint = App.v2.blueprints.find(b => b.id === blueprintId);
  if (!blueprint) return;
  App.v2.activeBlueprintId = blueprintId;
  App.v2.activeMatterId = blueprint.matter_id || '';
  switchView('blueprints');
  renderV2Shell();
  await loadV2PluginData();
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
  if (blueprint.plugin_id === 'contract_review') {
    showToast('Use the standalone Contract Review page for contract review settings.', 'error');
    switchView('contract-review');
    return;
  }
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
  if (blueprint.plugin_id === 'contract_review') {
    showToast('Use the standalone Contract Review page for contract reviews.', 'error');
    switchView('contract-review');
    return;
  }
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
    const run = (App.v2.pluginRuns || []).find(item => item.id === runId) || App.v2.activeContractRun?.run || {};
    downloadTextFile(text, `${slugify(run.title || blueprint.name || 'review-export')}.md`, 'text/markdown;charset=utf-8');
    showToast('Export downloaded.');
  } catch(e) { showToast('Export failed: ' + e.message, 'error'); }
}

function downloadTextFile(text, filename, type) {
  const blob = new Blob([text], {type});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(a.href);
  a.remove();
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
  App.v2.activeMatterId = '';
  App.v2.activeBlueprintId = null;
  await loadV2ShellData();
}

async function syncV2WorkspaceMatterDocuments(workspaceId, matterId = '', matterSelect = null, options = {}) {
  if (!App.v2.enabled || !App.v2.user || !workspaceId) return;
  if (workspaceId !== App.v2.workspaceId) await setV2Workspace(workspaceId);
  let matters = uploadMattersForWorkspace(workspaceId);
  if (!matters.length) {
    await loadUploadMattersForWorkspace(workspaceId);
    matters = uploadMattersForWorkspace(workspaceId);
  }
  const requestedMatter = options.resetMatter ? '' : matterId;
  const selectedMatter = matters.some(m => m.id === requestedMatter) ? requestedMatter : '';
  const activeMatter = matters.some(m => m.id === App.v2.activeMatterId) ? App.v2.activeMatterId : '';
  const nextMatter = selectedMatter || activeMatter || matters[0]?.id || '';
  if (matterSelect && nextMatter) matterSelect.value = nextMatter;
  if (!nextMatter) {
    App.v2.documents = [];
    if (typeof normalizeV2Document === 'function') App.documents = [];
    return;
  }
  if (App.v2.activeMatterId !== nextMatter) {
    App.v2.activeMatterId = nextMatter;
    App.v2.activeBlueprintId = null;
  }
  await loadV2Documents();
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
  if (!confirm('Permanently delete this matter and all related documents, chats, runs, and outputs? This cannot be undone.')) return;
  try {
    const r = await v2Fetch(`/matters/${encodeURIComponent(matterId)}`, {method:'DELETE'});
    if (!r || !r.ok) throw new Error(await apiError(r));
    if (App.v2.activeMatterId === matterId) App.v2.activeMatterId = '';
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
