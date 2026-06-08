// ── STANDALONE CONTRACT REVIEW ───────────────────────────────────────────
function contractReviewWorkspaceId() {
  const selectValue = document.getElementById('contract-review-workspace-select')?.value || '';
  return v2ExistingWorkspaceId(selectValue);
}

function selectedContractReviewMatterId() {
  const value = document.getElementById('contract-review-matter-select')?.value || '';
  return value.trim() || uploadMattersForWorkspace(contractReviewWorkspaceId())[0]?.id || null;
}

async function renderStandaloneContractReview() {
  if (!App.v2.user) await initV2();
  renderContractReviewScopeSelector();
  await syncContractReviewScope();
  renderContractReviewScopeSelector();
  await loadStandaloneContractPlaybooks();
  renderContractReviewSourceDocuments();
  await loadStandaloneContractReviewHistory();
}

async function syncContractReviewScope({resetMatter = false} = {}) {
  if (!App.v2.enabled || !App.v2.user) return;
  const workspaceId = contractReviewWorkspaceId();
  if (!workspaceId) return;
  if (workspaceId !== App.v2.workspaceId) await setV2Workspace(workspaceId);
  let matters = uploadMattersForWorkspace(workspaceId);
  if (!matters.length) {
    await loadUploadMattersForWorkspace(workspaceId);
    matters = uploadMattersForWorkspace(workspaceId);
  }
  const matterSelect = document.getElementById('contract-review-matter-select');
  const selectedMatter = resetMatter ? '' : (matterSelect?.value || '');
  const activeMatter = matters.some(m => m.id === App.v2.activeMatterId) ? App.v2.activeMatterId : '';
  const matterId = selectedMatter || activeMatter || matters[0]?.id || '';
  if (matterSelect && matterId) matterSelect.value = matterId;
  if (!matterId) {
    App.v2.documents = [];
    if (typeof normalizeV2Document === 'function') App.documents = [];
    return;
  }
  if (App.v2.activeMatterId !== matterId) {
    App.v2.activeMatterId = matterId;
    App.v2.activeBlueprintId = null;
  }
  await loadV2Documents();
}

function renderContractReviewScopeSelector() {
  const workspaceSelect = document.getElementById('contract-review-workspace-select');
  const matterSelect = document.getElementById('contract-review-matter-select');
  const card = document.getElementById('contract-review-scope-card');
  if (!workspaceSelect || !matterSelect || !card) return;
  const workspaces = App.v2.workspaces || [];
  if (!App.v2.enabled || !App.v2.user || !workspaces.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'grid';
  const currentWorkspaceId = contractReviewWorkspaceId();
  workspaceSelect.innerHTML = workspaces.map(w => `<option value="${esc(w.workspace_id)}" ${w.workspace_id === currentWorkspaceId ? 'selected' : ''}>${esc(w.workspace_name || 'Workspace')}</option>`).join('');
  const selectedMatter = matterSelect.value || App.v2.activeMatterId || '';
  const matters = uploadMattersForWorkspace(currentWorkspaceId);
  matterSelect.innerHTML = matters.map(m => `<option value="${esc(m.id)}" ${m.id === selectedMatter ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
  if (!matterSelect.value && matters.length) matterSelect.value = matters[0].id;
  if (!matters.length && currentWorkspaceId) loadUploadMattersForWorkspace(currentWorkspaceId).then(renderContractReviewScopeSelector).catch(() => {});
}

async function onContractReviewWorkspaceChange() {
  const workspaceId = contractReviewWorkspaceId();
  if (workspaceId && workspaceId !== App.v2.workspaceId) await setV2Workspace(workspaceId);
  const matterSelect = document.getElementById('contract-review-matter-select');
  if (matterSelect) matterSelect.value = '';
  renderContractReviewScopeSelector();
  await syncContractReviewScope({resetMatter: true});
  renderContractReviewScopeSelector();
  await loadStandaloneContractPlaybooks();
  renderContractReviewSourceDocuments();
  await loadStandaloneContractReviewHistory();
}

async function onContractReviewMatterChange() {
  await syncContractReviewScope();
  renderContractReviewSourceDocuments();
}

async function loadStandaloneContractReviewHistory() {
  const workspaceId = contractReviewWorkspaceId();
  const card = document.getElementById('contract-review-history-card');
  const list = document.getElementById('contract-review-history-list');
  if (!card || !list) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    card.style.display = 'none';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/runs?page_size=8`);
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    App.contractReview.history = data.items || [];
    card.style.display = App.contractReview.history.length ? 'block' : 'none';
    list.innerHTML = App.contractReview.history.map(run => `<div class="council-row contract-review-history-row">
      <div class="contract-review-history-main">
        <div class="contract-review-history-copy">
          <div class="council-card-title">${esc(run.title || 'Contract review')}</div>
          <div class="council-card-meta">${esc(run.completed_at ? new Date(run.completed_at).toLocaleString() : run.status || 'queued')}${run.review_depth ? ' · ' + esc(run.review_depth) : ''}</div>
        </div>
        <span class="council-status ${esc(run.status || 'pending')}">${esc(run.status || 'pending')}</span>
      </div>
      <div class="council-actions contract-review-history-actions">
        <button class="btn-secondary" type="button" onclick="openStandaloneContractReviewRun('${esc(run.id)}')">Open</button>
        <button class="danger-btn" type="button" onclick="deleteStandaloneContractReviewRun('${esc(run.id)}')">Delete</button>
      </div>
    </div>`).join('');
  } catch(e) {
    card.style.display = 'none';
  }
}

async function openStandaloneContractReviewRun(runId) {
  const workspaceId = contractReviewWorkspaceId();
  if (!workspaceId) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(await apiError(r));
    App.contractReview.result = await r.json();
    renderStandaloneContractReviewResult();
    showToast('Contract review loaded.');
  } catch(e) {
    showToast('Failed to load review: ' + e.message, 'error');
  }
}

async function deleteStandaloneContractReviewRun(runId) {
  const workspaceId = contractReviewWorkspaceId();
  if (!workspaceId || !runId) return;
  if (!confirm('Delete this contract review? This cannot be undone.')) return;
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/runs/${encodeURIComponent(runId)}`, {method:'DELETE'});
    if (!r.ok) throw new Error(await apiError(r));
    if (App.contractReview.result?.id === runId) {
      App.contractReview.result = null;
      const grid = document.getElementById('contract-review-result-grid');
      if (grid) grid.style.display = 'none';
    }
    await loadStandaloneContractReviewHistory();
    showToast('Contract review deleted.');
  } catch(e) {
    showToast('Failed to delete review: ' + e.message, 'error');
  }
}

async function loadStandaloneContractPlaybooks() {
  const workspaceId = contractReviewWorkspaceId();
  const select = document.getElementById('contract-review-playbook');
  if (!select) return;
  if (!App.v2.enabled || !App.v2.user || !workspaceId) {
    select.innerHTML = '<option value="">Sign in to load playbooks</option>';
    return;
  }
  try {
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/playbooks`);
    if (!r.ok) throw new Error(await apiError(r));
    App.contractReview.playbooks = await r.json();
    select.innerHTML = '<option value="">Auto-select / no playbook</option>' + App.contractReview.playbooks.map(p => `<option value="${esc(p.id)}">${esc(p.name)}${p.contract_category ? ' · ' + esc(p.contract_category.toUpperCase()) : ''}</option>`).join('');
  } catch(e) {
    select.innerHTML = '<option value="">Playbooks unavailable</option>';
  }
}

function renderContractReviewSourceDocuments() {
  const field = document.getElementById('contract-review-source-documents-field');
  const select = document.getElementById('contract-review-source-documents');
  if (!field || !select) return;
  const selectedWorkspace = contractReviewWorkspaceId();
  const selectedMatter = selectedContractReviewMatterId();
  if (!App.v2.enabled || !App.v2.user || !selectedWorkspace || selectedWorkspace !== App.v2.workspaceId) {
    field.style.display = 'none';
    select.innerHTML = '';
    return;
  }
  const docs = (App.v2.documents || []).filter(doc => {
    if (doc.status && doc.status !== 'indexed') return false;
    return doc.matter_id === selectedMatter;
  });
  field.style.display = 'block';
  select.innerHTML = docs.length
    ? docs.map(doc => `<option value="${esc(doc.id)}">${esc(doc.original_name || 'Document')}</option>`).join('')
    : '<option value="">No indexed documents available</option>';
}

function selectedContractReviewDocumentIds() {
  const select = document.getElementById('contract-review-source-documents');
  if (!select) return [];
  return [...select.selectedOptions].map(option => option.value).filter(Boolean);
}

function collectStandaloneContractReviewPayload() {
  const workspaceId = contractReviewWorkspaceId();
  if (!App.v2.enabled || !App.v2.user || !workspaceId) throw new Error('Sign in and choose a workspace first.');
  const payload = {
    title: document.getElementById('contract-review-title')?.value.trim() || 'Contract Review',
    matter_id: selectedContractReviewMatterId(),
    document_ids: selectedContractReviewDocumentIds(),
    playbook_id: document.getElementById('contract-review-playbook')?.value || null,
    review_depth: document.getElementById('contract-review-depth')?.value || 'standard',
    instructions: document.getElementById('contract-review-instructions')?.value.trim() || null,
  };
  return {workspaceId, payload};
}

function setContractReviewStatus(message = '', type = '') {
  const status = document.getElementById('contract-review-status');
  if (!status) return;
  status.textContent = message;
  status.classList.toggle('error', type === 'error');
}

function clearContractReviewStatus({force = false} = {}) {
  const status = document.getElementById('contract-review-status');
  if (!status) return;
  if (!force && status.classList.contains('error')) return;
  status.textContent = '';
  status.classList.remove('error');
}

async function runStandaloneContractReview() {
  if (App.contractReview.isRunning) return;
  const btn = document.getElementById('contract-review-run-btn');
  try {
    const {workspaceId, payload} = collectStandaloneContractReviewPayload();
    App.contractReview.isRunning = true;
    App.contractReview.result = null;
    if (btn) btn.disabled = true;
    setContractReviewStatus('Queuing review...');
    const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    if (!r.ok) throw new Error(await apiError(r));
    const data = await r.json();
    if (data.job) {
      startContractReviewJobStream(workspaceId, data.job);
      showToast('Contract review queued.');
      return;
    }
    App.contractReview.result = data;
    renderStandaloneContractReviewResult();
    showToast('Contract review complete.');
  } catch(e) {
    setContractReviewStatus('Contract review failed: ' + e.message, 'error');
    App.contractReview.isRunning = false;
    if (btn) btn.disabled = false;
  } finally {
    if (App.contractReview.job) return;
    App.contractReview.isRunning = false;
    if (btn) btn.disabled = false;
    clearContractReviewStatus();
  }
}

function stopContractReviewStream() {
  App.contractReview.stream?.close();
  App.contractReview.stream = null;
}

async function loadContractReviewResultFromJob(workspaceId, job) {
  const runId = job?.metadata?.run_id;
  if (!runId) return false;
  const r = await fetch(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/contract-review/runs/${encodeURIComponent(runId)}`);
  if (!r.ok) throw new Error(await apiError(r));
  App.contractReview.result = await r.json();
  renderStandaloneContractReviewResult();
  return true;
}

function renderContractReviewProgress() {
  const job = App.contractReview.job;
  if (!job) return;
  const latestEvent = [...(App.contractReview.events || [])].reverse().find(e => e.content);
  const latest = latestEvent?.content || job.status || 'running';
  const eventProgress = latestEvent?.metadata?.progress;
  const progress = Math.max(0, Math.min(100, Number(eventProgress ?? job.progress ?? 0)));
  setContractReviewStatus(`${latest} · ${progress}%`);
}

function startContractReviewJobStream(workspaceId, job) {
  stopContractReviewStream();
  App.contractReview.job = job;
  App.contractReview.events = [{type:'status', content:'Contract review queued', metadata:{progress:0}}];
  App.contractReview.startedAt = Date.now();
  renderContractReviewProgress();
  const source = new EventSource(`/api/v2/workspaces/${encodeURIComponent(workspaceId)}/jobs/${encodeURIComponent(job.id)}/events`);
  App.contractReview.stream = source;
  source.onmessage = async event => {
    let data;
    try { data = JSON.parse(event.data); } catch(e) { return; }
    if (data.type === 'status' && data.metadata?.id) App.contractReview.job = data.metadata;
    if (data.type && data.type !== 'status') App.contractReview.events.push(data);
    App.contractReview.events = App.contractReview.events.slice(-24);
    renderContractReviewProgress();
    if (data.type === 'done') {
      stopContractReviewStream();
      App.contractReview.job = data.metadata || App.contractReview.job;
      try {
        if (data.content === 'completed') {
          await loadContractReviewResultFromJob(workspaceId, App.contractReview.job);
          await loadStandaloneContractReviewHistory();
          showToast('Contract review complete.');
        } else {
          const error = data.metadata?.error || App.contractReview.job?.error || data.content;
          if (data.content === 'failed') {
            setContractReviewStatus('Contract review failed: ' + error, 'error');
          } else {
            setContractReviewStatus('Contract review ended: ' + data.content, 'error');
          }
        }
      } catch(e) {
        showToast('Review completed but result load failed: ' + e.message, 'error');
      } finally {
        App.contractReview.isRunning = false;
        App.contractReview.job = null;
        const btn = document.getElementById('contract-review-run-btn');
        if (btn) btn.disabled = false;
        clearContractReviewStatus();
      }
    }
  };
  source.onerror = () => {
    stopContractReviewStream();
    App.contractReview.isRunning = false;
    App.contractReview.job = null;
    const btn = document.getElementById('contract-review-run-btn');
    if (btn) btn.disabled = false;
    setContractReviewStatus('Contract review event stream disconnected.', 'error');
  };
}

function contractReviewDisplayValue(value) {
  if (value === null || value === undefined || value === '') return 'Not found';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(contractReviewDisplayValue).filter(Boolean).join('; ');
  if (typeof value === 'object') {
    for (const key of ['value', 'summary', 'text', 'finding', 'answer', 'name', 'description']) {
      if (value[key] !== null && value[key] !== undefined && value[key] !== '') return contractReviewDisplayValue(value[key]);
    }
    return Object.entries(value)
      .filter(([, item]) => item !== null && item !== undefined && item !== '')
      .map(([key, item]) => `${key.replace(/_/g, ' ')}: ${contractReviewDisplayValue(item)}`)
      .join('; ');
  }
  return String(value);
}

function standaloneRiskRank(level) {
  return {critical:4, high:3, medium:2, low:1}[level] || 0;
}

function contractReviewHumanLabel(value) {
  const text = String(value || '').replace(/_/g, ' ').trim();
  if (!text) return 'Clause';
  return text.split(/\s+/).map(word => {
    const lower = word.toLowerCase();
    if (lower === 'ip') return 'IP';
    if (lower === 'msa') return 'MSA';
    if (lower === 'nda') return 'NDA';
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }).join(' ');
}

function contractReviewDocumentName(value) {
  const raw = String(value || 'Source document').split('/').filter(Boolean).pop() || 'Source document';
  return raw.replace(/\.(html?|txt|md|pdf|docx?)$/i, '').replace(/[-_]+/g, ' ').trim() || raw;
}

function contractReviewSourceBasis(sources = []) {
  const grouped = new Map();
  for (const source of sources || []) {
    const filename = source?.filename || 'Source document';
    const current = grouped.get(filename) || {filename, count: 0, excerpts: []};
    current.count += 1;
    const excerpt = contractReviewDisplayValue(source?.excerpt || '').replace(/\s+/g, ' ').trim();
    if (excerpt && current.excerpts.length < 2) current.excerpts.push(excerpt.length > 220 ? excerpt.slice(0, 220).trim() + '...' : excerpt);
    grouped.set(filename, current);
  }
  return [...grouped.values()];
}

function contractReviewSourceBasisLabel(source) {
  const name = contractReviewDocumentName(source.filename);
  return `${name}${source.count ? ` (${source.count} excerpt${source.count === 1 ? '' : 's'} reviewed)` : ''}`;
}

function isContractReviewBoilerplateRisk(text) {
  const lower = String(text || '').toLowerCase();
  return lower.includes('no prohibited language found by deterministic check') || lower.includes('semantic alignment still requires review');
}

function summarizeStandaloneClauseItems(items = []) {
  const groups = new Map();
  for (const item of items || []) {
    const clause = item.clause || {};
    const type = clause.clause_type || clause.title || 'clause';
    const key = String(type).toLowerCase();
    const existing = groups.get(key) || {
      clause: {
        ...clause,
        title: contractReviewHumanLabel(type),
        clause_type: type,
        source_summary: new Set(),
      },
      count: 0,
      risks: [],
      playbook_findings: [],
      redline_suggestions: [],
      representative_texts: [],
    };
    existing.count += 1;
    if (clause.source?.filename) existing.clause.source_summary.add(contractReviewDocumentName(clause.source.filename));
    if (clause.text && existing.representative_texts.length < 2) existing.representative_texts.push(clause.text);
    existing.risks.push(...(item.risks || []));
    existing.playbook_findings.push(...(item.playbook_findings || []));
    existing.redline_suggestions.push(...(item.redline_suggestions || []));
    groups.set(key, existing);
  }
  return [...groups.values()].map(group => {
    const meaningfulRisks = group.risks.filter(r => !isContractReviewBoilerplateRisk(r.reasoning || r.finding));
    return {
      ...group,
      clause: {
        ...group.clause,
        source_summary: [...group.clause.source_summary],
        text: group.representative_texts.join('\n\n'),
      },
      risks: meaningfulRisks,
    };
  }).sort((a, b) => {
    const ar = Math.max(0, ...a.risks.map(r => standaloneRiskRank(r.risk_level || r.severity)));
    const br = Math.max(0, ...b.risks.map(r => standaloneRiskRank(r.risk_level || r.severity)));
    return br - ar || String(a.clause.title || '').localeCompare(String(b.clause.title || ''));
  });
}

function splitContractReviewExtraction(extraction = {}) {
  const confirmed = [];
  const needsReview = [];
  for (const [key, value] of Object.entries(extraction || {})) {
    const confidence = typeof value === 'object' && value ? Number(value.confidence_score ?? value.confidence) : null;
    const supported = typeof value === 'object' && value ? value.supported : undefined;
    const row = {key: contractReviewHumanLabel(key), value: contractReviewDisplayValue(value), confidence, supported};
    if (supported === false || (Number.isFinite(confidence) && confidence < 0.4)) needsReview.push(row);
    else confirmed.push(row);
  }
  return {confirmed, needsReview};
}

function contractReviewIssueFinding(risk) {
  const finding = contractReviewDisplayValue(risk.finding || risk.reasoning || risk.recommended_action || '');
  if (!finding || finding === 'Relevant language found for review.') {
    return 'Requires lawyer review; automated risk analysis did not produce detailed reasoning for this issue.';
  }
  return finding;
}

function contractReviewHasFallbackTrace(result) {
  return (result.agentic_review?.trace || []).some(step => step.status === 'fallback' || step.error);
}

function normalizeContractReviewMarkdownText(value) {
  return contractReviewDisplayValue(value)
    .replace(/\r\n/g, '\n')
    .replace(/\s+(#{2,4}\s+)/g, '\n\n$1')
    .replace(/\s+(-\s+)/g, '\n$1')
    .replace(/((?:CRITICAL|HIGH|MEDIUM-HIGH|MEDIUM|LOW)\s+SEVERITY\))\s+([A-Z])/g, '$1\n$2')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function inlineContractReviewMarkdown(value) {
  return esc(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>');
}

function renderContractReviewMarkdownBlock(value) {
  const lines = normalizeContractReviewMarkdownText(value).split('\n');
  const html = [];
  let paragraph = [];
  let list = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inlineContractReviewMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    html.push(`<ul>${list.map(item => `<li>${inlineContractReviewMarkdown(item)}</li>`).join('')}</ul>`);
    list = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{2,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(4, Math.max(3, heading[1].length + 1));
      html.push(`<h${level}>${inlineContractReviewMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = /^[-*]\s+(.+)$/.exec(line);
    if (bullet) {
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  return html.join('');
}

function renderContractReviewSummaryHtml(value) {
  const text = contractReviewDisplayValue(value).replace(/\s+/g, ' ').trim();
  const matches = [...text.matchAll(/\((\d+)\)\s+/g)];
  if (matches.length < 2) return `<p>${esc(text)}</p>`;
  const intro = text.slice(0, matches[0].index).trim();
  const items = matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = matches[index + 1]?.index ?? text.length;
    return text.slice(start, end).trim();
  }).filter(Boolean);
  return `${intro ? `<p>${esc(intro)}</p>` : ''}<ol>${items.map(item => `<li>${esc(item)}</li>`).join('')}</ol>`;
}

function renderStandaloneRiskHeatmap(clauses) {
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
        return `<div class="heatmap-cell risk-${esc(level)} ${value ? 'has-risk' : ''}">${value || ''}</div>`;
      }).join('')}`).join('')}
    </div>
  </div>`;
}

function renderContractSummaries(summaries) {
  const items = summaries || [];
  if (!items.length) return '';
  return `<div class="contract-summary-grid">
    ${items.map(summary => {
      const audience = summary.audience || summary.summary_type || 'summary';
      const text = summary.summary_text || summary.summary || summary.text || summary.content || '';
      const bullets = Array.isArray(summary.negotiation_points || summary.key_points || summary.bullets) ? (summary.negotiation_points || summary.key_points || summary.bullets) : [];
      const unusualTerms = Array.isArray(summary.unusual_terms) ? summary.unusual_terms : [];
      return `<div class="contract-summary-card">
        <div class="council-card-title">${esc(String(audience).replace(/_/g, ' '))}</div>
        ${text ? `<div class="council-card-desc">${esc(contractReviewDisplayValue(text)).replace(/\n/g, '<br>')}</div>` : ''}
        ${bullets.length ? `<ul>${bullets.map(item => `<li>${esc(contractReviewDisplayValue(item))}</li>`).join('')}</ul>` : ''}
        ${unusualTerms.length ? `<div class="council-card-meta">${esc(unusualTerms.length)} unusual term${unusualTerms.length === 1 ? '' : 's'}</div>` : ''}
      </div>`;
    }).join('')}
  </div>`;
}

function renderStandaloneWorkflowReview(workflow) {
  if (!workflow) return '';
  const rawClauses = workflow.clauses || [];
  const clauses = summarizeStandaloneClauseItems(rawClauses);
  const stats = workflow.stats || {};
  const summaries = workflow.summaries || [];
  const escalations = workflow.escalations || [];
  return `<section class="contract-review-workspace">
    <div class="contract-review-page-head">
      <div>
        <div class="settings-section-desc">Structured workflow review</div>
        <div class="contract-dashboard-title">${esc(workflow.intake?.contract_type || 'Contract')}</div>
        <div class="council-card-meta">${esc(workflow.intake?.contract_category || 'general')}${workflow.coverage_score !== null && workflow.coverage_score !== undefined ? ' · coverage ' + esc(String(workflow.coverage_score)) : ''}</div>
      </div>
    </div>
    <div class="contract-review-stats">
      <div class="stat-pill"><strong>${esc(String(clauses.length))}</strong> clause areas</div>
      <div class="stat-pill"><strong>${esc(String(stats.review_needed ?? 0))}</strong> need review</div>
      <div class="stat-pill"><strong>${esc(String(stats.high ?? 0))}</strong> high</div>
      <div class="stat-pill"><strong>${esc(String(stats.critical ?? 0))}</strong> critical</div>
      <div class="stat-pill"><strong>${esc(String(stats.escalations ?? escalations.length))}</strong> escalations</div>
    </div>
    ${renderContractSummaries(summaries)}
    ${renderStandaloneRiskHeatmap(clauses)}
    ${escalations.length ? `<div class="contract-escalations">
      <div class="council-row-head"><div><div class="council-card-title">Escalations</div><div class="council-card-meta">Items requiring human review before external delivery</div></div></div>
      <div class="contract-escalation-list">${escalations.map(e => `<div class="contract-escalation-item"><span class="risk-badge risk-${esc(e.severity || 'high')}">${esc(e.severity || 'high')}</span><span><strong>${esc(e.reason || 'Escalation')}</strong><small>${esc(e.required_action || '')}</small></span></div>`).join('')}</div>
    </div>` : ''}
    <div class="contract-filter-panel">
      <div><div class="council-card-title">Clause Areas</div><div class="council-card-meta">${rawClauses.length} extracted references grouped into ${clauses.length} clause areas</div></div>
    </div>
    <div class="contract-review-grid">
      <div class="contract-review-list">
        ${clauses.length ? clauses.map(item => renderStandaloneClauseRow(item)).join('') : '<div class="council-row"><div class="council-card-desc">No clauses were extracted from the indexed text.</div></div>'}
      </div>
      <div class="contract-review-detail">
        ${clauses.length ? renderStandaloneClauseDetail(clauses[0]) : renderContractSummaries(summaries)}
      </div>
    </div>
  </section>`;
}

function renderStandaloneClauseRow(item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  const topRisk = [...risks].sort((a,b) => standaloneRiskRank(b.risk_level) - standaloneRiskRank(a.risk_level))[0];
  const risk = topRisk?.risk_level || 'low';
  const sourceLabel = (clause.source_summary || []).join(', ') || contractReviewDocumentName(clause.source?.filename);
  return `<div class="contract-clause-row">
    <span>
      <strong>${esc(contractReviewHumanLabel(clause.title || clause.clause_type || 'Clause'))}</strong>
      <small>${esc(item.count ? `${item.count} reference${item.count === 1 ? '' : 's'} · ${sourceLabel}` : sourceLabel)}</small>
    </span>
    <span class="risk-badge risk-${esc(risk)}">${esc(risk)}</span>
  </div>`;
}

function renderStandaloneClauseDetail(item) {
  const clause = item.clause || {};
  const risks = item.risks || [];
  const findings = item.playbook_findings || [];
  const redlines = item.redline_suggestions || [];
  return `<div class="contract-clause-detail-card">
    <div class="council-row-head">
      <div>
        <div class="council-card-title">${esc(contractReviewHumanLabel(clause.title || clause.clause_type || 'Clause'))}</div>
        <div class="council-card-meta">${esc(item.count ? `${item.count} extracted reference${item.count === 1 ? '' : 's'}` : 'Extracted clause area')}${(clause.source_summary || []).length ? ' · ' + esc(clause.source_summary.join(', ')) : ''}</div>
      </div>
    </div>
    ${clause.text ? `<div class="contract-clause-text">${esc(clause.text)}</div>` : ''}
    ${risks.length ? `<div class="contract-risk-list">${risks.map(r => `<div class="contract-risk-item"><span class="risk-badge risk-${esc(r.risk_level || r.severity || 'medium')}">${esc(r.risk_level || r.severity || 'medium')}</span><span>${esc(contractReviewIssueFinding(r))}</span></div>`).join('')}</div>` : '<div class="council-card-desc">No material issue was extracted for this clause area.</div>'}
    ${(findings.length || redlines.length) ? `<div class="contract-detail-section"><div class="council-card-title">Playbook & Redline Notes</div>
      ${findings.map(f => `<div class="contract-finding-item"><strong>${esc(f.status || 'finding')}</strong><span>${esc(f.deviation_summary || '')}</span></div>`).join('')}
      ${redlines.map(r => `<div class="contract-finding-item"><strong>Suggested fallback</strong><span>${esc(r.fallback_language || r.suggestion_text || '')}</span></div>`).join('')}
    </div>` : ''}
  </div>`;
}

function contractReviewMarkdown(result = App.contractReview.result) {
  if (!result) return '';
  const workflow = result.workflow || {};
  const stats = workflow.stats || {};
  const {confirmed, needsReview} = splitContractReviewExtraction(result.extraction || {});
  const risks = (result.risk_matrix || []).map(r => {
    const issue = contractReviewDisplayValue(r.issue || r.clause_type || 'Issue');
    const severity = contractReviewDisplayValue(r.severity || r.risk_level || 'n/a');
    const clauseRef = r.clause_id ? ` [${r.clause_id}]` : '';
    return `- **${issue}** (${severity})${clauseRef}: ${contractReviewIssueFinding(r)}`;
  }).join('\n');
  const confirmedFacts = confirmed.map(row => `- **${row.key}**: ${row.value}`).join('\n');
  const reviewFacts = needsReview.map(row => {
    const confidence = Number.isFinite(row.confidence) ? `; confidence ${row.confidence}` : '';
    return `- **${row.key}**: ${row.value}${confidence}`;
  }).join('\n');
  const clauseAreas = summarizeStandaloneClauseItems(workflow.clauses || []).slice(0, 12).map(item => {
    const risk = [...(item.risks || [])].sort((a,b) => standaloneRiskRank(b.risk_level || b.severity) - standaloneRiskRank(a.risk_level || a.severity))[0];
    const severity = risk?.risk_level || risk?.severity || 'review';
    const sourceLabel = (item.clause?.source_summary || []).join(', ');
    return `- **${contractReviewHumanLabel(item.clause?.title || item.clause?.clause_type)}** (${severity}; ${item.count} reference${item.count === 1 ? '' : 's'}${sourceLabel ? `; ${sourceLabel}` : ''}): ${risk ? contractReviewIssueFinding(risk) : 'No material issue extracted.'}`;
  }).join('\n');
  const sourceBasis = contractReviewSourceBasis(result.sources || []).map(source => `- **${contractReviewSourceBasisLabel(source)}**`).join('\n');
  const qualityNotice = contractReviewHasFallbackTrace(result)
    ? 'Automated specialist output was incomplete for at least one internal step. The review below uses deterministic fallback where needed and requires lawyer verification.'
    : 'No internal agent-output fallback was recorded for this run.';
  const overview = workflow.stats ? `## Review Overview\n- Clause areas reviewed: ${summarizeStandaloneClauseItems(workflow.clauses || []).length}\n- Extracted references grouped: ${stats.clauses ?? (workflow.clauses || []).length}\n- Items marked for review: ${stats.review_needed ?? 0}\n- High risk items: ${stats.high ?? 0}\n- Critical risk items: ${stats.critical ?? 0}\n\n` : '';
  return `# ${result.title || 'Contract Review'}\n\n${overview}## Executive Summary\n${contractReviewDisplayValue(result.client_summary)}\n\n## Key Risks\n${risks || 'No material risks returned.'}\n\n## Key Clause Areas\n${clauseAreas || 'No clause areas returned.'}\n\n## Confirmed Contract Facts\n${confirmedFacts || 'No confirmed facts returned.'}\n\n## Items Needing Confirmation\n${reviewFacts || 'No low-confidence or unsupported extraction fields were returned.'}\n\n## Negotiation Memo\n${normalizeContractReviewMarkdownText(result.negotiation_memo)}\n\n## Source Basis\n${sourceBasis || 'No source documents returned.'}\n\n## Review Quality Note\n${qualityNotice}\n\n## Review Notice\nHuman legal review is required before use or circulation.\n`;
}

function renderStandaloneContractReviewResult() {
  const result = App.contractReview.result;
  const grid = document.getElementById('contract-review-result-grid');
  const preview = document.getElementById('contract-review-preview');
  const meta = document.getElementById('contract-review-result-meta');
  const side = document.getElementById('contract-review-side-list');
  if (!result || !grid || !preview || !side) return;
  grid.style.display = 'grid';
  const agentLabel = result.agentic_review?.enabled ? 'agentic review' : 'deterministic fallback';
  if (meta) meta.textContent = `${result.review_depth || 'standard'}${result.playbook?.name ? ' · ' + result.playbook.name : ''}${result.provider ? ' · ' + result.provider : ' · fallback'} · ${agentLabel}`;
  const riskRows = (result.risk_matrix || []).map(r => `<tr><td>${esc(contractReviewDisplayValue(r.issue || r.clause_type || 'Issue'))}</td><td>${esc(contractReviewDisplayValue(r.severity || r.risk_level || 'n/a'))}</td><td>${esc(contractReviewIssueFinding(r))}</td></tr>`).join('');
  const {confirmed, needsReview} = splitContractReviewExtraction(result.extraction || {});
  const confirmedRows = confirmed.map(row => `<tr><td>${esc(row.key)}</td><td>${esc(row.value)}</td></tr>`).join('');
  const needsReviewRows = needsReview.map(row => `<tr><td>${esc(row.key)}</td><td>${esc(row.value)}</td></tr>`).join('');
  const sourceBasis = contractReviewSourceBasis(result.sources || []);
  const qualityItems = contractReviewHasFallbackTrace(result)
    ? ['One or more internal specialist outputs were incomplete. Deterministic fallback was used where needed; verify the review before relying on it.']
    : ['No internal fallback was recorded for this run.'];
  preview.innerHTML = sanitizeDraftHtml(`
    ${renderStandaloneWorkflowReview(result.workflow)}
    <article class="draft-document">
      <h1>${esc(result.title || 'Contract Review')}</h1>
      <section><h2>Executive Summary</h2>${renderContractReviewSummaryHtml(result.client_summary)}</section>
      <section><h2>Risk Matrix</h2><table><thead><tr><th>Issue</th><th>Severity</th><th>Finding</th></tr></thead><tbody>${riskRows || '<tr><td colspan="3">No risks returned.</td></tr>'}</tbody></table></section>
      <section><h2>Confirmed Facts</h2><table><tbody>${confirmedRows || '<tr><td>No confirmed facts returned.</td></tr>'}</tbody></table></section>
      <section><h2>Needs Confirmation</h2><table><tbody>${needsReviewRows || '<tr><td>No low-confidence or unsupported extraction fields were returned.</td></tr>'}</tbody></table></section>
      <section><h2>Negotiation Memo</h2>${renderContractReviewMarkdownBlock(result.negotiation_memo)}</section>
    </article>
  `);
  side.innerHTML = `
    <div class="translate-review-section"><strong>Warnings</strong>${renderTranslationList(result.review_warnings || [], 'Human legal review required.')}</div>
    <div class="translate-review-section"><strong>Review Quality</strong>${renderTranslationList(qualityItems, 'No review quality notes returned.')}</div>
    <div class="translate-review-section"><strong>Source Basis</strong>${renderTranslationList(sourceBasis.map(contractReviewSourceBasisLabel), 'No source documents returned.')}</div>
  `;
}

async function copyStandaloneContractReview() {
  const text = contractReviewMarkdown();
  if (!text) return;
  await navigator.clipboard.writeText(text);
  showToast('Contract review copied.');
}

function downloadStandaloneContractReview() {
  const text = contractReviewMarkdown();
  if (!text) return;
  const blob = new Blob([text], {type:'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `contract-review-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function resetStandaloneContractReview() {
  App.contractReview.result = null;
  const ids = ['contract-review-title', 'contract-review-instructions'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  document.getElementById('contract-review-result-grid').style.display = 'none';
  clearContractReviewStatus({force: true});
}
