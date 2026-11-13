/* The signed-in MY SHACK overview. The public community counter is separate. */
(() => {
  'use strict';
  const home = document.querySelector('#page-home');
  if (!home) return;
  const words = {
    nb: ['Pålogget nå', 'Kallesignaler fra brukere som har valgt å vises og har hatt kontakt med Cloud de siste to minuttene.', 'Vis mitt kallesignal', 'Angi kallesignal i Min stasjon for å bli synlig.', 'Ingen har valgt å vises blant brukerne som er aktive nå.', 'Henter kallesignaler …', 'Listen er utilgjengelig. Prøver igjen automatisk.', 'Cloud-serveren må oppdateres til 0.6.4 eller nyere.', 'Neste', 'Til første side', 'Vises som', 'Oppdater kallesignal', 'Endringen kunne ikke bekreftes. Kontroller status før du prøver igjen.'],
    en: ['Online now', 'Callsigns of users who opted in and contacted Cloud within the last two minutes.', 'Show my callsign', 'Set your callsign in My station to appear here.', 'No active users have chosen to share their callsign.', 'Loading callsigns …', 'The list is unavailable. Retrying automatically.', 'Update the Cloud server to 0.6.4 or later.', 'Next', 'First page', 'Listed as', 'Update callsign', 'The change could not be confirmed. Check the status before trying again.'],
    sv: ['Inloggade nu', 'Anropssignaler för användare som har valt att synas och haft kontakt med Cloud de senaste två minuterna.', 'Visa min anropssignal', 'Ange din anropssignal under Min station för att synas här.', 'Ingen aktiv användare har valt att visa sin anropssignal.', 'Hämtar anropssignaler …', 'Listan är inte tillgänglig. Ett nytt försök görs automatiskt.', 'Uppdatera Cloud-servern till 0.6.4 eller senare.', 'Nästa', 'Första sidan', 'Visas som', 'Uppdatera anropssignal', 'Ändringen kunde inte bekräftas. Kontrollera statusen innan du försöker igen.']
  };
  const t = words[document.documentElement.lang.split('-')[0]] || words.nb;
  const card = document.createElement('section');
  card.id = 'online-callsigns';
  card.className = 'hn-community card';
  card.hidden = true;
  card.setAttribute('aria-labelledby', 'online-heading');
  card.innerHTML = '<h2 id="online-heading"></h2><p class="online-intro"></p><ul></ul><p role="status"></p><div class="online-pages"><button type="button" class="secondary" hidden></button><button type="button" class="secondary" hidden></button></div><label class="online-choice"><input type="checkbox" disabled> <span></span></label><small></small> <button class="secondary online-update" hidden></button>';
  (home.querySelector('#hn-community') || home.querySelector('.stats-grid')).after(card);
  const list = card.querySelector('ul'), status = card.querySelector('[role=status]');
  const toggle = card.querySelector('input'), label = card.querySelector('label span'), hint = card.querySelector('small');
  const [first, next] = card.querySelectorAll('.online-pages button');
  const update = card.querySelector('.online-update');
  card.querySelector('h2').textContent = t[0];
  card.querySelector('.online-intro').textContent = t[1];
  label.textContent = t[2]; first.textContent = t[9]; next.textContent = t[8]; update.textContent = t[11];
  let account = '', generation = 0, busy = false, after = '', last = '', station = '', own = '', updated = 0;
  const visible = () => !!account && !document.hidden && home.classList.contains('active');
  function clear() {
    list.replaceChildren(); first.hidden = true; next.hidden = true; update.hidden = true;
    toggle.disabled = true; toggle.checked = false; hint.textContent = ''; label.textContent = t[2];
    status.textContent = ''; own = ''; station = ''; last = ''; updated = 0;
  }
  async function refresh(change) {
    if (!visible() || busy) return;
    const current = generation;
    busy = true;
    toggle.disabled = true; update.disabled = true; next.disabled = true; first.disabled = true;
    try {
      const data = await api('cloud/online', {account: JSON.parse(account), after, ...change});
      if (current !== generation) return;
      if (data.station_changed) {
        after = ''; clear(); status.textContent = t[12];
        return;
      }
      if (!data.supported) {clear(); status.textContent = t[7]; return;}
      own = data.own_call; station = data.station_call; updated = Date.now();
      const validStation = /^(?=.{3,32}$)(?=.*[0-9])(?=.*[A-Z])[A-Z0-9]+(?:\/[A-Z0-9]+)*$/.test(station);
      toggle.checked = !!own; toggle.disabled = !own && !validStation;
      label.textContent = t[2] + (own || validStation ? ' (' + (own || station) + ')' : '');
      hint.textContent = own ? t[10] + ' ' + own : validStation ? '' : t[3];
      update.hidden = !own || !validStation || own === station;
      list.replaceChildren(...data.callsigns.map(call => {
        const item = document.createElement('li'); item.textContent = call; return item;
      }));
      last = data.callsigns.at(-1) || '';
      first.hidden = !after; next.hidden = !data.more || !last;
      status.textContent = !last && !after ? t[4] : '';
    } catch (_) {
      if (current === generation) {after = ''; clear(); status.textContent = change ? t[12] : t[6];}
    } finally {
      if (current === generation) {
        busy = false; first.disabled = false; next.disabled = false; update.disabled = false;
      }
    }
  }
  function reset() {
    generation++; busy = false; after = ''; clear();
    card.hidden = !account;
    if (visible()) {status.textContent = t[5]; refresh();}
  }
  window.addEventListener('hamnavigator-cloud-state', ({detail}) => {
    const identity = detail.authorized ? detail.account : '';
    if (account !== identity) {account = identity; reset();}
  });
  function poll() {
    if (!visible()) return;
    if (updated && Date.now() - updated >= 60000) {clear(); status.textContent = t[5];}
    refresh();
  }
  document.addEventListener('hamnavigator-page-changed', ({detail}) => {
    if (detail.page === 'home') poll();
  });
  document.addEventListener('visibilitychange', poll);
  first.onclick = () => {after = ''; refresh();};
  next.onclick = () => {after = last; refresh();};
  toggle.onchange = () => {
    const checked = toggle.checked;
    toggle.checked = !!own;
    after = '';
    refresh({share: checked, callsign: checked ? station : ''});
  };
  update.onclick = () => {after = ''; refresh({share: true, callsign: station});};
  setInterval(poll, 30000);
})();
