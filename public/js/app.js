// ── STATE ──────────────────────────────────────────────────────────────────
const App = { currentChatId: null, settings: {}, documents: [], chats: [], personas: [], editingPersonaId: null, emailMessages: [], selectedPersonaId: '', selectedPersonaCategory: '', chatMode: 'general', selectedDocIds: 'all', webSearchEnabled: false, isStreaming: false, activeChatController: null, voice: { active: false, connecting: false, pc: null, dc: null, stream: null, audioEl: null, statusEl: null, assistantText: '', assistantEl: null, toolCalls: {} }, openChatMenuId: null, chatArchiveFilter: false, chatSelectMode: false, chatSearchQuery: '', selectedChatIds: new Set(), models: [], liveModels: {}, liveModelRequestId: 0, editingModelId: null, adminUsers: [], adminWorkspaces: [], workspaceManager: { workspaces: [], selectedId: null, matters: [] }, translation: { sourceType: 'text', file: null, result: null, isRunning: false }, drafting: { result: null, isRunning: false, job: null, events: [], stream: null, startedAt: null, history: [], historyLoading: false }, v2: { enabled: false, user: null, workspaceId: null, workspaces: [], matters: [], blueprints: [], plugins: [], documents: [], personas: [], secrets: [], activeMatterId: '', activeBlueprintId: null, pluginConfig: null, pluginRuns: [], pluginJobs: {}, pluginJobEvents: {}, pluginJobStreams: {}, pluginJobTimers: {}, contractReviewPlaybooks: [], contractReviewModules: [], editingContractPlaybookId: null, activeContractRun: null, activeContractClauses: [], activeContractTrace: [], activeContractEscalations: [], contractReviewFilters: { risk: 'all', status: 'all', type: 'all', sort: 'risk' }, setupRequired: false, skipped: localStorage.getItem('aibp_v2_skip') === 'true' } };
App.contractReview = { result: null, isRunning: false, playbooks: [] };
const NAV_CONFIG = window.AIBP_NAVIGATION || {};
const PRIMARY_NAV_ITEMS = NAV_CONFIG.primaryNavItems || [];
const MORE_NAV_ITEMS = NAV_CONFIG.moreNavItems || [];
const NAV_ITEMS = NAV_CONFIG.navItems || [];
const VIEWS = NAV_CONFIG.views || {};
const NAVS = NAV_CONFIG.navs || {};
const TITLES = NAV_CONFIG.titles || {};
const VIEW_ROUTES = NAV_CONFIG.viewRoutes || {};
const ROUTE_VIEWS = NAV_CONFIG.routeViews || {'/':'chat'};
const LAST_VIEW_KEY = 'aibp_last_view';

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

async function jsonOrFallback(response, fallback) {
  if (!response.ok) return fallback;
  const data = await response.json().catch(() => fallback);
  return data == null ? fallback : data;
}

async function arrayOrEmpty(response) {
  const data = await jsonOrFallback(response, []);
  return Array.isArray(data) ? data : [];
}

async function apiError(response) {
  if (!response) return 'Request failed.';
  const fallback = `${response.status || 'Request'} ${response.statusText || 'failed'}`.trim();
  try {
    const data = await response.json();
    return data?.error || data?.detail || data?.message || fallback;
  } catch(e) {
    try {
      return (await response.text()) || fallback;
    } catch(_e) {
      return fallback;
    }
  }
}

// ── INIT ───────────────────────────────────────────────────────────────────
async function init() {
  NAV_CONFIG.renderSidebarNav?.({switchView, switchViewFromMore, toggleSidebarMore});
  await NAV_CONFIG.loadViewFragments?.();
  await window.loadSettingsFragments?.();
  hydrateProviderKeyLinks();
  hydrateKeyToggles();
  await Promise.all([loadSettings(), loadModels(), loadChats(), loadDocuments(), loadPersonas()]);
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

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeMobileSidebar();
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 760) closeMobileSidebar();
});

function openMobileSidebar() {
  document.body.classList.add('mobile-sidebar-open');
}

function closeMobileSidebar() {
  document.body.classList.remove('mobile-sidebar-open');
}

// ── VIEW SWITCHING ────────────────────────────────────────────────────────
function switchView(name, options = {}) {
  if (!VIEWS[name]) name = 'chat';
  closeMobileSidebar();
  document.body.classList.toggle('chat-view-active', name === 'chat');
  localStorage.setItem(LAST_VIEW_KEY, name);
  const nextPath = appPathForView(name);
  if (window.location.pathname !== nextPath) {
    const state = {view: name};
    if (options.replace) window.history.replaceState(state, '', nextPath);
    else if (!options.fromPopState) window.history.pushState(state, '', nextPath);
  }
  Object.values(VIEWS).forEach(id => document.getElementById(id)?.classList.remove('active'));
  Object.values(NAVS).forEach(id => document.getElementById(id)?.classList.remove('active'));
  document.getElementById(VIEWS[name])?.classList.add('active');
  document.getElementById(NAVS[name])?.classList.add('active');
  document.getElementById('view-settings')?.classList.toggle('workspace-standalone', name === 'workspaces');
  const moreViews = MORE_NAV_ITEMS.map(item => item.view);
  document.getElementById('nav-more')?.classList.toggle('active', moreViews.includes(name));
  document.querySelectorAll('.sidebar-more-menu button').forEach(b => b.classList.remove('active'));
  const moreActive = document.getElementById('more-' + name) || (name === 'admin-users' ? document.getElementById('nav-admin-users') : null);
  moreActive?.classList.add('active');
  document.getElementById('topbar-title').textContent = TITLES[name] || name;
  document.getElementById('doc-selector').style.display = name === 'chat' ? 'flex' : 'none';
  if (name === 'view-docs') loadDocuments();
  if (name === 'personas') renderPersonas();
  if (name === 'add-doc') renderUploadMatterSelector();
  if (name === 'translate') { renderTranslateScopeSelector(); setTranslateSourceType(App.translation.sourceType); renderTranslationFile(); }
  if (name === 'contract-review') loadV2ShellData().then(renderStandaloneContractReview).catch(() => renderStandaloneContractReview());
  if (name === 'draft') { renderDraftScopeSelector(); loadDraftHistory(); }
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
  const routed = viewForAppPath(window.location.pathname);
  if (routed && VIEWS[routed]) {
    switchView(routed, {replace: true});
    return;
  }
  const saved = localStorage.getItem(LAST_VIEW_KEY);
  if (saved && VIEWS[saved]) switchView(saved, {replace: true});
  else switchView('chat', {replace: true});
}

window.addEventListener('popstate', () => {
  const routed = viewForAppPath(window.location.pathname) || 'chat';
  switchView(routed, {fromPopState: true});
});

// ── EXISTING HELPERS ──────────────────────────────────────────────────────
function toggleKey(btn) {
  const input = btn.closest('.key-input-wrap')?.querySelector('.key-input');
  if (!input) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  btn.type = 'button';
  btn.setAttribute('aria-pressed', reveal ? 'true' : 'false');
  btn.setAttribute('aria-label', reveal ? 'Hide API key' : 'Show API key');
  btn.title = reveal ? 'Hide API key' : 'Show API key';
  btn.innerHTML = reveal
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
document.addEventListener('click', () => closeChatMenus());
document.addEventListener('DOMContentLoaded', async () => {
  await init();
  initUpload();
  initTranslationUpload();
});
