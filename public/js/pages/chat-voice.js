function toggleLiveVoice() {
  if (App.voice.active || App.voice.connecting) {
    stopLiveVoice();
    return;
  }
  startLiveVoice();
}

function updateVoiceButton(state) {
  const btn = document.getElementById('voice-btn');
  if (!btn) return;
  const active = state === 'active';
  const connecting = state === 'connecting';
  btn.classList.toggle('active', active);
  btn.classList.toggle('connecting', connecting);
  btn.title = active || connecting ? 'Stop live voice' : 'Start live voice';
  btn.setAttribute('aria-label', btn.title);
}

function setVoiceStatus(label, detail = '') {
  if (!App.voice.statusEl) return;
  App.voice.statusEl.querySelector('.voice-live-title').textContent = label;
  App.voice.statusEl.querySelector('.voice-live-status').textContent = detail;
}

function ensureVoiceCard() {
  document.getElementById('welcome-screen').style.display = 'none';
  const conv = document.getElementById('chat-conversation');
  conv.style.display = 'block';
  let card = document.getElementById('voice-live-card');
  if (!card) {
    card = document.createElement('div');
    card.id = 'voice-live-card';
    card.className = 'voice-live-card';
    card.innerHTML = '<div class="voice-live-dot"></div><div class="voice-live-title">Connecting voice</div><div class="voice-live-status">Mic requested</div>';
    conv.appendChild(card);
  }
  App.voice.statusEl = card;
  scrollBottom();
  return card;
}

async function waitForIceGatheringComplete(pc) {
  if (pc.iceGatheringState === 'complete') return;
  await new Promise(resolve => {
    const done = () => {
      if (pc.iceGatheringState === 'complete') {
        pc.removeEventListener('icegatheringstatechange', done);
        resolve();
      }
    };
    pc.addEventListener('icegatheringstatechange', done);
    setTimeout(resolve, 1200);
  });
}

async function startLiveVoice() {
  if (App.voice.active || App.voice.connecting) return;
  if (!navigator.mediaDevices?.getUserMedia || !window.RTCPeerConnection) {
    showToast('Live voice is not supported in this browser.', 'error');
    return;
  }
  if (App.isStreaming) stopChatResponse();
  App.voice.connecting = true;
  updateVoiceButton('connecting');
  const card = ensureVoiceCard();
  setVoiceStatus('Connecting voice', 'Mic requested');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    const pc = new RTCPeerConnection();
    const audioEl = document.createElement('audio');
    audioEl.autoplay = true;
    audioEl.setAttribute('playsinline', '');
    audioEl.style.display = 'none';
    document.body.appendChild(audioEl);

    pc.ontrack = event => {
      audioEl.srcObject = event.streams[0];
      audioEl.play().catch(() => {});
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === 'connected') {
        App.voice.active = true;
        App.voice.connecting = false;
        card.classList.add('active');
        updateVoiceButton('active');
        setVoiceStatus('Live voice connected', 'Listening');
      } else if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) {
        if (App.voice.active || App.voice.connecting) stopLiveVoice(pc.connectionState);
      }
    };

    stream.getAudioTracks().forEach(track => pc.addTrack(track, stream));
    const dc = pc.createDataChannel('oai-events');
    dc.addEventListener('message', handleRealtimeEvent);
    dc.addEventListener('open', () => {
      setVoiceStatus('Live voice connected', 'Greeting');
      sendVoiceWelcome();
    });

    App.voice = {...App.voice, pc, dc, stream, audioEl};
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc);
    const sdp = pc.localDescription?.sdp || offer.sdp;
    setVoiceStatus('Connecting voice', 'Starting session');
    const payload = JSON.stringify({sdp, persona_id: App.selectedPersonaId || null});
    let response = await fetch('/api/v2/realtime/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: payload,
    });
    if (response.status === 404 || response.status === 405) {
      response = await fetch('/api/realtime/session', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: payload,
      });
    }
    if (!response.ok) throw new Error(await apiError(response));
    await pc.setRemoteDescription({type: 'answer', sdp: await response.text()});
  } catch(e) {
    stopLiveVoice();
    showToast('Live voice failed: ' + e.message, 'error');
  }
}

function appendVoiceUserTranscript(text) {
  const clean = String(text || '').trim();
  if (!clean) return;
  document.getElementById('chat-conversation')?.appendChild(mkUser(clean));
  scrollBottom();
}

function realtimeSend(event) {
  if (!App.voice.dc || App.voice.dc.readyState !== 'open') return false;
  App.voice.dc.send(JSON.stringify(event));
  return true;
}

function voiceWelcomeText() {
  const appName = String(App.settings.app_name || 'AI Blueprint').trim() || 'AI Blueprint';
  const user = App.v2.user || {};
  const userName = String(user.display_name || user.name || user.username || '').trim();
  return userName ? `Hello ${userName}. Welcome to ${appName}.` : `Welcome to ${appName}.`;
}

function sendVoiceWelcome() {
  if (!realtimeSend({
    type: 'response.create',
    response: {
      instructions: `Say exactly this brief welcome and then wait for the user: "${voiceWelcomeText()}"`,
    },
  })) {
    setVoiceStatus('Live voice connected', 'Listening');
  }
}

function currentVoiceDocumentScope() {
  if (App.chatMode === 'general') return {doc_context: 'none'};
  const docCtx = App.chatMode === 'general'
    ? 'none'
    : App.selectedDocIds === 'all'
      ? 'all'
      : Array.isArray(App.selectedDocIds)
        ? App.selectedDocIds.join(',')
        : 'none';
  return {doc_context: docCtx, ...v2ChatScopePayload()};
}

async function callRealtimeDocumentSearch(args) {
  const query = String(args?.query || '').trim();
  if (!query) return {query, results: [], error: 'No search query was provided.'};
  const payload = JSON.stringify({query, ...currentVoiceDocumentScope()});
  let response = await fetch('/api/v2/realtime/search-documents', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: payload,
  });
  if (response.status === 404 || response.status === 405) {
    response = await fetch('/api/realtime/search-documents', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: payload,
    });
  }
  if (!response.ok) throw new Error(await apiError(response));
  return await response.json();
}

function parseRealtimeArgs(value) {
  if (!value) return {};
  if (typeof value === 'object') return value;
  try { return JSON.parse(value); } catch(e) { return {}; }
}

async function handleRealtimeToolCall(call) {
  if (!call?.call_id || call.name !== 'search_documents') return;
  if (App.voice.toolCalls[call.call_id]) return;
  App.voice.toolCalls[call.call_id] = true;
  setVoiceStatus('Searching documents', 'Reading context');
  let output;
  try {
    output = await callRealtimeDocumentSearch(parseRealtimeArgs(call.arguments));
  } catch(e) {
    output = {error: e.message, results: []};
  }
  realtimeSend({
    type: 'conversation.item.create',
    item: {
      type: 'function_call_output',
      call_id: call.call_id,
      output: JSON.stringify(output),
    },
  });
  realtimeSend({
    type: 'response.create',
    response: {
      instructions: 'Use the search_documents results to answer the user. Cite document names briefly when useful. If no results were returned, say no matching document context was found.',
    },
  });
}

function updateVoiceAssistantTranscript(delta, done = false) {
  if (!delta && !App.voice.assistantText) return;
  if (!App.voice.assistantEl) {
    App.voice.assistantText = '';
    App.voice.assistantEl = mkAi('', []);
    document.getElementById('chat-conversation')?.appendChild(App.voice.assistantEl);
  }
  if (delta) App.voice.assistantText += delta;
  const bubble = App.voice.assistantEl.querySelector('.bubble');
  bubble.innerHTML = renderAssistantBubble(App.voice.assistantText, done);
  if (done) {
    App.voice.assistantEl = null;
    App.voice.assistantText = '';
  }
  scrollBottom();
}

function handleRealtimeEvent(event) {
  let data;
  try { data = JSON.parse(event.data); } catch(e) { return; }
  if (data.type === 'input_audio_buffer.speech_started') {
    setVoiceStatus('Listening', 'User speaking');
    if (App.voice.assistantEl) updateVoiceAssistantTranscript('', true);
  } else if (data.type === 'input_audio_buffer.speech_stopped') {
    setVoiceStatus('Thinking', 'Processing speech');
  } else if (data.type === 'conversation.item.input_audio_transcription.completed') {
    appendVoiceUserTranscript(data.transcript || '');
  } else if (data.type === 'response.audio_transcript.delta') {
    setVoiceStatus('AI speaking', 'Streaming audio');
    updateVoiceAssistantTranscript(data.delta || '');
  } else if (data.type === 'response.audio_transcript.done') {
    if (!App.voice.assistantText && data.transcript) updateVoiceAssistantTranscript(data.transcript);
    updateVoiceAssistantTranscript('', true);
    setVoiceStatus('Live voice connected', 'Listening');
  } else if (data.type === 'response.function_call_arguments.done') {
    handleRealtimeToolCall({
      call_id: data.call_id,
      name: data.name,
      arguments: data.arguments,
    });
  } else if (data.type === 'response.done') {
    const calls = data.response?.output || [];
    calls
      .filter(item => item?.type === 'function_call')
      .forEach(item => handleRealtimeToolCall(item));
    updateVoiceAssistantTranscript('', true);
    setVoiceStatus('Live voice connected', 'Listening');
  } else if (data.type === 'error') {
    showToast(data.error?.message || 'Realtime voice error.', 'error');
  }
}

function stopLiveVoice(reason = '') {
  const voice = App.voice;
  try { voice.dc?.close(); } catch(e) {}
  try { voice.pc?.close(); } catch(e) {}
  try { voice.stream?.getTracks().forEach(track => track.stop()); } catch(e) {}
  if (voice.audioEl) voice.audioEl.remove();
  if (voice.statusEl) {
    voice.statusEl.classList.remove('active');
    voice.statusEl.remove();
  }
  App.voice = { active: false, connecting: false, pc: null, dc: null, stream: null, audioEl: null, statusEl: null, assistantText: '', assistantEl: null, toolCalls: {} };
  updateVoiceButton('idle');
  if (reason && reason !== 'closed') showToast('Live voice ended.', 'warning');
}
