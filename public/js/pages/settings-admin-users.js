// ── ADMIN USERS ──────────────────────────────────────────────────────────
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
            ${user.must_change_credentials ? '<span class="council-status">password change pending</span>' : ''}
          </div>
        </div>
        <div class="admin-user-fields">
          <input class="council-input admin-user-username" data-id="${esc(user.id)}" value="${esc(user.username || '')}" placeholder="Username"/>
          <input class="council-input admin-user-display" data-id="${esc(user.id)}" value="${esc(user.display_name || '')}" placeholder="Display name"/>
          <input class="council-input admin-user-email" data-id="${esc(user.id)}" value="${esc(user.email || '')}" placeholder="Email"/>
          <input class="council-input admin-user-password" data-id="${esc(user.id)}" type="password" value="" placeholder="New password" autocomplete="new-password" minlength="8" readonly onfocus="this.removeAttribute('readonly')"/>
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
  const usernameInput = document.getElementById('admin-user-username');
  const displayInput = document.getElementById('admin-user-display');
  const passwordInput = document.getElementById('admin-user-password');
  const payload = {
    username: usernameInput?.value.trim(),
    display_name: displayInput?.value.trim(),
    email: document.getElementById('admin-user-email')?.value.trim() || null,
    password: passwordInput?.value || '',
    workspace_id: document.getElementById('admin-user-workspace')?.value || null,
    workspace_role: document.getElementById('admin-user-role')?.value || 'member',
    is_system_admin: !!document.getElementById('admin-user-system-admin')?.checked
  };
  if (!payload.username || !payload.display_name || !payload.password) {
    showToast('Username, display name, and temporary password are required.', 'error');
    return;
  }
  if (payload.username.length < 3) {
    showToast('Username must be at least 3 characters.', 'error');
    usernameInput?.focus();
    return;
  }
  if (payload.password.length < 8) {
    showToast('Temporary password must be at least 8 characters.', 'error');
    passwordInput?.focus();
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
  const passwordInput = adminInput('.admin-user-password', userId);
  const password = passwordInput?.value || '';
  if (!password) {
    showToast('Enter a new password first.', 'error');
    passwordInput?.focus();
    return;
  }
  if (password.length < 8) {
    showToast('New password must be at least 8 characters.', 'error');
    passwordInput?.focus();
    return;
  }
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}/reset-password`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password, must_change_credentials:false})});
    if (!r.ok) throw new Error(await apiError(r));
    if (passwordInput) passwordInput.value = '';
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
