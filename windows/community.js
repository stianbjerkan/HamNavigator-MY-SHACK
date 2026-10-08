/* Shared MY SHACK / website aggregate-only community display. */
(() => {
  'use strict';
  const app = !!document.querySelector('#page-home');
  const host = app ? document.querySelector('#page-home') : document.querySelector('main');
  if (!host || document.querySelector('#hn-community')) return;
  const messages = {
    nb: ['HamNavigator-fellesskapet', 'Registrerte brukere', 'Aktive nå', 'Unike Cloud-kontoer. Aktiv = kontakt siste to minutter. Oppdateres automatisk. Ingen navn vises.', 'Henter brukertall…', 'Brukertall er utilgjengelige akkurat nå.', 'Oppdatert'],
    en: ['HamNavigator community', 'Registered users', 'Active now', 'Unique Cloud accounts. Active = connected within the last two minutes. Updates automatically. No names are displayed.', 'Loading user counts…', 'User counts are currently unavailable.', 'Updated'],
    sv: ['HamNavigator-gemenskapen', 'Registrerade användare', 'Aktiva nu', 'Unika Cloud-konton. Aktiv = kontakt under de senaste två minuterna. Uppdateras automatiskt. Inga namn visas.', 'Hämtar användarantal…', 'Användarantal är inte tillgängligt just nu.', 'Uppdaterat']
  };
  const lang = document.documentElement.lang.split('-')[0];
  const t = messages[lang] || messages.nb;
  const card = document.createElement('section');
  card.id = 'hn-community'; card.className = app ? 'hn-community card' : 'hn-community container';
  card.setAttribute('aria-label', t[0]);
  const heading = document.createElement('h2'); heading.textContent = t[0]; card.append(heading);
  const fields = document.createElement('div'); fields.className = 'hn-community-counts';
  const values = [1, 2].map(i => {
    const field = document.createElement('div'), label = document.createElement('span'), value = document.createElement('strong');
    label.textContent = t[i]; value.textContent = '—'; field.append(label, value); fields.append(field); return value;
  });
  const note = document.createElement('p'); note.textContent = t[3];
  const status = document.createElement('p'); status.className = 'hn-community-status'; status.setAttribute('role', 'status'); status.textContent = t[4];
  card.append(fields, note, status);
  if (app) host.querySelector('.stats-grid').after(card);
  else (host.querySelector('.page-intro') || host.firstElementChild).after(card);
  let busy = false, expires = 0;
  const unavailable = () => { values.forEach(v => v.textContent = '—'); status.textContent = t[5]; expires = 0; };
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(app ? '/api/community' : '/cloud/community', {cache: 'no-store', credentials: 'omit', signal: controller.signal});
      if (!response.ok) throw new Error('Unavailable');
      const data = await response.json();
      if (data.available !== true || !Number.isInteger(data.registered) || !Number.isInteger(data.active) ||
          data.active < 0 || data.registered < data.active || data.registered > 1000000000 ||
          !Number.isInteger(data.sample_age) || data.sample_age < 0 || data.sample_age >= 75 || data.active_seconds !== 120) throw new Error('Invalid counts');
      values[0].textContent = data.registered.toLocaleString(lang);
      values[1].textContent = data.active.toLocaleString(lang);
      expires = Date.now() + (75-data.sample_age)*1000;
      status.textContent = `${t[6]} ${new Date(Date.now()-data.sample_age*1000).toLocaleTimeString(lang)}`;
    } catch (_) { unavailable(); }
    finally { clearTimeout(timer); busy = false; }
  }
  setInterval(refresh, 30000);
  setInterval(() => { if (expires && Date.now() >= expires) unavailable(); }, 1000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { if (expires && Date.now() >= expires) unavailable(); refresh(); } });
  refresh();
})();
