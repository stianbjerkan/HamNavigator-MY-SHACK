/* Owner-only overview. Cloud checks authorization again on every request. */
(() => {
  pageNames.admin='Administrator';
  const nav=document.createElement('button');nav.dataset.page='admin';nav.textContent='♙ Administrator';nav.hidden=true;
  document.querySelector('nav').append(nav);
  const section=document.createElement('section');section.id='page-admin';section.className='page';
  section.innerHTML=`<div class="page-heading"><p class="eyebrow">ADMINISTRATOR</p><h1>HamNavigator users</h1>
    <p>See registered accounts and who is using HamNavigator now.</p></div>
    <div class="stats-grid"><article class="card"><p>Registered users</p><h2 id="admin-total">—</h2></article>
    <article class="card"><p>Logged in and active</p><h2 id="admin-active">—</h2></article></div>
    <article class="card"><p>Active means contact with the app in the last 2 minutes. Multiple PCs and phones on the same account count as one user. Status may take up to 2 minutes to change after closing or a network outage.</p>
    <form id="admin-filter"><label>Search by email <input name="search" type="search" maxlength="232" placeholder="Search for a user"></label>
    <label><input name="active" type="checkbox" checked> Active users only</label> <button class="secondary">Update</button></form>
    <p id="admin-status" role="status" aria-live="polite"></p><div style="overflow-x:auto"><table><thead><tr><th>Account</th><th>Status</th><th>Last connection</th><th>App / version</th></tr></thead><tbody id="admin-users"></tbody></table></div>
    <p><button id="admin-prev" class="secondary" disabled>Previous</button> <button id="admin-next" class="secondary" disabled>Next</button></p>
    <p class="small muted">Downloads are public. A registered account does not tell you how many times someone downloaded or installed the program. Older apps appear when they contact Cloud.</p></article>`;
  document.querySelector('main').insertBefore(section,document.querySelector('main footer'));
  let allowed=false,busy=false,offset=0,generation=0;
  const form=section.querySelector('form'),status=section.querySelector('#admin-status'),rows=section.querySelector('tbody');
  const date=t=>t?new Date(t*1000).toLocaleString("en-GB"):"Not recorded";
  async function refresh(){
    if(!allowed||busy)return;busy=true;const current=++generation;status.textContent="Retrieving users …";
    try{
      const result=await api('cloud/admin-users',{offset,search:form.elements.search.value,active_only:form.elements.active.checked});
      if(!allowed||current!==generation)return;
      section.querySelector('#admin-total').textContent=result.summary.total;
      section.querySelector('#admin-active').textContent=result.summary.active;
      rows.replaceChildren();
      for(const user of result.items){const tr=document.createElement('tr');
        for(const value of [user.email,user.disabled?"Disabled":!user.verified?"Waiting for email verification":user.active?"Active"+(user.admin?' · administrator':''):"Inactive",date(user.seen),user.clients||"Unknown / older app"]){
          const td=document.createElement('td');td.textContent=value;tr.append(td);
        }rows.append(tr);
      }
      section.querySelector('#admin-prev').disabled=offset===0;
      section.querySelector('#admin-next').disabled=!result.more;
      status.textContent=(result.items.length?"Showing "+(offset+1)+'–'+(offset+result.items.length)+'. ':"No users in this selection. ")+
        "Updated "+date(result.server_time)+'. '+result.summary.pending+" waiting for email verification.";
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
