// ── ADMIN USERS ──────────────────────────────────────────────────────────
async function loadAdminUsers() {
  if (!App.v2.user?.is_system_admin) return false;
  try {
    const [usersRes, workspacesRes] = await Promise.all([
      fetch('/api/v2/admin/users?page_size=200', {cache:'no-store'}),
      fetch('/api/v2/admin/workspaces', {cache:'no-store'})
    ]);
    if (!usersRes.ok) throw new Error(await apiError(usersRes));
    if (!workspacesRes.ok) throw new Error(await apiError(workspacesRes));
    const users = await usersRes.json();
    const workspaces = await workspacesRes.json();
    App.adminUsers = users.items || [];
    App.adminWorkspaces = workspaces.items || [];
    renderAdminWorkspaceOptions();
    renderAdminUsers();
    return true;
  } catch(e) {
    showToast('Failed to load users: ' + e.message, 'error');
    return false;
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
  if (App.adminExpandedUserId && !App.adminUsers.some(user => user.id === App.adminExpandedUserId)) {
    App.adminExpandedUserId = null;
  }
  list.innerHTML = App.adminUsers.map(user => {
    const identityParts = [user.username, user.email].filter(Boolean);
    const identityMeta = Array.from(new Set(identityParts.map(part => part.trim()).filter(Boolean))).join(' · ');
    const isExpanded = App.adminExpandedUserId === user.id;
    const userMemberships = user.memberships || [];
    const membershipCount = userMemberships.length;
    const memberships = userMemberships.length ? `
      <div class="admin-membership-list" role="table" aria-label="Workspace access for ${esc(user.display_name)}">
        <div class="admin-membership-row admin-membership-header" role="row">
          <div role="columnheader">Workspace</div>
          <div role="columnheader">Role</div>
          <div role="columnheader">Action</div>
        </div>
        ${userMemberships.map(m => `
          <div class="admin-membership-row" role="row">
            <div role="cell">${esc(m.workspace_name)}</div>
            <div role="cell">${esc(m.role)}</div>
            <div role="cell"><button class="btn-secondary compact-btn" type="button" onclick="removeAdminUserMembership('${esc(user.id)}','${esc(m.workspace_id)}')">Remove</button></div>
          </div>
        `).join('')}
      </div>
    ` : '<div class="council-card-desc">No workspace access</div>';
    const workspaceOptions = ['<option value="">Add workspace</option>'].concat(App.adminWorkspaces.map(w => `<option value="${esc(w.id)}">${esc(w.name)}</option>`)).join('');
    return `
      <div class="council-row admin-user-row ${isExpanded ? 'expanded' : ''}">
        <button class="admin-user-summary" type="button" onclick="toggleAdminUser('${esc(user.id)}')" aria-expanded="${isExpanded ? 'true' : 'false'}">
          <div class="admin-user-summary-main">
            <div class="council-card-title">${esc(user.display_name)}</div>
            <div class="council-card-meta">${esc(identityMeta)}</div>
          </div>
          <div class="admin-user-summary-meta">
            <span class="council-status ${user.is_active ? 'completed' : 'error'}">${user.is_active ? 'Active' : 'Inactive'}</span>
            ${user.is_system_admin ? '<span class="council-status running">system admin</span>' : ''}
            ${user.must_change_credentials ? '<span class="council-status">password change pending</span>' : ''}
            <span class="stat-pill"><strong>${membershipCount}</strong> ${membershipCount === 1 ? 'workspace' : 'workspaces'}</span>
            <span class="admin-user-chevron">${isExpanded ? 'Collapse' : 'Edit'}</span>
          </div>
        </button>
        ${isExpanded ? `
          <div class="admin-user-details">
            <section class="admin-user-section">
              <div class="admin-user-section-head">
                <div>
                  <div class="admin-user-section-title">Account Details</div>
                  <div class="council-card-desc">Identity and account permissions.</div>
                </div>
                <button class="btn-secondary" type="button" onclick="saveAdminUser('${esc(user.id)}')">Save Account</button>
              </div>
              <div class="admin-user-fields">
                <div class="council-field">
                  <label for="admin-user-username-${esc(user.id)}">Username</label>
                  <input class="council-input admin-user-username" id="admin-user-username-${esc(user.id)}" data-id="${esc(user.id)}" value="${esc(user.username || '')}" placeholder="Username"/>
                </div>
                <div class="council-field">
                  <label for="admin-user-display-${esc(user.id)}">Display name</label>
                  <input class="council-input admin-user-display" id="admin-user-display-${esc(user.id)}" data-id="${esc(user.id)}" value="${esc(user.display_name || '')}" placeholder="Display name"/>
                </div>
                <div class="council-field">
                  <label for="admin-user-email-${esc(user.id)}">Email</label>
                  <input class="council-input admin-user-email" id="admin-user-email-${esc(user.id)}" data-id="${esc(user.id)}" value="${esc(user.email || '')}" placeholder="Email"/>
                </div>
              </div>
              <div class="council-actions">
                <label class="admin-check"><input class="admin-user-active" data-id="${esc(user.id)}" type="checkbox" ${user.is_active ? 'checked' : ''}/> Active</label>
                <label class="admin-check"><input class="admin-user-system" data-id="${esc(user.id)}" type="checkbox" ${user.is_system_admin ? 'checked' : ''}/> System admin</label>
                <div class="council-field-help">System admins can manage users and global administration across the app.</div>
              </div>
            </section>

            <section class="admin-user-section">
              <div class="admin-user-section-head">
                <div>
                  <div class="admin-user-section-title">Password</div>
                  <div class="council-card-desc">Enter a new password before setting it.</div>
                </div>
                <button class="btn-secondary" type="button" onclick="resetAdminUserPassword('${esc(user.id)}')">Set New Password</button>
              </div>
              <div class="council-field">
                <label for="admin-user-password-${esc(user.id)}">New password</label>
                <input class="council-input admin-user-password" id="admin-user-password-${esc(user.id)}" data-id="${esc(user.id)}" type="password" value="" placeholder="New password" autocomplete="new-password" minlength="8" readonly onfocus="this.removeAttribute('readonly')"/>
              </div>
            </section>

            <section class="admin-user-section">
              <div class="admin-user-section-title">Workspace Access</div>
              <div class="admin-user-memberships">${memberships}</div>
              <div class="admin-add-access">
                <div class="council-field">
                  <label for="admin-membership-workspace-${esc(user.id)}">Workspace to add</label>
                  <select class="council-select admin-membership-workspace" id="admin-membership-workspace-${esc(user.id)}" data-id="${esc(user.id)}">${workspaceOptions}</select>
                </div>
                <div class="council-field">
                  <label for="admin-membership-role-${esc(user.id)}">Role to add</label>
                  <div class="council-field-help">Members can work in the workspace. Admins can manage workspace access and settings.</div>
                  <select class="council-select admin-membership-role" id="admin-membership-role-${esc(user.id)}" data-id="${esc(user.id)}"><option value="member">Member</option><option value="admin">Admin</option></select>
                </div>
                <button class="btn-secondary" type="button" onclick="addAdminUserMembership('${esc(user.id)}')">Add Access</button>
              </div>
            </section>

            <section class="admin-user-section admin-user-danger">
              <div>
                <div class="admin-user-section-title">Delete User</div>
                <div class="council-card-desc">Remove this account permanently.</div>
              </div>
              <button class="danger-btn" type="button" onclick="deleteAdminUser('${esc(user.id)}')">Delete User</button>
            </section>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

function toggleAdminUser(userId) {
  App.adminExpandedUserId = App.adminExpandedUserId === userId ? null : userId;
  renderAdminUsers();
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
    const created = await r.json();
    App.adminExpandedUserId = created.id;
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
    const refreshed = await loadAdminUsers();
    showToast(refreshed ? 'User saved.' : 'User saved, but the list could not refresh.', refreshed ? 'success' : 'warning');
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
    const refreshed = await loadAdminUsers();
    showToast(refreshed ? 'Password reset.' : 'Password reset, but the list could not refresh.', refreshed ? 'success' : 'warning');
  } catch(e) { showToast('Failed to reset password: ' + e.message, 'error'); }
}

async function deleteAdminUser(userId) {
  if (!confirm('Delete this user? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    const refreshed = await loadAdminUsers();
    showToast(refreshed ? 'User deleted.' : 'User deleted, but the list could not refresh.', refreshed ? 'success' : 'warning');
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
    const refreshed = await loadAdminUsers();
    showToast(refreshed ? 'Workspace access added.' : 'Workspace access added, but the list could not refresh.', refreshed ? 'success' : 'warning');
  } catch(e) { showToast('Failed to add workspace: ' + e.message, 'error'); }
}

async function removeAdminUserMembership(userId, workspaceId) {
  try {
    const r = await fetch(`/api/v2/admin/users/${encodeURIComponent(userId)}/memberships/${encodeURIComponent(workspaceId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    const refreshed = await loadAdminUsers();
    showToast(refreshed ? 'Workspace access removed.' : 'Workspace access removed, but the list could not refresh.', refreshed ? 'success' : 'warning');
  } catch(e) { showToast('Failed to remove workspace: ' + e.message, 'error'); }
}
