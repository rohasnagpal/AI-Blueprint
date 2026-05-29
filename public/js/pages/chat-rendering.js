function mkUser(text) {
  const d = document.createElement('div'); d.className = 'msg user';
  d.innerHTML = `<div class="msg-meta"><span>You</span><div class="avatar user-av">U</div></div><div class="bubble">${esc(text)}</div>`;
  return d;
}

function mkAi(content, sources, messageId = '') {
  const d = document.createElement('div'); d.className = 'msg ai';
  const docSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
  d.dataset.messageId = messageId || '';
  const body = content ? renderAssistantBubble(content, true) : '<span data-csp-style="opacity:.4">Preparing response…</span>';
  d.innerHTML = `<div class="msg-meta"><div class="avatar ai-av">${docSvg}</div><span>AI Blueprint</span></div><div class="bubble">${body}</div><div class="msg-actions"><div class="msg-action-btn" title="Copy" onclick="copyMsg(this)"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></div></div>`;
  if (sources.length) d.insertBefore(mkSources(sources), d.querySelector('.msg-actions'));
  return d;
}

function startChatStatus(bubble) {
  const state = {bubble, startedAt: Date.now(), message: 'Preparing response', progress: 6, timer: null, active: true};
  state.timer = setInterval(() => renderChatStatus(state), 1000);
  renderChatStatus(state);
  return state;
}

function updateChatStatus(state, message, progress) {
  if (!state?.active) return;
  state.message = message || state.message;
  if (progress != null && !Number.isNaN(Number(progress))) state.progress = Math.max(0, Math.min(95, Number(progress)));
  renderChatStatus(state);
}

function stopChatStatus(state) {
  if (!state) return;
  state.active = false;
  if (state.timer) clearInterval(state.timer);
}

function renderChatStatus(state) {
  if (!state?.active || !state.bubble) return;
  const elapsed = Math.max(0, Math.floor((Date.now() - state.startedAt) / 1000));
  const progress = Math.max(6, Math.min(95, Math.round(state.progress || 6)));
  state.bubble.innerHTML = `<div class="chat-status-card">
    <div class="chat-status-title">${esc(state.message)}</div>
    <div class="chat-status-meta">${elapsed}s elapsed · ${progress}%</div>
    <div class="progress-bar"><div class="progress-fill" data-csp-style="width:${progress}%"></div></div>
  </div>`;
}

function renderAssistantBubble(content, includeContinueAction = true) {
  const body = mdRender(content);
  if (!includeContinueAction || !needsContinueAction(content)) return body;
  return `${body}<div class="continue-card">
    <div>
      <div class="continue-title">More steps are available</div>
      <div class="continue-desc">Continue in this same chat to complete the remaining review sections.</div>
    </div>
    <button class="btn-secondary" type="button" onclick="continueChatReview()">Continue</button>
  </div>`;
}

function needsContinueAction(content) {
  const text = String(content || '');
  const upper = text.toUpperCase();
  if (/Remaining steps available/i.test(text) || /reply ['"]?continue['"]?/i.test(text)) return true;
  return upper.includes('STEP 0') && (upper.includes('STEP 1') || upper.includes('CUAD')) && !upper.includes('STEP 8');
}

function continueChatReview() {
  if (App.isStreaming) return;
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = 'continue';
  autoResize(input);
  sendMessage();
}

function mkSources(sources) {
  const d = document.createElement('div'); d.className = 'sources';
  const items = sources.map(s => {
    const icon = s.kind === 'web'
      ? '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 0 20"/><path d="M12 2a15.3 15.3 0 0 0 0 20"/>'
      : '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';
    const title = s.url ? `<a class="source-doc" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.filename||s.url)}</a>` : `<div class="source-doc">${esc(s.filename||'')}</div>`;
    return `<div class="source-item"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${icon}</svg><div>${title}${s.excerpt?`<div data-csp-style="font-size:11.5px;color:var(--text-subtle);margin-top:2px">${esc(s.excerpt.substring(0,120))}</div>`:''}</div>${s.page!=null?`<span class="source-page">Chunk ${s.page}</span>`:''}</div>`;
  }).join('');
  d.innerHTML = `<div class="sources-toggle" onclick="toggleSources(this)"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>${sources.length} source${sources.length>1?'s':''}<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-csp-style="transition:transform .2s"><polyline points="6 9 12 15 18 9"/></svg></div><div class="sources-panel">${items}</div>`;
  return d;
}

function copyMsg(btn) {
  const b = btn.closest('.msg').querySelector('.bubble');
  navigator.clipboard.writeText(b.innerText).then(() => showToast('Copied.'));
}

async function downloadChatMarkdown() {
  if (!App.currentChatId) {
    showToast('Open or start a chat before downloading.', 'warning');
    return;
  }
  try {
    const chat = App.chats.find(c => c.id === App.currentChatId);
    const r = await fetch(`/api/chats/${App.currentChatId}/messages`);
    if (!r.ok) throw new Error(await apiError(r));
    const messages = await r.json();
    if (!messages.length) {
      showToast('This chat has no messages to download.', 'warning');
      return;
    }
    const title = chat?.title || 'AI Blueprint chat';
    const lines = [`# ${title}`, '', `Exported: ${new Date().toLocaleString()}`, ''];
    for (const message of messages) {
      lines.push(`## ${message.role === 'user' ? 'User' : 'AI Blueprint'}`, '', message.content || '', '');
      if (message.sources?.length) {
        lines.push('Sources:', '');
        for (const source of message.sources) {
          const name = source.filename || source.url || 'Source';
          const page = source.page != null ? `, chunk ${source.page}` : '';
          const url = source.url ? ` - ${source.url}` : '';
          lines.push(`- ${name}${page}${url}`);
        }
        lines.push('');
      }
    }
    const blob = new Blob([lines.join('\n')], {type: 'text/markdown;charset=utf-8'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${slugify(title || 'chat')}.md`;
    document.body.appendChild(a);
    a.click();
    URL.revokeObjectURL(a.href);
    a.remove();
    showToast('Chat downloaded.');
  } catch(e) {
    showToast('Download failed: ' + e.message, 'error');
  }
}
