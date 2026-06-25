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
    App.emailMessages = await arrayOrEmpty(r);
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
    docSel.innerHTML = '<option value="none">No document search</option>';
    docSel.value = 'none';
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
    email_doc_context: 'none'
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
        <div class="council-field"><label>Persona</label><div class="council-field-help">Controls reply role, tone, and drafting style.</div><select class="council-select email-row-persona" data-id="${m.id}"><option value="">No persona</option>${App.personas.map(p => `<option value="${esc(p.id)}" ${p.id === m.persona_id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div>
        <div class="council-field"><label>RAG scope</label><div class="council-field-help">Controls which documents can be searched for this reply.</div><select class="council-select email-row-docs" data-id="${m.id}"><option value="none">No document search</option></select></div>
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
