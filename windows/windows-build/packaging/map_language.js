/* Local UI language only. Fixed application labels are separate from user content. */
'use strict';
(() => {
  const fs=require('fs'),path=require('path');
  const folder=process.env.RADIOASSISTENT_DATA||path.join(process.env.APPDATA,'Radioassistent');
  const file=path.join(folder,'ui-language.json');
  let code=process.env.HAMNAVIGATOR_LANGUAGE;
  if(!['en','nb','sv'].includes(code))try{code=JSON.parse(fs.readFileSync(file,'utf8')).language;}catch{}
  window.hnLanguage=code==='sv'?'sv':code==='en'?'en':'nb';window.hnEnglish=window.hnLanguage==='en';
  const labels={
    'Min stasjon':'My station','⌖ Min stasjon':'⌖ My station','Projeksjon':'Projection','Kallesignaler':'Callsigns','Fest punkt':'Place pin','Rutenett':'Grid','Statistikk':'Statistics','Grålinje':'Grey line','Månen':'Moon','Snarveier':'Shortcuts','Varsellyd':'Alert sound','Oppsett':'Settings','Importer logg':'Import log','Les lokal logg':'Read local log','Tidssoner':'Time zones','Lokatorlag':'Grid overlay','Spottere':'Spotters','Åpne':'Open','‹ Tilbake':'‹ Back',
    'Stasjon og tilkobling':'Station and connection','Arbeidsflyt':'Workflow','Kallesignaloppslag':'Callsign lookup','Lyd og tale':'Audio and speech','Kartvisning':'Map display','Lokatorruter':'Grid squares','Loggintegrasjoner':'Log integrations','Lydvarsler':'Audio alerts','Egne varsler':'Custom alerts','Loggbok':'Logbook','Om HamNavigator':'About HamNavigator',
    'Bruksanvisning':'User guide','HamNavigator Map – bruksanvisning':'HamNavigator Map – user guide','Lukk':'Close','Søkbar bruksanvisning for HamNavigator Map':'Searchable user guide for HamNavigator Map',
    'Åpne Map fra HamNavigator for felles leveringsstatus.':'Open Map from HamNavigator for shared delivery status.',
    'Levering kunne ikke legges i kø. Kontakt lagret lokalt. Se Status og sikkerhetskopi.':'Could not queue delivery. The contact is saved locally. See Status and backup.',
    'Logglevering registrert i HamNavigator. Se Status og sikkerhetskopi.':'Log delivery registered in HamNavigator. See Status and backup.'
  };
  const swedish=/* HN_SWEDISH_CATALOG */{};
  window.hnText=source=>window.hnLanguage==='sv'?(swedish[labels[source]||source]||source):window.hnEnglish?(labels[source]||source):source;
  document.addEventListener('DOMContentLoaded',()=>{
    const header=document.querySelector('#hn-map-header');if(!header)return;
    const nav=header.querySelector('nav');
    if(window.hnLanguage!=='nb'){
      const subtitle=header.querySelector('.hn-map-brand span');if(subtitle)subtitle.textContent=window.hnLanguage==='sv'?'KARTA / STATIONSÖVERSIKT':'MAP / STATION OVERVIEW';
      nav.setAttribute('aria-label',window.hnLanguage==='sv'?'Huvudverktyg':'Main tools');
      for(const button of nav.querySelectorAll('button'))button.textContent=window.hnText(button.textContent);
    }
    const button=document.createElement('button');button.textContent='Språk / Language';button.id='hn-language-button';nav.append(button);
    button.onclick=()=>{
      const dialog=document.createElement('dialog');dialog.setAttribute('aria-label','Språk / Language');
      Object.assign(dialog.style,{background:'#102332',color:'#eef5ff',border:'1px solid #6c96ad',borderRadius:'10px',maxWidth:'500px',padding:'24px'});
      const title=document.createElement('h2');title.textContent='Språk / Language';
      const select=document.createElement('select');select.setAttribute('aria-label','Språk / Language');
      for(const [value,label] of [['nb','Norsk (bokmål)'],['en','English'],['sv','Svenska']]){const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);}
      select.value=window.hnLanguage;
      const note=document.createElement('p');note.textContent=window.hnLanguage==='sv'?'Språket gäller HamNavigator, MY SHACK och Map. Spara, stoppa sändningen och starta om HN.':window.hnEnglish?'The language applies to HamNavigator, MY SHACK and Map. Save, stop transmission and restart HN.':'Språket gjelder HamNavigator, MY SHACK og Map. Lagre, stopp sending og start HN på nytt.';
      const status=document.createElement('p');status.setAttribute('role','status');
      const save=document.createElement('button');save.textContent=window.hnLanguage==='sv'?'Spara språk':window.hnEnglish?'Save language':'Lagre språk';
      const close=document.createElement('button');close.textContent=window.hnText('Lukk');close.onclick=()=>dialog.close();
      save.onclick=()=>{
        const temporary=file+'.'+require('crypto').randomBytes(6).toString('hex')+'.tmp';
        try{
          fs.mkdirSync(folder,{recursive:true});fs.writeFileSync(temporary,JSON.stringify({language:select.value}),{encoding:'utf8',flag:'wx'});fs.renameSync(temporary,file);
          status.textContent=select.value==='sv'?'Sparat. Stoppa sändningen och starta om HN.':select.value==='en'?'Saved. Stop transmission and restart HN.':'Lagret. Stopp sending og start HN på nytt.';
        }catch{status.textContent=window.hnLanguage==='sv'?'Språket kunde inte sparas. Försök igen i MY SHACK.':window.hnEnglish?'Could not save the language. Try again in MY SHACK.':'Språket kunne ikke lagres. Prøv igjen i MY SHACK.';}
        finally{try{fs.unlinkSync(temporary);}catch{}}
      };
      dialog.append(title,select,note,save,close,status);document.body.append(dialog);
      dialog.addEventListener('close',()=>{dialog.remove();button.focus();},{once:true});dialog.showModal();select.focus();
    };
  });
})();
