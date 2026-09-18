'use strict';
(() => {
  pageNames.operations="Status and backup";
  const nav=document.createElement('button');nav.dataset.page='operations';nav.textContent="◉ Status and backup";document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-operations';section.className='page';
  section.innerHTML=`<div class="page-heading"><div><p class="eyebrow">YOUR DEVICES AND CONTACTS</p><h1>Status and backup</h1><p>See what is saved locally, synchronized and delivered.</p></div></div>
  <p id="ops-message" role="status"></p><div class="actions"><button id="ops-refresh" class="primary">Refresh status</button><button id="ops-copy" class="secondary">Copy troubleshooting information</button></div>
  <article class="card"><h2>Synchronization</h2><p id="ops-summary"></p><p id="ops-device-error"></p><div id="ops-devices"></div></article>
  <article class="card"><h2>Contacts and logging services</h2><label>Search by callsign or date<input id="ops-search" placeholder="Callsign or YYYYMMDD"></label><p>In Cloud confirms synchronization. Confirmed stored means the logging service returned a receipt or the recipient's logbook was checked manually. It is not a QSL confirmation from the other station.</p><p id="ops-delivery-error"></p><div id="ops-contacts"></div><button id="ops-more" class="secondary">Show more</button></article>
  <article class="card"><h2>Error history</h2><p>Errors are kept after restart. Repeated identical errors are grouped. The copy includes no account details, passwords or API keys.</p><div id="ops-errors"></div></article>
  <article class="card"><h2>Local backups</h2><p>Check the date and counts before retrieving missing contacts. Existing contacts, newer contacts and current settings are kept. A backup is made before restoring.</p><button id="ops-backups" class="secondary">Show backups on this PC</button><div id="ops-backup-list"></div></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  const $=s=>section.querySelector(s),date=n=>n?new Date(n*1000).toLocaleString("en-GB"):"Not recorded";
  let busy=false,data=null,limit=30;
  const text=(parent,value,tag='p')=>{const el=document.createElement(tag);el.textContent=value;parent.append(el);return el;};
  async function call(action,body={}){const response=await fetch('/api/cloud/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':document.querySelector('meta[name="radio-token"]').content},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||"The action failed.");return result;}
  async function run(action){if(busy)return;busy=true;$('#ops-message').textContent="Working …";try{await action();$('#ops-message').textContent="Status updated.";}catch(e){$('#ops-message').textContent=e.message;}finally{busy=false;}}
  function contacts(){
    if(!data)return;const list=$('#ops-contacts'),expanded=new Set([...list.querySelectorAll('details[open]')].map(x=>x.dataset.key));list.replaceChildren();const query=$('#ops-search').value.trim().toUpperCase();
    const all=data.contacts.filter(q=>[q.call,q.date,q.time].join(' ').toUpperCase().includes(query));
    for(const q of all.slice(0,limit)){const box=document.createElement('details');box.dataset.key=q.key;box.open=expanded.has(q.key);list.append(box);text(box,`${q.call} · ${q.date} ${q.time} UTC · ${q.cloud}`,'summary');
      const deliveries=data.deliveries.filter(d=>d.qso===q.key);
      if(!deliveries.length)text(box,"No delivery receipt recorded in Cloud. This does not prove the contact is missing at a logging service.");
      for(const d of deliveries){text(box,`${d.service} · ${d.label} · ${date(d.updated)}${d.message?' · '+d.message:''}`);
        if(d.can_resolve){const b=text(box,"Resolve delivery",'button');b.className='secondary';b.onclick=()=>{
          const dialog=document.createElement('dialog');text(dialog,`${q.call} · ${q.date} ${q.time} UTC · ${d.service}`,'h2');text(dialog,"Check this contact in the recipient's logbook before choosing. An unknown result is not resent automatically.");
          for(const [state,label] of [['delivered',"The contact exists at the recipient"],['retry',"The contact does not exist – allow retry"]]){const choice=text(dialog,label,'button');choice.onclick=()=>{dialog.close();dialog.remove();run(async()=>{await call('delivery-choice',{qso:d.qso,service:d.service,profile:d.profile,expected:d.expected,checked:true,state});data=await call('overview');render();});};}
          text(dialog,"Cancel",'button').onclick=()=>{dialog.close();dialog.remove();};document.body.append(dialog);dialog.showModal();};}
      }
    }$('#ops-more').hidden=all.length<=limit;if(!all.length)text(list,"No contacts match your search.");
  }
  function render(){
    $('#ops-summary').textContent=`${data.total} contacts · ${data.pending} waiting for Cloud · ${data.conflicts} conflicts. Last synchronized: ${date(data.last_sync)}.`;
    $('#ops-device-error').textContent=data.device_error;$('#ops-delivery-error').textContent=data.delivery_error;
    const devices=$('#ops-devices');devices.replaceChildren();for(const d of data.devices.items||[])text(devices,`${d.name||d.platform||"Unknown device"}${d.current?" (this device)":''} · ${d.platform} ${d.version} · ${d.active?"Recently active":"Not recently active"} · last seen ${date(d.seen)} · last synchronized ${date(d.last_sync)} · ${d.pending} waiting`);
    const errors=$('#ops-errors');errors.replaceChildren();for(const e of [...data.errors].reverse())text(errors,`${date(e.last)} · ${e.area} · ${e.message} (${e.count} time(s)${e.count===1?'':""})`);if(!data.errors.length)text(errors,"No errors recorded.");contacts();
  }
  nav.onclick=()=>{showPage('operations');run(async()=>{data=await call('overview');render();});};
  $('#ops-refresh').onclick=()=>run(async()=>{data=await call('overview');render();});
  $('#ops-search').oninput=()=>{limit=30;contacts();};$('#ops-more').onclick=()=>{limit+=30;contacts();};
  $('#ops-copy').onclick=()=>run(async()=>{const d=await call('diagnostics');await navigator.clipboard.writeText(JSON.stringify(d,null,2));toast("Troubleshooting information copied.");});
  $('#ops-backups').onclick=()=>run(async()=>{const result=await call('backups'),list=$('#ops-backup-list');list.replaceChildren();
    for(const item of result.items){const row=text(list,`${date(item.time)} · ${item.contacts===null?"Cannot be read":item.contacts+" contacts"}`);if(item.error)continue;
      const button=text(row,"Check and restore",'button');button.className='secondary';button.onclick=()=>run(async()=>{const p=await call('backup-preview',{id:item.id});
        if(!confirm(`Backup from ${date(p.time)}: ${p.contacts} contacts.
${p.add} missing contacts will be added.
All ${p.current} current contacts will be kept. ${p.different} contacts with different details will keep their current version.

Retrieve the missing contacts?`))return;
        const restored=await call('backup-restore',{id:item.id,confirm:true});await refreshState();toast(`${restored.added} contacts retrieved. ${restored.preserved} kept.`);data=await call('overview');render();});
    }if(!result.items.length)text(list,"No Cloud backups for the logged-in account on this PC.");});
  setInterval(()=>{if(section.classList.contains('active')&&!busy&&!document.hidden&&!document.querySelector('dialog[open]'))run(async()=>{data=await call('overview');render();});},15000);
})();
