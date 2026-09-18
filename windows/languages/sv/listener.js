'use strict';
// Separate module: capture/inference is local; this file only drives its interface.
const listenerUI = (()=>{
  let devices=[], session=null, busy=false, lastResults='', playerURL=null, devicesLoading=false, devicesLoaded=false;
  let current={running:false,processing:false,results:[],level_db:-90,peak_db:-90,message:"Välj en ljudkälla för att komma igång.",model_ready:false};
  function render(data){
    current=data;
    $('#audio-status').textContent=data.message;
    $('#audio-error').textContent=data.error||'';
    $('#audio-level').value=data.level_db;
    $('#audio-level-label').textContent=data.level_db.toFixed(0)+' dBFS';
    const waiting=data.processing;
    $('#audio-start').disabled=data.running||waiting||!$('#audio-device').value||!data.model_ready;
    $('#audio-stop').disabled=!data.running;
    $('#audio-file-button').disabled=data.running||waiting;
    $('#audio-clear').disabled=data.running||waiting;
    for(const id of ['audio-device','audio-language','audio-gate','audio-filter','audio-devices-refresh'])$('#'+id).disabled=data.running||waiting;
    $('#audio-runtime').textContent=[data.model_ready?"Lokal talmodell redo":"Talmodell saknas",data.device?"Källa: "+data.device:'',data.dropped?data.dropped+" ljudsegment hoppades över eftersom taligenkänningen inte hann med":'',data.peak_db>-1?"Ljudet överstyrs – sänk ingångsnivån":''].filter(Boolean).join(' · ');
    const key=JSON.stringify(data.results);
    if(key!==lastResults){
      lastResults=key;
      const suggestions=new Map();
      for(const result of data.results)for(const c of result.candidates){if(!suggestions.has(c.call))suggestions.set(c.call,{...c,time:result.time});}
      $('#audio-candidates').innerHTML=suggestions.size?[...suggestions.values()].slice(0,12).map(c=>`<button class="audio-candidate" data-heard-call="${esc(c.call)}"><strong>${esc(c.call)}</strong><span>${c.kind==='fonetisk'?"Tolkad från stavning":"Finns i texten"} · ${esc(stamp(c.time))}</span><small>${esc(c.evidence)}</small></button>`).join(''):empty(data.results.length?"Inga tydliga anropssignaler hittades":"Väntar på tal från radion","Läs texten nedan eller prova ett tydligare ljudsegment.");
      $('#audio-transcripts').innerHTML=data.results.length?data.results.map(r=>`<div class="audio-transcript"><div><span class="small muted">${esc(stamp(r.time))} · ${r.duration} s · ${esc(r.source)}</span><p>${esc(r.text)}</p></div><button class="mini-button" data-audio-play="${esc(r.id)}">▶ Spela</button></div>`).join(''):empty("Inget tal identifierat ännu","Välj en ljudkälla och börja lyssna eller prova en kort WAV-inspelning.");
    }
    $('#audio-use-call').disabled=!moduleEnabled('log');
    $('#audio-use-call').textContent=moduleEnabled('log')?"Använd i en ny kontakt":"Välj modulen Loggbok först";
  }
  async function refreshDevices(){
    if(devicesLoading)return;
    devicesLoading=true;
    try{
    const result=await api('audio/devices',{});
    devices=result.devices;
    const chosen=$('#audio-device').selectedOptions[0]?.dataset.name||'';
    $('#audio-device').innerHTML="<option value=\"\">Välj ljudkälla …</option>"+devices.map(d=>`<option value="${d.id}" data-name="${esc(d.name)}">${d.loopback?"Datorljud":"Ljudingång"} · ${esc(d.name)}</option>`).join('');
    const previous=devices.find(d=>d.name===chosen);
    if(previous)$('#audio-device').value=String(previous.id);
    if(!devices.length)throw new Error("Inga tillgängliga ljudingångar hittades i Windows.");
    devicesLoaded=true;
    $('#audio-error').textContent='';
    await poll();
    }finally{devicesLoading=false;}
  }
  async function poll(){
    if(busy)return;busy=true;
    try{
      if(session){
        if(moduleEnabled('listener'))await api('audio/heartbeat',{session});
        else{await api('audio/stop',{});session=null;}
      }
      const data=await api('audio/status');
      if(session&&!data.running&&!data.processing)session=null;
      render(data);
    }catch(error){$('#audio-status').textContent="Förlorad kontakt med lyssnaren";$('#audio-error').textContent=error.message;}
    finally{busy=false;}
  }
  $('#audio-devices-refresh').onclick=action(refreshDevices);
  $('#audio-device').onchange=()=>render(current);
  $('#audio-start').onclick=action(async()=>{
    const selected=devices.find(d=>String(d.id)===$('#audio-device').value);
    if(!selected)throw new Error("Välj ljudkällan programmet ska lyssna på.");
    $('#audio-start').disabled=true;
    try{
      const result=await api('audio/start',{device:selected.id,device_name:selected.name,language:$('#audio-language').value,gate:Number($('#audio-gate').value),filter:$('#audio-filter').checked});
      session=result.session;
    }finally{await poll();}
  });
  $('#audio-stop').onclick=action(async()=>{await api('audio/stop',{});session=null;await poll();});
  $('#audio-file-button').onclick=()=>$('#audio-file').click();
  $('#audio-file').onchange=action(async event=>{
    const file=event.target.files[0];if(!file)return;
    try{
      if(file.size>12000000)throw new Error("Välj en WAV-fil mindre än 12 MB och inte längre än 60 sekunder.");
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
      for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      await api('audio/file',{audio:btoa(binary),language:$('#audio-language').value,filter:$('#audio-filter').checked});
      await poll();
    }finally{event.target.value='';}
  });
  $('#audio-clear').onclick=action(async()=>{
    await api('audio/clear',{});
    $('#audio-player').pause();$('#audio-player').hidden=true;$('#audio-player').removeAttribute('src');
    if(playerURL){URL.revokeObjectURL(playerURL);playerURL=null;}
    $('#audio-confirm-call').value='';await poll();
  });
  document.addEventListener('click',action(async event=>{
    const selected=event.target.closest('[data-heard-call]');
    if(selected){$('#audio-confirm-call').value=selected.dataset.heardCall;$('#audio-confirm-call').focus();}
    const play=event.target.closest('[data-audio-play]');
    if(play){
      // Pause capture before replay so PC-loopback never transcribes its own clip.
      if(current.running){await api('audio/stop',{});session=null;await poll();throw new Error("Lyssningen har stoppats före uppspelning. Tryck på Spela igen när det sista ljudsegmentet är klart.");}
      const response=await fetch('/api/audio/clip',{method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':token},body:JSON.stringify({id:play.dataset.audioPlay})});
      if(!response.ok){const error=await response.json();throw new Error(error.error);}
      if(playerURL)URL.revokeObjectURL(playerURL);
      playerURL=URL.createObjectURL(await response.blob());
      const player=$('#audio-player');player.src=playerURL;player.hidden=false;await player.play();
    }
  }));
  $('#audio-use-form').onsubmit=action(event=>{
    event.preventDefault();
    if(!moduleEnabled('log'))throw new Error("Välj Loggbok under Välj moduler först.");
    const call=$('#audio-confirm-call').value.trim().toUpperCase();
    if(!/^[A-Z0-9/]{3,32}$/.test(call)||!/[A-Z]/.test(call)||!/[0-9]/.test(call))throw new Error("Kontrollera anropssignalen.");
    openQso(null,call);
  });
  document.addEventListener('station-state-updated',()=>{render(current);});
  window.addEventListener('pagehide',()=>{
    if(session)fetch('/api/audio/stop',{method:'POST',headers:{'Content-Type':'application/json','X-Radio-Token':token},body:'{}',keepalive:true}).catch(()=>{});
  });
  // Hidden account/home pages must not probe audio hardware during startup.
  function visible(){return window.hnAuthorized===true && !document.hidden && $('#page-listener').classList.contains('active');}
  function opened(){if(visible()&&!devicesLoaded)refreshDevices().catch(error=>{$('#audio-error').textContent=error.message;});}
  document.addEventListener('hamnavigator-page-changed',opened);
  document.addEventListener('visibilitychange',opened);
  opened();
  setInterval(()=>{if(session||visible())poll();},2000);
  return {poll};
})();
