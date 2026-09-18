pageNames.portable='POTA / SOTA';
function portableRows(){
 const form=$('#portable-filter'),v=Object.fromEntries(new FormData(form));
 const field=(v.role==='activator'?'MY_':'')+(v.program==='pota'?'SIG_INFO':'SOTA_REF');
 const sig=v.role==='activator'?'MY_SIG':'SIG';
 const rows=sortedQsos().filter(q=>q[field]&&(v.program!=='pota'||q[sig]==='POTA')&&(!v.ref||q[field]===v.ref.trim().toUpperCase())&&(!v.date||q.QSO_DATE===v.date.replaceAll('-','')));
 $('#portable-count').textContent=`${rows.length} kontakter · ${new Set(rows.map(q=>q.CALL)).size} anropssignaler`;
 $('#portable-rows').innerHTML=rows.length?table(["ANROPSSIGNAL",'UTC',"TRAFIKSÄTT",'EGEN REF.',"MOTSTATION"],rows.slice(0,200).map(q=>`<tr><td><button class="text-button" data-edit-qso="${esc(q.id)}">${esc(q.CALL)}</button></td><td>${esc(qsoDate(q))} ${esc(qsoTime(q))}</td><td>${esc(mode(q))}</td><td>${esc([q.MY_SIG==='POTA'?q.MY_SIG_INFO:'',q.MY_SOTA_REF].filter(Boolean).join(' / '))}</td><td>${esc([q.SIG==='POTA'?q.SIG_INFO:'',q.SOTA_REF].filter(Boolean).join(' / '))}</td></tr>`)):empty("Inga kontakter i detta urval","Logga en kontakt med en park / toppreferens eller ändra filtret.");
 $('#portable-export').href='/api/export?'+new URLSearchParams(v);
 const a=state.portable||{},today=new Date().toISOString().slice(0,10).replaceAll('-','');
 $('#portable-status').textContent=a.active&&a.date===today?'Aktivering pågår: '+[a.MY_SIG_INFO,a.MY_SOTA_REF].filter(Boolean).join(' / ')+" · nya kontakter märks automatiskt":"Ingen aktiv aktivering. Ange jägare/chaserreferenser på kontakten.";
}
$('#portable-filter').addEventListener('input',portableRows);
document.addEventListener('station-state-updated',portableRows);
$('#portable-new').onclick=()=>openQso();
$('#portable-start').onclick=action(async()=>{const f=$('#portable-session');await api('portable',{active:true,MY_SIG_INFO:f.elements.MY_SIG_INFO.value,MY_SOTA_REF:f.elements.MY_SOTA_REF.value});await refreshState();toast("Aktivering startade för denna UTC-dag.");});
$('#portable-stop').onclick=action(async()=>{await api('portable',{active:false});await refreshState();toast("Aktiveringen avslutades.");});

