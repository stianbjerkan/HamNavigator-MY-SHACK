/* Local documentation only; Map actions and shortcut list remain intact. */
document.addEventListener('DOMContentLoaded', () => {
  const nav = document.querySelector('#hn-map-header nav');
  if (!nav || document.getElementById('hn-manual-button')) return;
  const button = document.createElement('button');
  button.id='hn-manual-button'; button.type='button'; button.textContent='Bruksanvisning';
  nav.append(button);
  button.addEventListener('click', () => {
    const dialog=document.createElement('dialog');
    dialog.setAttribute('aria-label','HamNavigator Map – bruksanvisning');
    Object.assign(dialog.style,{width:'min(1080px, 94vw)',height:'90vh',maxWidth:'94vw',maxHeight:'94vh',padding:'0',border:'1px solid #58768b',borderRadius:'10px',background:'#0e1923',color:'#e1edf4'});
    const top=document.createElement('div');
    Object.assign(top.style,{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'12px 16px',gap:'12px'});
    const heading=document.createElement('strong');heading.textContent='HamNavigator Map – bruksanvisning';
    const close=document.createElement('button');close.type='button';close.textContent='Lukk';
    Object.assign(close.style,{padding:'10px 18px',background:'#afe4d4',color:'#10232d',border:'0',borderRadius:'5px',cursor:'pointer'});
    const frame=document.createElement('iframe');frame.title='Søkbar bruksanvisning for HamNavigator Map';
    frame.setAttribute('sandbox','allow-scripts');frame.src='./HamNavigator-Map-bruksanvisning.html';
    Object.assign(frame.style,{width:'100%',height:'calc(100% - 66px)',border:'0',display:'block'});
    close.onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>{dialog.remove();button.focus();},{once:true});
    top.append(heading,close);dialog.append(top,frame);document.body.append(dialog);dialog.showModal();close.focus();
  });
});
