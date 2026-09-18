/* HamNavigator shared delivery queue. Original lookup/test requests are unchanged. */
'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const crypto=require('crypto');
  const text=(value)=>String(value||'').trim();
  const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
  function queue(service,profile,adif,request){
    const path=require('path'),root=path.resolve(process.resourcesPath,'../../..');
    const python=process.env.HAMNAVIGATOR_DELIVERY_PYTHON||path.join(root,'runtime','python.exe'),bridge=process.env.HAMNAVIGATOR_DELIVERY_BRIDGE||path.join(root,'log_delivery.py');
    if(!require('fs').existsSync(python)||!require('fs').existsSync(bridge)){addLastTraffic('<font style="color:orange">Åpne Map fra HamNavigator for felles leveringsstatus.</font>');return;}
    const child=require('child_process').execFile(python,['-E','-s',bridge],{windowsHide:true,timeout:15000,maxBuffer:128000},(error,stdout)=>{
      let result;try{result=JSON.parse(stdout);}catch{result={error:true};}
      if(error||result.error)addLastTraffic('<font style="color:orange">Levering kunne ikke legges i kø. Kontakt lagret lokalt. Se Status og sikkerhetskopi.</font>');
      else addLastTraffic('<font style="color:white">Logglevering registrert i HamNavigator. Se Status og sikkerhetskopi.</font>');
    });
    child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify({service,profile,adif,request}));
  }
  function recognize(url,data){
    const u=new URL(url),adif=data.ADIF||data.adif||data.ADIFData||data.string;
    if(typeof adif!=='string'||!/<EOR>/i.test(adif))return null;
    const q=parseADIFRecord(adif.split(/<EOH>/i).pop()),station=text(q.STATION_CALLSIGN).toUpperCase();
    if(u.hostname==='logbook.qrz.com'&&data.ACTION==='INSERT')return {service:'qrz',profile:station,adif};
    if(u.hostname==='clublog.org'&&u.pathname==='/realtime.php')return {service:'clublog',profile:text(data.callsign),adif};
    if(u.hostname==='www.hrdlog.net'&&u.pathname==='/NewEntry.aspx')return {service:'hrdlog',profile:text(data.Callsign),adif};
    if(['www.hamcq.cn','hamcq.cn','api.hamcq.cn'].includes(u.hostname))return {service:'hamcq',profile:station,adif};
    if(data.type==='adif'&&data.station_profile_id&&u.pathname.endsWith('/index.php/api/qso'))return {service:'cloudlog',profile:hash(url.replace(/\/index.php\/api\/qso$/,'').replace(/\/+$/,'').toLowerCase()+'|'+data.station_profile_id),adif};
    return null;
  }
  const form=getPostBuffer;
  getPostBuffer=function(url,callback,flag,mode,port,data,...rest){const found=recognize(url,data||{});if(!found)return form(url,callback,flag,mode,port,data,...rest);queue(found.service,found.profile,found.adif,{kind:'http',url,type:'application/x-www-form-urlencoded',body:require('querystring').stringify(data)});};
  const json=getPostJSONBuffer;
  getPostJSONBuffer=function(url,callback,flag,mode,port,data,...rest){const found=recognize(url,data||{});if(!found)return json(url,callback,flag,mode,port,data,...rest);queue(found.service,found.profile,found.adif,{kind:'http',url,type:'application/json',body:JSON.stringify(data)});};
  const get=getABuffer;
  getABuffer=function(url,...rest){const u=new URL(url);if(u.hostname.toLowerCase()==='www.eqsl.cc'&&u.pathname.toLowerCase()==='/qslcard/importadif.cfm'&&u.searchParams.has('ADIFData')){
    const adif=u.searchParams.get('ADIFData'),q=parseADIFRecord(adif.split(/<EOH>/i).pop()),nickname=text(q.APP_EQSL_QTH_NICKNAME);queue('eqsl',text(u.searchParams.get('EQSL_USER'))+(nickname?':'+hash(nickname).slice(0,16):''),adif,{kind:'http',method:'GET',url});return;}
    return get(url,...rest);
  };
  sendLotwLogEntry=function(report){if(GT.settings.map.offlineMode||!logLOTWqsoCheckBox.checked||!GT.settings.trustedQsl.binaryFileValid||!GT.settings.trustedQsl.stationFileValid||!lotwStation.value)return;
    const q=parseADIFRecord(report);queue('lotw',text(q.STATION_CALLSIGN),report,{kind:'tqsl',binary:GT.settings.trustedQsl.binaryFile,station:lotwStation.value,password:lotwTrusted.value});
  };
});
