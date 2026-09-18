const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const source=path.resolve(__dirname,'../packaging/map_delivery.js');
let callback,legacy=0,requests=[],traffic=[];
const c={URL,process:{env:{HAMNAVIGATOR_DELIVERY_PYTHON:'python',HAMNAVIGATOR_DELIVERY_BRIDGE:'bridge'},resourcesPath:'C:/HN/release/Map/resources'},
 document:{addEventListener:(name,fn)=>{callback=fn;}},require:name=>{
  if(name==='fs')return {existsSync:()=>true};
  if(name==='child_process')return {execFile:(exe,args,options,done)=>{assert(options.windowsHide);assert.deepEqual(args,['-E','-s','bridge']);return {stdin:{on:()=>{},end:data=>{requests.push(JSON.parse(data));done(null,'{"id":"synthetic"}');}}};}};
  return require(name);
 },addLastTraffic:x=>traffic.push(x),parseADIFRecord:adif=>{const q={};const r=/<([A-Z_]+):(\d+)>([^<]*)/g;let m;while((m=r.exec(adif)))q[m[1]]=m[3].slice(0,+m[2]);return q;},
 getPostBuffer:()=>legacy++,getPostJSONBuffer:()=>legacy++,getABuffer:()=>legacy++,sendLotwLogEntry:()=>legacy++,
 GT:{settings:{map:{},trustedQsl:{binaryFileValid:true,stationFileValid:true,binaryFile:'tqsl.exe'}}},logLOTWqsoCheckBox:{checked:true},lotwStation:{value:'Home'},lotwTrusted:{value:'private-canary'}};
vm.createContext(c);vm.runInContext(fs.readFileSync(source,'utf8'),c);callback();
const adif='<CALL:6>LA1ABC<QSO_DATE:8>20260914<TIME_ON:6>120000<STATION_CALLSIGN:6>LA2ABC<EOR>';
c.getPostBuffer('https://logbook.qrz.com/api',null,null,'https',443,{KEY:'private-canary',ACTION:'INSERT',ADIF:adif});
c.getPostBuffer('https://logbook.qrz.com/api',null,null,'https',443,{KEY:'private-canary',ACTION:'STATUS'});
c.getPostJSONBuffer('https://own.invalid/index.php/api/qso',null,null,'https',443,{key:'private-canary',station_profile_id:1,type:'adif',string:adif});
c.getABuffer('https://www.eqsl.cc/qslcard/importADIF.cfm?EQSL_USER=LA2ABC&EQSL_PSWD=private-canary&ADIFData='+encodeURIComponent('<PROGRAMID:2>HN<EOH>'+adif));
c.sendLotwLogEntry(adif);
assert.equal(legacy,1);assert.deepEqual(requests.map(x=>x.service),['qrz','cloudlog','eqsl','lotw']);assert.equal(requests[0].profile,'LA2ABC');assert.equal(requests[2].profile,'LA2ABC');assert(!traffic.join().includes('private-canary'));assert.equal(requests[1].profile,require('crypto').createHash('sha256').update('https://own.invalid|1').digest('hex'));
console.log('PASS: Map queue interception, credential tests untouched, EQSL header, Cloud profile identity, hidden bridge, no credential status and no external requests.');
