/* Owner-only overview. Cloud checks authorization again on every request. */
(() => {
  pageNames.admin='Administrator';
  const nav=document.createElement('button');nav.dataset.page='admin';nav.textContent='♙ Administrator';nav.hidden=true;
  document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-admin';section.className='page';
  section.innerHTML=`<div class="page-heading"><p class="eyebrow">Administratör</p><h1>HamNavigator-användare</h1>
    <p>Se registrerade konton och vem som använder HamNavigator nu.</p></div>
    <div class="stats-grid"><article class="card"><p>Registrerade användare</p><h2 id="admin-total">—</h2></article>
    <article class="card"><p>Inloggade och aktiva</p><h2 id="admin-active">—</h2></article></div>
    <article class="card"><p>Aktivt innebär kontakt med appen under de senaste 2 minuterna. Flera datorer och telefoner på samma konto räknas som en användare. Status kan ta upp till 2 minuter att ändra efter stängning eller ett nätverk avbrott.</p>
    <form id="admin-filter"><label>Sök via e-post <input name="search" type="search" maxlength="232" placeholder="Sök efter en användare"></label>
    <label><input name="active" type="checkbox" checked> Endast aktiva användare</label> <button class="secondary">Uppdatera</button></form>
    <p id="admin-status" role="status" aria-live="polite"></p><div style="overflow-x:auto"><table><thead><tr><th>Konto</th><th>Status</th><th>Senaste anslutning</th><th>App / version</th></tr></thead><tbody id="admin-users"></tbody></table></div>
    <p><button id="admin-prev" class="secondary" disabled>Föregående</button> <button id="admin-next" class="secondary" disabled>Nästa</button></p>
    <p class="small muted">Nedladdningar är offentliga. Ett registrerat konto berättar inte hur många gånger någon laddade ner eller installerade programmet. Äldre appar visas när de kontaktar Cloud.</p></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  let allowed=false,busy=false,offset=0,generation=0;
  const form=section.querySelector('form'),status=section.querySelector('#admin-status'),rows=section.querySelector('tbody');
  const date=t=>t?new Date(t*1000).toLocaleString("sv-SE"):"Inte registrerat";
  async function refresh(){
    if(!allowed||busy)return;busy=true;const current=++generation;status.textContent="Hämtar användare …";
    try{
      const result=await api('cloud/admin-users',{offset,search:form.elements.search.value,active_only:form.elements.active.checked});
      if(!allowed||current!==generation)return;
      section.querySelector('#admin-total').textContent=result.summary.total;
      section.querySelector('#admin-active').textContent=result.summary.active;
      rows.replaceChildren();
      for(const user of result.items){const tr=document.createElement('tr');
        for(const value of [user.email,user.disabled?"Inaktiverad":!user.verified?"Väntar på e-postverifiering":user.active?'Aktiv'+(user.admin?' · administrator':''):"Inaktiv",date(user.seen),user.clients||"Okänd / äldre app"]){
          const td=document.createElement('td');td.textContent=value;tr.append(td);
        }rows.append(tr);
      }
      section.querySelector('#admin-prev').disabled=offset===0;
      section.querySelector('#admin-next').disabled=!result.more;
      status.textContent=(result.items.length?"Visar "+(offset+1)+'–'+(offset+result.items.length)+'. ':"Inga användare i detta val. ")+
        "Uppdaterad "+date(result.server_time)+'. '+result.summary.pending+" väntar på e-postbekräftelse.";
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
