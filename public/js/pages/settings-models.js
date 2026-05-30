// ── SETTINGS MODELS ──────────────────────────────────────────────────────
async function loadModels() {
  try {
    const r = await fetch('/api/models');
    App.models = await arrayOrEmpty(r);
    renderChatProviderOptions();
    renderChatModelOptions();
    renderModelRegistry();
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
    perplexity:'Perplexity',
    mistral:'Mistral AI',
    cohere:'Cohere',
    xai:'xAI',
    cloudflare:'Cloudflare Workers AI',
    together:'Together AI'
  };
  return labels[provider] || provider;
}

function providerKeyField(provider) {
  const fields = {
    openai: 'openai_api_key',
    openrouter: 'openrouter_api_key',
    anthropic: 'anthropic_api_key',
    groq: 'groq_api_key',
    gemini: 'gemini_api_key',
    perplexity: 'perplexity_api_key',
    mistral: 'mistral_api_key',
    cohere: 'cohere_api_key',
    xai: 'xai_api_key',
    cloudflare: 'cloudflare_api_key',
    together: 'together_api_key',
    ollama: 'ollama_api_key'
  };
  return fields[provider] || '';
}

function providerNeedsApiKey(provider) {
  if (provider === 'ollama') {
    const baseUrl = (App.settings.ollama_base_url || 'http://localhost:11434').trim();
    return !['http://localhost:11434', 'http://127.0.0.1:11434'].includes(baseUrl);
  }
  return !!providerKeyField(provider);
}

function providerHasApiKey(provider) {
  if (!providerNeedsApiKey(provider)) return true;
  const field = providerKeyField(provider);
  return !!(field && App.settings[field] && App.settings[field] !== '');
}

function runnableModelProviders() {
  const supported = ['openai', 'openrouter', 'anthropic', 'groq', 'ollama', 'gemini', 'perplexity', 'mistral', 'xai'];
  const providers = modelProviders().filter(p => supported.includes(p));
  return providers;
}

function modelProviders() {
  const providers = [...new Set(App.models.filter(m => m.enabled).map(m => m.provider))];
  return providers;
}

function enabledModels(provider) {
  return App.models.filter(m => m.enabled && (!provider || m.provider === provider));
}

function liveModels(provider) {
  return App.liveModels[provider] || null;
}

function supportsLiveModels(provider) {
  return ['openai', 'openrouter', 'anthropic', 'groq', 'ollama', 'gemini', 'mistral', 'xai'].includes(provider);
}

function localModelOptionsHtml(provider, selected) {
  const models = enabledModels(provider);
  if (!models.length) return '<option value="">No enabled models</option>';
  const options = models.map(m => `<option value="${esc(m.model_id)}">${esc(m.display_name)} (${esc(m.model_id)})</option>`);
  if (selected && !models.some(m => m.model_id === selected)) {
    options.push(`<option value="${esc(selected)}" selected>${esc(selected)}</option>`);
  }
  return options.join('');
}

async function fetchLiveModels(provider) {
  if (!provider || !supportsLiveModels(provider) || !providerHasApiKey(provider)) return null;
  if (liveModels(provider)) return liveModels(provider);
  const r = await fetch(`/api/models/live?provider=${encodeURIComponent(provider)}`);
  if (!r.ok) throw new Error(await apiError(r));
  const data = await r.json();
  const models = Array.isArray(data.models) ? data.models : [];
  App.liveModels[provider] = models;
  return models;
}

function renderChatProviderOptions() {
  const sel = document.getElementById('sel-chat-provider');
  if (!sel) return;
  const current = sel.value || App.settings.local_llm_provider || 'openai';
  const providers = runnableModelProviders();
  if (!providers.length) {
    sel.innerHTML = '<option value="">No enabled runnable models</option>';
    sel.value = '';
    updateChatProviderKeyWarning();
    return;
  }
  sel.innerHTML = providers.map(p => `<option value="${esc(p)}">${esc(providerLabel(p))}</option>`).join('');
  sel.value = providers.includes(current) ? current : (providers[0] || 'openai');
  updateChatProviderKeyWarning();
}

async function renderChatModelOptions() {
  const sel = document.getElementById('sel-chat-model');
  const provider = document.getElementById('sel-chat-provider')?.value || 'openai';
  if (!sel) return;
  const current = sel.value || App.settings.chat_model || '';
  const requestId = ++App.liveModelRequestId;
  sel.innerHTML = '<option value="">Loading live models...</option>';
  try {
    const models = await fetchLiveModels(provider);
    if (requestId !== App.liveModelRequestId) return;
    if (models && models.length) {
      sel.innerHTML = models.map(m => `<option value="${esc(m.model_id)}">${esc(m.display_name)} (${esc(m.model_id)}) - live</option>`).join('');
      if (models.some(m => m.model_id === current)) sel.value = current;
      else if (App.settings.chat_model && models.some(m => m.model_id === App.settings.chat_model)) sel.value = App.settings.chat_model;
      updateChatProviderKeyWarning();
      return;
    }
  } catch(e) {
    if (requestId !== App.liveModelRequestId) return;
    showToast(`Live model list unavailable for ${providerLabel(provider)}. Using saved models.`, 'warning');
  }
  sel.innerHTML = localModelOptionsHtml(provider, current);
  const fallbackModels = enabledModels(provider);
  if (fallbackModels.some(m => m.model_id === current)) sel.value = current;
  else if (App.settings.chat_model && fallbackModels.some(m => m.model_id === App.settings.chat_model)) sel.value = App.settings.chat_model;
  updateChatProviderKeyWarning();
}

function updateChatProviderKeyWarning() {
  const warning = document.getElementById('chat-provider-key-warning');
  const provider = document.getElementById('sel-chat-provider')?.value || '';
  if (!warning) return;
  if (!provider) {
    warning.textContent = '';
    warning.hidden = true;
    return;
  }
  if (!providerHasApiKey(provider)) {
    warning.textContent = `${providerLabel(provider)} is selected, but its API key is not saved. Add the key in API Keys before using this provider.`;
    warning.hidden = false;
  } else {
    warning.textContent = '';
    warning.hidden = true;
  }
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
