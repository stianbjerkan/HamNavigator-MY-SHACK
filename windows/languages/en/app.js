const displayProgramName = value => String(value || '').replace(/\bMSHV\b/gi,'HamNavigator').replace(/GridTracker2?/gi,'HamNavigator Map');
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const token = $('meta[name="radio-token"]').content;
let state = {settings:{}, qsos:[], repeaters:[]};
let live = {udp:{running:false,decodes:[],clients:{}},dx:{running:false,spots:[]}};
let editingQso = null;
let toastTimer;
let lastLogged = 0;
let lastLogRevision = '';
let polling = false;
let liveError = false;
let alertedSpots = new Set();
let logPage = 0;
const pageNames = {home:"Overview",hf:'HF & DX',vhf:'VHF / UHF',ft8:'HamNavigator Digital',gridtracker:'HamNavigator Map',listener:"Callsign listener",log:"Logbook",tools:"Tools",help:"Radio help",manual:"User guide",settings:"My station"};
let moduleCatalogReady = false;
function moduleEnabled(id) {
  return !Array.isArray(state.settings.modules) || state.settings.modules.includes(id);
}
function pageEnabled(page) {
  const module = (state.module_catalog||[]).find(m=>m.page===page);
  return !module || moduleEnabled(module.id);
}
function syncModuleChoices() {
  $$('#module-options input').forEach(input=>input.checked=moduleEnabled(input.value));
  $('#module-form .form-error').textContent='';
}
function renderModules() {
  const catalog=state.module_catalog;
  if(!catalog)return;
  if(!moduleCatalogReady){
    $('#module-options').innerHTML=catalog.map(m=>`<label class="module-option"><input type="checkbox" name="module" value="${esc(m.id)}"><span><strong>${esc(m.title)}</strong><small>${esc(m.description)}</small></span></label>`).join('');
    moduleCatalogReady=true;
    $('#modules-save').disabled=false;
    syncModuleChoices();
  }
  for(const module of catalog){
    const enabled=moduleEnabled(module.id);
    if(module.targets) $$(module.targets).forEach(el=>el.hidden=!enabled);
    if(module.page){
      $$(`[data-page="${module.page}"]`).forEach(el=>el.hidden=!enabled);
      $('#page-'+module.page).hidden=!enabled;
    }
  }
  for(const container of $$('#page-home>.home-grid, #page-home>.stats-grid')){
    const visible=[...container.children].filter(el=>!el.hidden).length;
    container.hidden=visible===0;
    container.classList.toggle('single-module',visible===1);
  }
  $('#modules-empty').hidden=['utc','log','ft8'].some(moduleEnabled);
  $('#module-count').textContent=catalog.filter(m=>moduleEnabled(m.id)).length+'/'+catalog.length;
  const active=$('.page.active');
  if(active&&!pageEnabled(active.id.slice(5)))showPage('home');
  if(!moduleEnabled('log')&&$('#qso-dialog').open)$('#qso-dialog').close();
  if(!moduleEnabled('vhf')&&$('#repeater-dialog').open)$('#repeater-dialog').close();
  if(!$('#module-picker').open)syncModuleChoices();
}

function toast(message, error=false) {
  clearTimeout(toastTimer);
  const box = $('#toast');
  box.textContent = message;
  box.classList.toggle('error',error);
  box.hidden = false;
  toastTimer = setTimeout(()=>box.hidden=true,error?10000:6500);
}
async function api(path, data) {
  const response = await fetch('/api/'+path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':token},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The operation failed.");
  return result;
}
function action(fn) {
  return async event => {try {await fn(event);} catch(error){toast(error.message,true);}};
}
function showPage(page, updateHash=true) {
  if(window.hnAuthorized!==true && pageNames.cloud && page!=='language')page='cloud';
  if (!pageNames[page]) page='home';
  if (!pageEnabled(page)){page='home';updateHash=true;}
  $$('.page').forEach(el=>el.classList.toggle('active',el.id==='page-'+page));
  $$('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
  $('#page-label').textContent=pageNames[page];
  if (updateHash) history.replaceState(null,'','#'+page);
  if (page==='hf') renderBands();
  document.dispatchEvent(new CustomEvent('hamnavigator-page-changed',{detail:{page}}));
  window.scrollTo({top:0,behavior:'instant'});
}
const utcTime = date => new Intl.DateTimeFormat("en-GB",{timeZone:'UTC',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date);
function tick() {
  const now = new Date();
  $('#utc-clock').textContent=utcTime(now);
  $('#utc-clock').dateTime=now.toISOString();
  $('#utc-date').textContent=new Intl.DateTimeFormat("en-GB",{timeZone:'UTC',weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(now);
  $('#local-clock').textContent=new Intl.DateTimeFormat("en-GB",{hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(now);
  $('#footer-time').textContent=utcTime(now)+' UTC';
  setTimeout(tick,1000-Date.now()%1000);
}
function stamp(value) {
  if (!value) return '—';
  const normalized=/Z$|[+-]\d\d:\d\d$/.test(value)?value:value.replace(' ','T')+'Z';
  const date=new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-GB",{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date)+' UTC';
}
const mode = q => q.SUBMODE || q.MODE || '';
const sortedQsos = () => [...state.qsos].sort((a,b)=>(b.QSO_DATE+b.TIME_ON).localeCompare(a.QSO_DATE+a.TIME_ON));
const empty = (title, text) => `<div class="empty"><strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
function qsoDate(q) {return `${q.QSO_DATE.slice(6,8)}.${q.QSO_DATE.slice(4,6)}.${q.QSO_DATE.slice(0,4)}`;}
function qsoTime(q) {return (q.TIME_ON||'').padEnd(6,'0').replace(/(..)(..)(..)/,'$1:$2:$3');}
function qsoRows(qsos,edit=false) {
  return qsos.map(q=>`<tr><td class="call">${esc(q.CALL)}</td><td>${esc(qsoDate(q))}<br><small class="muted">${esc(qsoTime(q))}</small></td><td class="mono">${esc(q.FREQ||q.BAND||'—')}</td><td><span class="chip">${esc(mode(q))}</span></td><td>${esc(q.GRIDSQUARE||'—')}</td>${edit?`<td>${esc(q.RST_SENT||'—')} / ${esc(q.RST_RCVD||'—')}</td><td><button class="mini-button" data-edit-qso="${esc(q.id)}">Edit</button><button class="mini-button danger" data-delete-qso="${esc(q.id)}">Delete</button></td>`:''}</tr>`);
}
function renderLog() {
  const search=$('#log-search').value.trim().toUpperCase();
  const filter=$('#log-mode').value;
  const rows=sortedQsos().filter(q=>(!filter||mode(q)===filter)&&[q.CALL,q.GRIDSQUARE,q.NAME,q.COMMENT,q.BAND,q.FREQ].join(' ').toUpperCase().includes(search));
  const pages=Math.max(1,Math.ceil(rows.length/100));
  logPage=Math.max(0,Math.min(logPage,pages-1));
  $('#log-count').textContent=`${rows.length} of ${state.qsos.length} contacts`;
  $('#qso-table').innerHTML=rows.length?table(["CALLSIGN","DATE / UTC","MHz / BAND","MODE","GRID","S / R",''],qsoRows(rows.slice(logPage*100,(logPage+1)*100),true))+(pages>1?`<div class="actions pagination"><button class="secondary" data-log-page="${logPage-1}" ${logPage===0?'disabled':''}>← Previous</button><span class="small muted">Page ${logPage+1} of ${pages}</span><button class="secondary" data-log-page="${logPage+1}" ${logPage===pages-1?'disabled':''}>Next →</button></div>`:''):empty(state.qsos.length?"No matches":"Your first contact starts here",state.qsos.length?"Try a different search or mode.":"Add a contact, import ADIF or connect HamNavigator.");
}
function renderState(fillSettings=false) {
  const s=state.settings;
  $('#station-label').textContent=[s.call,s.grid].filter(Boolean).join(' / ')||"Station not configured";
  $('#setup-banner').hidden=!!(s.call&&s.grid);
  $('#nav-count').textContent=state.qsos.length;
  $('#stat-total').textContent=state.qsos.length;
  const today=new Date().toISOString().slice(0,10).replaceAll('-','');
  $('#stat-today').textContent=state.qsos.filter(q=>q.QSO_DATE===today).length+" today (UTC)";
  $('#stat-calls').textContent=new Set(state.qsos.map(q=>q.CALL)).size;
  const recent=sortedQsos().slice(0,5);
  $('#recent-qsos').innerHTML=recent.length?table(["CALLSIGN","DATE / UTC","MHz / BAND","MODE","GRID"],qsoRows(recent)):empty("No contacts yet","Log your first QSO or import an existing ADIF log.");
  $('#gt-forward-port').textContent=s.udp_port;
  $('#udp-address').textContent='127.0.0.1 : '+s.udp_port;
  $('#udp-instruction-port').textContent=s.udp_port;
  $('#data-path').textContent=state.data_dir||'';
  if(fillSettings){
    for(const [key,value] of Object.entries(s)){
      const input=$('#settings-form').elements.namedItem(key);
      if(input) input.value=value;
    }
    $('#radio-notes').value=s.radio_notes||'';
    $('#path-from').value=s.grid||'';
    $('#phonetic-input').value=s.call||'';
    renderPhonetic();
  }
  renderLog(); renderRepeaters(); renderBands(); renderDX();
  renderModules();
  document.dispatchEvent(new Event('station-state-updated'));
}
async function refreshState(fill=false) {state=await api('state');renderState(fill);}

function openQso(q=null,call='') {
  editingQso=q;
  const form=$('#qso-form');form.reset();form.querySelector('.form-error').textContent='';
  const now=new Date().toISOString();
  const values=q?{...q,MODE:mode(q),date:`${q.QSO_DATE.slice(0,4)}-${q.QSO_DATE.slice(4,6)}-${q.QSO_DATE.slice(6,8)}`,time:qsoTime(q)}:{CALL:call,date:now.slice(0,10),time:now.slice(11,19),MODE:'SSB'};
  for(const [key,value] of Object.entries(values)){const field=form.elements.namedItem(key);if(field)field.value=value;}
  $('#qso-dialog-title').textContent=q?"Edit contact":"New contact";
  $('#qso-dialog').showModal();form.elements.CALL.focus();
}
$('#qso-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;
  const data=Object.fromEntries(new FormData(form));
  data.QSO_DATE=data.date.replaceAll('-','');data.TIME_ON=data.time.replaceAll(':','').padEnd(6,'0');
  delete data.date;delete data.time;
  const q={...(editingQso||{}),...data};
  if(editingQso)q._expected=editingQso;
  if(editingQso&&data.MODE!==mode(editingQso)) delete q.SUBMODE;
  if(!editingQso){q.STATION_CALLSIGN=state.settings.call;q.MY_GRIDSQUARE=state.settings.grid;}
  const submit=form.querySelector('[type="submit"]')||form.querySelector('.primary');submit.disabled=true;
  try{await api('qso',q);$('#qso-dialog').close();await refreshState();toast("Contact saved. 73!");}
  catch(error){form.querySelector('.form-error').textContent=error.message;}
  finally{submit.disabled=false;}
});

function gridPoint(value){
  const g=(value||'').toUpperCase();if(!/^[A-R]{2}\d{2}([A-X]{2}(\d{2})?)?$/.test(g))return null;
  let lon=(g.charCodeAt(0)-65)*20-180+Number(g[2])*2,lat=(g.charCodeAt(1)-65)*10-90+Number(g[3]);
  let w=2,h=1;
  if(g.length>=6){w=2/24;h=1/24;lon+=(g.charCodeAt(4)-65)*w;lat+=(g.charCodeAt(5)-65)*h;}
  if(g.length===8){w/=10;h/=10;lon+=Number(g[6])*w;lat+=Number(g[7])*h;}
  return {lat:lat+h/2,lon:lon+w/2};
}
function distance(a,b){
  const rad=Math.PI/180;
  const h=Math.sin((b.lat-a.lat)*rad/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin((b.lon-a.lon)*rad/2)**2;
  return 6371.0088*2*Math.asin(Math.sqrt(Math.min(1,Math.max(0,h))));
}
function renderRepeaters(){
  const search=$('#repeater-search').value.toUpperCase();
  const own=gridPoint(state.settings.grid);
  const rows=state.repeaters.map(r=>({...r,point:gridPoint(r.grid)})).map(r=>({...r,km:own&&r.point?distance(own,r.point):null})).filter(r=>[r.name,r.call,r.grid,r.notes].join(' ').toUpperCase().includes(search)).sort((a,b)=>(a.km??Infinity)-(b.km??Infinity)||a.name.localeCompare(b.name));
  $('#repeater-list').innerHTML=rows.length?rows.map(r=>`<article class="card"><div class="card-top"><h2>${esc(r.name)}</h2><span class="tag">${r.km!==null?Math.round(r.km)+' km':esc(r.grid||"No grid locator")}</span></div><p class="small muted">${esc(r.call||"Callsign not provided")}</p><div class="repeater-frequency">${Number(r.rx).toFixed(4)} <small>MHz RX</small></div><div class="repeater-meta"><div><span>Radio TX</span>${(Number(r.rx)+Number(r.shift)).toFixed(4)} MHz</div><div><span>Shift</span>${Number(r.shift)>0?'+':''}${esc(r.shift)} MHz</div><div><span>Access / tone</span>${esc(r.tone||"Not provided")}</div><div><span>Last confirmed</span>${esc(r.checked||"Not provided")}</div></div>${r.notes?`<p class="small muted">${esc(r.notes)}</p>`:''}<div class="actions">${r.point?`<button class="mini-button" data-map="${esc(r.id)}">Show on map</button>`:''}<button class="mini-button" data-edit-repeater="${esc(r.id)}">Edit</button><button class="mini-button danger" data-delete-repeater="${esc(r.id)}">Delete</button></div></article>`).join(''):empty(state.repeaters.length?"No matches":"Collect the repeaters you use","Press Add repeater to save the frequency, shift, access tone and grid locator.");
}
function openRepeater(row=null){
  const form=$('#repeater-form');form.reset();form.querySelector('.form-error').textContent='';
  if(row)for(const [key,value] of Object.entries(row)){const field=form.elements.namedItem(key);if(field)field.value=value;}
  $('#repeater-dialog').showModal();form.elements.name.focus();
}
$('#repeater-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;
  const button=form.querySelector('.primary');button.disabled=true;
  try{await api('repeater',Object.fromEntries(new FormData(form)));$('#repeater-dialog').close();await refreshState();toast("Repeater saved.");}
  catch(error){form.querySelector('.form-error').textContent=error.message;}finally{button.disabled=false;}
});
function showMap(id){
  const row=state.repeaters.find(r=>r.id===id);const p=gridPoint(row.grid);if(!p)return;
  const bbox=[Math.max(-180,p.lon-1),Math.max(-90,p.lat-.4),Math.min(180,p.lon+1),Math.min(90,p.lat+.4)].join(',');
  $('#repeater-map').src='https://www.openstreetmap.org/export/embed.html?bbox='+encodeURIComponent(bbox)+'&layer=mapnik&marker='+encodeURIComponent(p.lat+','+p.lon);
  $('#map-link').href=`https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=10/${p.lat}/${p.lon}`;
  $('#map-title').textContent=row.name+' · '+row.grid;$('#map-card').hidden=false;$('#map-card').scrollIntoView({block:'center'});
}

function renderBands(){
  const own=gridPoint(state.settings.grid);
  let text="Enter your grid locator under My station for a suggestion based on the Sun's elevation at your location.";
  let daylight=null;
  if(own){
    const now=new Date();const day=(now-Date.UTC(now.getUTCFullYear(),0,0))/86400000;
    const rad=Math.PI/180;
    const declination=23.44*Math.sin(2*Math.PI*(day-81)/365.25)*rad;
    const solarHour=(now.getUTCHours()+now.getUTCMinutes()/60+own.lon/15+24)%24;
    const altitude=Math.asin(Math.sin(own.lat*rad)*Math.sin(declination)+Math.cos(own.lat*rad)*Math.cos(declination)*Math.cos((solarHour-12)*15*rad))/rad;
    daylight=altitude>0;
    text=daylight?"The Sun is approximately above your horizon. Try listening on 20 m, and check 17–10 m for activity.":"The Sun is approximately below your horizon. Try listening on 40 and 80 m; 20 m may also be interesting.";
    text+=" This is a rough estimate based on your grid locator and the time.";
  }
  const fresh=live.dx.spots.filter(s=>Date.now()-new Date(s.received)<1800000);
  const counts={};fresh.forEach(s=>counts[s.band]=(counts[s.band]||0)+1);
  $('#dx-count').textContent=fresh.length;
  if(fresh.length){const best=Object.entries(counts).filter(([k])=>k).sort((a,b)=>b[1]-a[1])[0];if(best)text+=` Most received spots in the last 30 minutes: ${best[0]}. Spots are other people's observations.`;}
  $('#band-advice').textContent=text;
  $('#band-grid').innerHTML=['80m','40m','30m','20m','17m','15m','12m','10m'].map(b=>`<div class="band-tile"><strong>${b.replace('m',' m')}</strong><span>${counts[b]?counts[b]+" recent spots":"No recent spots"}</span></div>`).join('');
}
async function weather(){
  const button=$('#weather-refresh');button.disabled=true;button.textContent="Retrieving …";
  try{
    const result=await api('weather');
    for(const [key,prefix] of [['kp','kp'],['flux','flux']]){
      const data=result[key];
      $('#'+prefix+'-value').textContent=data?data.value.toLocaleString("en-GB",{maximumFractionDigits:2}):'—';
      const age=data?Date.now()-new Date(data.time.replace(' ','T')+'Z'):0;
      const old=data&&age>(key==='kp'?6:48)*3600000;
      $('#'+prefix+'-date').textContent=data?(old?"Older measurement · ":"Measured ")+stamp(data.time):"Could not retrieve data";
    }
    $('#weather-status').textContent=result.errors.length?"Some solar data could not be retrieved. Check your internet connection and try again.":"Source: NOAA SWPC · Retrieved "+stamp(result.fetched)+". Results are cached for 10 minutes.";
  }finally{button.disabled=false;button.textContent="↻ Get solar data";}
}
const watchPrefixes=()=>String(state.settings.watch||'').split(/[\s,;]+/).filter(Boolean);
const isWatched=spot=>watchPrefixes().some(p=>spot.call.startsWith(p));
function renderDX(){
  $('#dx-status').textContent=live.dx.message||"Not connected";
  $('#dx-connect').disabled=live.dx.running;$('#dx-stop').disabled=!live.dx.running;
  const search=$('#dx-search').value.toUpperCase(),band=$('#dx-band').value;
  const watch=watchPrefixes();
  $('#watch-description').textContent=watch.length?"Watching: "+watch.join(', ')+" · Alerts appear in the app.":"No prefixes are being watched. Add them under My station.";
  const spots=live.dx.spots.filter(s=>(!band||s.band===band)&&(!$('#dx-watch-only').checked||isWatched(s))&&[s.call,s.spotter,s.comment].join(' ').toUpperCase().includes(search));
  $('#dx-spots').innerHTML=spots.length?table(["UTC · RECEIVED",'DX','MHz','SPOTTER',"MESSAGE"],spots.map(s=>`<tr class="${isWatched(s)?'row-watch':''}"><td>${esc(stamp(s.received))}</td><td class="call">${esc(s.call)} ${isWatched(s)?'★':''}</td><td class="mono">${s.freq.toFixed(4)}</td><td>${esc(s.spotter)}</td><td class="wrap">${esc(s.comment)}</td></tr>`)):empty("No DX spots to display",live.dx.running?"Waiting for cluster spots, or no spots match the filter.":"Save your cluster under My station and press Connect.");
}
function decodedCall(message){
  const parts=message.replace(/[<>]/g,'').split(/\s+/);
  const candidates=parts.filter(p=>/^[A-Z0-9/]{3,32}$/.test(p)&&/[A-Z]/.test(p)&&/\d/.test(p)&&!/^R?\d+$/.test(p)&&!/^RR73$/.test(p)&&!/^R?[+-]\d+$/.test(p)&&!/^\d{3}$/.test(p)&&!gridPoint(p));
  return candidates.at(-1)||'';
}
function renderFT8(){
  const u=live.udp;
  const logOnly=u.source==='MSHV (ADIF)'||u.source==='ADIF UDP';
  const stale=!logOnly&&u.last_seen&&Date.now()-new Date(u.last_seen)>45000;
  $('#udp-status').textContent=stale&&u.running?"No messages in the last 45 seconds":displayProgramName(u.message)||"Not started";
  $('#stat-ft8').textContent=!u.running?"Not started":!u.last_seen?"Waiting":logOnly?"QSO log only":stale?"No recent data":"Receiving";
  $('#stat-ft8-sub').textContent=u.logged?u.logged+" contacts saved in this session":"Connection under HamNavigator Digital";
  $('#udp-start').disabled=u.running;$('#udp-stop').disabled=!u.running;
  $('#ft8-last').textContent=u.last_seen?"Last received "+stamp(u.last_seen):"No data received";
  $('#ft8-clients').innerHTML=Object.values(u.clients).map(c=>`<article class="card stat"><span>${esc(displayProgramName(c.client))} · ${esc(c.call||"Unknown station")}</span><strong>${c.freq.toFixed(3)}</strong><small>MHz · ${esc(c.mode)} · ${stale?"Last known status":c.transmitting?"Transmitting":c.decoding?"Decoder":"Receive"} · ${esc(c.grid)}</small></article>`).join('');
  const search=$('#ft8-search').value.toUpperCase();const calls=new Set(state.qsos.map(q=>q.CALL));
  const rows=u.decodes.filter(d=>d.message.toUpperCase().includes(search)&&(!$('#ft8-cq').checked||/^CQ\b/.test(d.message)));
  $('#ft8-decodes').innerHTML=rows.length?table(['UTC','SNR','Δt','AUDIO',"MESSAGE","LOG"],rows.map(d=>{
    const call=decodedCall(d.message);const logged=call&&calls.has(call);const ms=d.milliseconds;
    const t=[Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(v=>String(v).padStart(2,'0')).join(':');
    return `<tr><td class="mono">${t}</td><td>${d.snr} dB</td><td>${d.dt.toFixed(1)} s</td><td>${d.df} Hz</td><td class="wrap mono">${esc(d.message)} ${d.off_air?"<span class=\"chip warn\">Audio file</span>":''}${d.low_confidence?"<span class=\"chip warn\">Uncertain</span>":''}</td><td>${call?`<span class="chip ${logged?'':'green'}">${logged?"Logged":"New"}</span>`:'—'}</td></tr>`;
  })):empty("No decodes to display",logOnly?"You are using the ADIF output. Enable Enable Decoded Text under the regular UDP Broadcast Settings for received messages.":u.running?"Waiting for HamNavigator or messages matching the filter.":"Start receiving and set the UDP address in HamNavigator.");
}
async function poll(){
  if(polling)return;polling=true;
  try{
    live=await api('live');liveError=false;
    if(live.udp.logged!==lastLogged||live.log_revision!==lastLogRevision){await refreshState();lastLogged=live.udp.logged;lastLogRevision=live.log_revision;}
    renderFT8();renderDX();renderBands();
    const alerts=live.dx.spots.filter(s=>!alertedSpots.has(s.id)&&isWatched(s)&&Date.now()-new Date(s.received)<60000);
    live.dx.spots.forEach(s=>alertedSpots.add(s.id));
    if(alertedSpots.size>2000)alertedSpots=new Set(live.dx.spots.map(s=>s.id));
    if(alerts.length&&moduleEnabled('hf'))toast(`DX alert: ${alerts.slice(0,3).map(s=>s.call+" on "+s.freq.toFixed(3)+' MHz').join(' · ')}`);
  }catch(error){
    $('#stat-ft8').textContent="Disconnected";
    if(!liveError)toast("Lost contact with the app. Start HamNavigator MY SHACK from the desktop again.",true);
    liveError=true;
  }finally{polling=false;}
}

$('#settings-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));
  await api('settings',data);await refreshState(true);toast("Station settings saved.");
}));
$('#notes-save').addEventListener('click',action(async()=>{
  await api('settings',{radio_notes:$('#radio-notes').value});state.settings.radio_notes=$('#radio-notes').value;toast("Station notes saved.");
}));
$('#path-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=await api('path',Object.fromEntries(new FormData(event.currentTarget)));
  $('#path-result').innerHTML=`<strong>${data.km.toLocaleString("en-GB")} km</strong> &nbsp; · &nbsp; <strong>${data.bearing===null?"Same point":data.bearing.toLocaleString("en-GB")+'°'}</strong><br>From ${data.from.lat.toFixed(4)}°, ${data.from.lon.toFixed(4)}° to ${data.to.lat.toFixed(4)}°, ${data.to.lon.toFixed(4)}°.`;
}));
$('#antenna-form').addEventListener('submit',action(event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));
  const f=Number(data.frequency),factor=Number(data.factor);if(!Number.isFinite(f)||f<=0||factor<=0||factor>1)throw new Error("Check the frequency and shortening factor.");
  const wavelength=299.792458/f,half=wavelength*factor/2,quarter=half/2;
  $('#antenna-result').innerHTML=`Half-wave dipole, total: <strong>${half.toLocaleString("en-GB",{maximumFractionDigits:3})} m</strong><br>Each dipole leg / quarter-wave vertical: <strong>${quarter.toLocaleString("en-GB",{maximumFractionDigits:3})} m</strong><br>Free-space wavelength: ${wavelength.toLocaleString("en-GB",{maximumFractionDigits:3})} m.`;
}));
$('#grid-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=await api('grid',Object.fromEntries(new FormData(event.currentTarget)));
  $('#grid-result').innerHTML=`Maidenhead grid locator: <strong>${esc(data.grid)}</strong>`;
}));
const alphabet={A:'Alfa',B:'Bravo',C:'Charlie',D:'Delta',E:'Echo',F:'Foxtrot',G:'Golf',H:'Hotel',I:'India',J:'Juliett',K:'Kilo',L:'Lima',M:'Mike',N:'November',O:'Oscar',P:'Papa',Q:'Quebec',R:'Romeo',S:'Sierra',T:'Tango',U:'Uniform',V:'Victor',W:'Whiskey',X:'X-ray',Y:'Yankee',Z:'Zulu','0':'Zero','1':'One','2':'Two','3':'Three','4':'Four','5':'Five','6':'Six','7':'Seven','8':'Eight','9':'Nine','/':'Stroke'};
function renderPhonetic(){$('#phonetic-result').textContent=[...$('#phonetic-input').value.toUpperCase()].map(c=>alphabet[c]||c).join(' · ')||'Alfa · Bravo · Charlie …';}

document.addEventListener('click',action(async event=>{
  const button=event.target.closest('button');if(!button)return;
  const d=button.dataset;
  if(d.page)showPage(d.page);
  if(d.close)$('#'+d.close).close();
  if(d.editQso)openQso(state.qsos.find(q=>q.id===d.editQso));
  if(d.deleteQso){const q=state.qsos.find(q=>q.id===d.deleteQso);if(confirm(`Delete the contact with ${q.CALL} from ${qsoDate(q)}?`)){await api('qso/delete',{id:q.id,_expected:q});await refreshState();toast("Contact deleted.");}}
  if(d.editRepeater)openRepeater(state.repeaters.find(r=>r.id===d.editRepeater));
  if(d.deleteRepeater){const r=state.repeaters.find(r=>r.id===d.deleteRepeater);if(confirm(`Delete the favourite repeater ${r.name}?`)){await api('repeater/delete',{id:r.id});await refreshState();$('#map-card').hidden=true;toast("Favourite deleted.");}}
  if(d.map)showMap(d.map);
  if(d.logPage!==undefined){logPage=Number(d.logPage);renderLog();}
}));
$('#qso-add').onclick=()=>openQso();
$('#quick-add').onclick=()=>{openQso(null,$('#quick-call').value.trim().toUpperCase());$('#quick-call').value='';};
$('#quick-call').addEventListener('keydown',event=>{if(event.key==='Enter')$('#quick-add').click();});
$('#repeater-add').onclick=()=>openRepeater();
$('#widget-button').onclick=action(async()=>{await api('widget',{});toast("UTC widget opened.");});
$('#weather-refresh').onclick=action(weather);
$('#mshv-open').onclick=action(async()=>{await api('desktop/open',{panel:'digital'});await poll();toast("HamNavigator is opening in the shack. MY SHACK is listening for data.");});
$('#udp-start').onclick=action(async()=>{await api('udp',{start:true});await poll();toast("Reception started. Waiting for HamNavigator.");});
$('#udp-stop').onclick=action(async()=>{await api('udp',{start:false});await poll();});
$('#dx-connect').onclick=action(async()=>{await api('dx',{start:true});await poll();});
$('#dx-stop').onclick=action(async()=>{await api('dx',{start:false});await poll();});
for(const id of ['log-search','log-mode'])$('#'+id).addEventListener('input',()=>{logPage=0;renderLog();});
for(const id of ['dx-search','dx-band','dx-watch-only'])$('#'+id).addEventListener('input',renderDX);
for(const id of ['ft8-search','ft8-cq'])$('#'+id).addEventListener('input',renderFT8);
$('#repeater-search').addEventListener('input',renderRepeaters);
$('#phonetic-input').addEventListener('input',renderPhonetic);
$('#adif-import').onclick=()=>$('#adif-file').click();
$('#adif-file').onchange=action(async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    if(file.size>15_000_000)throw new Error("The ADIF file is too large (maximum 15 MB).");
    const result=await api('import',{text:await file.text()});
    const box=$('#import-result');box.hidden=false;box.textContent=`Import complete: ${result.added} added, ${result.duplicates} duplicates skipped, ${result.invalid} invalid. ${result.errors.join(' ')}`;
    await refreshState();toast(result.added+" contacts imported.");
  }finally{event.target.value='';}
});
$('#restore-button').onclick=()=>$('#restore-file').click();
$('#restore-file').onchange=action(async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    if(file.size>15_000_000)throw new Error("The backup is too large (maximum 15 MB).");
    const data=JSON.parse(await file.text());
    const preview=await api('restore-preview',{data});
    if(!confirm(`Backup: ${preview.date}\n${preview.contacts} contacts in the backup. ${preview.add} missing contacts will be added.
All ${preview.current} current contacts, favourites and settings will be kept. A local backup is made first.

Restore?`))return;
    const result=await api('restore',{data,confirm:true});await refreshState();toast(`${result.added} contacts added and ${result.repeaters} repeater favourites retrieved.`);
  }finally{event.target.value='';}
});
$('#module-picker').addEventListener('toggle',()=>{if($('#module-picker').open)syncModuleChoices();});
$('#modules-all').onclick=()=>{$$('#module-options input').forEach(input=>input.checked=true);};
$('#modules-clock').onclick=()=>{$$('#module-options input').forEach(input=>input.checked=input.value==='utc');};
$('#modules-choose').onclick=()=>{$('#module-picker').open=true;$('#module-picker>summary').focus();};
$('#module-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const selected=$$('#module-options input:checked').map(input=>input.value);
  const controls=$$('#module-form input, #module-form button');
  controls.forEach(control=>control.disabled=true);
  try{
    const result=await api('modules',{modules:selected});
    state.settings.modules=result.modules;
    renderModules();
    $('#module-picker').open=false;
    $('#module-picker>summary').focus();
    toast("Module selection saved.");
  }catch(error){$('#module-form .form-error').textContent=error.message;}
  finally{controls.forEach(control=>control.disabled=false);}
});
document.addEventListener('click',event=>{
  if($('#module-picker').open&&!$('#module-picker').contains(event.target)&&!event.target.closest('#modules-choose'))$('#module-picker').open=false;
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&$('#module-picker').open){$('#module-picker').open=false;$('#module-picker>summary').focus();}
});
window.addEventListener('hashchange',()=>showPage(location.hash.slice(1),false));
document.addEventListener('visibilitychange',()=>{if(!document.hidden){poll();refreshState().catch(()=>{});}});
tick();showPage(location.hash.slice(1)||'home',false);
setInterval(()=>{if(window.hnAuthorized)poll();},3000);

for(const [id,panel] of [['gridtracker-open','hammap'],['station-mshv-open','digital'],['station-open','hamnavigator']]) { $('#'+id).onclick=action(async()=>{await api('desktop/open',{panel});toast("Opening the shack …");}); }

// The handbook is local HTML. Search never sends the query over the network.
(() => {
  const input=$('#manual-search'), category=$('#manual-category'), toc=$('#manual-toc');
  const entries=$$('#manual-chapters>.manual-chapter').map(chapter=>({
    chapter, original:chapter.innerHTML, title:chapter.querySelector('summary').textContent,
    text:(chapter.textContent+' '+chapter.dataset.category).toLocaleLowerCase("en-GB")
  }));
  for(const entry of entries){
    const button=document.createElement('button');
    button.type='button';button.className='manual-toc-link';button.textContent=entry.title;
    button.setAttribute('aria-controls',entry.chapter.id);
    button.onclick=()=>{
      entry.chapter.open=true;
      entry.chapter.scrollIntoView({block:'start',behavior:'instant'});
      entry.chapter.querySelector('summary').focus({preventScroll:true});
    };
    toc.append(button);entry.button=button;
  }
  function highlight(root, terms){
    if(!terms.length)return;
    const pattern=new RegExp(terms.map(t=>t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).sort((a,b)=>b.length-a.length).join('|'),'giu');
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT), nodes=[];
    while(walker.nextNode())nodes.push(walker.currentNode);
    for(const node of nodes){
      const text=node.nodeValue;let cursor=0,matched=false;const fragment=document.createDocumentFragment();
      for(const match of text.matchAll(pattern)){
        matched=true;fragment.append(document.createTextNode(text.slice(cursor,match.index)));
        const mark=document.createElement('mark');mark.textContent=match[0];fragment.append(mark);
        cursor=match.index+match[0].length;
      }
      if(matched){fragment.append(document.createTextNode(text.slice(cursor)));node.replaceWith(fragment);}
    }
  }
  let debounce;
  function search(){
    clearTimeout(debounce);
    const terms=[...new Set(input.value.trim().toLocaleLowerCase("en-GB").split(/\s+/).filter(Boolean))];
    let visible=0;
    for(const entry of entries){
      const {chapter}=entry;
      const matches=(!category.value||chapter.dataset.category===category.value)&&terms.every(term=>entry.text.includes(term));
      chapter.innerHTML=entry.original;chapter.hidden=!matches;entry.button.hidden=!matches;
      chapter.open=matches&&terms.length>0;
      if(matches){visible++;highlight(chapter,terms);}
    }
    $('#manual-count').textContent=`${visible} of ${entries.length} chapters`+(terms.length?" match your search":'');
    $('#manual-empty').hidden=visible!==0;
    $('#manual-expand').disabled=visible===0;
    $('#manual-collapse').disabled=visible===0;
  }
  input.addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(search,120);});
  category.addEventListener('change',search);
  $('#manual-reset').onclick=()=>{input.value='';category.value='';search();input.focus();};
  $('#manual-expand').onclick=()=>entries.forEach(e=>{if(!e.chapter.hidden)e.chapter.open=true;});
  $('#manual-collapse').onclick=()=>entries.forEach(e=>e.chapter.open=false);
  search();
})();
