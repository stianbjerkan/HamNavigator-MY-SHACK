using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Diagnostics;
using System.IO;

namespace RadioLog;

public sealed class LogSyncService
{
    readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(15) };
    public event Action<string>? Status;

    public LogSyncService() => http.DefaultRequestHeaders.UserAgent.ParseAdd("HamNavigator/1.0 (Stian Bjerkan)");

    public static string Adif(Qso q, string stationCall)
    {
        string F(string n,string v)=>string.IsNullOrWhiteSpace(v)?"":$"<{n}:{v.Length}>{v}";
        return F("QSO_DATE",q.TimeUtc.ToString("yyyyMMdd"))+F("TIME_ON",q.TimeUtc.ToString("HHmmss"))+F("CALL",q.Call)+F("STATION_CALLSIGN",stationCall)+F("MODE",q.Mode)+F("BAND",q.Band)+F("FREQ",q.FrequencyMhz>0?q.FrequencyMhz.ToString("0.######",System.Globalization.CultureInfo.InvariantCulture):"")+F("RST_SENT",q.RstSent)+F("RST_RCVD",q.RstReceived)+F("GRIDSQUARE",q.Grid)+F("SIG",q.Program)+F("SIG_INFO",q.Reference)+"<EOR>";
    }

    public async Task UploadAsync(Qso q, Settings s)
    {
        if(!s.AutoUpload) return;
        var adif=Adif(q,s.MyCall);
        var jobs=new List<Task>();
        if(s.SyncQrz&&!string.IsNullOrWhiteSpace(s.QrzApiKey)) jobs.Add(PostQrz(adif,s.QrzApiKey));
        if(s.SyncCloudlog&&!string.IsNullOrWhiteSpace(s.CloudlogUrl)) jobs.Add(PostCloudlog(adif,s));
        if(s.SyncClubLog) jobs.Add(PostClubLog(adif,s));
        if(s.SyncHrdLog) jobs.Add(PostHrdLog(adif,s));
        if(s.SyncEqsl) jobs.Add(PostEqsl(adif,s));
        if(s.SyncHamQth) jobs.Add(PostHamQth(adif,s));
        if(s.SyncLotw) jobs.Add(PostLotw(adif,s));
        if(s.SyncUdp) jobs.Add(SendUdp(adif,s.SyncUdpPort));
        if(s.SyncLog4Om) jobs.Add(SendUdp(adif,2236));
        if(s.SyncN3fjp) jobs.Add(SendUdp(adif,1100));
        if(s.SyncDxKeeper) jobs.Add(SendUdp(adif,52000));
        if(s.SyncHrdLocal) jobs.Add(SendUdp(adif,7826));
        if(jobs.Count==0){Status?.Invoke("Autolasting er på, men ingen ferdig konfigurert tjeneste er valgt.");return;}
        await Task.WhenAll(jobs);
    }

    async Task PostQrz(string adif,string key)
    {
        try{using var body=new FormUrlEncodedContent(new Dictionary<string,string>{{"KEY",key},{"ACTION","INSERT"},{"ADIF",adif}});var response=await http.PostAsync("https://logbook.qrz.com/api",body);var text=await response.Content.ReadAsStringAsync();Status?.Invoke(response.IsSuccessStatusCode&&text.Contains("RESULT=OK",StringComparison.OrdinalIgnoreCase)?"QRZ: QSO lastet opp":"QRZ: "+text[..Math.Min(120,text.Length)]);}
        catch(Exception ex){Status?.Invoke("QRZ-feil: "+ex.Message);}
    }

    async Task PostCloudlog(string adif,Settings s)
    {
        try{var url=s.CloudlogUrl.TrimEnd('/')+"/index.php/api/qso";var json=JsonSerializer.Serialize(new{key=s.CloudlogApiKey,station_profile_id=s.CloudlogStationId,type="adif",@string=adif});using var body=new StringContent(json,Encoding.UTF8,"application/json");var response=await http.PostAsync(url,body);Status?.Invoke(response.IsSuccessStatusCode?"Cloudlog/Wavelog: QSO sendt":"Cloudlog/Wavelog: HTTP "+(int)response.StatusCode);}
        catch(Exception ex){Status?.Invoke("Cloudlog-feil: "+ex.Message);}
    }

    async Task SendUdp(string adif,int port)
    {
        try{using var udp=new UdpClient();var bytes=Encoding.UTF8.GetBytes(adif);await udp.SendAsync(bytes,bytes.Length,new IPEndPoint(IPAddress.Loopback,Math.Clamp(port,1,65535)));Status?.Invoke($"Lokal UDP: QSO sendt til 127.0.0.1:{port}");}
        catch(Exception ex){Status?.Invoke("UDP-feil: "+ex.Message);}
    }

    async Task PostClubLog(string adif,Settings s)=>await PostForm("Club Log","https://clublog.org/realtime.php",new(){{"email",s.ClubLogEmail},{"password",s.ClubLogPassword},{"callsign",s.MyCall},{"adif",adif}});
    async Task PostHrdLog(string adif,Settings s)=>await PostForm("HRDLOG.net","https://www.hrdlog.net/NewEntry.aspx",new(){{"Callsign",s.HrdLogCall},{"Code",s.HrdLogCode},{"App","HamNavigator"},{"ADIFData",adif}});
    async Task PostEqsl(string adif,Settings s)=>await PostForm("eQSL.cc","https://www.eqsl.cc/qslcard/importADIF.cfm",new(){{"EQSL_USER",s.EqslUser},{"EQSL_PSWD",s.EqslPassword},{"ADIFData",adif}});
    async Task PostHamQth(string adif,Settings s)=>await PostForm("HamQTH","https://www.hamqth.com/qso_realtime.php",new(){{"u",s.HamQthUser},{"p",s.HamQthPassword},{"adif",adif},{"prg","HamNavigator"}});
    async Task PostForm(string name,string url,Dictionary<string,string> values){try{using var body=new FormUrlEncodedContent(values);var r=await http.PostAsync(url,body);var t=await r.Content.ReadAsStringAsync();Status?.Invoke(r.IsSuccessStatusCode?$"{name}: svar mottatt ({t[..Math.Min(70,t.Length)]})":$"{name}: HTTP {(int)r.StatusCode}");}catch(Exception ex){Status?.Invoke(name+"-feil: "+ex.Message);}}
    async Task PostLotw(string adif,Settings s){try{if(string.IsNullOrWhiteSpace(s.TqslPath)||!File.Exists(s.TqslPath)){Status?.Invoke("LoTW: TQSL-programmet ble ikke funnet.");return;}var file=Path.Combine(Path.GetTempPath(),$"hamnavigator-{Guid.NewGuid():N}.adi");await File.WriteAllTextAsync(file,adif);var p=Process.Start(new ProcessStartInfo(s.TqslPath,$"-d -u \"{file}\""){UseShellExecute=false,CreateNoWindow=true});if(p!=null)await p.WaitForExitAsync();File.Delete(file);Status?.Invoke(p?.ExitCode==0?"LoTW: QSO sendt gjennom TQSL":"LoTW: TQSL returnerte feil");}catch(Exception ex){Status?.Invoke("LoTW-feil: "+ex.Message);}}

    public async Task<string> TestQrz(string key)
    {
        if(string.IsNullOrWhiteSpace(key)) return "Skriv inn QRZ API-nøkkel.";
        try{using var body=new FormUrlEncodedContent(new Dictionary<string,string>{{"KEY",key},{"ACTION","STATUS"}});var r=await http.PostAsync("https://logbook.qrz.com/api",body);var t=await r.Content.ReadAsStringAsync();return "QRZ: "+t[..Math.Min(180,t.Length)];}catch(Exception ex){return "QRZ-feil: "+ex.Message;}
    }

    public async Task<string> TestService(string name, Settings s)
    {
        string? missing=name switch
        {
            "ClubLog" when string.IsNullOrWhiteSpace(s.ClubLogEmail)||string.IsNullOrWhiteSpace(s.ClubLogPassword)=>"e-mail/password",
            "HRDLOG" when string.IsNullOrWhiteSpace(s.HrdLogCall)||string.IsNullOrWhiteSpace(s.HrdLogCode)=>"call sign/upload code",
            "eQSL" when string.IsNullOrWhiteSpace(s.EqslUser)||string.IsNullOrWhiteSpace(s.EqslPassword)=>"username/password",
            "HamQTH" when string.IsNullOrWhiteSpace(s.HamQthUser)||string.IsNullOrWhiteSpace(s.HamQthPassword)=>"username/password",
            _=>null
        };
        if(missing!=null)return $"{name}: missing {missing}.";
        if(name=="UDP")
        {
            try{using var udp=new UdpClient();var data=Encoding.UTF8.GetBytes("HamNavigator connection test");await udp.SendAsync(data,data.Length,new IPEndPoint(IPAddress.Loopback,Math.Clamp(s.SyncUdpPort,1,65535)));return $"Local UDP test sent to 127.0.0.1:{s.SyncUdpPort}.";}catch(Exception ex){return "UDP test error: "+ex.Message;}
        }
        if(name=="LoTW")
        {
            if(string.IsNullOrWhiteSpace(s.TqslPath)||!File.Exists(s.TqslPath))return "LoTW: tqsl.exe was not found at the selected path.";
            try{var p=Process.Start(new ProcessStartInfo(s.TqslPath,"--version"){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true});if(p==null)return "LoTW: TQSL could not be started.";await p.WaitForExitAsync();return p.ExitCode==0?"LoTW: TQSL installation test passed.":$"LoTW: TQSL returned exit code {p.ExitCode}.";}catch(Exception ex){return "LoTW test error: "+ex.Message;}
        }
        string url=name switch{"ClubLog"=>"https://clublog.org/","HRDLOG"=>"https://www.hrdlog.net/","eQSL"=>"https://www.eqsl.cc/","HamQTH"=>"https://www.hamqth.com/",_=>""};
        try{using var response=await http.GetAsync(url,HttpCompletionOption.ResponseHeadersRead);return response.IsSuccessStatusCode?$"{name}: connection and required fields test passed.":$"{name}: server responded HTTP {(int)response.StatusCode}.";}catch(Exception ex){return $"{name} test error: {ex.Message}";}
    }

    public async Task<string> TestCloudlog(Settings s)
    {
        if(string.IsNullOrWhiteSpace(s.CloudlogUrl))return "Enter the Cloudlog/Wavelog address.";
        if(string.IsNullOrWhiteSpace(s.CloudlogApiKey))return "Enter the Cloudlog/Wavelog API key.";
        try{using var response=await http.GetAsync(s.CloudlogUrl,HttpCompletionOption.ResponseHeadersRead);return response.IsSuccessStatusCode?"Cloudlog/Wavelog: server connection passed; API settings are present.":$"Cloudlog/Wavelog: server responded HTTP {(int)response.StatusCode}.";}catch(Exception ex){return "Cloudlog/Wavelog test error: "+ex.Message;}
    }
}
