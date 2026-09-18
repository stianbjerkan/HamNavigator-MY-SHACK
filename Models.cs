namespace RadioLog;

public sealed class Qso
{
    public DateTime TimeUtc { get; set; } = DateTime.UtcNow;
    public string Call { get; set; } = "";
    public string Mode { get; set; } = "FT8";
    public string Band { get; set; } = "20m";
    public double FrequencyMhz { get; set; }
    public string RstSent { get; set; } = "-10";
    public string RstReceived { get; set; } = "-10";
    public string Grid { get; set; } = "";
    public string Program { get; set; } = "";
    public string Reference { get; set; } = "";
    public string Notes { get; set; } = "";
}

public sealed class Activation
{
    public string Program { get; set; } = "POTA";
    public string Reference { get; set; } = "";
    public string Name { get; set; } = "";
    public double Latitude { get; set; }
    public double Longitude { get; set; }
    public string Notes { get; set; } = "";
    public bool IsLive { get; set; }
    public string ActivityType { get; set; } = "";
}

public sealed class Settings
{
    public string MyCall { get; set; } = "LA0XXX";
    public string MyGrid { get; set; } = "JO59";
    public int WsjtxPort { get; set; } = 2237;
    public string RadioManufacturer { get; set; } = "Icom";
    public string RadioModel { get; set; } = "IC-7300";
    public string Port { get; set; } = "COM1";
    public int BaudRate { get; set; } = 19200;
    public string PttMethod { get; set; } = "CAT";
    public int AudioInputId { get; set; } = -1;
    public int AudioOutputId { get; set; } = -1;
    public double DialFrequencyMhz { get; set; } = 14.074;
    public bool AutoUpload { get; set; }
    public bool SyncQrz { get; set; }
    public string QrzApiKey { get; set; } = "";
    public bool SyncClubLog { get; set; }
    public string ClubLogEmail { get; set; } = "";
    public string ClubLogPassword { get; set; } = "";
    public bool SyncHrdLog { get; set; }
    public string HrdLogCall { get; set; } = "";
    public string HrdLogCode { get; set; } = "";
    public bool SyncCloudlog { get; set; }
    public string CloudlogUrl { get; set; } = "";
    public string CloudlogApiKey { get; set; } = "";
    public int CloudlogStationId { get; set; } = 1;
    public bool SyncEqsl { get; set; }
    public string EqslUser { get; set; } = "";
    public string EqslPassword { get; set; } = "";
    public bool SyncUdp { get; set; }
    public int SyncUdpPort { get; set; } = 2333;
    public bool SyncHamQth { get; set; }
    public string HamQthUser { get; set; } = "";
    public string HamQthPassword { get; set; } = "";
    public bool SyncLotw { get; set; }
    public string TqslPath { get; set; } = "";
    public bool SyncLog4Om { get; set; }
    public bool SyncN3fjp { get; set; }
    public bool SyncDxKeeper { get; set; }
    public bool SyncHrdLocal { get; set; }
}

public sealed record RadioProfile(string Manufacturer, string Model, string Protocol);
