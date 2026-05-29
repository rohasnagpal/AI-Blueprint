// ── COUNCILS ──────────────────────────────────────────────────────────────
async function loadCouncils() {
  try {
    const [templatesRes, runsRes] = await Promise.all([
      fetch('/api/council/templates'),
      fetch('/api/council/runs')
    ]);
    App.councilTemplates = await arrayOrEmpty(templatesRes);
    App.councilRuns = await arrayOrEmpty(runsRes);
    renderCouncilTemplates();
    renderCouncilRuns();
    renderCouncilTemplateOptions();
    renderCouncilDocOptions();
    if (!App.councilBuilder) resetCouncilBuilder();
  } catch(e) {}
}

function renderCouncilTemplateOptions() {
  const sel = document.getElementById('council-run-template');
  if (!sel) return;
  sel.innerHTML = App.councilTemplates.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join('');
}

function renderCouncilDocOptions() {
  const sel = document.getElementById('council-run-docs');
  if (!sel) return;
  const opts = ['<option value="all">All documents</option>'].concat(
    App.documents.map(d => `<option value="${d.id}">${esc(d.original_name)}</option>`)
  );
  sel.innerHTML = opts.join('');
}

function renderCouncilTemplates() {
  const grid = document.getElementById('council-templates-grid');
  if (!grid) return;
  if (!App.councilTemplates.length) {
    grid.innerHTML = '<div class="council-card"><div class="council-card-desc">No templates yet.</div></div>';
    return;
  }
  grid.innerHTML = App.councilTemplates.map(t => `
    <div class="council-card">
      <div class="council-card-title">${esc(t.name)}</div>
      <div class="council-card-meta">${t.is_builtin ? 'Built-in template' : 'Custom template'} · ${(t.config.agents || []).length} AI${(t.config.agents || []).length === 1 ? '' : 's'} · ${(t.config.phases || []).length} phase${(t.config.phases || []).length === 1 ? '' : 's'}</div>
      <div class="council-card-desc">${esc(t.description || t.config.description || '')}</div>
      <div class="council-actions">
        <button class="btn-primary" type="button" onclick="useCouncilTemplate('${t.id}')">Use</button>
        <button class="btn-secondary" type="button" onclick="loadTemplateIntoBuilder('${t.id}')">Edit</button>
        <button class="danger-btn" type="button" onclick="deleteCouncilTemplate('${t.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function renderCouncilRuns() {
  const list = document.getElementById('council-runs-list');
  if (!list) return;
  if (!App.councilRuns.length) {
    list.innerHTML = '<div class="council-row"><div class="council-card-desc">No council runs yet.</div></div>';
    return;
  }
  list.innerHTML = App.councilRuns.map(r => `
    <div class="council-row">
      <div class="council-row-head">
        <div>
          <div class="council-card-title">${esc(r.title || 'Council Run')}</div>
          <div class="council-card-meta">${esc((r.objective || '').slice(0, 120))}${(r.objective || '').length > 120 ? '…' : ''}</div>
        </div>
        <span class="council-status ${esc(r.status || 'pending')}">${esc(r.status || 'pending')}</span>
      </div>
      ${r.error ? `<div class="council-card-desc" data-csp-style="color:var(--danger)">${esc(r.error)}</div>` : ''}
      <div class="council-actions">
        <button class="btn-secondary" type="button" onclick="openCouncilRun('${r.id}')">Open</button>
        ${r.status === 'pending' || r.status === 'error' ? `<button class="btn-primary" type="button" onclick="startExistingCouncilRun('${r.id}')">Run</button>` : ''}
        <button class="danger-btn" type="button" onclick="deleteCouncilRun('${r.id}')">Delete</button>
      </div>
    </div>
  `).join('');
}

function useCouncilTemplate(templateId) {
  const sel = document.getElementById('council-run-template');
  if (sel) sel.value = templateId;
  switchCouncilTab('runs');
}

function switchCouncilTab(tab, el) {
  document.querySelectorAll('.council-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.council-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('council-panel-' + tab)?.classList.add('active');
  if (el) el.classList.add('active');
  else document.querySelector(`.council-tab[onclick*="'${tab}'"]`)?.classList.add('active');
}

async function startCouncilFromForm() {
  const templateId = document.getElementById('council-run-template')?.value;
  const title = document.getElementById('council-run-title')?.value.trim() || '';
  const objective = document.getElementById('council-run-objective')?.value.trim();
  const docContext = document.getElementById('council-run-docs')?.value || 'all';
  if (!templateId) { showToast('Choose a council template.', 'error'); return; }
  if (!objective) { showToast('Enter a council objective or submission.', 'error'); return; }
  showToast('Council run started. This may take a while.', 'warning');
  try {
    const createRes = await fetch('/api/council/runs', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({template_id:templateId, title, objective, doc_context:docContext})
    });
    if (!createRes.ok) throw new Error(await apiError(createRes));
    const run = await createRes.json();
    await startExistingCouncilRun(run.id);
    document.getElementById('council-run-title').value = '';
  } catch(e) {
    showToast('Council run failed: ' + e.message, 'error');
  }
}

async function startExistingCouncilRun(runId) {
  try {
    const r = await fetch(`/api/council/runs/${runId}/start`, {method:'POST'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    await streamCouncilRun(runId);
  } catch(e) {
    await loadCouncils();
    showToast('Council run failed: ' + e.message, 'error');
  }
}

async function openCouncilRun(runId) {
  try {
    const [runRes, outRes] = await Promise.all([
      fetch(`/api/council/runs/${runId}`),
      fetch(`/api/council/runs/${runId}/outputs`)
    ]);
    if (!runRes.ok) throw new Error(await apiError(runRes));
    if (!outRes.ok) throw new Error(await apiError(outRes));
    const run = await runRes.json();
    const data = await outRes.json();
    renderCouncilRunResult(run, data.outputs || [], data.evidence || []);
    if (run.status === 'running') streamCouncilRun(runId, false);
  } catch(e) {
    showToast('Failed to open council run: ' + e.message, 'error');
  }
}

async function streamCouncilRun(runId, showStartedToast = true) {
  App.activeCouncilRunId = runId;
  App.councilRenderKey = '';
  if (App.councilPollTimer) clearTimeout(App.councilPollTimer);
  if (showStartedToast) showToast('Council run is streaming as each participant finishes.', 'warning');
  const poll = async () => {
    if (App.activeCouncilRunId !== runId) return;
    try {
      const [runRes, outRes] = await Promise.all([
        fetch(`/api/council/runs/${runId}`),
        fetch(`/api/council/runs/${runId}/outputs`)
      ]);
      if (!runRes.ok) throw new Error(await apiError(runRes));
      if (!outRes.ok) throw new Error(await apiError(outRes));
      const run = await runRes.json();
      const data = await outRes.json();
      const key = JSON.stringify({
        status: run.status,
        error: run.error,
        outputs: (data.outputs || []).map(o => [o.id, o.content?.length || 0]),
        evidence: (data.evidence || []).map(e => [e.id, e.sources?.length || 0])
      });
      if (key !== App.councilRenderKey) {
        App.councilRenderKey = key;
        renderCouncilRunResult(run, data.outputs || [], data.evidence || [], !document.getElementById('council-run-result')?.innerHTML);
      }
      if (run.status === 'running' || run.status === 'pending') {
        App.councilPollTimer = setTimeout(poll, 1200);
        return;
      }
      App.councilPollTimer = null;
      await loadCouncils();
      if (run.status === 'completed') showToast('Council run completed.', 'success');
      if (run.status === 'error') showToast('Council run failed: ' + (run.error || 'Unknown error'), 'error');
    } catch(e) {
      App.councilPollTimer = setTimeout(poll, 2000);
    }
  };
  await poll();
}

function renderCouncilRunResult(run, outputs, evidence, shouldScroll = true) {
  const box = document.getElementById('council-run-result');
  if (!box) return;
  const phases = [...new Set(outputs.map(o => o.phase_id))];
  const phaseHtml = phases.map(pid => {
    const phaseOutputs = outputs.filter(o => o.phase_id === pid);
    const phaseName = phaseOutputs[0]?.phase_name || pid;
    const ev = evidence.find(e => e.phase_id === pid);
    const evidenceHtml = ev && ev.sources?.length ? `<div class="sources" data-csp-style="margin-bottom:10px">${mkSources(ev.sources).innerHTML}</div>` : '';
    return `
      <div class="settings-card">
        <div class="settings-card-header">
          <div><div class="settings-card-title">${esc(phaseName)}</div><div class="settings-card-subtitle">${ev ? esc(ev.query || '') : ''}</div></div>
        </div>
        ${evidenceHtml}
        ${phaseOutputs.map(o => `
          <div class="council-output">
            <div class="council-output-role">${esc(o.role_name)}</div>
            <div class="council-output-phase">${esc(o.metadata?.model || '')} · ${esc(o.metadata?.output_type || 'output')}</div>
            <div>${mdRender(o.content || '')}</div>
            ${o.sources?.length ? `<div data-csp-style="margin-top:10px">${mkSources(o.sources).innerHTML}</div>` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }).join('');
  box.innerHTML = `
    <div class="settings-card">
      <div class="settings-card-header">
        <div><div class="settings-card-title">${esc(run.title || 'Council Run')}</div><div class="settings-card-subtitle">${esc(run.objective || '')}</div></div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
    </div>
    ${phaseHtml || '<div class="council-row"><div class="council-card-desc">No outputs yet.</div></div>'}
  `;
  if (shouldScroll) box.scrollIntoView({behavior:'smooth', block:'start'});
}

async function deleteCouncilRun(runId) {
  if (!confirm('Delete this council run? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/council/runs/${runId}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    document.getElementById('council-run-result').innerHTML = '';
    await loadCouncils();
    showToast('Council run deleted.');
  } catch(e) { showToast('Failed to delete run: ' + e.message, 'error'); }
}

function resetCouncilBuilder(render = true) {
  App.councilEditingTemplateId = null;
  App.councilBuilder = {
    agents: [
      {id:'agent_1', name:'AI Participant 1', instructions:'Analyze the documents and objective from this role.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt'], output_type:'argument', require_citations:true},
      {id:'agent_2', name:'AI Participant 2', instructions:'Critique and complement the other perspective.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt','prior_outputs'], output_type:'critique', require_citations:true}
    ],
    phases: [
      {id:'phase_1', name:'Initial Analysis', mode:'parallel', agents:['agent_1','agent_2'], instructions:'Produce initial council outputs.', retrieval_query:'objective'}
    ]
  };
  const name = document.getElementById('builder-name'); if (name) name.value = 'Custom Council';
  const desc = document.getElementById('builder-description'); if (desc) desc.value = '';
  const obj = document.getElementById('builder-objective'); if (obj) obj.value = 'Analyze the user objective using uploaded documents.';
  const out = document.getElementById('builder-output'); if (out) out.value = 'memo';
  if (render) renderCouncilBuilder();
}

function renderCouncilBuilder() {
  renderBuilderAgents();
  renderBuilderPhases();
}

function renderBuilderAgents() {
  const box = document.getElementById('builder-agents');
  if (!box || !App.councilBuilder) return;
  box.innerHTML = App.councilBuilder.agents.map((a, i) => `
    <div class="council-row">
      <div class="council-row-head">
        <div class="council-card-title">AI ${i + 1}</div>
        <button class="danger-btn" type="button" onclick="removeCouncilAgent(${i})">Remove</button>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Role name</label><input class="council-input builder-agent-name" data-i="${i}" value="${esc(a.name)}"/></div>
        <div class="council-field"><label>Output type</label><input class="council-input builder-agent-output" data-i="${i}" value="${esc(a.output_type || 'custom')}"/></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Provider</label><select class="council-select builder-agent-provider" data-i="${i}" onchange="renderBuilderAgentModelSelect(${i})"><option value="default">Default</option>${providerOptions(a.provider)}</select></div>
        <div class="council-field"><label>Model</label><select class="council-select builder-agent-model" data-i="${i}">${modelOptions(a.provider === 'default' ? (App.settings.local_llm_provider || 'openai') : a.provider, a.model || 'default')}</select></div>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Temperature</label><input class="council-input builder-agent-temp" data-i="${i}" type="number" min="0" max="1" step="0.1" value="${a.temperature ?? 0.2}"/></div>
        <div class="council-field"><label>Max tokens</label><input class="council-input builder-agent-tokens" data-i="${i}" type="number" min="256" step="128" value="${a.max_tokens || 1400}"/></div>
      </div>
      <div class="council-field"><label>Instructions</label><textarea class="council-textarea builder-agent-instructions" data-i="${i}">${esc(a.instructions || '')}</textarea></div>
      <div class="council-field"><label>Context access</label><input class="council-input builder-agent-context" data-i="${i}" value="${esc((a.context_access || []).join(','))}"/></div>
    </div>
  `).join('');
  App.councilBuilder.agents.forEach((a, i) => {
    const sel = box.querySelector(`.builder-agent-provider[data-i="${i}"]`);
    if (sel) sel.value = a.provider || 'default';
  });
}

function renderBuilderAgentModelSelect(i) {
  const providerSel = document.querySelector(`.builder-agent-provider[data-i="${i}"]`);
  const modelSel = document.querySelector(`.builder-agent-model[data-i="${i}"]`);
  if (!providerSel || !modelSel) return;
  const provider = providerSel.value === 'default' ? (App.settings.local_llm_provider || 'openai') : providerSel.value;
  modelSel.innerHTML = modelOptions(provider, modelSel.value || 'default');
}

function renderBuilderPhases() {
  const box = document.getElementById('builder-phases');
  if (!box || !App.councilBuilder) return;
  const agentOptions = App.councilBuilder.agents.map(a => `${a.id}:${a.name}`).join(', ');
  box.innerHTML = App.councilBuilder.phases.map((p, i) => `
    <div class="council-row">
      <div class="council-row-head">
        <div class="council-card-title">Phase ${i + 1}</div>
        <button class="danger-btn" type="button" onclick="removeCouncilPhase(${i})">Remove</button>
      </div>
      <div class="council-form-row">
        <div class="council-field"><label>Phase name</label><input class="council-input builder-phase-name" data-i="${i}" value="${esc(p.name)}"/></div>
        <div class="council-field"><label>Mode</label><select class="council-select builder-phase-mode" data-i="${i}"><option value="sequential">Sequential</option><option value="parallel">Parallel</option></select></div>
      </div>
      <div class="council-field"><label>Agent ids (${esc(agentOptions)})</label><input class="council-input builder-phase-agents" data-i="${i}" value="${esc((p.agents || []).join(','))}"/></div>
      <div class="council-field"><label>Instructions</label><textarea class="council-textarea builder-phase-instructions" data-i="${i}">${esc(p.instructions || '')}</textarea></div>
    </div>
  `).join('');
  App.councilBuilder.phases.forEach((p, i) => {
    const sel = box.querySelector(`.builder-phase-mode[data-i="${i}"]`);
    if (sel) sel.value = p.mode || 'sequential';
  });
}

function collectCouncilBuilder() {
  const agents = [...document.querySelectorAll('.builder-agent-name')].map(input => {
    const i = input.dataset.i;
    const old = App.councilBuilder.agents[i];
    return {
      id: old.id,
      name: input.value.trim() || old.id,
      instructions: document.querySelector(`.builder-agent-instructions[data-i="${i}"]`)?.value.trim() || '',
      provider: document.querySelector(`.builder-agent-provider[data-i="${i}"]`)?.value || 'default',
      model: document.querySelector(`.builder-agent-model[data-i="${i}"]`)?.value || 'default',
      temperature: parseFloat(document.querySelector(`.builder-agent-temp[data-i="${i}"]`)?.value || '0.2'),
      max_tokens: parseInt(document.querySelector(`.builder-agent-tokens[data-i="${i}"]`)?.value || '1400'),
      context_access: (document.querySelector(`.builder-agent-context[data-i="${i}"]`)?.value || 'documents,user_prompt').split(',').map(v => v.trim()).filter(Boolean),
      output_type: document.querySelector(`.builder-agent-output[data-i="${i}"]`)?.value.trim() || 'custom',
      require_citations: true
    };
  });
  const phases = [...document.querySelectorAll('.builder-phase-name')].map(input => {
    const i = input.dataset.i;
    const old = App.councilBuilder.phases[i];
    return {
      id: old.id,
      name: input.value.trim() || old.id,
      mode: document.querySelector(`.builder-phase-mode[data-i="${i}"]`)?.value || 'sequential',
      agents: (document.querySelector(`.builder-phase-agents[data-i="${i}"]`)?.value || '').split(',').map(v => v.trim()).filter(Boolean),
      instructions: document.querySelector(`.builder-phase-instructions[data-i="${i}"]`)?.value.trim() || '',
      retrieval_query: 'objective'
    };
  });
  App.councilBuilder.agents = agents;
  App.councilBuilder.phases = phases;
  return {
    name: document.getElementById('builder-name')?.value.trim() || 'Custom Council',
    description: document.getElementById('builder-description')?.value.trim() || '',
    document_scope: 'run',
    objective_prompt: document.getElementById('builder-objective')?.value.trim() || '',
    output_format: document.getElementById('builder-output')?.value || 'memo',
    agents,
    phases
  };
}

function addCouncilAgent() {
  collectCouncilBuilder();
  const n = App.councilBuilder.agents.length + 1;
  App.councilBuilder.agents.push({id:`agent_${n}`, name:`AI Participant ${n}`, instructions:'Analyze the objective from this role.', provider:'default', model:'default', temperature:0.2, max_tokens:1400, context_access:['documents','user_prompt','prior_outputs'], output_type:'custom', require_citations:true});
  renderCouncilBuilder();
}

function removeCouncilAgent(i) {
  collectCouncilBuilder();
  App.councilBuilder.agents.splice(i, 1);
  renderCouncilBuilder();
}

function addCouncilPhase() {
  collectCouncilBuilder();
  const n = App.councilBuilder.phases.length + 1;
  App.councilBuilder.phases.push({id:`phase_${n}`, name:`Phase ${n}`, mode:'sequential', agents:App.councilBuilder.agents.map(a => a.id).slice(0,1), instructions:'Run this phase.', retrieval_query:'objective'});
  renderCouncilBuilder();
}

function removeCouncilPhase(i) {
  collectCouncilBuilder();
  App.councilBuilder.phases.splice(i, 1);
  renderCouncilBuilder();
}

async function saveCouncilTemplate() {
  const config = collectCouncilBuilder();
  try {
    const url = App.councilEditingTemplateId ? `/api/council/templates/${App.councilEditingTemplateId}` : '/api/council/templates';
    const r = await fetch(url, {
      method: App.councilEditingTemplateId ? 'PUT' : 'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:config.name, description:config.description, config})
    });
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    switchCouncilTab('templates');
    showToast('Council template saved.');
  } catch(e) { showToast('Failed to save template: ' + e.message, 'error'); }
}

function loadTemplateIntoBuilder(templateId) {
  const t = App.councilTemplates.find(x => x.id === templateId);
  if (!t) return;
  const config = JSON.parse(JSON.stringify(t.config || {}));
  App.councilEditingTemplateId = t.id;
  App.councilBuilder = {agents: config.agents || [], phases: config.phases || []};
  document.getElementById('builder-name').value = t.name;
  document.getElementById('builder-description').value = t.description || config.description || '';
  document.getElementById('builder-objective').value = config.objective_prompt || '';
  document.getElementById('builder-output').value = config.output_format || 'memo';
  renderCouncilBuilder();
  switchCouncilTab('builder');
}

async function deleteCouncilTemplate(templateId) {
  if (!confirm('Delete this council template?')) return;
  try {
    const r = await fetch(`/api/council/templates/${templateId}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    await loadCouncils();
    showToast('Council template deleted.');
  } catch(e) { showToast('Failed to delete template: ' + e.message, 'error'); }
}

async function apiError(response) {
  const data = await response.json().catch(() => ({}));
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body').join('.') : '';
      return field ? `${field}: ${item.msg}` : item.msg;
    }).filter(Boolean).join('; ') || response.statusText || 'Request failed';
  }
  return data.detail || data.error || response.statusText || 'Request failed';
}
