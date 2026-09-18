using System.Text.Json;
using System.IO;

namespace RadioLog;

public sealed class Storage
{
    readonly string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "RadioLog");
    string LogPath => Path.Combine(folder, "log.json");
    string SettingsPath => Path.Combine(folder, "settings.json");
    string PointsPath => Path.Combine(folder, "activations.json");
    static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };
    public Storage() => Directory.CreateDirectory(folder);
    public List<Qso> LoadLog() => Load<List<Qso>>(LogPath) ?? [];
    public List<Activation> LoadPoints() => Load<List<Activation>>(PointsPath) ?? [];
    public Settings LoadSettings() => Load<Settings>(SettingsPath) ?? new();
    T? Load<T>(string path) { try { return File.Exists(path) ? JsonSerializer.Deserialize<T>(File.ReadAllText(path)) : default; } catch { return default; } }
    public void SaveLog(IEnumerable<Qso> data) => File.WriteAllText(LogPath, JsonSerializer.Serialize(data, JsonOptions));
    public void SavePoints(IEnumerable<Activation> data) => File.WriteAllText(PointsPath, JsonSerializer.Serialize(data, JsonOptions));
    public void SaveSettings(Settings data) => File.WriteAllText(SettingsPath, JsonSerializer.Serialize(data, JsonOptions));
    public void ExportAdif(string path, IEnumerable<Qso> qsos)
    {
        using var w = new StreamWriter(path);
        w.WriteLine("HamNavigator ADIF export <ADIF_VER:5>3.1.4 <EOH>");
        foreach (var q in qsos)
        {
            string F(string n, string v) => string.IsNullOrWhiteSpace(v) ? "" : $"<{n}:{v.Length}>{v} ";
            w.WriteLine(F("QSO_DATE", q.TimeUtc.ToString("yyyyMMdd")) + F("TIME_ON", q.TimeUtc.ToString("HHmmss")) + F("CALL", q.Call) + F("MODE", q.Mode) + F("BAND", q.Band) + F("FREQ", q.FrequencyMhz>0?q.FrequencyMhz.ToString("0.######",System.Globalization.CultureInfo.InvariantCulture):"") + F("RST_SENT", q.RstSent) + F("RST_RCVD", q.RstReceived) + F("GRIDSQUARE", q.Grid) + F("SIG", q.Program) + F("SIG_INFO", q.Reference) + F("COMMENT",q.Notes) + "<EOR>");
        }
    }
}
