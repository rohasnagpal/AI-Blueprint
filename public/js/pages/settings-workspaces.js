// ── WORKSPACE MANAGER ─────────────────────────────────────────────────────
function workspaceApi(workspaceId, path = '') {
  return `/api/v2/workspaces/${encodeURIComponent(workspaceId)}${path}`;
}

function workspaceManagerSelected() {
  return App.workspaceManager.workspaces.find(w => w.id === App.workspaceManager.selectedId) || null;
}

function firstAvailableWorkspaceId() {
  const workspaces = App.workspaceManager.workspaces || [];
  if (App.v2.workspaceId && workspaces.some(w => w.id === App.v2.workspaceId)) {
    return App.v2.workspaceId;
  }
  return workspaces[0]?.id || null;
}

async function loadWorkspaceManagerFallback() {
  const r = await fetch('/api/v2/me/navigation?page_size=200');
  if (!r.ok) throw new Error(await apiError(r));
  const data = await r.json();
  App.workspaceManager.workspaces = (data.items || []).map(w => ({
    id: w.workspace_id,
    name: w.workspace_name || 'Workspace',
    slug: null,
    role: w.role || 'member'
  }));
}

async function loadWorkspaceManager() {
  if (!App.v2.user) {
    renderWorkspaceManagerSignedOut();
    return;
  }
  let primaryError = null;
  try {
    const r = await fetch('/api/v2/workspaces?page_size=200');
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.workspaceManager.workspaces = data.items || [];
  } catch(e) {
    primaryError = e;
    try {
      await loadWorkspaceManagerFallback();
    } catch(fallbackError) {
      showToast('Failed to load workspaces: ' + fallbackError.message, 'error');
      return;
    }
  }
  try {
    if (!App.workspaceManager.workspaces.some(w => w.id === App.workspaceManager.selectedId)) {
      App.workspaceManager.selectedId = firstAvailableWorkspaceId();
    }
    await loadWorkspaceManagerMatters();
    renderWorkspaceManager();
    if (primaryError) showToast('Loaded workspaces with limited details.', 'error');
  } catch(e) {
    showToast('Failed to load workspace matters: ' + e.message, 'error');
  }
}

function renderWorkspaceManagerSignedOut() {
  const empty = '<div class="council-row"><div class="council-card-desc">Sign in to manage workspaces and matters.</div></div>';
  const workspaceSelect = document.getElementById('workspace-manager-select');
  const matterWorkspaceSelect = document.getElementById('matter-manager-workspace-select');
  const detail = document.getElementById('workspace-manager-detail');
  const matters = document.getElementById('workspace-manager-matters');
  if (workspaceSelect) workspaceSelect.innerHTML = '<option value="">Sign in first</option>';
  if (matterWorkspaceSelect) matterWorkspaceSelect.innerHTML = '<option value="">Sign in first</option>';
  if (detail) detail.innerHTML = empty;
  if (matters) matters.innerHTML = empty;
}

function renderWorkspaceManager() {
  renderWorkspaceManagerList();
  renderWorkspaceManagerDetail();
  renderWorkspaceManagerMatters();
}

function renderWorkspaceManagerList() {
  const selects = [
    document.getElementById('workspace-manager-select'),
    document.getElementById('matter-manager-workspace-select')
  ].filter(Boolean);
  if (!selects.length) return;
  if (!App.workspaceManager.workspaces.length) {
    selects.forEach(select => {
      select.innerHTML = '<option value="">Create a workspace first</option>';
      select.value = '';
    });
    return;
  }
  const options = App.workspaceManager.workspaces.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');
  const value = App.workspaceManager.selectedId || App.workspaceManager.workspaces[0]?.id || '';
  selects.forEach(select => {
    select.innerHTML = options;
    select.value = value;
  });
}

function renderWorkspaceManagerDetail() {
  const selected = workspaceManagerSelected();
  const detail = document.getElementById('workspace-manager-detail');
  el('workspace-manager-selected-title', selected ? selected.name : 'Workspace');
  el('workspace-manager-selected-subtitle', selected ? `${selected.role || 'member'}` : 'Select a workspace to manage its details and matters.');
  if (!detail) return;
  if (!selected) {
    detail.innerHTML = '<div class="council-row"><div class="council-card-desc">Select a workspace first.</div></div>';
    return;
  }
  const canAdmin = selected.role === 'admin' || App.v2.user?.is_system_admin;
  detail.innerHTML = `<div class="council-form-row">
      <div class="council-field"><label for="workspace-edit-name">Name</label><input class="council-input" id="workspace-edit-name" value="${esc(selected.name)}" ${canAdmin ? '' : 'disabled'}/></div>
    </div>
    <div class="council-actions">
      ${canAdmin ? `<button class="btn-primary" type="button" onclick="updateWorkspaceManagerWorkspace()">Save Workspace</button><button class="danger-btn" type="button" onclick="deleteWorkspaceManagerWorkspace('${esc(selected.id)}')">Delete Workspace</button>` : '<span class="council-card-desc">Only workspace admins can edit workspace details.</span>'}
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
        <div class="council-field"><label>Status</label><select class="council-select matter-edit-status" data-id="${esc(m.id)}"><option value="active" ${m.status === 'active' ? 'selected' : ''}>Active</option><option value="closed" ${m.status === 'closed' ? 'selected' : ''}>Closed</option></select></div>
        <div class="council-field"><label>Description</label><input class="council-input matter-edit-description" data-id="${esc(m.id)}" value="${esc(m.description || '')}"/></div>
      </div>
      <div class="council-actions">
        <button class="btn-primary" type="button" onclick="updateWorkspaceManagerMatter('${esc(m.id)}')">Save Matter</button>
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
  if (!name) {
    showToast('Workspace name is required.', 'error');
    return;
  }
  try {
    const r = await fetch('/api/v2/workspaces', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})});
    if (!r.ok) throw new Error(await apiError(r));
    const workspace = await r.json();
    App.workspaceManager.selectedId = workspace.id;
    ['workspace-name'].forEach(id => { const input = document.getElementById(id); if (input) input.value = ''; });
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
  if (!name) {
    showToast('Workspace name is required.', 'error');
    return;
  }
  try {
    const r = await fetch(workspaceApi(selected.id), {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, slug: selected.slug || null})});
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
  if (!workspace || !confirm(`Permanently delete workspace "${workspace.name}" and all related matters, documents, chats, runs, and outputs? This cannot be undone.`)) return;
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
    showToast('Choose a workspace first.', 'error');
    return;
  }
  if (App.workspaceManager.selectedId !== workspaceId) {
    App.workspaceManager.selectedId = workspaceId;
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
  let matter = null;
  try {
    const r = await fetch(workspaceApi(workspaceId, '/matters'), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    matter = await r.json();
    ['matter-name','matter-client','matter-description'].forEach(id => { const input = document.getElementById(id); if (input) input.value = ''; });
    const status = document.getElementById('matter-status');
    if (status) status.value = 'active';
  } catch(e) {
    showToast('Failed to create matter: ' + e.message, 'error');
    return;
  }
  try {
    await loadWorkspaceManagerMatters();
    if (matter?.id) App.v2.activeMatterId = matter.id;
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter created.');
  } catch(e) {
    showToast('Matter created, but refresh failed: ' + e.message, 'error');
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
  } catch(e) {
    showToast('Failed to save matter: ' + e.message, 'error');
    return;
  }
  try {
    await loadWorkspaceManagerMatters();
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter saved.');
  } catch(e) {
    showToast('Matter saved, but refresh failed: ' + e.message, 'error');
  }
}

async function deleteWorkspaceManagerMatter(matterId) {
  const workspaceId = App.workspaceManager.selectedId;
  const matter = App.workspaceManager.matters.find(m => m.id === matterId);
  if (!workspaceId || !matter || !confirm(`Permanently delete matter "${matter.name}" and all related documents, chats, runs, and outputs? This cannot be undone.`)) return;
  try {
    const r = await fetch(workspaceApi(workspaceId, `/matters/${encodeURIComponent(matterId)}`), {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
  } catch(e) {
    showToast('Failed to delete matter: ' + e.message, 'error');
    return;
  }
  try {
    await loadWorkspaceManagerMatters();
    if (workspaceId === App.v2.workspaceId) await loadV2ShellData();
    renderWorkspaceManager();
    showToast('Matter deleted.');
  } catch(e) {
    showToast('Matter deleted, but refresh failed: ' + e.message, 'error');
  }
}
