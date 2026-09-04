/* The Live System page. Every verdict, every signal, every branch shown
   here comes from a real HTTP call to the FastAPI backend, which calls the
   real, unmodified financial_system decision functions against the real
   database -- computed at click time. This file also drives the
   phase-by-phase walkthrough: each phase is rendered from that same real
   response data (verdict.metrics, verdict.reason, verdict.decision), never
   invented for display. */

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

const CY_STYLE = [
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
];

let currentCase = null;
let walkthroughToken = 0; // bumped on every selection; stale async work checks this and bails
const chatThreads = {}; // id -> {turns:[{role,content}], messages:[...], busy, verdict, type, id}

function liveShell(){
  return `
  <div class="live-topbar">
    <h1>LIVE SYSTEM</h1>
    <span class="sub">Pick a real transaction &mdash; watch Heimdall reason through it, phase by phase, live.</span>
    <span class="meta"><span class="status-dot js-backend-dot"></span><span class="js-backend-label">connecting…</span></span>
  </div>
  <div class="app-shell2">
    <div class="rail"><div class="rail-head">// REAL CASES</div><div id="live-rail-list"><p style="padding:0 14px; font-size:11px; color:var(--muted-2);">loading…</p></div></div>
    <div class="chat-panel">
      <div class="chat-head" id="live-chat-head">Select a case</div>
      <div class="chat-evidence" id="live-phase-panel"></div>
      <div class="chat-messages" id="live-chat-messages"></div>
      <div class="chat-composer">
        <input id="live-chat-input" placeholder="Ask about this case…" disabled autocomplete="off" onkeydown="if(event.key==='Enter'){submitLiveChat();}">
        <button class="btn btn-ghost" id="live-chat-send" onclick="submitLiveChat()" disabled>ASK</button>
      </div>
    </div>
    <div class="graphpanel graph-panel-shell">
      <div class="graph-toolbar"><span id="live-graph-count">select a case to begin</span><span style="color:var(--muted-2);">history of every phase, top to bottom</span></div>
      <div id="live-canvas"></div>
    </div>
  </div>`;
}

async function initLivePage(){
  document.getElementById('live').innerHTML = liveShell();
  renderStatus();
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
      <div class="rail-item${currentCase===c.id?' active':''}" data-case-id="${c.id}" onclick="selectLiveCase('${c.id}','${kind}')">
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

function fetchVerdict(id, type){
  if(type === 'Payment') return api(`/api/recovery/${encodeURIComponent(id)}`);
  if(type === 'Device') return api(`/api/risk/${encodeURIComponent(id)}`);
  if(type === 'Settlement') return api(`/api/controller/${encodeURIComponent(id)}`);
  return Promise.resolve(null);
}

async function selectLiveCase(id, type){
  currentCase = id;
  const myToken = ++walkthroughToken;
  document.querySelectorAll('.rail-item').forEach(el => el.classList.toggle('active', el.dataset.caseId === id));
  document.getElementById('live-chat-head').textContent = 'Loading ' + id + '…';
  document.getElementById('live-phase-panel').innerHTML = `<p style="font-size:12px; color:var(--muted-2);">Calling the real backend…</p>`;
  document.getElementById('live-chat-messages').innerHTML = '';
  document.getElementById('live-canvas').innerHTML = '';
  document.getElementById('live-graph-count').textContent = 'loading…';

  try{
    const [neighborhood, verdict] = await Promise.all([
      api(`/api/graph/neighborhood/${encodeURIComponent(id)}`),
      fetchVerdict(id, type),
    ]);
    if(myToken !== walkthroughToken) return; // a later click superseded this one
    if(!chatThreads[id]) chatThreads[id] = { turns:null, messages:[], busy:false, verdict, type, id };
    else chatThreads[id].verdict = verdict;
    startWalkthrough(id, type, verdict, neighborhood, myToken);
  }catch(e){
    if(myToken !== walkthroughToken) return;
    document.getElementById('live-chat-head').textContent = id;
    document.getElementById('live-phase-panel').innerHTML = `<p style="font-size:12px; color:var(--critical);">Live call failed: ${escapeHtml(e.message)}</p>`;
  }
}

function addCanvasBox(n, total, label, innerHTML, extraClass){
  const canvas = document.getElementById('live-canvas');
  const box = document.createElement('div');
  box.className = 'canvas-box' + (extraClass ? ' ' + extraClass : '');
  box.innerHTML = `<div class="box-label"><span class="n">PHASE ${n}/${total}</span> — ${label}</div>${innerHTML}`;
  canvas.appendChild(box);
  canvas.scrollTop = canvas.scrollHeight;
  return box;
}

function initLiveGraphInto(container, neighborhood, centerId){
  const elements = [
    ...neighborhood.nodes.map(n => ({ data:{ id:n.id, label: shortId(n.id), type:n.type } })),
    ...neighborhood.edges.map(e => ({ data:{ source:e.from, target:e.to, rel:e.rel } })),
  ];
  const cy = cytoscape({
    container, elements, wheelSensitivity: 0.25, style: CY_STYLE, layout: { name:'preset' },
  });
  cy.layout({ name:'fcose', quality:'proof', animate:true, animationDuration:400,
    fit:true, padding:18, nodeDimensionsIncludeLabels:true, nodeSeparation:60,
    nodeRepulsion:8000, idealEdgeLength:55, gravity:0.25 }).run();
  cy.$id(centerId).addClass('live-focus');
  cy.on('tap', 'node', (evt) => selectLiveCase(evt.target.id(), evt.target.data('type')));
}

function branchTreeHTML(branches){
  return `<div class="branch-list">${branches.map(b => `
    <div class="branch${b.taken ? ' taken' : ''}">
      <span class="cond">${escapeHtml(b.cond)}</span>
      <span class="arrow">${b.taken ? '⟹' : '→'}</span>
      <span class="out">${escapeHtml(b.out)}</span>
    </div>`).join('')}</div>`;
}

function metricRow(k, v){
  return `<div class="verdict-metric"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(String(v))}</span></div>`;
}

// -- per-domain phase builders. Every branch below is the real branch that
// exists in recovery_agent.py / risk_agent.py / controller.py -- "taken" is
// determined from the real verdict's own decision + reason string (each
// branch stamps a distinct, literal reason substring in the real code), not
// guessed.

function recoveryPhases(verdict){
  const m = verdict.metrics;
  const r = verdict.reason;
  return [
    {
      label: 'SIGNALS',
      desc: 'Recovery reads this payment’s real status and failure_reason, checks whether a sibling payment on the same order already succeeded (never retry into a duplicate charge), and whether this order has seen prior failed attempts.',
      render: () => (
        metricRow('base_success_rate (this category)', (m.base_success_rate*100).toFixed(0) + '%') +
        metricRow('has_alternate_success', m.has_alternate_success ? 'true' : 'false') +
        metricRow('has_prior_failed_attempts', m.has_prior_failed_attempts ? 'true' : 'false')
      ),
    },
    {
      label: 'BRANCH',
      desc: 'Five possible branches. Exactly one applies — the one this payment’s real signals actually satisfy.',
      render: () => branchTreeHTML([
        { cond:'payment status is not "failed"', out:'DO_NOT_RETRY', taken: r.includes('is not currently failed') },
        { cond:'a sibling payment on this order already succeeded', out:'DO_NOT_RETRY', taken: r.includes('already succeeded') },
        { cond:'failure_reason is unrecognized', out:'INVESTIGATE', taken: r.includes('unrecognized failure_reason') },
        { cond:'category is not recoverable', out:'ESCALATE', taken: r.includes('is not a recoverable category') },
        { cond:'category is recoverable', out:'RETRY', taken: r.includes('is recoverable; category') },
      ]),
    },
  ];
}

function riskPhases(verdict){
  const m = verdict.metrics;
  return [
    {
      label: 'SIGNALS',
      desc: 'Risk computes four signals over every payment that used this device: how many distinct customers share it, the minimum account age among them, the densest 60-minute payment burst, and that burst’s amount clustering.',
      render: () => (
        metricRow('n_sharers', m.n_sharers) +
        metricRow('max_burst_count (60min window)', m.max_burst_count) +
        metricRow('burst_amount_cov', Number(m.burst_amount_cov).toFixed(3)) +
        metricRow('weighted score', verdict.decision_score)
      ),
    },
    {
      label: 'BRANCH',
      desc: 'One weighted score maps onto one of three tiers — no LLM, no black box, the thresholds are 0.3 and 0.6.',
      render: () => branchTreeHTML([
        { cond:'score < 0.3', out:'LOW → RELEASE', taken: verdict.decision === 'RELEASE' },
        { cond:'0.3 ≤ score < 0.6', out:'MEDIUM → REVIEW', taken: verdict.decision === 'REVIEW' },
        { cond:'score ≥ 0.6', out:'HIGH → HOLD', taken: verdict.decision === 'HOLD' },
      ]),
    },
  ];
}

function controllerPhases(verdict){
  const m = verdict.metrics;
  return [
    {
      label: 'SIGNALS',
      desc: 'Controller sums every real bank transaction deposited against this settlement, compares it to the settlement’s own expected net_amount, and checks for an exact duplicate line item under its real contains-edges.',
      render: () => (
        metricRow('expected', money(m.expected)) +
        metricRow('actual', money(m.actual)) +
        metricRow('unexplained', money(m.unexplained))
      ),
    },
    {
      label: 'BRANCH',
      desc: 'Four possible branches based on whether a gap exists and whether it’s explained.',
      render: () => branchTreeHTML([
        { cond:'no discrepancy', out:'PASS', taken: verdict.decision === 'PASS' },
        { cond:'gap fully explained by a duplicate line item', out:'RESOLVE / ADJUST', taken: verdict.decision === 'RESOLVE' },
        { cond:'gap partially explained', out:'REVIEW', taken: verdict.decision === 'REVIEW' },
        { cond:'gap still unexplained', out:'INVESTIGATE', taken: verdict.decision === 'INVESTIGATE' },
      ]),
    },
  ];
}

function actionDescriptionFor(type, verdict){
  if(type === 'Payment' && verdict.decision === 'RETRY'){
    return 'In this submission’s live bridge (see the Truman page), a real RETRY decision actually re-attempts the purchase against the person’s real, current balance inside a running Truman world. This page queries the frozen, judged dataset — a real, one-time run, not a live clock — so here the action is authorized and logged, not re-executed against a live world.';
  }
  if(type === 'Device' && verdict.decision === 'HOLD'){
    return 'Risk’s own live bridge blocks this device’s subsequent purchases inside a running Truman world (see the Truman page). Here, against the frozen dataset, the action is authorized and logged.';
  }
  return 'Controller has no live loop yet — documented openly as the one domain still batch-only. The action below is what Controller authorized for this real settlement.';
}

function investigationHTML(inv){
  if(!inv.triggered){
    return `<p style="font-size:11.5px; color:var(--muted-2); line-height:1.6;">${escapeHtml(inv.reason)}</p>`;
  }
  const r = inv.result;
  if(inv.degraded_reason){
    return `<p style="font-size:11.5px; color:var(--warn); line-height:1.6;">Investigation was triggered, but this deployment can’t run it right now (${escapeHtml(inv.degraded_reason)}). The Branch phase’s decision above is unaffected — it never depended on this.</p>`;
  }
  if(!r.executed_4b){
    return `<p style="font-size:11.5px; color:var(--warn); line-height:1.6;">${escapeHtml(r.execution_note || 'No server-side LLM key is configured for this deployment, so Discovery.AI’s real 4B pass was not executed.')}</p>`;
  }
  const steps = (r.decompose_steps || []).map((s,i) => `
    <div class="chain-step">
      <div class="q">Step ${i+1} — ${escapeHtml(s.action)}${s.sub_question ? ': ' + escapeHtml(s.sub_question) : ''}</div>
      ${s.sub_answer ? `<div class="a">${escapeHtml(s.sub_answer)}</div>` : ''}
    </div>`).join('');
  return `${steps}
    ${metricRow('investigation_confidence', r.investigation_confidence)}
    <p style="font-size:11.5px; color:var(--muted); line-height:1.6; margin-top:8px;">${escapeHtml(r.narrative || '')}</p>
    <p style="font-size:10px; color:var(--muted-2); margin-top:8px;">Carried for audit only — structurally cannot change the Branch phase’s decision above.</p>`;
}

function buildPhases(type, id, verdict){
  const phases = [
    { label:'DISPATCH', isGraph:true,
      desc:`Heimdall reads ${id}’s real, current state and its immediate neighborhood from the graph, then routes it to the ${verdict.agent} agent.` },
  ];
  if(type === 'Payment') phases.push(...recoveryPhases(verdict));
  else if(type === 'Device') phases.push(...riskPhases(verdict));
  else if(type === 'Settlement') phases.push(...controllerPhases(verdict));

  const mightInvestigate =
    (type === 'Payment' && verdict.decision === 'INVESTIGATE') ||
    (type === 'Device' && verdict.decision === 'HOLD') ||
    (type === 'Settlement' && verdict.decision === 'INVESTIGATE');
  if(mightInvestigate){
    phases.push({
      label: 'SUB-AGENT INVESTIGATION',
      desc: 'Deterministic evidence ran out. Discovery.AI is asked one narrow question, grounded in exactly this case — its answer is logged for audit only and structurally cannot become the decision.',
      render: async () => {
        try{
          const inv = await api(`/api/investigate/${type}/${encodeURIComponent(id)}`);
          return investigationHTML(inv);
        }catch(e){
          return `<p style="font-size:11.5px; color:var(--muted-2);">Investigation call failed: ${escapeHtml(e.message)}</p>`;
        }
      },
    });
  }

  phases.push({
    label: 'POLICY',
    desc: `Policy checks the proposed action against deterministic rules. decision_score=${verdict.decision_score} authorizes ${verdict.proposed_action}. investigation_confidence — if any exists above — has no field in PolicyDecision; it structurally cannot reach this step.`,
    render: () => (
      metricRow('decision_score', verdict.decision_score) +
      metricRow('authorized action', verdict.proposed_action) +
      `<p style="font-size:11.5px; color:var(--muted); line-height:1.6; margin-top:8px;">${escapeHtml(verdict.reason)}</p>`
    ),
  });

  phases.push({
    label: 'ACTION / OUTCOME',
    desc: actionDescriptionFor(type, verdict),
    render: () => (
      metricRow('decision', verdict.decision) +
      metricRow('action', verdict.proposed_action)
    ),
  });

  return phases;
}

function startWalkthrough(id, type, verdict, neighborhood, token){
  document.getElementById('live-chat-head').textContent = `${type} — ${id}`;
  document.getElementById('live-graph-count').textContent =
    `${neighborhood.nodes.length} real nodes · ${neighborhood.edges.length} real edges`;
  const phases = buildPhases(type, id, verdict);
  let i = 0;

  function progressHTML(){
    return `<div class="phase-progress">${phases.map((_,idx) =>
      `<div class="dot ${idx < i ? 'done' : idx === i ? 'current' : ''}"></div>`).join('')}</div>`;
  }

  function renderControls(){
    if(token !== walkthroughToken) return;
    if(i >= phases.length){
      document.getElementById('live-phase-panel').innerHTML =
        `${progressHTML()}<p style="font-size:11.5px; color:var(--good); line-height:1.6;">Walkthrough complete — every phase above ran against ${id}’s real, live-computed data.</p>`;
      renderLiveChat(id);
      return;
    }
    const p = phases[i];
    document.getElementById('live-phase-panel').innerHTML = `
      ${progressHTML()}
      <div class="loop-title" style="margin-bottom:8px;">// PHASE ${i+1} OF ${phases.length} — ${p.label}</div>
      <p style="font-size:12px; color:var(--muted); line-height:1.7;">${p.desc}</p>
      <button class="btn btn-primary" style="margin-top:14px; width:100%;" onclick="advanceWalkthrough()">${i === phases.length-1 ? 'RUN FINAL PHASE ▶' : 'NEXT PHASE ▶'}</button>`;
  }

  window.advanceWalkthrough = async function(){
    if(token !== walkthroughToken) return;
    const p = phases[i];
    document.getElementById('live-phase-panel').innerHTML = `${progressHTML()}<p style="font-size:12px; color:var(--muted-2);">Running phase ${i+1}…</p>`;
    if(p.isGraph){
      const box = addCanvasBox(i+1, phases.length, p.label, `<p style="font-size:11.5px; color:var(--muted); line-height:1.6; padding:0 18px 10px;">${p.desc}</p><div id="live-cy"></div>`, 'graph-box');
      initLiveGraphInto(box.querySelector('#live-cy'), neighborhood, id);
    } else {
      const html = await p.render();
      if(token !== walkthroughToken) return;
      addCanvasBox(i+1, phases.length, p.label, html);
    }
    if(token !== walkthroughToken) return;
    i++;
    renderControls();
  };

  renderControls();
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
      : `<p style="font-size:11.5px; color:var(--warn); line-height:1.6;">Add a key in <a href="#" onclick="go('settings'); return false;">Settings</a> to chat about this case.</p>`;
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
    thread.messages[idx] = { role:'assistant', content: e.code === 'no_key' ? 'Add a key in Settings first.' : ('Error: ' + e.message), error:true };
  }finally{
    thread.busy = false;
  }
  if(currentCase === id) renderLiveChat(id);
}
