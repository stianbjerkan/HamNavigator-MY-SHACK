using System.Net.Http;
using System.Text.Json;
using System.IO;

namespace RadioLog;

public sealed class ActivationFeeds
{
    static readonly HttpClient Http = Create();
    static HttpClient Create(){var h=new HttpClient{Timeout=TimeSpan.FromSeconds(15)};h.DefaultRequestHeaders.UserAgent.ParseAdd("HamNavigator/1.0 amateur-radio-client");return h;}
    public async Task<List<Activation>> RefreshAsync()
    {
        var jobs=new[]{Load("POTA","https://api.pota.app/spot/activator"),LoadSotaLiveSpots(),LoadSotaLiveAlerts(),LoadPotaCatalog(),LoadSotaCatalog(),LoadBotaCatalog(),LoadBota()};
        var sets=await Task.WhenAll(jobs);return sets.SelectMany(x=>x).GroupBy(x=>$"{x.Program}|{x.Reference}").Select(x=>x.First()).ToList();
    }
    async Task<List<Activation>> LoadPotaCatalog()=>await LoadCsv("POTA","https://pota.app/all_parks_ext.csv","pota-world.csv","reference","name","latitude","longitude");
    async Task<List<Activation>> LoadBotaCatalog()=>await LoadCsv("BOTA","https://api.wwbota.org/bunkers/?format=CSV","wwbota-world.csv","Reference","Name","Lat","Long");
    async Task<List<Activation>> LoadSotaCatalog()=>await LoadCsv("SOTA","https://storage.sota.org.uk/summitslist.csv","sota-world.csv","SummitCode","SummitName","Latitude","Longitude",1);
    async Task<List<Activation>> LoadSotaLiveSpots()=>await LoadSotaLive("https://api2.sota.org.uk/api/spots/-1/all/all/","LIVE SPOT");
    async Task<List<Activation>> LoadSotaLiveAlerts()=>await LoadSotaLive("https://api2.sota.org.uk/api/alerts","ALERT");
    async Task<List<Activation>> LoadSotaLive(string url,string type)
    {
        try
        {
            using var stream=await Http.GetStreamAsync(url);using var doc=await JsonDocument.ParseAsync(stream);var root=doc.RootElement;if(root.ValueKind==JsonValueKind.Object&&(Try(root,"spots",out var a)||Try(root,"alerts",out a)||Try(root,"data",out a)))root=a;if(root.ValueKind!=JsonValueKind.Array)return[];var result=new List<Activation>();
            foreach(var e in root.EnumerateArray())
            {
                if(Text(e,"type").Equals("QRT",StringComparison.OrdinalIgnoreCase)||Text(e,"comments","comment").Trim().Equals("QRT",StringComparison.OrdinalIgnoreCase))continue;string reference=Text(e,"summitCode","reference","summit").Trim().ToUpperInvariant();double lat=Number(e,"latitude","lat"),lon=Number(e,"longitude","lon","lng");if(string.IsNullOrWhiteSpace(reference)||(lat==0&&lon==0))continue;string call=Text(e,"activatorCallsign","callsign","station"),freq=Value(e,"frequency"),mode=Text(e,"mode"),comments=Text(e,"comments","comment"),time=Text(e,"timeStamp","dateTime","dateActivated");string detail=string.Join(" • ",new[]{call,string.IsNullOrWhiteSpace(freq)?"":freq+" MHz",mode,time,comments}.Where(x=>!string.IsNullOrWhiteSpace(x)));
                result.Add(new Activation{Program="SOTA",Reference=reference,Name=$"{type} • {detail}",Latitude=lat,Longitude=lon,IsLive=true,ActivityType=type,Notes=comments});
            }return result;
        }catch{return[];}
    }
    async Task<List<Activation>> LoadCsv(string program,string url,string cacheName,string refField,string nameField,string latField,string lonField,int skip=0)
    {
        try
        {
            string text=await CachedText(url,cacheName);var lines=text.Split('\n');if(lines.Length<=skip+1)return[];var header=Csv(lines[skip]);int ri=Find(header,refField),ni=Find(header,nameField),lai=Find(header,latField),loi=Find(header,lonField);if(ri<0||lai<0||loi<0)return[];var result=new List<Activation>(lines.Length);
            for(int i=skip+1;i<lines.Length;i++){var c=Csv(lines[i]);if(c.Count<=Math.Max(Math.Max(ri,ni),Math.Max(lai,loi)))continue;if(!double.TryParse(c[lai],System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out var lat)||!double.TryParse(c[loi],System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out var lon)||(lat==0&&lon==0))continue;result.Add(new Activation{Program=program,Reference=c[ri],Name=ni>=0?c[ni]:"",Latitude=lat,Longitude=lon});}return result;
        }catch{return[];}
    }
    static int Find(List<string> h,string n)=>h.FindIndex(x=>x.Trim().Equals(n,StringComparison.OrdinalIgnoreCase));
    static List<string> Csv(string line){var r=new List<string>();var s=new System.Text.StringBuilder();bool q=false;for(int i=0;i<line.Length;i++){char ch=line[i];if(ch=='"'){if(q&&i+1<line.Length&&line[i+1]=='"'){s.Append('"');i++;}else q=!q;}else if(ch==','&&!q){r.Add(s.ToString());s.Clear();}else if(ch!='\r')s.Append(ch);}r.Add(s.ToString());return r;}
    static async Task<string> CachedText(string url,string file)
    {
        string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RadioLog","cache"),path=Path.Combine(dir,file);Directory.CreateDirectory(dir);if(File.Exists(path)&&DateTime.UtcNow-File.GetLastWriteTimeUtc(path)<TimeSpan.FromHours(24))return await File.ReadAllTextAsync(path);string text=await Http.GetStringAsync(url);await File.WriteAllTextAsync(path,text);return text;
    }
    async Task<List<Activation>> LoadBota()
    {
        try
        {
            using var stream=await Http.GetStreamAsync("https://api.wwbota.org/spots/?age=1");using var doc=await JsonDocument.ParseAsync(stream);var result=new List<Activation>();
            if(doc.RootElement.ValueKind!=JsonValueKind.Array)return result;
            foreach(var spot in doc.RootElement.EnumerateArray())
            {
                if(Text(spot,"type").Equals("QRT",StringComparison.OrdinalIgnoreCase))continue;string call=Text(spot,"call","callsign");
                if(!Try(spot,"references",out var refs)||refs.ValueKind!=JsonValueKind.Array)continue;
                foreach(var r in refs.EnumerateArray())
                {
                    double lat=Number(r,"lat","latitude"),lon=Number(r,"long","lon","longitude");if(lat==0&&lon==0)continue;
                    result.Add(new Activation{Program="BOTA",Reference=Text(r,"reference","ref"),Name=$"{call} — {Text(r,"name","type")}",Latitude=lat,Longitude=lon});
                }
            }return result;
        }catch{return [];}
    }
    async Task<List<Activation>> Load(string program,string url)
    {
        try
        {
            using var stream=await Http.GetStreamAsync(url);using var doc=await JsonDocument.ParseAsync(stream);var root=doc.RootElement;
            if(root.ValueKind==JsonValueKind.Object){if(Try(root,"spots",out var s))root=s;else if(Try(root,"data",out var d))root=d;}
            if(root.ValueKind!=JsonValueKind.Array)return [];
            var result=new List<Activation>();foreach(var e in root.EnumerateArray())
            {
                double lat=Number(e,"latitude","lat"),lon=Number(e,"longitude","lon","lng");if(lat==0&&lon==0)continue;
                string reference=Text(e,"reference","summitCode","ref","bunker","code");string call=Text(e,"activator","activatorCallsign","callsign","call");string name=Text(e,"name","parkName","summitDetails","title","comments");
                result.Add(new Activation{Program=program,Reference=reference,Name=string.IsNullOrWhiteSpace(call)?name:$"{call} — {name}",Latitude=lat,Longitude=lon});
            }return result;
        }catch{return [];}
    }
    static bool Try(JsonElement e,string name,out JsonElement v){foreach(var p in e.EnumerateObject())if(p.Name.Equals(name,StringComparison.OrdinalIgnoreCase)){v=p.Value;return true;}v=default;return false;}
    static string Text(JsonElement e,params string[] names){foreach(var n in names)if(Try(e,n,out var v)&&v.ValueKind==JsonValueKind.String)return v.GetString()??"";return"";}
    static string Value(JsonElement e,params string[] names){foreach(var n in names)if(Try(e,n,out var v)){if(v.ValueKind==JsonValueKind.String)return v.GetString()??"";if(v.ValueKind==JsonValueKind.Number)return v.GetRawText();}return"";}
    static double Number(JsonElement e,params string[] names){foreach(var n in names)if(Try(e,n,out var v)){if(v.ValueKind==JsonValueKind.Number&&v.TryGetDouble(out var d))return d;if(v.ValueKind==JsonValueKind.String&&double.TryParse(v.GetString(),System.Globalization.NumberStyles.Float,System.Globalization.CultureInfo.InvariantCulture,out d))return d;}return 0;}
}
