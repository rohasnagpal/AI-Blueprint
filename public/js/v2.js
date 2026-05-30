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
  const workspaceShow = App.v2.user ? 'flex' : 'none';
  const workspaceNav = document.getElementById('settings-nav-workspaces');
  const mattersNav = document.getElementById('settings-nav-matters');
  const settingsNav = document.getElementById('settings-nav-users');
  const mainNav = document.getElementById('nav-admin-users');
  if (workspaceNav) workspaceNav.style.display = workspaceShow;
  if (mattersNav) mattersNav.style.display = workspaceShow;
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

async function loadV2Matters() {
  const r = await v2Fetch('/matters?page_size=200');
  if (!r || !r.ok) return;
  const data = await r.json();
  App.v2.matters = data.items || [];
}

async function loadV2ShellData() {
  await Promise.all([loadV2Matters(), loadV2Documents(), loadV2Personas(), loadV2Secrets()]);
  renderV2Shell();
  renderUploadMatterSelector();
  updateChatScopeControls();
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
  if (!App.v2.enabled || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = uploadWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || (App.v2.activeMatterId && App.v2.activeMatterId !== 'all' ? App.v2.activeMatterId : '');
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = '<option value="">Workspace documents</option>' + matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId);
}

function uploadWorkspaceId() {
  const selectValue = document.getElementById('upload-workspace-select')?.value || '';
  const workspaces = App.v2.workspaces || [];
  if (selectValue && workspaces.some(w => w.workspace_id === selectValue)) return selectValue;
  return App.v2.workspaceId || workspaces[0]?.workspace_id || null;
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
}

function selectedUploadMatterId() {
  const value = document.getElementById('upload-matter-select')?.value || '';
  return value.trim() || null;
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
  matterSelect.innerHTML = '<option value="">No matter</option>' + matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderTranslateScopeSelector).catch(() => {});
}

function translateWorkspaceId() {
  const selectValue = document.getElementById('translate-workspace-select')?.value || '';
  const workspaces = App.v2.workspaces || [];
  if (selectValue && workspaces.some(w => w.workspace_id === selectValue)) return selectValue;
  return App.v2.workspaceId || workspaces[0]?.workspace_id || null;
}

function onTranslateWorkspaceChange() {
  const matterSelect = document.getElementById('translate-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderTranslateScopeSelector();
}

function selectedTranslateMatterId() {
  const value = document.getElementById('translate-matter-select')?.value || '';
  return value.trim() || null;
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
    filter.innerHTML = `<option value="all">All matters</option>${options}`;
    filter.value = App.v2.activeMatterId && App.v2.activeMatterId !== '' ? App.v2.activeMatterId : 'all';
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
  if (pluginId === 'contract_review') return {review_standard:'balanced', jurisdiction:'', risk_tolerance:'medium', mode:'workflow'};
  return {review_standard:'balanced', jurisdiction:'', risk_tolerance:'medium'};
}

function v2PluginRunFields(blueprint) {
  if (!blueprint) return '';
  if (blueprint.plugin_id === 'contract_review') {
    const playbooks = App.v2.contractReviewPlaybooks || [];
    const documents = App.v2.documents || [];
    const playbookOptions = ['<option value="">Auto-select playbook</option>'].concat(playbooks.map(p => `<option value="${esc(p.id)}">${esc(p.name)}${p.contract_category ? ' · ' + esc(p.contract_category.toUpperCase()) : ''}</option>`)).join('');
    const matchingIndexedDocs = documents.filter(doc => doc.status === 'indexed' && (!blueprint.matter_id || doc.matter_id === blueprint.matter_id));
    const sourceDocs = documents.length
      ? documents.map(doc => {
        const isIndexed = doc.status === 'indexed';
        const matchesMatter = !blueprint.matter_id || doc.matter_id === blueprint.matter_id;
        const checked = isIndexed && matchesMatter && matchingIndexedDocs.length > 0;
        const disabled = !isIndexed ? 'disabled' : '';
        const statusLabel = !isIndexed ? ` (${esc(doc.status || 'not indexed')})` : (!matchesMatter ? ' (other matter)' : '');
        return `<label class="contract-source-option ${!isIndexed ? 'disabled' : ''}"><input type="checkbox" class="contract-source-doc" value="${esc(doc.id)}" ${checked ? 'checked' : ''} ${disabled}/> <span>${esc(doc.original_name || 'Document')}${statusLabel}</span></label>`;
      }).join('')
      : '<div class="council-card-desc">Upload a document before starting a structured review.</div>';
    return `
      <div class="council-field"><label for="v2-plugin-run-title">Run title</label><input class="council-input" id="v2-plugin-run-title" placeholder="Contract review"/></div>
      <div class="council-form-row">
        <div class="council-field"><label for="v2-contract-review-mode">Review mode</label><select class="council-select" id="v2-contract-review-mode"><option value="workflow">Structured workflow</option></select></div>
        <div class="council-field"><label for="v2-contract-playbook">Playbook</label><select class="council-select" id="v2-contract-playbook">${playbookOptions}</select></div>
      </div>
      <div class="council-field">
        <label>Source documents</label>
        <div class="contract-source-docs">${sourceDocs}</div>
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
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  const base = `/api/v2/workspaces/${encodeURIComponent(App.v2.workspaceId)}/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(run.id)}`;
  if (blueprint.plugin_id === 'contract_review') {
    const reviewButton = run.mode === 'workflow' ? `<button class="btn-secondary" type="button" onclick="openContractReviewRun('${esc(run.id)}')">Review</button>` : '';
    const auditButton = run.mode === 'workflow' ? `<button class="btn-secondary" type="button" onclick="openContractAuditPackage('${esc(run.id)}')">Audit JSON</button>` : '';
    return `
      ${reviewButton}
      ${auditButton}
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
  if (blueprint.plugin_id === 'contract_review') {
    host.innerHTML = renderContractReviewPluginWorkspace(blueprint, matter, config, runs);
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
      ${blueprint.plugin_id === 'contract_review' ? renderContractPlaybookManager() : ''}
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
      ${blueprint.plugin_id === 'contract_review' ? renderContractReviewWorkspace() : ''}
        </div>
  `;
}

function renderContractReviewPluginWorkspace(blueprint, matter, config, runs) {
  const active = App.v2.activeContractRun?.run;
  return `
    <div class="settings-card-header contract-review-shell-header">
      <div>
        <div class="settings-card-title">${active ? esc(active.title || 'Contract review') : esc(blueprint.name)}</div>
        <div class="settings-card-subtitle">${active ? 'Single contract review' : esc(v2PluginLabel(blueprint.plugin_id))}${matter ? ' · ' + esc(matter.name) : ''}</div>
      </div>
      <div class="contract-shell-actions">
        ${active ? `<button class="btn-secondary" type="button" onclick="closeContractReviewRun()">All Reviews</button>` : ''}
        <button class="btn-secondary" type="button" onclick="openV2BlueprintChat('${esc(blueprint.id)}')">Chat</button>
      </div>
    </div>
    <div class="council-form v2-plugin-workspace-body contract-review-shell">
      ${active ? renderContractReviewWorkspace() : renderContractReviewDashboard(blueprint, config, runs)}
    </div>
  `;
}

function renderContractReviewDashboard(blueprint, config, runs) {
  const reviewRuns = runs || [];
  const completed = reviewRuns.filter(run => run.status === 'completed').length;
  const running = reviewRuns.filter(run => ['pending','running'].includes(run.status)).length;
  const complete = reviewRuns.filter(run => run.review_complete).length;
  return `
    <div class="contract-dashboard">
      <div class="contract-dashboard-summary">
        <div>
          <div class="settings-section-desc">Contract reviews</div>
          <div class="contract-dashboard-title">All Reviews</div>
        </div>
        <div class="contract-review-stats">
          <div class="stat-pill"><strong>${reviewRuns.length}</strong> reviews</div>
          <div class="stat-pill"><strong>${completed}</strong> completed</div>
          <div class="stat-pill"><strong>${running}</strong> running</div>
          <div class="stat-pill"><strong>${complete}</strong> human complete</div>
        </div>
      </div>
      <details class="contract-setup-panel">
        <summary>New review and settings</summary>
        <div class="contract-setup-content">
          <div class="settings-section-desc">New review</div>
          ${v2PluginRunFields(blueprint)}
          <div class="council-actions"><button class="btn-primary" type="button" onclick="runV2Plugin()">Run Contract Review</button></div>
          <div class="settings-section-desc">Plugin config</div>
          <div class="council-field"><textarea class="council-textarea" id="v2-plugin-config-json">${esc(JSON.stringify(config, null, 2))}</textarea></div>
          <div class="council-actions">
            <button class="btn-secondary" type="button" onclick="saveV2PluginConfig()">Save Config</button>
            <button class="btn-secondary" type="button" onclick="loadV2PluginData()">Refresh</button>
          </div>
          ${renderContractPlaybookManager()}
        </div>
      </details>
      <div class="contract-review-cards">
        ${reviewRuns.length ? reviewRuns.map(run => renderContractReviewDashboardRow(blueprint, run)).join('') : '<div class="contract-empty-state">No contract reviews yet. Start one from New review and settings.</div>'}
      </div>
    </div>
  `;
}

function renderContractReviewDashboardRow(blueprint, run) {
  const statusDetail = run.status_detail || (run.review_complete ? 'Review complete' : 'Human review pending');
  const started = run.completed_at || run.started_at || run.created_at;
  const dateLabel = started ? new Date(started).toLocaleString() : 'n/a';
  return `<div class="contract-review-card-row">
    <div class="contract-review-card-main">
      <div class="contract-review-card-title">
        <strong>${esc(run.title || 'Contract review')}</strong>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="contract-review-card-meta">
        <span>${esc(run.config_snapshot?.document_ids?.length ? run.config_snapshot.document_ids.length + ' source document(s)' : 'Source documents captured in run')}</span>
        <span>${esc(statusDetail)}</span>
        <span>${esc(dateLabel)}</span>
      </div>
      ${renderV2RunProgress(run)}
      ${run.error ? `<div class="contract-run-error">${esc(run.error)}</div>` : ''}
    </div>
    <div class="contract-row-actions">${renderContractReviewDashboardActions(run)}</div>
  </div>`;
}

function renderContractReviewDashboardActions(run) {
  const reviewButton = run.mode === 'workflow' ? `<button class="btn-primary" type="button" onclick="openContractReviewRun('${esc(run.id)}')">Open Review</button>` : '';
  const auditButton = run.mode === 'workflow' ? `<button class="btn-secondary" type="button" onclick="openContractAuditPackage('${esc(run.id)}')">Audit JSON</button>` : '';
  const chatButton = App.v2.activeBlueprintId ? `<button class="btn-secondary" type="button" onclick="openV2BlueprintChat('${esc(App.v2.activeBlueprintId)}')">Chat</button>` : '';
  return `
    ${reviewButton}
    ${auditButton}
    <button class="btn-secondary" type="button" onclick="exportV2PluginRun('${esc(run.id)}')">Export</button>
    ${chatButton}
    <button class="danger-btn" type="button" onclick="deleteV2PluginRun('${esc(run.id)}')">Delete</button>
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

function closeContractReviewRun() {
  App.v2.activeContractRun = null;
  App.v2.activeContractClauses = [];
  App.v2.activeContractTrace = [];
  App.v2.activeContractEscalations = [];
  renderV2PluginWorkspace();
}

function renderContractPlaybookManager() {
  const playbooks = App.v2.contractReviewPlaybooks || [];
  const editingId = App.v2.editingContractPlaybookId;
  const editing = playbooks.find(p => p.id === editingId);
  const canEdit = !!editing && !editing.is_builtin;
  return `<div class="contract-playbook-manager">
    <div class="settings-section-desc">Playbooks</div>
    <div class="council-form compact-playbook-form">
      <div class="council-form-row">
        <div class="council-field"><label for="contract-playbook-name">Name</label><input class="council-input" id="contract-playbook-name" value="${esc(editing?.name || '')}" placeholder="Workspace playbook"/></div>
        <div class="council-field"><label for="contract-playbook-category">Category</label><input class="council-input" id="contract-playbook-category" value="${esc(editing?.contract_category || 'msa')}" placeholder="msa"/></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label for="contract-playbook-version">Version</label><input class="council-input" id="contract-playbook-version" value="${esc(editing?.version || '1.0')}"/></div>
        <div class="council-field"><label for="contract-playbook-status">Status</label><select class="council-select" id="contract-playbook-status">${['active','draft','archived'].map(s => `<option value="${s}" ${editing?.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      </div>
      <div class="council-field"><label for="contract-playbook-clauses">Clauses JSON</label><textarea class="council-textarea playbook-clauses-json" id="contract-playbook-clauses">${esc(JSON.stringify((editing?.clauses || defaultContractPlaybookClauses()), null, 2))}</textarea></div>
      <div class="council-actions">
        <button class="btn-primary" type="button" onclick="saveContractPlaybook()">${canEdit ? 'Update Playbook' : 'Create Playbook'}</button>
        <button class="btn-secondary" type="button" onclick="newContractPlaybook()">New</button>
      </div>
    </div>
    <div class="council-list contract-playbook-list">
      ${playbooks.length ? playbooks.map(p => `<div class="council-row">
        <div class="council-row-head">
          <div>
            <div class="council-card-title">${esc(p.name)}</div>
            <div class="council-card-meta">${esc(p.contract_category)} · v${esc(p.version)}${p.is_builtin ? ' · built-in' : ' · workspace'}</div>
          </div>
          <span class="council-status ${esc(p.status || 'active')}">${esc(p.status || 'active')}</span>
        </div>
        <div class="council-actions">
          <button class="btn-secondary" type="button" onclick="loadContractPlaybook('${esc(p.id)}')">${p.is_builtin ? 'Use as Draft' : 'Edit'}</button>
        </div>
      </div>`).join('') : '<div class="council-row"><div class="council-card-desc">No playbooks available.</div></div>'}
    </div>
  </div>`;
}

function defaultContractPlaybookClauses() {
  return [
    {clause_type:'limitation_of_liability', title:'Limitation of Liability', required:true, severity_default:'critical', prohibited_patterns:['unlimited liability']},
    {clause_type:'indemnity', title:'Indemnity', required:true, severity_default:'high', prohibited_patterns:['uncapped indemnity']},
    {clause_type:'governing_law', title:'Governing Law', required:true, severity_default:'high', prohibited_patterns:['missing governing law']}
  ];
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
  const config = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/config`);
  App.v2.pluginConfig = config?.ok ? (await config.json()).config : defaultV2PluginConfig(blueprint.plugin_id);
  if (blueprint.plugin_id === 'contract_review') {
    const playbooks = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/playbooks`);
    if (playbooks?.ok) App.v2.contractReviewPlaybooks = await playbooks.json();
    const modules = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/workflow-modules`);
    if (modules?.ok) App.v2.contractReviewModules = (await modules.json()).items || [];
  }
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
  if (blueprint.plugin_id === 'contract_review') {
    const mode = document.getElementById('v2-contract-review-mode')?.value || 'workflow';
    const playbookId = document.getElementById('v2-contract-playbook')?.value || '';
    const documentIds = Array.from(document.querySelectorAll('.contract-source-doc:checked')).map(input => input.value).filter(Boolean);
    if (!documentIds.length) { showToast('Select at least one source document.', 'error'); return; }
    body.mode = mode;
    body.config = {...(App.v2.pluginConfig || {}), mode};
    if (playbookId) body.config.playbook_id = playbookId;
    body.config.document_ids = documentIds;
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

async function loadContractPlaybook(playbookId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/contract-review/playbooks/${encodeURIComponent(playbookId)}`);
    if (!r?.ok) throw new Error(await apiError(r));
    const playbook = await r.json();
    const existingIndex = App.v2.contractReviewPlaybooks.findIndex(p => p.id === playbook.id);
    if (existingIndex >= 0) App.v2.contractReviewPlaybooks[existingIndex] = playbook;
    else App.v2.contractReviewPlaybooks.push(playbook);
    App.v2.editingContractPlaybookId = playbook.is_builtin ? null : playbook.id;
    renderV2PluginWorkspace();
    const nameInput = document.getElementById('contract-playbook-name');
    if (playbook.is_builtin && nameInput) nameInput.value = `${playbook.name} Copy`;
    const categoryInput = document.getElementById('contract-playbook-category');
    if (categoryInput) categoryInput.value = playbook.contract_category || 'msa';
    const versionInput = document.getElementById('contract-playbook-version');
    if (versionInput) versionInput.value = playbook.is_builtin ? '1.0' : (playbook.version || '1.0');
    const statusInput = document.getElementById('contract-playbook-status');
    if (statusInput) statusInput.value = 'active';
    const clausesInput = document.getElementById('contract-playbook-clauses');
    if (clausesInput) clausesInput.value = JSON.stringify(playbook.clauses || defaultContractPlaybookClauses(), null, 2);
  } catch(e) { showToast('Failed to load playbook: ' + e.message, 'error'); }
}

function newContractPlaybook() {
  App.v2.editingContractPlaybookId = null;
  renderV2PluginWorkspace();
}

async function saveContractPlaybook() {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  let clauses;
  try { clauses = JSON.parse(document.getElementById('contract-playbook-clauses')?.value || '[]'); }
  catch(e) { showToast('Clauses JSON must be valid.', 'error'); return; }
  if (!Array.isArray(clauses)) { showToast('Clauses JSON must be an array.', 'error'); return; }
  const payload = {
    name: document.getElementById('contract-playbook-name')?.value.trim() || '',
    contract_category: document.getElementById('contract-playbook-category')?.value.trim() || '',
    version: document.getElementById('contract-playbook-version')?.value.trim() || '1.0',
    status: document.getElementById('contract-playbook-status')?.value || 'active',
    rules: {review_posture:'balanced'},
    clauses
  };
  if (!payload.name || !payload.contract_category) { showToast('Playbook name and category are required.', 'error'); return; }
  const editingId = App.v2.editingContractPlaybookId;
  const method = editingId ? 'PUT' : 'POST';
  const path = editingId
    ? `/blueprints/${encodeURIComponent(blueprint.id)}/contract-review/playbooks/${encodeURIComponent(editingId)}`
    : `/blueprints/${encodeURIComponent(blueprint.id)}/contract-review/playbooks`;
  try {
    const r = await v2Fetch(path, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r?.ok) throw new Error(await apiError(r));
    const saved = await r.json();
    App.v2.editingContractPlaybookId = saved.id;
    const playbooks = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/contract-review/playbooks`);
    if (playbooks?.ok) App.v2.contractReviewPlaybooks = await playbooks.json();
    const existingIndex = App.v2.contractReviewPlaybooks.findIndex(p => p.id === saved.id);
    if (existingIndex >= 0) App.v2.contractReviewPlaybooks[existingIndex] = saved;
    else App.v2.contractReviewPlaybooks.push(saved);
    renderV2PluginWorkspace();
    showToast('Playbook saved.');
  } catch(e) { showToast('Playbook save failed: ' + e.message, 'error'); }
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

async function openContractAuditPackage(runId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}/audit-package`);
    if (!r?.ok) throw new Error(await apiError(r));
    const data = await r.json();
    const text = JSON.stringify(data, null, 2);
    downloadTextFile(text, `${slugify(data.run?.title || 'contract-review')}-audit.json`, 'application/json');
    showToast('Audit package downloaded.');
  } catch(e) { showToast('Audit package failed: ' + e.message, 'error'); }
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

function renderContractWorkflowModules() {
  const modules = App.v2.contractReviewModules || [];
  if (!modules.length) return '';
  return `<div class="council-row contract-modules-panel">
    <div class="council-row-head">
      <div>
        <div class="council-card-title">Workflow modules</div>
        <div class="council-card-meta">Structured review stages and their JSON contracts.</div>
      </div>
    </div>
    <div class="contract-module-strip">
      ${modules.map(module => `<div class="contract-module-chip">
        <strong>${esc(module.name || module.id)}</strong>
        <span>${esc(module.execution || 'sequential')} · ${esc(module.output_schema || '')}</span>
      </div>`).join('')}
    </div>
  </div>`;
}

function renderContractReviewWorkspace() {
  const run = App.v2.activeContractRun;
  if (!run) {
    const latestWorkflow = (App.v2.pluginRuns || []).find(r => r.mode === 'workflow' && r.status === 'completed');
    return `<div class="contract-review-workspace">
      <div class="settings-section-desc">Structured review workspace</div>
      <div class="council-row">
        <div class="council-row-head">
          <div>
            <div class="council-card-title">Clause-by-clause review</div>
            <div class="council-card-meta">Run a structured workflow review, then open it here.</div>
          </div>
          ${latestWorkflow ? `<button class="btn-secondary" type="button" onclick="openContractReviewRun('${esc(latestWorkflow.id)}')">Open Latest</button>` : ''}
        </div>
      </div>
      ${renderContractWorkflowModules()}
    </div>`;
  }
  const clauses = App.v2.activeContractClauses || [];
  const trace = App.v2.activeContractTrace || [];
  const escalations = App.v2.activeContractEscalations || [];
  const summaries = run.summaries || [];
  const filteredClauses = filterContractClauses(clauses);
  const critical = clauses.filter(item => (item.risks || []).some(r => r.risk_level === 'critical')).length;
  const high = clauses.filter(item => (item.risks || []).some(r => r.risk_level === 'high')).length;
  const reviewNeeded = clauses.filter(item => (item.risks || []).some(r => r.requires_review)).length;
  const openHighEscalations = escalations.filter(e => (e.status || 'open') === 'open' && ['high', 'critical'].includes(e.severity || 'high')).length;
  const pendingClauses = clauses.filter(item => (item.clause?.review_status || 'pending') === 'pending').length;
  const selected = filteredClauses[0]?.clause;
  return `<div class="contract-review-workspace">
    <div class="contract-review-page-head">
      <div>
        <div class="settings-section-desc">Review detail</div>
        <div class="contract-dashboard-title">${esc(run.run?.title || 'Contract review')}</div>
        <div class="council-card-meta">${esc(run.run?.status_detail || run.run?.status || 'pending')}${run.run?.coverage_score !== null && run.run?.coverage_score !== undefined ? ' · coverage ' + esc(String(run.run.coverage_score)) : ''}</div>
      </div>
      <div class="contract-detail-nav" aria-label="Contract review sections">
        <a href="#contract-summary-section">Summary</a>
        <a href="#contract-issues-section">Issues</a>
        <a href="#contract-clauses-section">Clauses</a>
        <a href="#contract-trace-section">Trace</a>
      </div>
    </div>
    ${renderContractCompletionPanel(run.run, pendingClauses, openHighEscalations)}
    <div class="contract-review-stats">
      <div class="stat-pill"><strong>${clauses.length}</strong> clauses</div>
      <div class="stat-pill"><strong>${reviewNeeded}</strong> need review</div>
      <div class="stat-pill"><strong>${high}</strong> high</div>
      <div class="stat-pill"><strong>${critical}</strong> critical</div>
      <div class="stat-pill"><strong>${escalations.length}</strong> escalations</div>
      <div class="stat-pill"><strong>${trace.length}</strong> trace steps</div>
    </div>
    <div id="contract-summary-section">${renderContractSummaries(summaries) || '<div class="contract-empty-state">No summary is available yet.</div>'}</div>
    <div id="contract-issues-section">
      ${renderContractRiskHeatmap(clauses)}
      ${renderContractEscalationPanel(escalations)}
    </div>
    <div id="contract-clauses-section">${renderContractClauseFilters(clauses, filteredClauses)}</div>
    <div class="contract-review-grid">
      <div class="contract-review-list">
        ${filteredClauses.length ? filteredClauses.map(item => renderContractClauseRow(run.run.id, item)).join('') : '<div class="council-row"><div class="council-card-desc">No clauses match the current filters.</div></div>'}
      </div>
      <div class="contract-review-detail" id="contract-review-detail">
        ${selected ? renderContractClausePreview(run.run.id, filteredClauses[0]) : renderContractSummaries(summaries)}
      </div>
    </div>
    <div id="contract-trace-section" class="contract-trace-panel">
      <details>
        <summary>Workflow trace and modules</summary>
        ${renderContractWorkflowModules()}
        <div class="contract-trace-list">
          ${trace.length ? trace.map(step => `<div class="trace-step"><strong>${esc(step.step_name)}</strong><span>${esc(step.status)}${step.confidence_score ? ' · ' + esc(String(step.confidence_score)) : ''}</span></div>`).join('') : '<div class="council-card-desc">No trace records yet.</div>'}
        </div>
      </details>
      </div>
  </div>`;
}

function filterContractClauses(clauses) {
  const filters = App.v2.contractReviewFilters || {};
  let items = [...(clauses || [])];
  if (filters.risk && filters.risk !== 'all') {
    items = items.filter(item => (item.risks || []).some(r => r.risk_level === filters.risk));
  }
  if (filters.status && filters.status !== 'all') {
    items = items.filter(item => (item.clause?.review_status || 'pending') === filters.status);
  }
  if (filters.type && filters.type !== 'all') {
    items = items.filter(item => item.clause?.clause_type === filters.type);
  }
  const sort = filters.sort || 'risk';
  items.sort((a, b) => {
    if (sort === 'status') return String(a.clause?.review_status || 'pending').localeCompare(String(b.clause?.review_status || 'pending'));
    if (sort === 'type') return String(a.clause?.clause_type || '').localeCompare(String(b.clause?.clause_type || ''));
    return topContractRiskRank(b) - topContractRiskRank(a) || String(a.clause?.clause_type || '').localeCompare(String(b.clause?.clause_type || ''));
  });
  return items;
}

function renderContractClauseFilters(clauses, filteredClauses) {
  const filters = App.v2.contractReviewFilters || {};
  const types = Array.from(new Set((clauses || []).map(item => item.clause?.clause_type).filter(Boolean))).sort();
  const statuses = Array.from(new Set((clauses || []).map(item => item.clause?.review_status || 'pending'))).sort();
  const option = (value, label, selected) => `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>${esc(label)}</option>`;
  return `<div class="contract-filter-panel">
    <div>
      <div class="council-card-title">Clause Filters</div>
      <div class="council-card-meta">${filteredClauses.length} of ${(clauses || []).length} clauses shown</div>
    </div>
    <div class="contract-filter-controls">
      <label>Risk<select class="council-input" onchange="setContractClauseFilter('risk', this.value)">
        ${option('all', 'All risks', filters.risk || 'all')}
        ${['critical','high','medium','low'].map(level => option(level, level, filters.risk)).join('')}
      </select></label>
      <label>Status<select class="council-input" onchange="setContractClauseFilter('status', this.value)">
        ${option('all', 'All statuses', filters.status || 'all')}
        ${statuses.map(status => option(status, status.replace(/_/g, ' '), filters.status)).join('')}
      </select></label>
      <label>Type<select class="council-input" onchange="setContractClauseFilter('type', this.value)">
        ${option('all', 'All types', filters.type || 'all')}
        ${types.map(type => option(type, type.replace(/_/g, ' '), filters.type)).join('')}
      </select></label>
      <label>Sort<select class="council-input" onchange="setContractClauseFilter('sort', this.value)">
        ${option('risk', 'Risk first', filters.sort || 'risk')}
        ${option('status', 'Status', filters.sort || 'risk')}
        ${option('type', 'Clause type', filters.sort || 'risk')}
      </select></label>
      <button class="btn-secondary" type="button" onclick="resetContractClauseFilters()">Reset</button>
    </div>
  </div>`;
}

function setContractClauseFilter(key, value) {
  App.v2.contractReviewFilters = {...(App.v2.contractReviewFilters || {}), [key]: value};
  renderV2PluginWorkspace();
}

function resetContractClauseFilters() {
  App.v2.contractReviewFilters = {risk: 'all', status: 'all', type: 'all', sort: 'risk'};
  renderV2PluginWorkspace();
}

function renderContractCompletionPanel(run, pendingClauses, openHighEscalations) {
  const complete = !!run?.review_complete;
  const blockers = [];
  if (pendingClauses) blockers.push(`${pendingClauses} pending clause${pendingClauses === 1 ? '' : 's'}`);
  if (openHighEscalations) blockers.push(`${openHighEscalations} open high/critical escalation${openHighEscalations === 1 ? '' : 's'}`);
  const canComplete = !complete && run?.status === 'completed' && blockers.length === 0;
  return `<div class="contract-completion-panel">
    <div>
      <div class="council-card-title">Review Completion</div>
      <div class="council-card-meta">${complete ? 'Human review has been marked complete.' : blockers.length ? esc(blockers.join(' · ')) : 'Ready for human completion.'}</div>
    </div>
    <div class="contract-completion-actions">
      <span class="council-status ${complete ? 'completed' : blockers.length ? 'running' : 'pending'}">${complete ? 'complete' : blockers.length ? 'blocked' : 'ready'}</span>
      <button class="btn-primary" type="button" onclick="completeContractReviewRun()" ${canComplete ? '' : 'disabled'}>Mark Review Complete</button>
    </div>
  </div>`;
}

async function completeContractReviewRun() {
  const runId = App.v2.activeContractRun?.run?.id;
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!runId || !blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}/complete`, {method:'PUT'});
    if (!r?.ok) throw new Error(await apiError(r));
    showToast('Review marked complete.', 'success');
    await openContractReviewRun(runId);
  } catch(e) { showToast('Review completion failed: ' + e.message, 'error'); }
}

function renderContractRiskHeatmap(clauses) {
  const levels = ['critical', 'high', 'medium', 'low'];
  const types = Array.from(new Set((clauses || []).map(item => item.clause?.clause_type).filter(Boolean))).sort();
  if (!types.length) return '';
  const count = (type, level) => clauses.filter(item => item.clause?.clause_type === type && (item.risks || []).some(r => r.risk_level === level)).length;
  return `<div class="contract-heatmap">
    <div class="council-card-title">Risk Heatmap</div>
    <div class="contract-heatmap-grid" style="grid-template-columns:minmax(140px,1fr) repeat(${levels.length}, minmax(70px, 0.45fr))">
      <div class="heatmap-head">Clause</div>${levels.map(level => `<div class="heatmap-head">${esc(level)}</div>`).join('')}
      ${types.map(type => `<div class="heatmap-label">${esc(type.replace(/_/g, ' '))}</div>${levels.map(level => {
        const value = count(type, level);
        return `<button class="heatmap-cell risk-${esc(level)} ${value ? 'has-risk' : ''}" type="button" onclick="focusContractRisk('${esc(type)}','${esc(level)}')">${value || ''}</button>`;
      }).join('')}`).join('')}
    </div>
  </div>`;
}

function renderContractEscalationPanel(escalations) {
  if (!escalations?.length) return '';
  return `<div class="contract-escalations">
    <div class="council-row-head">
      <div>
        <div class="council-card-title">Escalations</div>
        <div class="council-card-meta">Items requiring human review before external delivery</div>
      </div>
    </div>
    <div class="contract-escalation-list">
      ${escalations.map(e => `<div class="contract-escalation-item">
        <span class="risk-badge risk-${esc(e.severity || 'high')}">${esc(e.severity || 'high')}</span>
        <span><strong>${esc(e.reason || 'Escalation')}</strong><small>${esc(e.required_action || '')}</small></span>
        <span class="contract-escalation-actions">
          <span class="council-status ${esc(e.status || 'open')}">${esc(e.status || 'open')}</span>
          ${(e.status || 'open') === 'open' ? `<button class="btn-secondary" type="button" onclick="updateContractEscalation('${esc(e.id)}','resolve')">Resolve</button><button class="btn-secondary" type="button" onclick="updateContractEscalation('${esc(e.id)}','dismiss')">Dismiss</button>` : ''}
        </span>
      </div>`).join('')}
    </div>
  </div>`;
}

async function updateContractEscalation(escalationId, action) {
  if (!App.v2.activeContractRun?.run?.id) return;
  if (!['resolve', 'dismiss'].includes(action)) return;
  try {
    const r = await v2Fetch(`/escalations/${encodeURIComponent(escalationId)}/${action}`, {method:'PUT'});
    if (!r?.ok) throw new Error(await apiError(r));
    showToast(action === 'resolve' ? 'Escalation resolved.' : 'Escalation dismissed.');
    await openContractReviewRun(App.v2.activeContractRun.run.id);
  } catch(e) { showToast('Escalation update failed: ' + e.message, 'error'); }
}

function focusContractRisk(clauseType, riskLevel) {
  const match = (App.v2.activeContractClauses || []).find(item => item.clause?.clause_type === clauseType && (item.risks || []).some(r => r.risk_level === riskLevel));
  if (match?.clause?.id && App.v2.activeContractRun?.run?.id) {
    loadContractClauseDetail(App.v2.activeContractRun.run.id, match.clause.id);
  }
}

function renderContractClauseRow(runId, item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  const topRisk = risks.sort((a,b) => riskRank(b.risk_level) - riskRank(a.risk_level))[0];
  const risk = topRisk?.risk_level || 'low';
  return `<button class="contract-clause-row" type="button" onclick="loadContractClauseDetail('${esc(runId)}','${esc(clause.id)}')">
    <span>
      <strong>${esc(clause.title || clause.clause_type || 'Clause')}</strong>
      <small>${esc(clause.source?.filename || 'source')} ${clause.source?.chunk_index !== undefined && clause.source?.chunk_index !== null ? '· chunk ' + esc(String(Number(clause.source.chunk_index) + 1)) : ''}</small>
    </span>
    <span class="risk-badge risk-${esc(risk)}">${esc(risk)}</span>
    <span class="council-status ${esc(clause.review_status || 'pending')}">${esc(clause.review_status || 'pending')}</span>
  </button>`;
}

function renderContractClausePreview(runId, item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  return `<div class="contract-clause-detail-card">
    <div class="council-row-head">
      <div>
        <div class="council-card-title">${esc(clause.title || clause.clause_type || 'Clause')}</div>
        <div class="council-card-meta">${esc(clause.source?.filename || 'source')} · confidence ${esc(String(clause.confidence_score ?? 'n/a'))}</div>
      </div>
      <span class="council-status ${esc(clause.review_status || 'pending')}">${esc(clause.review_status || 'pending')}</span>
    </div>
    <div class="contract-clause-text">${esc(clause.text || '')}</div>
    ${renderContractSourceEvidence(clause.source || {})}
    ${risks.length ? `<div class="contract-risk-list">${risks.map(r => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(r.risk_level)}">${esc(r.risk_level)}</span><span>${esc(r.reasoning || '')}</span></div>`).join('')}</div>` : ''}
    <div class="council-actions">
      <button class="btn-secondary" type="button" onclick="recordContractClauseDecision('${esc(runId)}','${esc(clause.id)}','approve')">Approve</button>
      <button class="btn-secondary" type="button" onclick="recordContractClauseDecision('${esc(runId)}','${esc(clause.id)}','request_revision')">Request Revision</button>
      <button class="danger-btn" type="button" onclick="recordContractClauseDecision('${esc(runId)}','${esc(clause.id)}','reject')">Reject</button>
    </div>
  </div>`;
}

function renderContractSourceEvidence(source) {
  if (!source || !Object.keys(source).length) return '';
  const chunk = source.chunk_index !== undefined && source.chunk_index !== null ? Number(source.chunk_index) + 1 : null;
  const offsets = source.start_offset !== undefined && source.start_offset !== null && source.end_offset !== undefined && source.end_offset !== null
    ? `${source.start_offset}-${source.end_offset}`
    : '';
  return `<div class="contract-source-evidence">
    <div class="source-evidence-head">Source Evidence</div>
    <div class="source-meta-grid">
      <span><strong>File</strong>${esc(source.filename || 'source')}</span>
      <span><strong>Chunk</strong>${chunk ? esc(String(chunk)) : 'n/a'}</span>
      <span><strong>Page</strong>${source.page ? esc(String(source.page)) : 'n/a'}</span>
      <span><strong>Offsets</strong>${offsets ? esc(offsets) : 'n/a'}</span>
    </div>
    ${source.excerpt ? `<div class="source-excerpt">${esc(source.excerpt)}</div>` : ''}
  </div>`;
}

function renderContractSummaries(summaries) {
  if (!summaries?.length) return '';
  return `<div class="contract-summary-tabs">
    ${summaries.map(s => `<div class="contract-summary-card">
      <div class="council-card-title">${esc((s.audience || 'summary').replace(/_/g, ' '))}</div>
      <div class="council-card-desc">${esc(s.summary_text || '')}</div>
      ${(s.negotiation_points || []).length ? `<ul>${s.negotiation_points.slice(0,4).map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
    </div>`).join('')}
  </div>`;
}

function riskRank(level) {
  return {critical:4, high:3, medium:2, low:1}[level] || 0;
}

function topContractRiskRank(item) {
  return Math.max(0, ...(item?.risks || []).map(r => riskRank(r.risk_level)));
}

async function openContractReviewRun(runId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const base = `/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}`;
    const detail = await v2Fetch(base);
    const clauses = await v2Fetch(`${base}/clauses`);
    const trace = await v2Fetch(`${base}/trace`);
    const escalations = await v2Fetch(`/escalations/blueprints/${encodeURIComponent(blueprint.id)}?page_size=100`);
    if (!detail?.ok) throw new Error(await apiError(detail));
    if (!clauses?.ok) throw new Error(await apiError(clauses));
    if (!trace?.ok) throw new Error(await apiError(trace));
    App.v2.activeContractRun = await detail.json();
    App.v2.activeContractClauses = await clauses.json();
    App.v2.activeContractTrace = await trace.json();
    App.v2.activeContractEscalations = escalations?.ok ? ((await escalations.json()).items || []).filter(e => e.source_id === runId) : [];
    renderV2PluginWorkspace();
  } catch(e) { showToast('Failed to open review: ' + e.message, 'error'); }
}

async function loadContractClauseDetail(runId, clauseId) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}/clauses/${encodeURIComponent(clauseId)}`);
    if (!r?.ok) throw new Error(await apiError(r));
    const data = await r.json();
    const host = document.getElementById('contract-review-detail');
    if (host) host.innerHTML = renderContractClauseFull(runId, data);
  } catch(e) { showToast('Failed to load clause: ' + e.message, 'error'); }
}

function renderContractClauseFull(runId, data) {
  const clause = data.clause || {};
  const risks = data.risk_findings || [];
  const playbook = data.playbook_findings || [];
  const playbookClauses = data.playbook_clauses || [];
  const redlines = data.redline_suggestions || [];
  const decisions = data.decisions || [];
  return `${renderContractClausePreview(runId, {clause, risks})}
    <div class="contract-detail-sections">
      ${renderContractComparisonView(clause, playbook, playbookClauses, redlines)}
      <div class="contract-detail-section"><div class="council-card-title">Review History</div>${decisions.length ? decisions.map(d => `<div class="council-card-desc"><strong>${esc(d.decision)}</strong>${d.note ? ': ' + esc(d.note) : ''} · ${esc(new Date(d.created_at).toLocaleString())}</div>`).join('') : '<div class="council-card-desc">No decisions yet.</div>'}</div>
    </div>`;
}

function renderContractComparisonView(clause, findings, playbookClauses, redlines) {
  const finding = (findings || [])[0] || {};
  const standard = (playbookClauses || []).find(item => item.id === finding.playbook_clause_id) || (playbookClauses || [])[0] || {};
  const suggestion = (redlines || [])[0] || {};
  return `<div class="contract-detail-section">
    <div class="council-card-title">AI Suggestion vs Playbook Standard</div>
    <div class="contract-comparison-grid">
      <div class="comparison-pane">
        <div class="comparison-label">Extracted Clause</div>
        <div class="comparison-text">${esc(clause.text || '')}</div>
      </div>
      <div class="comparison-pane">
        <div class="comparison-label">Playbook Standard</div>
        ${standard.approved_text ? `<div class="comparison-text">${esc(standard.approved_text)}</div>` : '<div class="council-card-desc">No playbook standard text for this clause.</div>'}
        ${finding.status ? `<div class="comparison-foot"><span class="council-status ${esc(finding.status)}">${esc(finding.status)}</span><span>${esc(finding.deviation_summary || '')}</span></div>` : ''}
      </div>
      <div class="comparison-pane">
        <div class="comparison-label">Suggested Fallback</div>
        ${suggestion.fallback_language ? `<div class="comparison-text">${esc(suggestion.fallback_language)}</div>` : standard.fallback_text ? `<div class="comparison-text">${esc(standard.fallback_text)}</div>` : '<div class="council-card-desc">No fallback language generated for this clause.</div>'}
        ${suggestion.suggestion_text ? `<div class="comparison-foot">${esc(suggestion.suggestion_text)}</div>` : ''}
      </div>
    </div>
    ${(findings || []).length ? `<div class="contract-finding-list">${findings.map(p => `<div class="contract-finding-item"><strong>${esc(p.status)}</strong><span>${esc(p.deviation_summary || '')}</span></div>`).join('')}</div>` : ''}
  </div>`;
}

async function recordContractClauseDecision(runId, clauseId, decision) {
  const blueprint = App.v2.blueprints.find(b => b.id === App.v2.activeBlueprintId);
  if (!blueprint) return;
  const note = decision === 'approve' ? '' : prompt('Optional review note') || '';
  const segment = v2PluginApiSegment(blueprint.plugin_id);
  try {
    const r = await v2Fetch(`/blueprints/${encodeURIComponent(blueprint.id)}/${segment}/runs/${encodeURIComponent(runId)}/clauses/${encodeURIComponent(clauseId)}/decisions`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({decision, note})});
    if (!r?.ok) throw new Error(await apiError(r));
    showToast('Decision saved.');
    await openContractReviewRun(runId);
    await loadContractClauseDetail(runId, clauseId);
  } catch(e) { showToast('Decision failed: ' + e.message, 'error'); }
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
