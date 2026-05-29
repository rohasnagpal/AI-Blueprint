// ── SETTINGS ───────────────────────────────────────────────────────────────
async function loadSettings() {
  try {
    const r = await fetch('/api/settings');
    App.settings = await jsonOrFallback(r, {});
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
  set('sel-chat-model', s.chat_model);
  renderChatProviderOptions();
  renderChatModelOptions();
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
  hydrateProviderKeyLinks();
  hydrateKeyToggles();
  renderEmailControls();
  // Show connected status for API keys
  document.querySelectorAll('.provider-card').forEach(card => {
    const name = providerCardName(card);
    const keyMap = { 'OpenAI':'openai_api_key','OpenRouter':'openrouter_api_key','Anthropic':'anthropic_api_key','Google Gemini':'gemini_api_key','Perplexity':'perplexity_api_key','Mistral AI':'mistral_api_key','Cohere':'cohere_api_key','Groq':'groq_api_key','Ollama':'ollama_api_key','xAI (Grok)':'xai_api_key','Cloudflare Workers AI':'cloudflare_api_key','Together AI':'together_api_key','Brave Search':'brave_search_api_key','SearXNG':'searxng_base_url' };
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

const PROVIDER_KEY_URLS = {
  'OpenAI': 'https://platform.openai.com/api-keys',
  'OpenRouter': 'https://openrouter.ai/settings/keys',
  'Anthropic': 'https://console.anthropic.com/settings/keys',
  'Google Gemini': 'https://aistudio.google.com/app/apikey',
  'Perplexity': 'https://www.perplexity.ai/settings/api',
  'Mistral AI': 'https://console.mistral.ai/api-keys',
  'Cohere': 'https://dashboard.cohere.com/api-keys',
  'Groq': 'https://console.groq.com/keys',
  'Ollama': 'https://ollama.com/settings/keys',
  'xAI (Grok)': 'https://console.x.ai/api-keys',
  'Cloudflare Workers AI': 'https://dash.cloudflare.com/profile/api-tokens',
  'Together AI': 'https://api.together.xyz/settings/api-keys',
  'Brave Search': 'https://api-dashboard.search.brave.com/app/keys',
  'SearXNG': 'https://docs.searxng.org/admin/installation.html'
};

function providerCardName(card) {
  const nameEl = card?.querySelector('.provider-name');
  return nameEl?.childNodes?.[0]?.textContent?.trim() || nameEl?.textContent?.trim() || '';
}

function hydrateProviderKeyLinks() {
  document.querySelectorAll('.provider-card').forEach(card => {
    const nameEl = card.querySelector('.provider-name');
    const name = providerCardName(card);
    const url = PROVIDER_KEY_URLS[name];
    if (!nameEl || !url || nameEl.querySelector('.provider-key-link')) return;
    const link = document.createElement('a');
    link.className = 'provider-key-link';
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.title = `Open ${name} API key page`;
    link.setAttribute('aria-label', `Open ${name} API key page`);
    link.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>';
    nameEl.appendChild(link);
  });
}

function hydrateKeyToggles() {
  document.querySelectorAll('.key-toggle').forEach(btn => {
    btn.type = 'button';
    btn.title = 'Show API key';
    btn.setAttribute('aria-label', 'Show API key');
    btn.setAttribute('aria-pressed', 'false');
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

function saveApiKey(btn) {
  const card = btn.closest('.provider-card');
  const input = card.querySelector('.key-input');
  const val = input.value.trim();
  if (!val || val === '••••••••') return;
  const name = providerCardName(card);
  const keyMap = { 'OpenAI':'openai_api_key','OpenRouter':'openrouter_api_key','Anthropic':'anthropic_api_key','Google Gemini':'gemini_api_key','Perplexity':'perplexity_api_key','Mistral AI':'mistral_api_key','Cohere':'cohere_api_key','Groq':'groq_api_key','Ollama':'ollama_api_key','xAI (Grok)':'xai_api_key','Cloudflare Workers AI':'cloudflare_api_key','Together AI':'together_api_key','Brave Search':'brave_search_api_key','SearXNG':'searxng_base_url' };
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
  if (p && !providerHasApiKey(p)) {
    showToast(`${providerLabel(p)} needs an API key before it can be saved as the chat provider.`, 'error');
    updateChatProviderKeyWarning();
    return;
  }
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
  if (p && !providerHasApiKey(p)) {
    showToast(`${providerLabel(p)} needs an API key before it can be saved as the chat provider.`, 'error');
    updateChatProviderKeyWarning();
    return;
  }
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
    const defaults = { rag_provider:'openai', chat_model:'gpt-5.2', openai_assistants_model:'gpt-4.1', temperature:'0.2', max_tokens:'2048', top_k:'5', similarity_threshold:'0.72', chunk_size:'512', chunk_overlap:'64', retrieval_strategy:'semantic', response_language:'English', auto_detect_language:'false', response_length:'balanced', always_show_sources:'false', stream_responses:'true', max_file_size_mb:'25', auto_delete_days:'0', dark_mode:'false', font_size:'14', openai_api_key:'', openrouter_api_key:'', anthropic_api_key:'', groq_api_key:'', gemini_api_key:'', perplexity_api_key:'', mistral_api_key:'', cohere_api_key:'', xai_api_key:'', cloudflare_api_key:'', together_api_key:'', ollama_api_key:'', ollama_base_url:'http://localhost:11434', brave_search_api_key:'', searxng_base_url:'', app_name:'AI Blueprint by Rohas Nagpal', app_intro:'Open source AI-native infrastructure for Lawyers', suggested_questions:'[]' };
    await saveSettings(defaults);
  } catch(e) { showToast('Reset failed.', 'error'); }
}

// ── SETTINGS TABS ─────────────────────────────────────────────────────────
function switchSettingsTab(tab, el) {
  document.querySelectorAll('.settings-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.settings-nav-item').forEach(s => s.classList.remove('active'));
  document.getElementById('stab-' + tab)?.classList.add('active');
  el.classList.add('active');
  if (tab === 'workspaces' || tab === 'matters') loadWorkspaceManager();
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
