/* Owner-only overview. Cloud checks authorization again on every request. */
(() => {
  pageNames.admin='Administrator';
  const nav=document.createElement('button');nav.dataset.page='admin';nav.textContent='♙ Administrator';nav.hidden=true;
  document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-admin';section.className='page';
  section.innerHTML=`<div class="page-heading"><p class="eyebrow">ADMINISTRATOR</p><h1>Brukere av HamNavigator</h1>
    <p>Se registrerte kontoer og hvem som bruker HamNavigator nå.</p></div>
    <div class="stats-grid"><article class="card"><p>Registrerte brukere</p><h2 id="admin-total">—</h2></article>
    <article class="card"><p>Pålogget og aktiv</p><h2 id="admin-active">—</h2></article></div>
    <article class="card"><p>Aktiv betyr kontakt med appen de siste 2 minuttene. Flere PC-er og mobiler på samme konto teller som én bruker. Status kan bruke opptil 2 minutter på å endres etter lukking eller nettbrudd.</p>
    <form id="admin-filter"><label>Søk etter e-post <input name="search" type="search" maxlength="232" placeholder="Søk etter bruker"></label>
    <label><input name="active" type="checkbox" checked> Bare aktive brukere</label> <button class="secondary">Oppdater</button></form>
    <p id="admin-status" role="status" aria-live="polite"></p><div style="overflow-x:auto"><table><thead><tr><th>Konto</th><th>Status</th><th>Siste kontakt</th><th>App / versjon</th></tr></thead><tbody id="admin-users"></tbody></table></div>
    <p><button id="admin-prev" class="secondary" disabled>Forrige</button> <button id="admin-next" class="secondary" disabled>Neste</button></p>
    <p class="small muted">Nedlasting er åpen. En registrert konto forteller ikke hvor mange ganger personen har lastet ned eller installert programmet. Eldre apper vises når de kontakter Cloud.</p></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  let allowed=false,busy=false,offset=0,generation=0;
  const form=section.querySelector('form'),status=section.querySelector('#admin-status'),rows=section.querySelector('tbody');
  const date=t=>t?new Date(t*1000).toLocaleString('nb-NO'):'Ikke registrert';
  async function refresh(){
    if(!allowed||busy)return;busy=true;const current=++generation;status.textContent='Henter brukeroversikten …';
    try{
      const result=await api('cloud/admin-users',{offset,search:form.elements.search.value,active_only:form.elements.active.checked});
      if(!allowed||current!==generation)return;
      section.querySelector('#admin-total').textContent=result.summary.total;
      section.querySelector('#admin-active').textContent=result.summary.active;
      rows.replaceChildren();
      for(const user of result.items){const tr=document.createElement('tr');
        for(const value of [user.email,user.disabled?'Deaktivert':!user.verified?'Venter på e-postbekreftelse':user.active?'Aktiv'+(user.admin?' · administrator':''):'Ikke aktiv',date(user.seen),user.clients||'Ukjent / eldre app']){
          const td=document.createElement('td');td.textContent=value;tr.append(td);
        }rows.append(tr);
      }
      section.querySelector('#admin-prev').disabled=offset===0;
      section.querySelector('#admin-next').disabled=!result.more;
      status.textContent=(result.items.length?'Viser '+(offset+1)+'–'+(offset+result.items.length)+'. ':'Ingen brukere i dette utvalget. ')+
        'Oppdatert '+date(result.server_time)+'. '+result.summary.pending+' venter på e-postbekreftelse.';
    }catch(error){if(current===generation){rows.replaceChildren();status.textContent=error.message;}}
    finally{busy=false;}
  }
  window.addEventListener('hamnavigator-cloud-state',e=>{
    allowed=e.detail.admin===true;nav.hidden=!allowed;
    if(!allowed){generation++;rows.replaceChildren();section.querySelector('#admin-total').textContent='—';section.querySelector('#admin-active').textContent='—';status.textContent='';if(section.classList.contains('active'))showPage('cloud');}
  });
  nav.onclick=()=>{showPage('admin');refresh();};
  form.onsubmit=e=>{e.preventDefault();offset=0;refresh();};
  section.querySelector('#admin-next').onclick=()=>{offset+=100;refresh();};
  section.querySelector('#admin-prev').onclick=()=>{offset=Math.max(0,offset-100);refresh();};
  setInterval(()=>{if(allowed&&section.classList.contains('active')&&!document.hidden)refresh();},15000);
})();
