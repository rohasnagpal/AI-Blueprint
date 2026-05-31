// ── ADMIN ACTIVITY ────────────────────────────────────────────────────────
async function ensureAdminActivityOptions() {
  if (!App.v2.user?.is_system_admin) return false;
  if (!App.adminUsers.length || !App.adminWorkspaces.length) {
    try {
      const [usersRes, workspacesRes] = await Promise.all([
        fetch('/api/v2/admin/users?page_size=200'),
        fetch('/api/v2/admin/workspaces')
      ]);
      if (usersRes.ok) {
        const users = await usersRes.json();
        App.adminUsers = users.items || [];
      }
      if (workspacesRes.ok) {
        const workspaces = await workspacesRes.json();
        App.adminWorkspaces = workspaces.items || [];
      }
    } catch(e) {}
  }
  renderAdminActivityOptions();
  return true;
}

function renderAdminActivityOptions() {
  const userSelect = document.getElementById('admin-activity-user');
  const workspaceSelect = document.getElementById('admin-activity-workspace');
  if (userSelect) {
    const current = userSelect.value;
    userSelect.innerHTML = '<option value="">All users</option>' + App.adminUsers.map(user => `<option value="${esc(user.id)}">${esc(user.display_name || user.username || user.email || user.id)}</option>`).join('');
    userSelect.value = current;
  }
  if (workspaceSelect) {
    const current = workspaceSelect.value;
    workspaceSelect.innerHTML = '<option value="">All workspaces</option>' + App.adminWorkspaces.map(workspace => `<option value="${esc(workspace.id)}">${esc(workspace.name)}</option>`).join('');
    workspaceSelect.value = current;
  }
}

function adminActivityParams(page = App.adminActivity.page || 1) {
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('page_size', String(App.adminActivity.pageSize || 50));
  const fields = [
    ['search', 'admin-activity-search'],
    ['category', 'admin-activity-category'],
    ['user_id', 'admin-activity-user'],
    ['workspace_id', 'admin-activity-workspace'],
    ['date_from', 'admin-activity-from'],
    ['date_to', 'admin-activity-to'],
  ];
  fields.forEach(([key, id]) => {
    const value = document.getElementById(id)?.value;
    if (value) params.set(key, value);
  });
  return params;
}

async function loadAdminActivity(page = App.adminActivity.page || 1) {
  if (!(await ensureAdminActivityOptions())) return false;
  try {
    const r = await fetch(`/api/v2/admin/activity?${adminActivityParams(page).toString()}`);
    if (!r.ok) {
      const message = await apiError(r);
      if (r.status === 404) {
        App.adminActivity.items = [];
        App.adminActivity.total = 0;
        App.adminActivity.page = 1;
        App.adminActivity.selectedId = null;
        renderAdminActivity();
        const count = document.getElementById('admin-activity-count');
        if (count) count.textContent = 'Activity API unavailable. Restart the app server to load the new admin endpoint.';
        return false;
      }
      throw new Error(message);
    }
    const data = await r.json();
    App.adminActivity.items = data.items || [];
    App.adminActivity.total = data.total || 0;
    App.adminActivity.page = data.page || page;
    App.adminActivity.pageSize = data.page_size || 50;
    if (!App.adminActivity.items.some(item => item.id === App.adminActivity.selectedId)) {
      App.adminActivity.selectedId = App.adminActivity.items[0]?.id || null;
    }
    renderAdminActivity();
    return true;
  } catch(e) {
    showToast('Failed to load activity: ' + e.message, 'error');
    return false;
  }
}

function renderAdminActivity() {
  const list = document.getElementById('admin-activity-list');
  const count = document.getElementById('admin-activity-count');
  if (count) {
    const start = App.adminActivity.total ? ((App.adminActivity.page - 1) * App.adminActivity.pageSize) + 1 : 0;
    const end = Math.min(App.adminActivity.total, App.adminActivity.page * App.adminActivity.pageSize);
    count.textContent = `${start}-${end} of ${App.adminActivity.total} events`;
  }
  if (!list) return;
  if (!App.adminActivity.items.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No activity matches these filters.</div></div>';
    renderAdminActivityDetail();
    return;
  }
  list.innerHTML = App.adminActivity.items.map(item => {
    const selected = item.id === App.adminActivity.selectedId ? 'selected' : '';
    const actor = item.user?.display_name || item.user?.email || 'Unknown user';
    const workspace = item.workspace?.name || 'No workspace';
    return `<button class="activity-log-row ${selected}" type="button" onclick="selectAdminActivity('${esc(item.id)}')">
      <span class="activity-log-row-main">
        <strong>${esc(item.summary || item.action)}</strong>
        <small>${esc(actor)} · ${esc(workspace)}</small>
      </span>
      <span class="activity-log-row-meta">
        <span class="council-status">${esc(item.category || 'activity')}</span>
        <small>${esc(formatActivityDate(item.created_at))}</small>
      </span>
    </button>`;
  }).join('');
  renderAdminActivityDetail();
}

function selectAdminActivity(id) {
  App.adminActivity.selectedId = id;
  renderAdminActivity();
}

function renderAdminActivityDetail() {
  const detail = document.getElementById('admin-activity-detail');
  if (!detail) return;
  const item = App.adminActivity.items.find(event => event.id === App.adminActivity.selectedId);
  if (!item) {
    detail.innerHTML = '<div class="council-card-desc">Select an event to inspect metadata.</div>';
    return;
  }
  const actor = item.user?.display_name || item.user?.email || 'Unknown user';
  const workspace = item.workspace?.name || 'No workspace';
  detail.innerHTML = `
    <div class="activity-detail-title">${esc(item.summary || item.action)}</div>
    <dl class="activity-detail-grid">
      <dt>Time</dt><dd>${esc(formatActivityDate(item.created_at))}</dd>
      <dt>User</dt><dd>${esc(actor)}</dd>
      <dt>Workspace</dt><dd>${esc(workspace)}</dd>
      <dt>Action</dt><dd>${esc(item.action)}</dd>
      <dt>Resource</dt><dd>${esc(item.resource_type || '')}${item.resource_id ? ' · ' + esc(item.resource_id) : ''}</dd>
    </dl>
    <pre class="activity-metadata">${esc(JSON.stringify(item.metadata || {}, null, 2))}</pre>
  `;
}

function formatActivityDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function pageAdminActivity(delta) {
  const maxPage = Math.max(1, Math.ceil((App.adminActivity.total || 0) / (App.adminActivity.pageSize || 50)));
  const next = Math.min(maxPage, Math.max(1, (App.adminActivity.page || 1) + delta));
  if (next !== App.adminActivity.page) loadAdminActivity(next);
}

function resetAdminActivityFilters() {
  ['admin-activity-search','admin-activity-category','admin-activity-user','admin-activity-workspace','admin-activity-from','admin-activity-to'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  App.adminActivity.selectedId = null;
  loadAdminActivity(1);
}

function handleAdminActivitySearchKey(event) {
  if (event.key === 'Enter') loadAdminActivity(1);
}

async function exportAdminActivity() {
  if (!App.v2.user?.is_system_admin) return;
  try {
    const params = adminActivityParams(1);
    params.delete('page');
    params.delete('page_size');
    const r = await fetch(`/api/v2/admin/activity/export.csv?${params.toString()}`);
    if (!r.ok) throw new Error(await apiError(r));
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `activity-log-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
    showToast('Activity export downloaded.');
  } catch(e) {
    showToast('Activity export failed: ' + e.message, 'error');
  }
}
