// ── CHAT ──────────────────────────────────────────────────────────────────
function chatPrimaryAction() {
  if (App.isStreaming) {
    stopChatResponse();
    return;
  }
  sendMessage();
}

function setChatStreaming(active) {
  App.isStreaming = active;
  const btn = document.getElementById('chat-send-btn');
  if (!btn) return;
  btn.title = active ? 'Stop response' : 'Send message';
  btn.setAttribute('aria-label', active ? 'Stop response' : 'Send message');
  btn.classList.toggle('stopping', active);
  btn.innerHTML = active
    ? '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
}

function stopChatResponse() {
  if (!App.isStreaming) return;
  App.activeChatController?.abort();
}

async function sendMessage() {
  if (App.isStreaming) {
    stopChatResponse();
    return;
  }
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = ''; input.style.height = 'auto';
  document.getElementById('welcome-screen').style.display = 'none';
  const conv = document.getElementById('chat-conversation');
  conv.style.display = 'block';
  if (!App.currentChatId) {
    try {
      const docCtx = App.chatMode === 'help' ? 'help' : App.chatMode === 'general' ? 'none' : App.selectedDocIds === 'all' ? 'all' : App.selectedDocIds.join(',');
      const r = await fetch('/api/chats', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({doc_context:docCtx, persona_id:App.selectedPersonaId || null, ...v2ChatScopePayload()})});
      const chat = await r.json();
      if (!r.ok) throw new Error(chat.detail || chat.error || 'Chat creation failed');
      App.currentChatId = chat.id;
    } catch(e) { showToast('Failed to create chat.', 'error'); return; }
  }
  conv.appendChild(mkUser(text));
  const aiEl = mkAi('', []);
  const bubble = aiEl.querySelector('.bubble');
  conv.appendChild(aiEl);
  scrollBottom();
  const controller = new AbortController();
  App.activeChatController = controller;
  setChatStreaming(true);
  const statusState = startChatStatus(bubble);
  let content = '', sources = [], hadError = false, wasStopped = false;
  try {
    const r = await fetch(`/api/chats/${App.currentChatId}/message`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:text, web_search:App.webSearchEnabled}), signal: controller.signal});
    if (!r.ok) throw new Error(await apiError(r));
    if (!r.body) throw new Error('The chat stream did not start.');
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream:true});
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.type === 'token') {
            stopChatStatus(statusState);
            content += ev.content;
            bubble.innerHTML = renderAssistantBubble(content, false);
            scrollBottom();
          }
          else if (ev.type === 'status') {
            updateChatStatus(statusState, ev.content || 'Working…', ev.progress);
            scrollBottom();
          }
          else if (ev.type === 'source') sources.push(ev);
          else if (ev.type === 'error') {
            stopChatStatus(statusState);
            hadError = true;
            content = ev.content || 'Chat request failed.';
            bubble.textContent = content;
            showToast(content, 'error');
          }
          else if (ev.type === 'done' && sources.length) {
            const sp = mkSources(sources);
            aiEl.insertBefore(sp, aiEl.querySelector('.msg-actions'));
            if (App.settings.always_show_sources === 'true') sp.querySelector('.sources-panel').classList.add('open');
          }
        } catch(ex) {}
      }
    }
    stopChatStatus(statusState);
    if (content) bubble.innerHTML = renderAssistantBubble(content, true);
    if (!content && !hadError) bubble.textContent = 'No response was returned.';
  } catch(e) {
    stopChatStatus(statusState);
    if (e.name === 'AbortError') {
      wasStopped = true;
      if (!content) bubble.textContent = 'Response stopped.';
      showToast('Response stopped.', 'warning');
    } else {
      content = 'Stream error: ' + e.message;
      bubble.textContent = content;
      showToast(content, 'error');
    }
  }
  if (wasStopped && content) bubble.innerHTML = renderAssistantBubble(content, true);
  App.activeChatController = null;
  setChatStreaming(false);
  await loadChats();
}
