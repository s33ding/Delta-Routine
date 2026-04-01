const COGNITO_DOMAIN = 'https://delta-routine.auth.us-east-1.amazoncognito.com';
const CLIENT_ID = '2riu3lp4933v6tvh0hl79vj0ud';
const REDIRECT_URI = 'https://s33ding-delta-routine.s3.amazonaws.com/index.html';
const API_BASE = 'https://6w810d95ci.execute-api.us-east-1.amazonaws.com/prod';

let currentColors = { health: '#9e6878', work: '#5e7e94', personal: '#94705e', learning: '#6a946a', other: '#7e7494', sleep: '#4a5568', free: '#a0aec0' };
let allSchedules = [];
let allTodos = [];

// Auth
function loginGoogle() { window.location.href = `${COGNITO_DOMAIN}/oauth2/authorize?response_type=token&client_id=${CLIENT_ID}&redirect_uri=${encodeURIComponent(REDIRECT_URI)}&scope=openid+email+profile&identity_provider=Google`; }
function logout() { sessionStorage.clear(); window.location.href = `${COGNITO_DOMAIN}/logout?client_id=${CLIENT_ID}&logout_uri=${encodeURIComponent(REDIRECT_URI)}`; }
function parseToken() { return new URLSearchParams(window.location.hash.substring(1)).get('id_token'); }
function decodeJwt(t) { return JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); }
function getToken() { return sessionStorage.getItem('id_token'); }

// Colors
function applyColors(colors) {
  if (!colors) return;
  for (const [k, v] of Object.entries(colors)) currentColors[k.toLowerCase().replace(/[^a-z0-9]/g, '-')] = v;
  const style = document.getElementById('dynamic-colors') || document.createElement('style');
  style.id = 'dynamic-colors';
  const categories = ['health', 'work', 'personal', 'learning', 'other'];
  const catRules = [], actRules = [];
  for (const [key, color] of Object.entries(currentColors)) {
    if (categories.includes(key)) catRules.push(`.cal-event.cat-${key} { background: ${color}; }`);
    else actRules.push(`.cal-event.cal-event.cat-${key} { background: ${color}; }`);
  }
  style.textContent = catRules.join('\n') + '\n' + actRules.join('\n');
  document.head.appendChild(style);
}

// Schedule rendering
function renderSchedules(s) { allSchedules = s || []; switchScheduleView(); }

function switchScheduleView() {
  const type = document.getElementById('schedule-type').value;
  document.getElementById('schedule-title').textContent = type === 'routine' ? 'Routine' : 'Custom';
  const filtered = allSchedules.filter(r => (r.schedule_type || 'routine') === type);
  const el = document.getElementById('schedule-table');
  if (!filtered.length) { el.innerHTML = `<p class="cal-empty">No ${type} schedules yet.</p>`; return; }

  if (type === 'routine') {
    const dayNames = ['SUN','MON','TUE','WED','THU','FRI','SAT'];
    const dayMap = {sunday:0,monday:1,tuesday:2,wednesday:3,thursday:4,friday:5,saturday:6};
    const byDay = {0:[],1:[],2:[],3:[],4:[],5:[],6:[]};
    filtered.forEach(r => {
      if (!r.day) return;
      let dow; const lower = r.day.toLowerCase();
      if (dayMap[lower] !== undefined) dow = dayMap[lower];
      else { const d = new Date(r.day+'T12:00:00'); dow = isNaN(d)?null:d.getDay(); }
      if (dow !== null && byDay[dow]) byDay[dow].push(r);
    });
    for (let d in byDay) byDay[d].sort((a,b)=>(a.start_time||'').localeCompare(b.start_time||''));
    let html = '<table class="cal-grid"><tr>'+dayNames.map(d=>'<th>'+d+'</th>').join('')+'</tr><tr>';
    for (let d=0;d<7;d++) {
      html += '<td>';
      byDay[d].forEach(item => {
        const cat = (item.category||'other').toLowerCase();
        const act = (item.title||'').toLowerCase().replace(/[^a-z0-9]/g,'-');
        html += `<div class="cal-event cat-${cat} cat-${act}"><div class="ev-time">${item.start_time||''} - ${item.end_time||''}</div><div class="ev-title">${item.title||''}</div></div>`;
      });
      html += '</td>';
    }
    el.innerHTML = html + '</tr></table>';
  } else {
    filtered.sort((a,b)=>(a.day||'').localeCompare(b.day||''));
    let html = '<table class="cal-grid"><tr><th>Date</th><th>Time</th><th>Title</th><th>Category</th></tr>';
    filtered.forEach(r => {
      const cat = (r.category||'other').toLowerCase();
      html += `<tr><td>${r.day||''}</td><td><span class="cal-event cat-${cat}" style="display:inline-block;padding:2px 6px">${r.start_time||''}-${r.end_time||''}</span></td><td>${r.title||''}</td><td>${r.category||''}</td></tr>`;
    });
    el.innerHTML = html + '</table>';
  }
}

// Todos
function renderTodos(todos) {
  allTodos = todos || [];
  const el = document.getElementById('todo-list');
  if (!allTodos.length) { el.innerHTML = '<p class="cal-empty">No todos yet.</p>'; return; }
  const sorted = [...allTodos].sort((a,b) => {
    if (a.done !== b.done) return a.done ? 1 : -1;
    const p = {high:0,medium:1,low:2};
    return (p[a.priority]||2) - (p[b.priority]||2);
  });
  el.innerHTML = sorted.map(t =>
    `<div class="todo-item ${t.done?'done':''}"><input type="checkbox" ${t.done?'checked':''} disabled><span class="todo-text">${t.title||''}</span>${t.priority?`<span class="todo-priority ${t.priority}">${t.priority}</span>`:''}</div>`
  ).join('');
}

// Chat
function addMsg(t, c) {
  const d = document.createElement('div'); d.className = 'msg ' + c; d.textContent = t;
  const m = document.getElementById('messages'); m.appendChild(d); m.scrollTop = m.scrollHeight;
}

// API
async function loadSchedules() {
  const token = getToken(); if (!token) return;
  try {
    const [sResp, cResp, tResp] = await Promise.all([
      fetch(API_BASE+'/schedules', {headers:{Authorization:token}}),
      fetch(API_BASE+'/settings', {headers:{Authorization:token}}),
      fetch(API_BASE+'/todos', {headers:{Authorization:token}})
    ]);
    if (cResp.ok) { const cd = await cResp.json(); applyColors(cd.colors); }
    if (sResp.ok) { const sd = await sResp.json(); renderSchedules(sd.schedules); }
    if (tResp.ok) { const td = await tResp.json(); renderTodos(td.todos); }
  } catch(e) {}
  loadInsights();
}

async function loadInsights() {
  const token = getToken(); if (!token) return;
  const sel = document.getElementById('insights-view').value;
  const fromNow = document.getElementById('from-now').checked;
  let url = API_BASE+'/insights?view=week';
  if (sel.startsWith('day-')) url = API_BASE+'/insights?view=day&day='+sel.replace('day-','');
  if (fromNow) url += '&from_now='+new Date().getHours()+':'+String(new Date().getMinutes()).padStart(2,'0');
  try {
    const r = await fetch(url, {headers:{Authorization:token}});
    if (r.ok) { const d = await r.json(); renderInsights(d); }
  } catch(e) {}
}

function renderInsights(d) {
  const el = document.getElementById('insights-content');
  if (!d.by_category || !Object.keys(d.by_category).length) { el.innerHTML = '<p class="cal-empty">No data yet.</p>'; return; }
  const colors = currentColors;
  const totalDay = d.view==='day' ? 24 : 168;
  const allItems = [];
  for (const [cat,pct] of Object.entries(d.by_category)) {
    const awakePct = (pct*d.total_awake_hours/totalDay).toFixed(1);
    allItems.push({label:cat,pct:parseFloat(awakePct),hours:(pct*d.total_awake_hours/100).toFixed(1),color:colors[cat]||'#999'});
  }
  allItems.push({label:'Free',pct:parseFloat((d.free_hours/totalDay*100).toFixed(1)),hours:d.free_hours,color:colors.free||'#a0aec0'});
  allItems.push({label:'Sleep',pct:parseFloat(d.sleep_pct.toFixed(1)),hours:d.sleep_hours,color:colors.sleep||'#4a5568'});

  let html = '<div class="insight-summary">';
  html += `<div class="insight-stat"><div class="num">${d.total_scheduled_hours}h</div><div class="lbl">Scheduled</div></div>`;
  html += `<div class="insight-stat"><div class="num">${d.free_hours}h</div><div class="lbl">Free</div></div>`;
  html += `<div class="insight-stat"><div class="num">${d.sleep_hours}h</div><div class="lbl">Sleep</div></div></div>`;
  html += '<div class="insight-stacked">';
  allItems.forEach(i => { if(i.pct>0) html+=`<div class="insight-stacked-seg" style="width:${i.pct}%;background:${i.color}" title="${i.label}: ${i.hours}h (${i.pct}%)"></div>`; });
  html += '</div><div class="insights-grid"><div class="insight-block"><h4>Time Breakdown</h4>';
  allItems.forEach(i => {
    html += `<div class="insight-row"><span class="label" style="display:flex;align-items:center;gap:4px"><span style="width:8px;height:8px;border-radius:2px;background:${i.color};display:inline-block"></span>${i.label}</span><div class="insight-bar-bg"><div class="insight-bar-fill" style="width:${i.pct}%;background:${i.color}"></div></div><span class="value">${i.hours}h</span></div>`;
  });
  html += '</div><div class="insight-block"><h4>By Task</h4>';
  for (const [task,pct] of Object.entries(d.by_task)) {
    const key = task.toLowerCase().replace(/[^a-z0-9]/g,'-');
    const c = colors[key]||'#888';
    html += `<div class="insight-row"><span class="label">${task}</span><div class="insight-bar-bg"><div class="insight-bar-fill" style="width:${pct}%;background:${c}"></div></div><span class="value">${(pct*d.total_awake_hours/100).toFixed(1)}h</span></div>`;
  }
  html += '</div></div>';
  if (!d.has_sleep_data) html += '<p style="font-size:0.7rem;color:#aaa;margin-top:0.4rem;font-style:italic">Using default sleep (7am-11pm). Tell the assistant your actual times.</p>';
  el.innerHTML = html;
}

async function sendPrompt() {
  const i = document.getElementById('prompt'), p = i.value.trim(); if(!p) return; i.value = '';
  addMsg(p, 'user');
  document.getElementById('loading').style.display = 'block';
  const token = getToken();
  if (!token) { addMsg('No token. Please sign in again.','bot'); document.getElementById('loading').style.display='none'; return; }
  try {
    const r = await fetch(API_BASE+'/agent', {method:'POST',headers:{'Content-Type':'application/json',Authorization:token},body:JSON.stringify({prompt:p})});
    if (r.status===401) { addMsg('Session expired. Redirecting...','bot'); setTimeout(()=>{sessionStorage.clear();loginGoogle();},1500); return; }
    const d = await r.json();
    addMsg(d.message||'Done.','bot');
    if (d.colors) applyColors(d.colors);
    if (d.schedules) renderSchedules(d.schedules);
    if (d.todos) renderTodos(d.todos);
    loadInsights();
  } catch(e) { addMsg('Error: '+e.message,'bot'); }
  document.getElementById('loading').style.display = 'none';
}

function checkAuth() {
  let t = parseToken() || sessionStorage.getItem('id_token');
  if (t) {
    sessionStorage.setItem('id_token', t);
    window.history.replaceState(null,'',window.location.pathname);
    const c = decodeJwt(t);
    if (c.exp*1000 < Date.now()) { sessionStorage.clear(); return; }
    document.getElementById('user-email').textContent = c.email||'';
    document.getElementById('login-section').style.display = 'none';
    document.getElementById('app-section').style.display = 'flex';
    const days = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
    document.getElementById('insights-view').value = 'day-'+days[new Date().getDay()];
    document.getElementById('from-now').checked = true;
    loadSchedules();
  }
}

checkAuth();
