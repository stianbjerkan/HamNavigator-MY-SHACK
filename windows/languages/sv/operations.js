'use strict';
(() => {
  pageNames.operations="Status och säkerhetskopiering";
  const nav=document.createElement('button');nav.dataset.page='operations';nav.textContent="◉ Status och säkerhetskopiering";document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-operations';section.className='page';
  section.innerHTML=`<div class="page-heading"><div><p class="eyebrow">DINA ENHETER OCH KONTAKTER</p><h1>Status och säkerhetskopiering</h1><p>Se vad som sparas lokalt, synkroniseras och levereras.</p></div></div>
  <p id="ops-message" role="status"></p><div class="actions"><button id="ops-refresh" class="primary">Uppdatera status</button><button id="ops-copy" class="secondary">Kopiera felsökningsinformation</button></div>
  <article class="card"><h2>Synkronisering</h2><p id="ops-summary"></p><p id="ops-device-error"></p><div id="ops-devices"></div></article>
  <article class="card"><h2>Kontakter och loggtjänster</h2><label>Sök efter anropssignal eller datum<input id="ops-search" placeholder="Anropssignal eller YYYYMMDD"></label><p>I Cloud bekräftar synkronisering. Bekräftad sparad betyder att loggtjänsten har skickat ett kvitto eller att mottagarens loggbok har kontrollerats manuellt. Det är inte en QSL-bekräftelse från motstationen.</p><p id="ops-delivery-error"></p><div id="ops-contacts"></div><button id="ops-more" class="secondary">Visa fler</button></article>
  <article class="card"><h2>Felhistorik</h2><p>Fel finns kvar efter omstart. Identiska fel grupperas. Kopieringen innehåller inga kontouppgifter, lösenord eller API-nycklar.</p><div id="ops-errors"></div></article>
  <article class="card"><h2>Lokala säkerhetskopior</h2><p>Kontrollera datum och antal innan du hämtar saknade kontakter. Befintliga och nyare kontakter samt nuvarande inställningar behålls. En säkerhetskopia skapas före återställning.</p><button id="ops-backups" class="secondary">Visa säkerhetskopior på denna PC</button><div id="ops-backup-list"></div></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  const $=s=>section.querySelector(s),date=n=>n?new Date(n*1000).toLocaleString("sv-SE"):"Inte registrerat";
  let busy=false,data=null,limit=30;
  const text=(parent,value,tag='p')=>{const el=document.createElement(tag);el.textContent=value;parent.append(el);return el;};
  async function call(action,body={}){const response=await fetch('/api/cloud/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':document.querySelector('meta[name="radio-token"]').content},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||"Åtgärden misslyckades.");return result;}
  async function run(action){if(busy)return;busy=true;$('#ops-message').textContent="Arbetar …";try{await action();$('#ops-message').textContent="Statusen har uppdaterats.";}catch(e){$('#ops-message').textContent=e.message;}finally{busy=false;}}
  function contacts(){
    if(!data)return;const list=$('#ops-contacts'),expanded=new Set([...list.querySelectorAll('details[open]')].map(x=>x.dataset.key));list.replaceChildren();const query=$('#ops-search').value.trim().toUpperCase();
    const all=data.contacts.filter(q=>[q.call,q.date,q.time].join(' ').toUpperCase().includes(query));
    for(const q of all.slice(0,limit)){const box=document.createElement('details');box.dataset.key=q.key;box.open=expanded.has(q.key);list.append(box);text(box,`${q.call} · ${q.date} ${q.time} UTC · ${q.cloud}`,'summary');
      const deliveries=data.deliveries.filter(d=>d.qso===q.key);
      if(!deliveries.length)text(box,"Inget leveranskvitto registrerat i Cloud. Detta bevisar inte att kontakten saknas vid en loggningstjänst.");
      for(const d of deliveries){text(box,`${d.service} · ${d.label} · ${date(d.updated)}${d.message?' · '+d.message:''}`);
        if(d.can_resolve){const b=text(box,"Lös leverans",'button');b.className='secondary';b.onclick=()=>{
          const dialog=document.createElement('dialog');text(dialog,`${q.call} · ${q.date} ${q.time} UTC · ${d.service}`,'h2');text(dialog,"Kontrollera kontakten i mottagarens loggbok innan du väljer. Ett okänt resultat provas inte automatiskt igen.");
          for(const [state,label] of [['delivered',"Kontakten finns hos mottagaren"],['retry',"Kontakten saknas – tillåt nytt försök"]]){const choice=text(dialog,label,'button');choice.onclick=()=>{dialog.close();dialog.remove();run(async()=>{await call('delivery-choice',{qso:d.qso,service:d.service,profile:d.profile,expected:d.expected,checked:true,state});data=await call('overview');render();});};}
          text(dialog,'Avbryt','button').onclick=()=>{dialog.close();dialog.remove();};document.body.append(dialog);dialog.showModal();};}
      }
    }$('#ops-more').hidden=all.length<=limit;if(!all.length)text(list,"Inga kontakter matchar din sökning.");
  }
  function render(){
    $('#ops-summary').textContent=`${data.total} kontakter · ${data.pending} väntar på Cloud · ${data.conflicts} konflikter. Senast synkroniserad: ${date(data.last_sync)}.`;
    $('#ops-device-error').textContent=data.device_error;$('#ops-delivery-error').textContent=data.delivery_error;
    const devices=$('#ops-devices');devices.replaceChildren();for(const d of data.devices.items||[])text(devices,`${d.name||d.platform||"Okänd enhet"}${d.current?" (den här enheten)":''} · ${d.platform} ${d.version} · ${d.active?"Nyligen aktiv":"Inte nyligen aktiv"} · senast sedd ${date(d.seen)} · senast synkroniserad ${date(d.last_sync)} · ${d.pending} väntar`);
    const errors=$('#ops-errors');errors.replaceChildren();for(const e of [...data.errors].reverse())text(errors,`${date(e.last)} · ${e.area} · ${e.message} (${e.count} gång(er)${e.count===1?'':""})`);if(!data.errors.length)text(errors,"Inga fel registrerade.");contacts();
  }
  nav.onclick=()=>{showPage('operations');run(async()=>{data=await call('overview');render();});};
  $('#ops-refresh').onclick=()=>run(async()=>{data=await call('overview');render();});
  $('#ops-search').oninput=()=>{limit=30;contacts();};$('#ops-more').onclick=()=>{limit+=30;contacts();};
  $('#ops-copy').onclick=()=>run(async()=>{const d=await call('diagnostics');await navigator.clipboard.writeText(JSON.stringify(d,null,2));toast("Felsökningsinformation kopierad.");});
  $('#ops-backups').onclick=()=>run(async()=>{const result=await call('backups'),list=$('#ops-backup-list');list.replaceChildren();
    for(const item of result.items){const row=text(list,`${date(item.time)} · ${item.contacts===null?"Kan inte läsas":item.contacts+' kontakter'}`);if(item.error)continue;
      const button=text(row,"Kontrollera och återställ",'button');button.className='secondary';button.onclick=()=>run(async()=>{const p=await call('backup-preview',{id:item.id});
        if(!confirm(`Säkerhetskopia från ${date(p.time)}: ${p.contacts} kontakter.\n${p.add} saknade kontakter läggs till.
Alla ${p.current} befintliga kontakter behålls. ${p.different} kontakter med olika uppgifter behåller sin nuvarande version. Hämta de saknade kontakterna?`))return;
        const restored=await call('backup-restore',{id:item.id,confirm:true});await refreshState();toast(`${restored.added} kontakter hämtade. ${restored.preserved} bevarade.`);data=await call('overview');render();});
    }if(!result.items.length)text(list,"Inga Cloud-backups för det inloggade kontot på denna dator.");});
  setInterval(()=>{if(section.classList.contains('active')&&!busy&&!document.hidden&&!document.querySelector('dialog[open]'))run(async()=>{data=await call('overview');render();});},15000);
})();
