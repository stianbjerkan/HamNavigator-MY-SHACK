# HamNavigator: enklere drift

PC 1.9.11, Mobile 0.5.0 og privat Cloud-server 0.6.2.

## Status og sikkerhetskopi

Åpne **Status og sikkerhetskopi** i PC-menyen eller mobilens meny øverst til
høyre. Du får kontaktantall, ventende Cloud-endringer, tidspunkt for siste
synkronisering og egne enheter. Enhetslisten krever server 0.6.2. «Nylig aktiv»
betyr at serveren har hørt fra enheten de siste to minuttene; det er ikke en
bekreftelse på at en person sitter ved radioen. Hver konto ser bare egne enheter.

Søk etter kallesignal eller UTC-dato for å se Cloud-status og leveringskvitteringer.
«Bekreftet lagret» gjelder kvittering fra loggtjenesten eller manuell kontroll.
Det er ikke QSL fra motstasjonen. En eldre kontakt uten kvittering kan allerede
finnes hos mottakeren. Historiske leveringer blir ikke merket levert uten bevis.

## Levering til loggtjenester

Nye PC Map-leveringer legges i en lokal, kryptert kø. Etter at kontakten er
synkronisert, hentes én sendetillatelse fra Cloud. PC og mobil deler denne
kontrollen, slik at en kontakt som allerede er levert til samme tjenestekonto
ikke sendes på nytt. Køen behandles mens HamNavigator kjører og kontoen er
innlogget. Når automatisk Cloud-synkronisering er avslått, må nye kontakter
synkroniseres manuelt før de kan leveres.

Ved mistet forbindelse etter sendestart står resultatet som ukjent. Kontroller
akkurat kontakten i mottakerens logg, velg **Avklar levering** og oppgi om den
finnes der. Et nytt forsøk tillates bare etter dette valget. Nyere kvitteringer
eller en pågående sending kan ikke overskrives med et gammelt valg.

QRZ, Club Log, eQSL og Cloudlog/Wavelog har egne kontroller for positive svar.
TQSL-opplasting vises som sendt til LoTW; behandling/QSL må kontrolleres hos LoTW.
HRDLOG og HamCQ-opplastinger uten en entydig lagringskvittering vises som ukjent.
Club Logs realtime-kø brukes ikke til gamle kontakter; bruk historisk import.
Cloud videresender ikke loggdata til tjenestene. Leveringen skjer fra klienten.
Denne utgaven legger ikke til direkte mobilopplasting til LoTW, HRDLOG eller HamCQ.

## Radioveiviser på Android

Velg **Radioveiviser** i menyen. Fem trinn hjelper med radiomodell, CAT/PTT,
USB-mottakslyd, USB-sendelydutgang og kontroll før bruk. CAT/PTT-testen sender
bare PTT AV. Lydutgangstesten bruker stillhet. Veiviseren starter aldri Auto TX
eller en RF-test. Modell, USB og lydvalg er fortsatt lokale for hver enhet.

## Feilhistorikk og gjenoppretting

Feilhistorikken beholdes ved omstart og samler gjentatte feil. **Kopier
feilsøkingsinformasjon** kopierer teknisk status og faste feilmeldinger uten
kontonavn, passord, API-nøkler eller leveringsinnhold.

Sikkerhetskopier viser dato, antall og hvor mange manglende kontakter som kan
hentes. Gjenoppretting tar først en lokal kopi, legger bare til manglende
kontakter og beholder nåværende kontakter, nyere endringer og innstillinger.
Den starter ingen historiske opplastinger til loggtjenester. Cloud-kopier velges
bare innenfor innlogget konto. Eldre mobilkopier uten sikker kontotilknytning
beholdes på enheten, men velges ikke automatisk.

## Oppdatering

Oppdater først Cloud til 0.6.2 med serverens private oppdateringsknapp, deretter
PC til 1.9.11 og mobil/nettbrett til 0.5.0. Konto og lokale data beholdes.
Serverpakken og serverkoden er private. Mobilen støtter Android 7.1 og nyere.
Ikke avinstaller mobilen for å oppgradere.
