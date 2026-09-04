/* Heimdall Beta -- app shell: nav, settings (API base + BYOK Anthropic key,
   both stored only in this browser's localStorage), and the fetch wrapper
   every page uses to reach the real FastAPI backend. Nothing here is
   precomputed -- every call hits a live endpoint. */

const DEFAULT_API_BASE = 'https://heimdall-beta-api.onrender.com';

const Settings = {
  get apiBase(){ return localStorage.getItem('hb-api-base') || DEFAULT_API_BASE; },
  set apiBase(v){ localStorage.setItem('hb-api-base', v || DEFAULT_API_BASE); },
  get anthropicKey(){ return localStorage.getItem('hb-anthropic-key') || ''; },
  set anthropicKey(v){ if(v) localStorage.setItem('hb-anthropic-key', v); else localStorage.removeItem('hb-anthropic-key'); },
};

async function api(path){
  const res = await fetch(Settings.apiBase + path);
  if(!res.ok){
    const body = await res.text().catch(()=> '');
    throw new Error(`${res.status} ${res.statusText} -- ${body.slice(0,200)}`);
  }
  return res.json();
}

async function askClaude(messages, system, onDelta){
  const key = Settings.anthropicKey;
  if(!key) throw Object.assign(new Error('no_key'), { code:'no_key' });
  const res = await fetch(Settings.apiBase + '/api/ask', {
    method:'POST',
    headers:{ 'content-type':'application/json', 'x-api-key':key },
    body: JSON.stringify({ model:'claude-sonnet-4-5-20250929', max_tokens:1024, system, messages }),
  });
  const data = await res.json().catch(()=>null);
  if(!res.ok){
    const msg = (data && data.error && data.error.message) || res.statusText;
    throw Object.assign(new Error(msg), { code:'api_error', status:res.status });
  }
  const text = (data.content || []).map(b => b.text || '').join('');
  return text;
}

let backendState = 'pending'; // pending | ok | bad

async function pingBackend(){
  backendState = 'pending';
  renderStatus();
  try{
    await api('/api/health');
    backendState = 'ok';
  }catch(e){
    backendState = 'bad';
  }
  renderStatus();
}

function renderStatus(){
  document.querySelectorAll('.js-backend-dot').forEach(el => {
    el.className = 'status-dot js-backend-dot ' + (backendState === 'ok' ? 'ok' : backendState === 'bad' ? 'bad' : 'pending');
  });
  document.querySelectorAll('.js-backend-label').forEach(el => {
    el.textContent = backendState === 'ok' ? 'backend live' : backendState === 'bad' ? 'backend unreachable' : 'connecting…';
  });
}

const pages = [
  { id:'home', label:'Home' },
  { id:'live', label:'Live System' },
  { id:'truman', label:'Truman' },
  { id:'discovery', label:'Discovery.AI' },
  { id:'heimdall', label:'Heimdall' },
  { id:'docs', label:'Documentation' },
  { id:'settings', label:'Settings' },
  { id:'about', label:'About' },
];

function renderNav(){
  const nav = document.getElementById('nav');
  nav.innerHTML = pages.map(p=>`<button data-page="${p.id}">${p.label}</button>`).join('');
  nav.addEventListener('click', e=>{
    const b = e.target.closest('button[data-page]');
    if(b) go(b.dataset.page);
  });
}

let liveInited = false;
function go(id){
  document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active', p.id===id));
  document.querySelectorAll('#nav button').forEach(b=>{
    if(b.dataset.page===id) b.setAttribute('aria-current','page'); else b.removeAttribute('aria-current');
  });
  window.scrollTo({top:0, behavior:'instant'});
  try{ localStorage.setItem('hb-page', id); }catch(e){}
  if(id === 'live' && !liveInited){ liveInited = true; initLivePage(); }
  if(id === 'settings') renderSettingsPage();
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('pages').innerHTML = [
    `<div class="page" id="home">${homeHTML()}</div>`,
    `<div class="page" id="truman">${trumanHTML()}</div>`,
    `<div class="page" id="discovery">${discoveryHTML()}</div>`,
    `<div class="page" id="heimdall">${heimdallHTML()}</div>`,
    `<div class="page" id="docs">${docsHTML()}</div>`,
    `<div class="page" id="settings">${settingsHTML()}</div>`,
    `<div class="page" id="about">${aboutHTML()}</div>`,
  ].join('');
  renderNav();
  wireSettingsForm();
  pingBackend();

  let start = 'home';
  try{ const saved = localStorage.getItem('hb-page'); if(saved && pages.some(p=>p.id===saved)) start = saved; }catch(e){}
  go(start);
});
