[Code]
function HNInstallerText(NorwegianText, EnglishText, SwedishText: String): String;
begin
  if ActiveLanguage = 'norwegian' then Result := NorwegianText
  else if ActiveLanguage = 'swedish' then Result := SwedishText
  else Result := EnglishText;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PythonExe, Params: String;
  Code: Integer;
begin
  Result := '';
  PythonExe := ExpandConstant('{app}\runtime\python.exe');
  if not FileExists(PythonExe) then exit;
  WizardForm.PreparingLabel.Caption := HNInstallerText('Lagrer og lukker HamNavigator, Digital og Map ...', 'Saving and closing HamNavigator, Digital and Map ...', 'Sparar och stänger HamNavigator, Digital och Map ...');
  ExtractTemporaryFile('prepare_update.py');
  Params := '-E -s "' + ExpandConstant('{tmp}\prepare_update.py') + '" "' + ExpandConstant('{app}') + '"';
  if not Exec(PythonExe, Params, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := HNInstallerText('Kunne ikke starte normal avslutning av HamNavigator. Lukk programmet og prøv igjen.', 'Could not start a normal shutdown of HamNavigator. Close the program and try again.', 'Kunde inte starta normal avslutning av HamNavigator. Stäng programmet och försök igen.');
  if (Result = '') and (Code <> 0) then
    Result := HNInstallerText('HamNavigator er ikke ferdig med å lagre og lukke. Fullfør eventuelle dialoger i programmet og prøv igjen. Ingen programfiler er erstattet.', 'HamNavigator has not finished saving and closing. Complete any dialogs in the program and try again. No program files have been replaced.', 'HamNavigator är inte klart med att spara och stänga. Slutför eventuella dialoger i programmet och försök igen. Inga programfiler har ersatts.');
end;
