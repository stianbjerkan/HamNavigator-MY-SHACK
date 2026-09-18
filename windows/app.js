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
const pageNames = {home:'Oversikt',hf:'HF & DX',vhf:'VHF / UHF',ft8:'HamNavigator Digital',gridtracker:'HamNavigator Map',listener:'Kallesignallytter',log:'Loggbok',tools:'Verktøy',help:'Radiohjelp',manual:'Bruksanvisning',settings:'Min stasjon'};
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
  if (!response.ok) throw new Error(result.error || 'Operasjonen mislyktes.');
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
const utcTime = date => new Intl.DateTimeFormat('nb-NO',{timeZone:'UTC',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(date);
function tick() {
  const now = new Date();
  $('#utc-clock').textContent=utcTime(now);
  $('#utc-clock').dateTime=now.toISOString();
  $('#utc-date').textContent=new Intl.DateTimeFormat('nb-NO',{timeZone:'UTC',weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(now);
  $('#local-clock').textContent=new Intl.DateTimeFormat('nb-NO',{hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(now);
  $('#footer-time').textContent=utcTime(now)+' UTC';
  setTimeout(tick,1000-Date.now()%1000);
}
function stamp(value) {
  if (!value) return '—';
  const normalized=/Z$|[+-]\d\d:\d\d$/.test(value)?value:value.replace(' ','T')+'Z';
  const date=new Date(normalized);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('nb-NO',{timeZone:'UTC',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date)+' UTC';
}
const mode = q => q.SUBMODE || q.MODE || '';
const sortedQsos = () => [...state.qsos].sort((a,b)=>(b.QSO_DATE+b.TIME_ON).localeCompare(a.QSO_DATE+a.TIME_ON));
const empty = (title, text) => `<div class="empty"><strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
function qsoDate(q) {return `${q.QSO_DATE.slice(6,8)}.${q.QSO_DATE.slice(4,6)}.${q.QSO_DATE.slice(0,4)}`;}
function qsoTime(q) {return (q.TIME_ON||'').padEnd(6,'0').replace(/(..)(..)(..)/,'$1:$2:$3');}
function qsoRows(qsos,edit=false) {
  return qsos.map(q=>`<tr><td class="call">${esc(q.CALL)}</td><td>${esc(qsoDate(q))}<br><small class="muted">${esc(qsoTime(q))}</small></td><td class="mono">${esc(q.FREQ||q.BAND||'—')}</td><td><span class="chip">${esc(mode(q))}</span></td><td>${esc(q.GRIDSQUARE||'—')}</td>${edit?`<td>${esc(q.RST_SENT||'—')} / ${esc(q.RST_RCVD||'—')}</td><td><button class="mini-button" data-edit-qso="${esc(q.id)}">Endre</button><button class="mini-button danger" data-delete-qso="${esc(q.id)}">Slett</button></td>`:''}</tr>`);
}
function renderLog() {
  const search=$('#log-search').value.trim().toUpperCase();
  const filter=$('#log-mode').value;
  const rows=sortedQsos().filter(q=>(!filter||mode(q)===filter)&&[q.CALL,q.GRIDSQUARE,q.NAME,q.COMMENT,q.BAND,q.FREQ].join(' ').toUpperCase().includes(search));
  const pages=Math.max(1,Math.ceil(rows.length/100));
  logPage=Math.max(0,Math.min(logPage,pages-1));
  $('#log-count').textContent=`${rows.length} av ${state.qsos.length} kontakter`;
  $('#qso-table').innerHTML=rows.length?table(['KALLESIGNAL','DATO / UTC','MHz / BÅND','MODUS','LOKATOR','S / M',''],qsoRows(rows.slice(logPage*100,(logPage+1)*100),true))+(pages>1?`<div class="actions pagination"><button class="secondary" data-log-page="${logPage-1}" ${logPage===0?'disabled':''}>← Forrige</button><span class="small muted">Side ${logPage+1} av ${pages}</span><button class="secondary" data-log-page="${logPage+1}" ${logPage===pages-1?'disabled':''}>Neste →</button></div>`:''):empty(state.qsos.length?'Ingen treff':'Din første kontakt starter her',state.qsos.length?'Prøv et annet søk eller modus.':'Legg til en kontakt, importer ADIF eller koble til HamNavigator.');
}
function renderState(fillSettings=false) {
  const s=state.settings;
  $('#station-label').textContent=[s.call,s.grid].filter(Boolean).join(' / ')||'Stasjon ikke satt opp';
  $('#setup-banner').hidden=!!(s.call&&s.grid);
  $('#nav-count').textContent=state.qsos.length;
  $('#stat-total').textContent=state.qsos.length;
  const today=new Date().toISOString().slice(0,10).replaceAll('-','');
  $('#stat-today').textContent=state.qsos.filter(q=>q.QSO_DATE===today).length+' i dag (UTC)';
  $('#stat-calls').textContent=new Set(state.qsos.map(q=>q.CALL)).size;
  const recent=sortedQsos().slice(0,5);
  $('#recent-qsos').innerHTML=recent.length?table(['KALLESIGNAL','DATO / UTC','MHz / BÅND','MODUS','LOKATOR'],qsoRows(recent)):empty('Ingen kontakter ennå','Loggfør din første QSO, eller importer en eksisterende ADIF-logg.');
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
  $('#qso-dialog-title').textContent=q?'Endre kontakt':'Ny kontakt';
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
  try{await api('qso',q);$('#qso-dialog').close();await refreshState();toast('Kontakten er lagret. 73!');}
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
  $('#repeater-list').innerHTML=rows.length?rows.map(r=>`<article class="card"><div class="card-top"><h2>${esc(r.name)}</h2><span class="tag">${r.km!==null?Math.round(r.km)+' km':esc(r.grid||'Ingen lokator')}</span></div><p class="small muted">${esc(r.call||'Kallesignal ikke oppgitt')}</p><div class="repeater-frequency">${Number(r.rx).toFixed(4)} <small>MHz RX</small></div><div class="repeater-meta"><div><span>Radioens TX</span>${(Number(r.rx)+Number(r.shift)).toFixed(4)} MHz</div><div><span>Skift</span>${Number(r.shift)>0?'+':''}${esc(r.shift)} MHz</div><div><span>Tilgang / tone</span>${esc(r.tone||'Ikke oppgitt')}</div><div><span>Sist bekreftet</span>${esc(r.checked||'Ikke oppgitt')}</div></div>${r.notes?`<p class="small muted">${esc(r.notes)}</p>`:''}<div class="actions">${r.point?`<button class="mini-button" data-map="${esc(r.id)}">Vis på kart</button>`:''}<button class="mini-button" data-edit-repeater="${esc(r.id)}">Endre</button><button class="mini-button danger" data-delete-repeater="${esc(r.id)}">Slett</button></div></article>`).join(''):empty(state.repeaters.length?'Ingen treff':'Samle repeaterne du bruker','Trykk «Legg til repeater» for å lagre frekvens, skift, tilgangstone og lokator.');
}
function openRepeater(row=null){
  const form=$('#repeater-form');form.reset();form.querySelector('.form-error').textContent='';
  if(row)for(const [key,value] of Object.entries(row)){const field=form.elements.namedItem(key);if(field)field.value=value;}
  $('#repeater-dialog').showModal();form.elements.name.focus();
}
$('#repeater-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;
  const button=form.querySelector('.primary');button.disabled=true;
  try{await api('repeater',Object.fromEntries(new FormData(form)));$('#repeater-dialog').close();await refreshState();toast('Repeateren er lagret.');}
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
  let text='Legg inn egen lokator under Min stasjon for et forslag basert på solhøyden hos deg.';
  let daylight=null;
  if(own){
    const now=new Date();const day=(now-Date.UTC(now.getUTCFullYear(),0,0))/86400000;
    const rad=Math.PI/180;
    const declination=23.44*Math.sin(2*Math.PI*(day-81)/365.25)*rad;
    const solarHour=(now.getUTCHours()+now.getUTCMinutes()/60+own.lon/15+24)%24;
    const altitude=Math.asin(Math.sin(own.lat*rad)*Math.sin(declination)+Math.cos(own.lat*rad)*Math.cos(declination)*Math.cos((solarHour-12)*15*rad))/rad;
    daylight=altitude>0;
    text=daylight?'Solen er omtrent over horisonten hos deg. Prøv å lytte på 20 m, og sjekk 17–10 m for aktivitet.':'Solen er omtrent under horisonten hos deg. Prøv å lytte på 40 og 80 m; 20 m kan også være interessant.';
    text+=' Dette er en grov vurdering fra lokator og tidspunkt.';
  }
  const fresh=live.dx.spots.filter(s=>Date.now()-new Date(s.received)<1800000);
  const counts={};fresh.forEach(s=>counts[s.band]=(counts[s.band]||0)+1);
  $('#dx-count').textContent=fresh.length;
  if(fresh.length){const best=Object.entries(counts).filter(([k])=>k).sort((a,b)=>b[1]-a[1])[0];if(best)text+=` Flest mottatte spots siste 30 minutter: ${best[0]}. Spottene er andres observasjoner.`;}
  $('#band-advice').textContent=text;
  $('#band-grid').innerHTML=['80m','40m','30m','20m','17m','15m','12m','10m'].map(b=>`<div class="band-tile"><strong>${b.replace('m',' m')}</strong><span>${counts[b]?counts[b]+' ferske spots':'Ingen ferske spots'}</span></div>`).join('');
}
async function weather(){
  const button=$('#weather-refresh');button.disabled=true;button.textContent='Henter …';
  try{
    const result=await api('weather');
    for(const [key,prefix] of [['kp','kp'],['flux','flux']]){
      const data=result[key];
      $('#'+prefix+'-value').textContent=data?data.value.toLocaleString('nb-NO',{maximumFractionDigits:2}):'—';
      const age=data?Date.now()-new Date(data.time.replace(' ','T')+'Z'):0;
      const old=data&&age>(key==='kp'?6:48)*3600000;
      $('#'+prefix+'-date').textContent=data?(old?'Eldre måling · ':'Målt ')+stamp(data.time):'Kunne ikke hente data';
    }
    $('#weather-status').textContent=result.errors.length?'Noen soldata kunne ikke hentes. Kontroller internett og prøv igjen.':'Kilde: NOAA SWPC · Hentet '+stamp(result.fetched)+'. Resultatet mellomlagres i 10 minutter.';
  }finally{button.disabled=false;button.textContent='↻ Hent soldata';}
}
const watchPrefixes=()=>String(state.settings.watch||'').split(/[\s,;]+/).filter(Boolean);
const isWatched=spot=>watchPrefixes().some(p=>spot.call.startsWith(p));
function renderDX(){
  $('#dx-status').textContent=live.dx.message||'Ikke tilkoblet';
  $('#dx-connect').disabled=live.dx.running;$('#dx-stop').disabled=!live.dx.running;
  const search=$('#dx-search').value.toUpperCase(),band=$('#dx-band').value;
  const watch=watchPrefixes();
  $('#watch-description').textContent=watch.length?'Overvåker: '+watch.join(', ')+' · Varsler vises i appen.':'Ingen prefikser overvåkes. Legg dem til under Min stasjon.';
  const spots=live.dx.spots.filter(s=>(!band||s.band===band)&&(!$('#dx-watch-only').checked||isWatched(s))&&[s.call,s.spotter,s.comment].join(' ').toUpperCase().includes(search));
  $('#dx-spots').innerHTML=spots.length?table(['UTC · MOTTATT','DX','MHz','SPOTTER','MELDING'],spots.map(s=>`<tr class="${isWatched(s)?'row-watch':''}"><td>${esc(stamp(s.received))}</td><td class="call">${esc(s.call)} ${isWatched(s)?'★':''}</td><td class="mono">${s.freq.toFixed(4)}</td><td>${esc(s.spotter)}</td><td class="wrap">${esc(s.comment)}</td></tr>`)):empty('Ingen DX-spots å vise',live.dx.running?'Venter på spots fra cluster, eller ingen spots passer filteret.':'Lagre din cluster under Min stasjon, og trykk Koble til.');
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
  $('#udp-status').textContent=stale&&u.running?'Ingen meldinger siste 45 sekunder':displayProgramName(u.message)||'Ikke startet';
  $('#stat-ft8').textContent=!u.running?'Ikke startet':!u.last_seen?'Venter':logOnly?'Kun QSO-logg':stale?'Ingen ferske data':'Mottar';
  $('#stat-ft8-sub').textContent=u.logged?u.logged+' kontakter lagret i denne økten':'Tilkobling under HamNavigator Digital';
  $('#udp-start').disabled=u.running;$('#udp-stop').disabled=!u.running;
  $('#ft8-last').textContent=u.last_seen?'Sist mottatt '+stamp(u.last_seen):'Ingen data mottatt';
  $('#ft8-clients').innerHTML=Object.values(u.clients).map(c=>`<article class="card stat"><span>${esc(displayProgramName(c.client))} · ${esc(c.call||'Ukjent stasjon')}</span><strong>${c.freq.toFixed(3)}</strong><small>MHz · ${esc(c.mode)} · ${stale?'Siste kjente status':c.transmitting?'Sender':c.decoding?'Dekoder':'Mottak'} · ${esc(c.grid)}</small></article>`).join('');
  const search=$('#ft8-search').value.toUpperCase();const calls=new Set(state.qsos.map(q=>q.CALL));
  const rows=u.decodes.filter(d=>d.message.toUpperCase().includes(search)&&(!$('#ft8-cq').checked||/^CQ\b/.test(d.message)));
  $('#ft8-decodes').innerHTML=rows.length?table(['UTC','SNR','Δt','AUDIO','MELDING','LOGG'],rows.map(d=>{
    const call=decodedCall(d.message);const logged=call&&calls.has(call);const ms=d.milliseconds;
    const t=[Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(v=>String(v).padStart(2,'0')).join(':');
    return `<tr><td class="mono">${t}</td><td>${d.snr} dB</td><td>${d.dt.toFixed(1)} s</td><td>${d.df} Hz</td><td class="wrap mono">${esc(d.message)} ${d.off_air?'<span class="chip warn">Lydfil</span>':''}${d.low_confidence?'<span class="chip warn">Usikker</span>':''}</td><td>${call?`<span class="chip ${logged?'':'green'}">${logged?'Logget':'Ny'}</span>`:'—'}</td></tr>`;
  })):empty('Ingen dekodinger å vise',logOnly?'Du bruker ADIF-utgangen. Aktiver Enable Decoded Text under vanlig UDP Broadcast Settings for hørte meldinger.':u.running?'Venter på HamNavigator eller meldinger som passer filteret.':'Start mottak og sett UDP-adressen i HamNavigator.');
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
    if(alerts.length&&moduleEnabled('hf'))toast(`DX-varsel: ${alerts.slice(0,3).map(s=>s.call+' på '+s.freq.toFixed(3)+' MHz').join(' · ')}`);
  }catch(error){
    $('#stat-ft8').textContent='Frakoblet';
    if(!liveError)toast('Mistet kontakt med appen. Start HamNavigator MY SHACK fra skrivebordet igjen.',true);
    liveError=true;
  }finally{polling=false;}
}

$('#settings-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));
  await api('settings',data);await refreshState(true);toast('Stasjonsoppsettet er lagret.');
}));
$('#notes-save').addEventListener('click',action(async()=>{
  await api('settings',{radio_notes:$('#radio-notes').value});state.settings.radio_notes=$('#radio-notes').value;toast('Stasjonsnotatene er lagret.');
}));
$('#path-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=await api('path',Object.fromEntries(new FormData(event.currentTarget)));
  $('#path-result').innerHTML=`<strong>${data.km.toLocaleString('nb-NO')} km</strong> &nbsp; · &nbsp; <strong>${data.bearing===null?'Samme punkt':data.bearing.toLocaleString('nb-NO')+'°'}</strong><br>Fra ${data.from.lat.toFixed(4)}°, ${data.from.lon.toFixed(4)}° til ${data.to.lat.toFixed(4)}°, ${data.to.lon.toFixed(4)}°.`;
}));
$('#antenna-form').addEventListener('submit',action(event=>{
  event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));
  const f=Number(data.frequency),factor=Number(data.factor);if(!Number.isFinite(f)||f<=0||factor<=0||factor>1)throw new Error('Sjekk frekvens og forkortningsfaktor.');
  const wavelength=299.792458/f,half=wavelength*factor/2,quarter=half/2;
  $('#antenna-result').innerHTML=`Halvbølgedipol, totalt: <strong>${half.toLocaleString('nb-NO',{maximumFractionDigits:3})} m</strong><br>Hvert dipolbein / kvartbølgevertikal: <strong>${quarter.toLocaleString('nb-NO',{maximumFractionDigits:3})} m</strong><br>Bølgelengde i fritt rom: ${wavelength.toLocaleString('nb-NO',{maximumFractionDigits:3})} m.`;
}));
$('#grid-form').addEventListener('submit',action(async event=>{
  event.preventDefault();const data=await api('grid',Object.fromEntries(new FormData(event.currentTarget)));
  $('#grid-result').innerHTML=`Maidenhead-lokator: <strong>${esc(data.grid)}</strong>`;
}));
const alphabet={A:'Alfa',B:'Bravo',C:'Charlie',D:'Delta',E:'Echo',F:'Foxtrot',G:'Golf',H:'Hotel',I:'India',J:'Juliett',K:'Kilo',L:'Lima',M:'Mike',N:'November',O:'Oscar',P:'Papa',Q:'Quebec',R:'Romeo',S:'Sierra',T:'Tango',U:'Uniform',V:'Victor',W:'Whiskey',X:'X-ray',Y:'Yankee',Z:'Zulu','0':'Zero','1':'One','2':'Two','3':'Three','4':'Four','5':'Five','6':'Six','7':'Seven','8':'Eight','9':'Nine','/':'Stroke'};
function renderPhonetic(){$('#phonetic-result').textContent=[...$('#phonetic-input').value.toUpperCase()].map(c=>alphabet[c]||c).join(' · ')||'Alfa · Bravo · Charlie …';}

document.addEventListener('click',action(async event=>{
  const button=event.target.closest('button');if(!button)return;
  const d=button.dataset;
  if(d.page)showPage(d.page);
  if(d.close)$('#'+d.close).close();
  if(d.editQso)openQso(state.qsos.find(q=>q.id===d.editQso));
  if(d.deleteQso){const q=state.qsos.find(q=>q.id===d.deleteQso);if(confirm(`Slette kontakten med ${q.CALL} fra ${qsoDate(q)}?`)){await api('qso/delete',{id:q.id,_expected:q});await refreshState();toast('Kontakten er slettet.');}}
  if(d.editRepeater)openRepeater(state.repeaters.find(r=>r.id===d.editRepeater));
  if(d.deleteRepeater){const r=state.repeaters.find(r=>r.id===d.deleteRepeater);if(confirm(`Slette repeaterfavoritten ${r.name}?`)){await api('repeater/delete',{id:r.id});await refreshState();$('#map-card').hidden=true;toast('Favoritten er slettet.');}}
  if(d.map)showMap(d.map);
  if(d.logPage!==undefined){logPage=Number(d.logPage);renderLog();}
}));
$('#qso-add').onclick=()=>openQso();
$('#quick-add').onclick=()=>{openQso(null,$('#quick-call').value.trim().toUpperCase());$('#quick-call').value='';};
$('#quick-call').addEventListener('keydown',event=>{if(event.key==='Enter')$('#quick-add').click();});
$('#repeater-add').onclick=()=>openRepeater();
$('#widget-button').onclick=action(async()=>{await api('widget',{});toast('UTC-widgeten er åpnet.');});
$('#weather-refresh').onclick=action(weather);
$('#mshv-open').onclick=action(async()=>{await api('desktop/open',{panel:'digital'});await poll();toast('HamNavigator åpnes i radiorommet. MY SHACK lytter etter data.');});
$('#udp-start').onclick=action(async()=>{await api('udp',{start:true});await poll();toast('Mottak er startet. Venter på HamNavigator.');});
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
    if(file.size>15_000_000)throw new Error('ADIF-filen er for stor (maks 15 MB).');
    const result=await api('import',{text:await file.text()});
    const box=$('#import-result');box.hidden=false;box.textContent=`Import ferdig: ${result.added} lagt til, ${result.duplicates} duplikater hoppet over, ${result.invalid} ugyldige. ${result.errors.join(' ')}`;
    await refreshState();toast(result.added+' kontakter importert.');
  }finally{event.target.value='';}
});
$('#restore-button').onclick=()=>$('#restore-file').click();
$('#restore-file').onchange=action(async event=>{
  const file=event.target.files[0];if(!file)return;
  try{
    if(file.size>15_000_000)throw new Error('Sikkerhetskopien er for stor (maks 15 MB).');
    const data=JSON.parse(await file.text());
    const preview=await api('restore-preview',{data});
    if(!confirm(`Kopi: ${preview.date}\n${preview.contacts} kontakter i kopien. ${preview.add} manglende kontakter legges til.\nAlle ${preview.current} nåværende kontakter, favoritter og innstillinger beholdes. Det tas en lokal kopi først.\n\nGjenopprette?`))return;
    const result=await api('restore',{data,confirm:true});await refreshState();toast(`${result.added} kontakter lagt til og ${result.repeaters} repeaterfavoritter hentet.`);
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
    toast('Modulvalget er lagret.');
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

for(const [id,panel] of [['gridtracker-open','hammap'],['station-mshv-open','digital'],['station-open','hamnavigator']]) { $('#'+id).onclick=action(async()=>{await api('desktop/open',{panel});toast('Åpner radiorommet …');}); }

// The handbook is local HTML. Search never sends the query over the network.
(() => {
  const input=$('#manual-search'), category=$('#manual-category'), toc=$('#manual-toc');
  const entries=$$('#manual-chapters>.manual-chapter').map(chapter=>({
    chapter, original:chapter.innerHTML, title:chapter.querySelector('summary').textContent,
    text:(chapter.textContent+' '+chapter.dataset.category).toLocaleLowerCase('nb-NO')
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
    const terms=[...new Set(input.value.trim().toLocaleLowerCase('nb-NO').split(/\s+/).filter(Boolean))];
    let visible=0;
    for(const entry of entries){
      const {chapter}=entry;
      const matches=(!category.value||chapter.dataset.category===category.value)&&terms.every(term=>entry.text.includes(term));
      chapter.innerHTML=entry.original;chapter.hidden=!matches;entry.button.hidden=!matches;
      chapter.open=matches&&terms.length>0;
      if(matches){visible++;highlight(chapter,terms);}
    }
    $('#manual-count').textContent=`${visible} av ${entries.length} kapitler`+(terms.length?' passer søket':'');
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
