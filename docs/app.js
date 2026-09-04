/* Heimdall Beta -- app shell: nav, settings (API base + BYOK keys for
   Groq/Gemini/Anthropic, all stored only in this browser's localStorage),
   and the fetch wrapper every page uses to reach the real FastAPI backend.
   Nothing here is precomputed -- every call hits a live endpoint. */

const DEFAULT_API_BASE = 'https://heimdall-beta-api.onrender.com';

// Free-tier providers tried first, Anthropic last -- matches Discovery.AI's
// own "Groq / Gemini / Cerebras fallback chain" pattern.
const PROVIDER_ORDER = ['groq', 'gemini', 'anthropic'];
const PROVIDER_LABEL = { groq:'Groq', gemini:'Gemini', anthropic:'Anthropic (Claude)' };

const Settings = {
  get apiBase(){ return localStorage.getItem('hb-api-base') || DEFAULT_API_BASE; },
  set apiBase(v){ localStorage.setItem('hb-api-base', v || DEFAULT_API_BASE); },
  _keysRaw(provider){ return localStorage.getItem('hb-keys-' + provider) || ''; },
  keys(provider){ return this._keysRaw(provider).split(',').map(s=>s.trim()).filter(Boolean); },
  setKeys(provider, raw){
    if(raw) localStorage.setItem('hb-keys-' + provider, raw);
    else localStorage.removeItem('hb-keys-' + provider);
  },
  get anyKeySet(){ return PROVIDER_ORDER.some(p => this.keys(p).length > 0); },
};

async function api(path){
  const res = await fetch(Settings.apiBase + path);
  if(!res.ok){
    const body = await res.text().catch(()=> '');
    throw new Error(`${res.status} ${res.statusText} -- ${body.slice(0,200)}`);
  }
  return res.json();
}

/* Tries every configured key, in provider order (Groq -> Gemini ->
   Anthropic), then every comma-separated key within a provider, stopping
   at the first successful reply. Each attempt is one request to our own
   /api/ask proxy, which forwards that one key to that one provider and
   never sees any of the others. */
async function askLLM(messages, system){
  const attempts = [];
  for(const provider of PROVIDER_ORDER){
    for(const key of Settings.keys(provider)) attempts.push({ provider, key });
  }
  if(!attempts.length) throw Object.assign(new Error('no_key'), { code:'no_key' });

  let lastErr = null;
  for(const { provider, key } of attempts){
    try{
      const res = await fetch(Settings.apiBase + '/api/ask', {
        method:'POST',
        headers:{ 'content-type':'application/json', 'x-api-key':key },
        body: JSON.stringify({ provider, max_tokens:1024, system, messages }),
      });
      const data = await res.json().catch(()=>null);
      if(!res.ok){
        lastErr = Object.assign(new Error((data && data.detail) || res.statusText), { status:res.status, provider });
        continue;
      }
      return data.text;
    }catch(e){
      lastErr = e;
    }
  }
  throw Object.assign(lastErr || new Error('all configured providers failed'), { code:'api_error' });
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
