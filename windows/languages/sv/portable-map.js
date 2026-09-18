/* Radioassistent's own POTA/SOTA map. Public reference points, no remote app UI. */
let parkMap, mapSelected, mapLoadId=0, mapSearchId=0, mapDebounce;
const pointSources={}, pointLayers={};
const mapPrograms=()=>['POTA','SOTA'].filter(p=>document.getElementById('map-layer-'+p).checked);
function mapPick(row,pan=true){
 mapSelected=row;
 $('#map-selection').hidden=false;
 $('#map-place').textContent=row.ref+' · '+row.name;
 $('#map-place-info').textContent=row.program+' · '+row.region+(row.height!==undefined?` · ${row.height} m över havet · ${row.points} poäng`:'')+` · ${row.lat.toFixed(5)}, ${row.lon.toFixed(5)}`;
 if(pan)parkMap.getView().animate({center:ol.proj.fromLonLat([row.lon,row.lat]),zoom:12,duration:350});
}
function mapResults(rows){
 $('#map-results').innerHTML=rows.length?rows.map((r,i)=>`<button type="button" class="secondary" data-map-result="${i}">${esc(r.ref)} · ${esc(r.name)}</button>`).join(''):"Inga träffar.";
 $('#map-results').querySelectorAll('[data-map-result]').forEach(b=>b.onclick=()=>mapPick(rows[Number(b.dataset.mapResult)]));
}
async function loadMapPoints(){
 if(!parkMap||!$('#reference-map').offsetWidth)return;
 const id=++mapLoadId,view=parkMap.getView(),extent=ol.proj.transformExtent(view.calculateExtent(parkMap.getSize()),'EPSG:3857','EPSG:4326');
 const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
 const params=new URLSearchParams({programs:mapPrograms().join(','),west:clamp(extent[0],-180,180),south:clamp(extent[1],-90,90),east:clamp(extent[2],-180,180),north:clamp(extent[3],-90,90)});
 try{
  const data=await api('portable-map?'+params);if(id!==mapLoadId)return;
  for(const program of ['POTA','SOTA']){
   pointSources[program].clear();
   pointSources[program].addFeatures(data.items.filter(r=>r.program===program).map(row=>new ol.Feature({geometry:new ol.geom.Point(ol.proj.fromLonLat([row.lon,row.lat])),row})));
  }
  $('#map-data-status').textContent=`${data.items.length} av ${data.total} platser i denna vy${data.truncated?" · Zooma in för att visa alla":''} · Katalog hämtad ${data.updated.slice(0,10)}.`;
 }catch(e){$('#map-data-status').textContent=e.message;}
}
function initReferenceMap(){
 if(parkMap||!$('#reference-map').offsetWidth)return;
 const styles={};
 for(const [program,color,letter] of [['POTA','#45b985','P'],['SOTA','#469dff','S']]){
  pointSources[program]=new ol.source.Vector();
  pointLayers[program]=new ol.layer.Vector({source:new ol.source.Cluster({distance:35,source:pointSources[program]}),style:feature=>{
   const count=feature.get('features').length,key=program+count;
   return styles[key]||(styles[key]=new ol.style.Style({image:new ol.style.Circle({radius:count>1?17:12,fill:new ol.style.Fill({color}),stroke:new ol.style.Stroke({color:'#102039',width:2})}),text:new ol.style.Text({text:count>1?String(count):letter,fill:new ol.style.Fill({color:'#fff'}),font:'bold 12px sans-serif'})}));
  }});
 }
 let center=[10.5,64];
 try{if(state.settings.grid){const p=gridPoint(state.settings.grid);if(p)center=[p.lon,p.lat];}}catch{}
 parkMap=new ol.Map({target:'reference-map',layers:[new ol.layer.Tile({source:new ol.source.OSM()}),pointLayers.POTA,pointLayers.SOTA],view:new ol.View({center:ol.proj.fromLonLat(center),zoom:7,minZoom:2,maxZoom:19,multiWorld:false})});
 parkMap.on('moveend',()=>{clearTimeout(mapDebounce);mapDebounce=setTimeout(loadMapPoints,160);});
 parkMap.on('singleclick',event=>{
  const cluster=parkMap.forEachFeatureAtPixel(event.pixel,f=>f);
  if(!cluster)return;
  const features=cluster.get('features');
  if(features.length===1)mapPick(features[0].get('row'),false);
  else if(parkMap.getView().getZoom()<16)parkMap.getView().animate({center:event.coordinate,zoom:parkMap.getView().getZoom()+2,duration:300});
  else mapResults(features.map(f=>f.get('row')));
 });
 loadMapPoints();
}
new ResizeObserver(()=>{initReferenceMap();if(parkMap){parkMap.updateSize();loadMapPoints();}}).observe($('#reference-map'));
for(const program of ['POTA','SOTA'])$('#map-layer-'+program).onchange=()=>{if(pointLayers[program])pointLayers[program].setVisible($('#map-layer-'+program).checked);loadMapPoints();};
$('#map-search-form').onsubmit=action(async event=>{
 event.preventDefault();const q=$('#map-search').value.trim();if(!q)return;
 const id=++mapSearchId,data=await api('portable-map?'+new URLSearchParams({q,programs:mapPrograms().join(',')}));
 if(id===mapSearchId){mapResults(data.items);if(data.items.length===1)mapPick(data.items[0]);}
});
$('#map-use-own').onclick=()=>{
 if(!mapSelected)return;const field=mapSelected.program==='POTA'?'MY_SIG_INFO':'MY_SOTA_REF';
 $('#portable-session').elements[field].value=mapSelected.ref;
 $('#portable-session').scrollIntoView({behavior:'smooth',block:'center'});toast("Referens vald. Tryck på Starta aktivering när du är redo.");
};
$('#map-log-target').onclick=()=>{
 if(!mapSelected)return;openQso();$('#qso-form').elements[mapSelected.program==='POTA'?'SIG_INFO':'SOTA_REF'].value=mapSelected.ref;
};
$('#map-home').onclick=()=>{try{const p=gridPoint(state.settings.grid);if(!p)throw Error();parkMap.getView().animate({center:ol.proj.fromLonLat([p.lon,p.lat]),zoom:9,duration:350});}catch{toast("Ange en lokator under Min station.",true);}};
$('#map-update').onclick=action(async()=>{const b=$('#map-update');b.disabled=true;$('#map-data-status').textContent="Hämtar uppdaterade park- och toppregister …";try{await api('portable-map/update',{});await loadMapPoints();}finally{b.disabled=false;}});
