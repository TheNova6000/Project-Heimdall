/* The Live System page. Every verdict shown here comes from a real HTTP
   call to the FastAPI backend, which calls the real, unmodified
   financial_system decision functions against the real database --
   computed at click time, not read from a file baked into this site. */

const NODE_META = {
  Customer:         { color:'#5ee7ff', shape:'hexagon' },
  Merchant:         { color:'#3ddc84', shape:'round-diamond' },
  Payment:          { color:'#ffffff', shape:'round-rectangle' },
  Device:           { color:'#ffd166', shape:'diamond' },
  PaymentInstrument:{ color:'rgba(255,255,255,0.5)', shape:'round-rectangle' },
  Order:            { color:'rgba(255,255,255,0.4)', shape:'round-rectangle' },
  Settlement:       { color:'rgba(255,255,255,0.4)', shape:'round-rectangle' },
  BankTransaction:  { color:'rgba(255,255,255,0.4)', shape:'round-rectangle' },
  Fee:              { color:'rgba(255,255,255,0.35)', shape:'round-rectangle' },
  Refund:           { color:'rgba(255,255,255,0.35)', shape:'round-rectangle' },
};
function metaFor(type){ return NODE_META[type] || { color:'#ffffff', shape:'round-rectangle' }; }
function shortId(id){ return id && id.length > 16 ? id.slice(0,10) + '…' : id; }

let liveCy = null;
let currentCase = null;
const chatThreads = {}; // id -> {turns:[{role,content}], messages:[...], busy}

function liveShell(){
  return `
  <div class="live-topbar">
    <h1>LIVE SYSTEM</h1>
    <span class="sub">Click a real transaction &mdash; the verdict is computed live, right now, by the real backend.</span>
    <span class="meta"><span class="status-dot js-backend-dot"></span><span class="js-backend-label">connecting…</span></span>
  </div>
  <div class="app-shell2">
    <div class="rail"><div class="rail-head">// REAL CASES</div><div id="live-rail-list"><p style="padding:0 14px; font-size:11px; color:var(--muted-2);">loading…</p></div></div>
    <div class="chat-panel">
      <div class="chat-head" id="live-chat-head">Select a case</div>
      <div class="chat-evidence" id="live-chat-evidence"></div>
      <div class="chat-messages" id="live-chat-messages"></div>
      <div class="chat-composer">
        <input id="live-chat-input" placeholder="Ask about this case…" disabled autocomplete="off" onkeydown="if(event.key==='Enter'){submitLiveChat();}">
        <button class="btn btn-ghost" id="live-chat-send" onclick="submitLiveChat()" disabled>ASK</button>
      </div>
    </div>
    <div class="graphpanel graph-panel-shell"><div class="corner tl"></div><div class="corner br"></div>
      <div class="graph-toolbar"><span id="live-graph-count">loading real graph…</span><span style="color:var(--muted-2);">scroll to zoom &middot; click a node</span></div>
      <div id="live-cy"></div>
    </div>
  </div>`;
}

async function initLivePage(){
  document.getElementById('live').innerHTML = liveShell();
  renderStatus();
  liveCy = cytoscape({
    container: document.getElementById('live-cy'),
    elements: [],
    wheelSensitivity: 0.25,
    style: [
      { selector:'node', style:{
          'label':'data(label)', 'color':'#ffffff', 'font-size':9, 'font-family':'JetBrains Mono, monospace',
          'text-valign':'center', 'text-halign':'center', 'width':'label', 'height':24, 'padding':'8px',
          'shape':(ele)=>metaFor(ele.data('type')).shape, 'background-color':'#000000', 'background-opacity':1,
          'border-width':1.4, 'border-color':(ele)=>metaFor(ele.data('type')).color, 'border-opacity':0.9,
          'text-wrap':'wrap', 'text-max-width':'80px',
      }},
      { selector:'node[type="Customer"]', style:{ 'font-weight':'bold', 'border-width':2, 'height':32 } },
      { selector:'node.live-focus', style:{ 'background-color':'#ffffff', 'border-color':'#000000', 'border-width':2.5, 'color':'#000000', 'font-weight':'bold' } },
      { selector:'edge', style:{
          'width':1.1, 'line-color':'#ffffff', 'line-opacity':0.2, 'target-arrow-color':'#ffffff',
          'target-arrow-shape':'triangle', 'arrow-scale':0.65, 'curve-style':'bezier',
          'line-style':'dashed', 'line-dash-pattern':[4,3], 'label':'data(rel)',
          'font-size':7, 'color':'rgba(255,255,255,0.4)', 'text-rotation':'autorotate',
      }},
    ],
    layout: { name:'grid' },
  });
  liveCy.on('tap', 'node', (evt) => selectLiveCase(evt.target.id(), evt.target.data('type')));

  try{
    const cases = await api('/api/cases');
    renderLiveRail(cases);
  }catch(e){
    document.getElementById('live-rail-list').innerHTML = `<p style="padding:0 14px; font-size:11px; color:var(--critical);">Backend unreachable: ${escapeHtml(e.message)}</p>`;
  }
}

function renderLiveRail(cases){
  const el = document.getElementById('live-rail-list');
  const section = (title, items, kind) => `
    <div class="rail-head" style="margin-top:14px;">${title}</div>
    ${items.map(c => `
      <div class="rail-item${currentCase===c.id?' active':''}" onclick="selectLiveCase('${c.id}','${kind}')">
        <div class="t">${escapeHtml(c.label)}</div>
        <div class="sub">${escapeHtml(c.hint)}</div>
      </div>`).join('')}`;
  el.innerHTML =
    section('PAYMENTS', cases.payments, 'Payment') +
    section('DEVICES', cases.devices, 'Device') +
    section('SETTLEMENTS', cases.settlements, 'Settlement');
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function selectLiveCase(id, type){
  currentCase = id;
  document.querySelectorAll('.rail-item').forEach(el => el.classList.toggle('active', el.textContent.includes(id)));
  document.getElementById('live-chat-head').textContent = 'Loading ' + id + '…';
  document.getElementById('live-chat-evidence').innerHTML = `<p style="font-size:12px; color:var(--muted-2);">Calling the real backend…</p>`;
  document.getElementById('live-chat-messages').innerHTML = '';

  try{
    const [neighborhood, verdict] = await Promise.all([
      api(`/api/graph/neighborhood/${encodeURIComponent(id)}`),
      fetchVerdict(id, type),
    ]);
    renderLiveGraph(neighborhood, id);
    if(!chatThreads[id]) chatThreads[id] = { turns:null, messages:[], busy:false, verdict, type, id };
    else chatThreads[id].verdict = verdict;
    renderLiveEvidence(verdict, type, id);
    renderLiveChat(id);
  }catch(e){
    document.getElementById('live-chat-head').textContent = id;
    document.getElementById('live-chat-evidence').innerHTML = `<p style="font-size:12px; color:var(--critical);">Live call failed: ${escapeHtml(e.message)}</p>`;
  }
}

function fetchVerdict(id, type){
  if(type === 'Payment') return api(`/api/recovery/${encodeURIComponent(id)}`);
  if(type === 'Device') return api(`/api/risk/${encodeURIComponent(id)}`);
  if(type === 'Settlement') return api(`/api/controller/${encodeURIComponent(id)}`);
  return Promise.resolve(null);
}

function renderLiveGraph(neighborhood, centerId){
  document.getElementById('live-graph-count').textContent =
    `${neighborhood.nodes.length} real nodes · ${neighborhood.edges.length} real edges · fetched live`;
  const elements = [
    ...neighborhood.nodes.map(n => ({ data:{ id:n.id, label: shortId(n.id), type:n.type } })),
    ...neighborhood.edges.map(e => ({ data:{ source:e.from, target:e.to, rel:e.rel } })),
  ];
  liveCy.elements().remove();
  liveCy.add(elements);
  liveCy.layout({ name:'fcose', quality:'proof', animate:true, animationDuration:400,
    fit:true, padding:30, nodeDimensionsIncludeLabels:true, nodeSeparation:70,
    nodeRepulsion:8000, idealEdgeLength:60, gravity:0.25 }).run();
  liveCy.nodes().removeClass('live-focus');
  liveCy.$id(centerId).addClass('live-focus');
}

function renderLiveEvidence(verdict, type, id){
  document.getElementById('live-chat-head').textContent = `${type} — ${id}`;
  if(!verdict){
    document.getElementById('live-chat-evidence').innerHTML = `<p style="font-size:12px; color:var(--muted);">No decision applies to this node type.</p>`;
    return;
  }
  const good = ['RELEASE','PASS','DO_NOT_RETRY'].includes(verdict.decision);
  document.getElementById('live-chat-evidence').innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap;">
      <span class="pill ${good?'pill-good':'pill-warn'}">${escapeHtml(verdict.decision)}</span>
      <span style="font-size:10.5px; color:var(--muted-2);">agent: ${verdict.agent}</span>
    </div>
    <div class="verdict-metric" style="border-top:none; padding-top:0;"><span class="k">decision_score</span><span class="v">${verdict.decision_score}</span></div>
    <div class="verdict-metric"><span class="k">proposed_action</span><span class="v">${escapeHtml(verdict.proposed_action)}</span></div>
    <p style="font-size:11.5px; color:var(--muted); line-height:1.6; margin-top:8px;">${escapeHtml(verdict.reason)}</p>
    <p style="font-size:10px; color:var(--muted-2); margin-top:10px;">Computed just now by <code>run_${verdict.agent === 'recovery' ? 'recovery_for_payment' : verdict.agent === 'risk' ? 'risk_for_device' : 'controller_for_settlement'}()</code> &mdash; the real, unmodified function.</p>`;
}

function buildLiveSystemPrompt(thread){
  const v = thread.verdict;
  const lines = [
    'You are Discovery.AI, narrating a decision already computed live by a real backend inside a financial system called Heimdall, for a judge evaluating a hackathon submission. This decision was NOT precomputed -- it was calculated moments ago by calling the real decision function against the real database. Narrate and answer questions about it; never re-decide it or invent facts beyond what is given below.',
    'When you go beyond the given facts, label the sentence INFERRED: (a reasonable reading) or HYPOTHESIS: (a plausible but unconfirmed guess); if the evidence does not cover something asked, say UNKNOWN: plainly.',
    '',
    'OBSERVED (given, not to be doubted):',
    `Entity: ${thread.type} ${thread.id}`,
  ];
  if(v){
    lines.push(`Domain: ${v.agent}`, `Decision: ${v.decision}`, `decision_score: ${v.decision_score}`,
      `Proposed action: ${v.proposed_action}`, `Deterministic reason: ${v.reason}`);
    if(v.metrics) lines.push('Metrics: ' + JSON.stringify(v.metrics));
  }
  return lines.join('\n');
}

function renderLiveChat(id){
  const thread = chatThreads[id];
  const msgEl = document.getElementById('live-chat-messages');
  const input = document.getElementById('live-chat-input');
  const send = document.getElementById('live-chat-send');
  const hasKey = Settings.anyKeySet;

  if(!thread.messages.length){
    msgEl.innerHTML = hasKey
      ? `<p style="font-size:11px; color:var(--muted-2); line-height:1.6;">Ask a question below, or tap one:</p>
         <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
           <button class="btn btn-ghost" style="font-size:11px; padding:8px 12px;" onclick="sendLiveChat('Explain this decision for a non-technical judge.')">Explain this decision</button>
           <button class="btn btn-ghost" style="font-size:11px; padding:8px 12px;" onclick="sendLiveChat('What evidence would change this decision?')">What would change it?</button>
         </div>`
      : `<p style="font-size:11.5px; color:var(--warn); line-height:1.6;">Add your Anthropic API key in <a href="#" onclick="go('settings'); return false;">Settings</a> to chat about this case.</p>`;
  } else {
    msgEl.innerHTML = thread.messages.map((m,i) => `<div class="msg ${m.role}${m.error?' err':''}" id="live-msg-${i}">${m.pending && !m.content ? 'Thinking…' : escapeHtml(m.content)}</div>`).join('');
    msgEl.scrollTop = msgEl.scrollHeight;
  }
  input.disabled = !hasKey || thread.busy;
  send.disabled = !hasKey || thread.busy;
}

function submitLiveChat(){
  const input = document.getElementById('live-chat-input');
  const text = input.value.trim();
  if(!text || !currentCase) return;
  input.value = '';
  sendLiveChat(text);
}

async function sendLiveChat(text){
  const id = currentCase;
  const thread = chatThreads[id];
  if(!thread || thread.busy) return;
  if(!thread.turns) thread.turns = [{ role:'user', content: buildLiveSystemPrompt(thread) }];
  thread.busy = true;
  thread.messages.push({ role:'user', content:text });
  thread.turns.push({ role:'user', content:text });
  const idx = thread.messages.length;
  thread.messages.push({ role:'assistant', content:'', pending:true });
  renderLiveChat(id);
  try{
    const reply = await askLLM(thread.turns);
    thread.messages[idx] = { role:'assistant', content: reply };
    thread.turns.push({ role:'assistant', content: reply });
  }catch(e){
    thread.messages[idx] = { role:'assistant', content: e.code === 'no_key' ? 'Add your Anthropic key in Settings first.' : ('Error: ' + e.message), error:true };
  }finally{
    thread.busy = false;
  }
  if(currentCase === id) renderLiveChat(id);
}
