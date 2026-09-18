'use strict';
(() => {
  pageNames.operations='Status og sikkerhetskopi';
  const nav=document.createElement('button');nav.dataset.page='operations';nav.textContent='◉ Status og sikkerhetskopi';document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-operations';section.className='page';
  section.innerHTML=`<div class="page-heading"><div><p class="eyebrow">DINE ENHETER OG KONTAKTER</p><h1>Status og sikkerhetskopi</h1><p>Se hva som er lagret lokalt, synkronisert og levert.</p></div></div>
  <p id="ops-message" role="status"></p><div class="actions"><button id="ops-refresh" class="primary">Oppdater status</button><button id="ops-copy" class="secondary">Kopier feilsøkingsinformasjon</button></div>
  <article class="card"><h2>Synkronisering</h2><p id="ops-summary"></p><p id="ops-device-error"></p><div id="ops-devices"></div></article>
  <article class="card"><h2>Kontakter og loggtjenester</h2><label>Søk etter kallesignal eller dato<input id="ops-search" placeholder="Kallesignal eller ÅÅÅÅMMDD"></label><p>«I Cloud» bekrefter synkronisering. «Bekreftet lagret» betyr at loggtjenesten har kvittert eller at mottakerens logg er kontrollert manuelt. Det er ikke en QSL-bekreftelse fra motstasjonen.</p><p id="ops-delivery-error"></p><div id="ops-contacts"></div><button id="ops-more" class="secondary">Vis flere</button></article>
  <article class="card"><h2>Feilhistorikk</h2><p>Feil beholdes etter omstart. Like gjentakelser samles. Kopien inneholder ingen kontoopplysninger, passord eller API-nøkler.</p><div id="ops-errors"></div></article>
  <article class="card"><h2>Lokale sikkerhetskopier</h2><p>Kontroller dato og antall før du henter manglende kontakter. Kontakter som allerede finnes, nyere kontakter og dagens innstillinger beholdes. Det tas en kopi før gjenoppretting.</p><button id="ops-backups" class="secondary">Vis sikkerhetskopier på denne PC-en</button><div id="ops-backup-list"></div></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  const $=s=>section.querySelector(s),date=n=>n?new Date(n*1000).toLocaleString('nb-NO'):'Ikke registrert';
  let busy=false,data=null,limit=30;
  const text=(parent,value,tag='p')=>{const el=document.createElement(tag);el.textContent=value;parent.append(el);return el;};
  async function call(action,body={}){const response=await fetch('/api/cloud/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':document.querySelector('meta[name="radio-token"]').content},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||'Handlingen feilet.');return result;}
  async function run(action){if(busy)return;busy=true;$('#ops-message').textContent='Arbeider …';try{await action();$('#ops-message').textContent='Status oppdatert.';}catch(e){$('#ops-message').textContent=e.message;}finally{busy=false;}}
  function contacts(){
    if(!data)return;const list=$('#ops-contacts'),expanded=new Set([...list.querySelectorAll('details[open]')].map(x=>x.dataset.key));list.replaceChildren();const query=$('#ops-search').value.trim().toUpperCase();
    const all=data.contacts.filter(q=>[q.call,q.date,q.time].join(' ').toUpperCase().includes(query));
    for(const q of all.slice(0,limit)){const box=document.createElement('details');box.dataset.key=q.key;box.open=expanded.has(q.key);list.append(box);text(box,`${q.call} · ${q.date} ${q.time} UTC · ${q.cloud}`,'summary');
      const deliveries=data.deliveries.filter(d=>d.qso===q.key);
      if(!deliveries.length)text(box,'Ingen leveringskvittering registrert i Cloud. Dette beviser ikke at kontakten mangler hos en loggtjeneste.');
      for(const d of deliveries){text(box,`${d.service} · ${d.label} · ${date(d.updated)}${d.message?' · '+d.message:''}`);
        if(d.can_resolve){const b=text(box,'Avklar levering','button');b.className='secondary';b.onclick=()=>{
          const dialog=document.createElement('dialog');text(dialog,`${q.call} · ${q.date} ${q.time} UTC · ${d.service}`,'h2');text(dialog,'Kontroller denne kontakten i mottakerens logg før du velger. Ved ukjent resultat sendes den ikke automatisk på nytt.');
          for(const [state,label] of [['delivered','Kontakten finnes hos mottaker'],['retry','Kontakten finnes ikke – tillat nytt forsøk']]){const choice=text(dialog,label,'button');choice.onclick=()=>{dialog.close();dialog.remove();run(async()=>{await call('delivery-choice',{qso:d.qso,service:d.service,profile:d.profile,expected:d.expected,checked:true,state});data=await call('overview');render();});};}
          text(dialog,'Avbryt','button').onclick=()=>{dialog.close();dialog.remove();};document.body.append(dialog);dialog.showModal();};}
      }
    }$('#ops-more').hidden=all.length<=limit;if(!all.length)text(list,'Ingen kontakter passer søket.');
  }
  function render(){
    $('#ops-summary').textContent=`${data.total} kontakter · ${data.pending} venter på Cloud · ${data.conflicts} konflikter. Sist synkronisert: ${date(data.last_sync)}.`;
    $('#ops-device-error').textContent=data.device_error;$('#ops-delivery-error').textContent=data.delivery_error;
    const devices=$('#ops-devices');devices.replaceChildren();for(const d of data.devices.items||[])text(devices,`${d.name||d.platform||'Ukjent enhet'}${d.current?' (denne enheten)':''} · ${d.platform} ${d.version} · ${d.active?'Nylig aktiv':'Ikke nylig aktiv'} · sist sett ${date(d.seen)} · sist synkronisert ${date(d.last_sync)} · ${d.pending} venter`);
    const errors=$('#ops-errors');errors.replaceChildren();for(const e of [...data.errors].reverse())text(errors,`${date(e.last)} · ${e.area} · ${e.message} (${e.count} gang${e.count===1?'':'er'})`);if(!data.errors.length)text(errors,'Ingen feil registrert.');contacts();
  }
  nav.onclick=()=>{showPage('operations');run(async()=>{data=await call('overview');render();});};
  $('#ops-refresh').onclick=()=>run(async()=>{data=await call('overview');render();});
  $('#ops-search').oninput=()=>{limit=30;contacts();};$('#ops-more').onclick=()=>{limit+=30;contacts();};
  $('#ops-copy').onclick=()=>run(async()=>{const d=await call('diagnostics');await navigator.clipboard.writeText(JSON.stringify(d,null,2));toast('Feilsøkingsinformasjon kopiert.');});
  $('#ops-backups').onclick=()=>run(async()=>{const result=await call('backups'),list=$('#ops-backup-list');list.replaceChildren();
    for(const item of result.items){const row=text(list,`${date(item.time)} · ${item.contacts===null?'Kan ikke leses':item.contacts+' kontakter'}`);if(item.error)continue;
      const button=text(row,'Kontroller og gjenopprett','button');button.className='secondary';button.onclick=()=>run(async()=>{const p=await call('backup-preview',{id:item.id});
        if(!confirm(`Sikkerhetskopi fra ${date(p.time)}: ${p.contacts} kontakter.\n${p.add} manglende kontakter legges til.\nAlle ${p.current} nåværende kontakter beholdes. ${p.different} kontakter med ulike opplysninger beholder dagens versjon.\n\nHente de manglende kontaktene?`))return;
        const restored=await call('backup-restore',{id:item.id,confirm:true});await refreshState();toast(`${restored.added} kontakter hentet. ${restored.preserved} beholdt.`);data=await call('overview');render();});
    }if(!result.items.length)text(list,'Ingen Cloud-sikkerhetskopier på denne PC-en for den innloggede kontoen.');});
  setInterval(()=>{if(section.classList.contains('active')&&!busy&&!document.hidden&&!document.querySelector('dialog[open]'))run(async()=>{data=await call('overview');render();});},15000);
})();
