using System.Net.Http;
using System.IO;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace RadioLog;

/// <summary>Native slippy-map control using Web Mercator tiles. No browser or map SDK required.</summary>
public sealed class SlippyMap : FrameworkElement
{
    const double TileSize = 256;
    static readonly HttpClient Http = CreateHttp();
    readonly Dictionary<string, ImageSource> tiles = [];
    readonly HashSet<string> loading = [];
    Point dragStart;
    double dragWorldX, dragWorldY;
    bool dragging;
    bool draggingHome;
    double centerLat = 61.0, centerLon = 10.0;
    int zoom = 5;
    bool satellite;
    IReadOnlyList<Activation> markers = [];
    IReadOnlyList<(Qso q,double lat,double lon)> qsos=[];
    (double lat,double lon)? home;
    Point? homeScreen;
    HashSet<string> activated=[];
    readonly List<(Activation marker,Point screen)> hitMarkers=[];
    public event Action<Activation>? MarkerSelected;
    public event Action<double,double>? HomeMoved;
    public int Zoom => zoom;
    public bool ShowMaidenhead { get; set; }
    public bool AllowHomeDrag { get; set; }
    public bool ShowQsoPaths { get; set; } = true;
    public double CenterLatitude => centerLat;
    public double CenterLongitude => centerLon;

    static HttpClient CreateHttp()
    {
        var h = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
        h.DefaultRequestHeaders.UserAgent.ParseAdd("HamNavigator/1.0 (amateur-radio desktop mapping)");
        return h;
    }
    public SlippyMap()
    {
        ClipToBounds = true; Focusable = true;
        MouseWheel += Wheel; MouseLeftButtonDown += Down; MouseLeftButtonUp += Up; MouseMove += Move;
    }
    public void SetMarkers(IEnumerable<Activation> value) { markers = value.ToArray(); InvalidateVisual(); }
    public void SetActivated(IEnumerable<string> keys) { activated=new HashSet<string>(keys,StringComparer.OrdinalIgnoreCase);InvalidateVisual(); }
    public bool ToggleGrid(){ShowMaidenhead=!ShowMaidenhead;InvalidateVisual();return ShowMaidenhead;}
    public bool TogglePaths(){ShowQsoPaths=!ShowQsoPaths;InvalidateVisual();return ShowQsoPaths;}
    public void UseSatellite(bool value){if(satellite==value)return;satellite=value;InvalidateVisual();}
    public void SetQsoData(IEnumerable<Qso> log,string myGrid){qsos=log.Where(q=>Maidenhead.TryCenter(q.Grid,out _,out _)).Select(q=>{Maidenhead.TryCenter(q.Grid,out var lat,out var lon);return(q,lat,lon);}).ToArray();home=Maidenhead.TryCenter(myGrid,out var hlat,out var hlon)?(hlat,hlon):null;InvalidateVisual();}
    bool IsActivated(Activation m)=>activated.Contains($"{m.Program}|{m.Reference}");
    static Color ProgramColor(string program)=>program switch{"POTA"=>Color.FromRgb(38,190,92),"SOTA"=>Color.FromRgb(202,62,220),"BOTA"=>Color.FromRgb(245,188,35),_=>Colors.SlateGray};
    public void SetView(double lat, double lon, int newZoom) { centerLat = Math.Clamp(lat, -85, 85); centerLon = WrapLon(lon); zoom = Math.Clamp(newZoom, 2, 19); InvalidateVisual(); }
    static double WrapLon(double lon) { while (lon < -180) lon += 360; while (lon > 180) lon -= 360; return lon; }
    static (double x,double y) Project(double lat,double lon,int z)
    {
        double n=Math.Pow(2,z), x=(lon+180)/360*n; lat=Math.Clamp(lat,-85.05112878,85.05112878); double r=lat*Math.PI/180;
        return (x,(1-Math.Log(Math.Tan(r)+1/Math.Cos(r))/Math.PI)/2*n);
    }
    static (double lat,double lon) Unproject(double x,double y,int z)
    {
        double n=Math.Pow(2,z), lon=x/n*360-180, lat=Math.Atan(Math.Sinh(Math.PI*(1-2*y/n)))*180/Math.PI; return(lat,WrapLon(lon));
    }
    protected override void OnRender(DrawingContext dc)
    {
        base.OnRender(dc); hitMarkers.Clear(); dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(7,30,47)),null,new Rect(RenderSize));
        var c=Project(centerLat,centerLon,zoom); double cx=c.x*TileSize,cy=c.y*TileSize,left=cx-ActualWidth/2,top=cy-ActualHeight/2;
        int minX=(int)Math.Floor(left/TileSize),maxX=(int)Math.Floor((left+ActualWidth)/TileSize),minY=(int)Math.Floor(top/TileSize),maxY=(int)Math.Floor((top+ActualHeight)/TileSize),count=1<<zoom;
        for(int ty=minY;ty<=maxY;ty++) for(int tx=minX;tx<=maxX;tx++)
        {
            if(ty<0||ty>=count)continue;int wx=((tx%count)+count)%count;string key=$"{(satellite?'S':'M')}/{zoom}/{wx}/{ty}";var rect=new Rect(tx*TileSize-left,ty*TileSize-top,TileSize+1,TileSize+1);
            if(tiles.TryGetValue(key,out var img))dc.DrawImage(img,rect);else{dc.DrawRectangle(new SolidColorBrush(Color.FromRgb(15,38,52)),new Pen(new SolidColorBrush(Color.FromRgb(30,60,75)),.5),rect);LoadTile(key,zoom,wx,ty);}
        }
        if(ShowMaidenhead)DrawMaidenhead(dc,left,top);
        if(home is { } h)
        {
            var hp=Project(h.lat,h.lon,zoom);var hs=new Point(hp.x*TileSize-left,hp.y*TileSize-top);homeScreen=hs;if(ShowQsoPaths)foreach(var item in qsos){var p=Project(item.lat,item.lon,zoom);var dest=new Point(p.x*TileSize-left,p.y*TileSize-top);if((dest.X>=0&&dest.X<=ActualWidth&&dest.Y>=0&&dest.Y<=ActualHeight)||zoom<=3)dc.DrawLine(new Pen(new SolidColorBrush(Color.FromArgb(90,56,189,248)),1),hs,dest);}dc.DrawEllipse(Brushes.Red,new Pen(Brushes.White,2),hs,AllowHomeDrag?9:6,AllowHomeDrag?9:6);
        }
        IEnumerable<Activation> source=markers;
        if(zoom<=7){double cell=zoom<=3?10:zoom<=5?3:1;source=markers.GroupBy(m=>((int)Math.Floor(m.Latitude/cell),(int)Math.Floor(m.Longitude/cell),m.Program)).Select(g=>g.First());}
        var visible=new List<(Activation m,double x,double y)>();
        foreach(var m in source)
        {
            var p=Project(m.Latitude,m.Longitude,zoom);double x=p.x*TileSize-left,y=p.y*TileSize-top;if(x<0||y<0||x>ActualWidth||y>ActualHeight)continue;visible.Add((m,x,y));
        }
        if(zoom<10)
        {
            foreach(var cluster in visible.GroupBy(v=>((int)(v.x/48),(int)(v.y/48))))
            {
                double x=cluster.Average(v=>v.x),y=cluster.Average(v=>v.y);var first=cluster.First().m;int markerCount=cluster.Count();bool live=cluster.Any(v=>v.m.IsLive),done=cluster.Any(v=>IsActivated(v.m));var programColor=ProgramColor(first.Program);var color=done?Colors.Red:markerCount>1?Colors.Orange:programColor;double radius=markerCount>1?Math.Min(18,8+Math.Log10(markerCount)*5):7;
                var ringPen=new Pen(new SolidColorBrush(live?Color.FromRgb(54,242,139):Colors.White),live?3:1.2);dc.DrawEllipse(Brushes.Transparent,ringPen,new Point(x,y),radius+4,radius+4);dc.DrawEllipse(new SolidColorBrush(color),null,new Point(x,y),radius,radius);if(markerCount>1){var ft=new FormattedText(markerCount.ToString(),System.Globalization.CultureInfo.InvariantCulture,FlowDirection.LeftToRight,new Typeface("Segoe UI Bold"),11,Brushes.Black,VisualTreeHelper.GetDpi(this).PixelsPerDip);dc.DrawText(ft,new Point(x-ft.Width/2,y-ft.Height/2));}
            }
        }
        else foreach(var item in visible)
        {
            var m=item.m;double x=item.x,y=item.y;
            hitMarkers.Add((m,new Point(x,y)));
            var programColor=ProgramColor(m.Program);var color=IsActivated(m)?Colors.Red:programColor;var ringColor=m.IsLive?Color.FromRgb(54,242,139):Colors.White;
            dc.DrawEllipse(Brushes.Transparent,new Pen(new SolidColorBrush(ringColor),m.IsLive?3:1),new Point(x,y),10,10);dc.DrawEllipse(new SolidColorBrush(color),null,new Point(x,y),6.5,6.5);var textBrush=m.Program=="BOTA"?Brushes.Black:Brushes.White;var ft=new FormattedText($"{m.Program} {m.Reference}",System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Segoe UI Semibold"),12,textBrush,VisualTreeHelper.GetDpi(this).PixelsPerDip);var labelRect=new Rect(x+8,y-11,ft.Width+10,ft.Height+5);dc.DrawRoundedRectangle(new SolidColorBrush(Color.FromArgb(225,programColor.R,programColor.G,programColor.B)),new Pen(new SolidColorBrush(ringColor),m.IsLive?2:0.7),labelRect,4,4);dc.DrawText(ft,new Point(x+13,y-9));
        }
        DrawScale(dc);string credit=satellite?"Esri, Maxar, Earthstar Geographics, GIS Community":"© OpenStreetMap contributors";var attr=new FormattedText(credit,System.Globalization.CultureInfo.InvariantCulture,FlowDirection.LeftToRight,new Typeface("Segoe UI"),10,Brushes.White,VisualTreeHelper.GetDpi(this).PixelsPerDip);dc.DrawRectangle(new SolidColorBrush(Color.FromArgb(170,0,0,0)),null,new Rect(ActualWidth-attr.Width-12,ActualHeight-20,attr.Width+8,17));dc.DrawText(attr,new Point(ActualWidth-attr.Width-8,ActualHeight-19));
    }
    async void LoadTile(string key,int z,int x,int y)
    {
        if(!loading.Add(key))return;try{string url=key[0]=='S'?$"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}":$"https://tile.openstreetmap.org/{z}/{x}/{y}.png";var bytes=await Http.GetByteArrayAsync(url);await Dispatcher.InvokeAsync(()=>{using var ms=new MemoryStream(bytes);var b=new BitmapImage();b.BeginInit();b.CacheOption=BitmapCacheOption.OnLoad;b.StreamSource=ms;b.EndInit();b.Freeze();tiles[key]=b;if(tiles.Count>500){foreach(var k in tiles.Keys.Take(100).ToArray())tiles.Remove(k);}InvalidateVisual();});}catch{}finally{loading.Remove(key);}
    }
    void Wheel(object s,MouseWheelEventArgs e)
    {
        int nz=Math.Clamp(zoom+(e.Delta>0?1:-1),2,19);if(nz==zoom)return;var before=ScreenToGeo(e.GetPosition(this));zoom=nz;var after=ScreenToGeo(e.GetPosition(this));centerLat=Math.Clamp(centerLat+(before.lat-after.lat),-85,85);centerLon=WrapLon(centerLon+(before.lon-after.lon));InvalidateVisual();
    }
    (double lat,double lon) ScreenToGeo(Point p){var c=Project(centerLat,centerLon,zoom);return Unproject(c.x+(p.X-ActualWidth/2)/TileSize,c.y+(p.Y-ActualHeight/2)/TileSize,zoom);}
    void Down(object s,MouseButtonEventArgs e){Focus();dragStart=e.GetPosition(this);draggingHome=AllowHomeDrag&&homeScreen is Point hs&&(hs-dragStart).Length<16;dragging=!draggingHome;var c=Project(centerLat,centerLon,zoom);dragWorldX=c.x;dragWorldY=c.y;CaptureMouse();Cursor=Cursors.Hand;}
    void Up(object s,MouseButtonEventArgs e){var p=e.GetPosition(this);if(draggingHome&&home is{} h){draggingHome=false;ReleaseMouseCapture();Cursor=Cursors.Arrow;HomeMoved?.Invoke(h.lat,h.lon);return;}bool click=(p-dragStart).Length<6;dragging=false;ReleaseMouseCapture();Cursor=Cursors.Arrow;if(click){var hit=hitMarkers.Select(x=>(x.marker,d:(x.screen-p).Length)).Where(x=>x.d<14).OrderBy(x=>x.d).FirstOrDefault();if(hit.marker!=null)MarkerSelected?.Invoke(hit.marker);}}
    void Move(object s,MouseEventArgs e){var p=e.GetPosition(this);if(draggingHome){home=ScreenToGeo(p);InvalidateVisual();return;}if(!dragging)return;var g=Unproject(dragWorldX-(p.X-dragStart.X)/TileSize,dragWorldY-(p.Y-dragStart.Y)/TileSize,zoom);centerLat=g.lat;centerLon=g.lon;InvalidateVisual();}
    void DrawScale(DrawingContext dc)
    {
        double metersPerPixel=156543.03392*Math.Cos(centerLat*Math.PI/180)/Math.Pow(2,zoom),target=metersPerPixel*120;double pow=Math.Pow(10,Math.Floor(Math.Log10(target))),norm=target/pow,nice=(norm>=5?5:norm>=2?2:1)*pow,px=nice/metersPerPixel;string label=nice>=1000?$"{nice/1000:0.#} km":$"{nice:0} m";double y=ActualHeight-27;dc.DrawLine(new Pen(Brushes.White,3),new Point(15,y),new Point(15+px,y));var ft=new FormattedText($"{label}  •  zoom {zoom}",System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Segoe UI"),11,Brushes.White,VisualTreeHelper.GetDpi(this).PixelsPerDip);dc.DrawText(ft,new Point(15,y-19));
    }
    void DrawMaidenhead(DrawingContext dc,double left,double top)
    {
        if(zoom<3)return;double lonStep,latStep;string level;
        if(zoom<=6){lonStep=20;latStep=10;level="2 tegn";}else if(zoom<=10){lonStep=2;latStep=1;level="4 tegn";}else if(zoom<=14){lonStep=1d/12;latStep=1d/24;level="6 tegn";}else if(zoom<=17){lonStep=1d/120;latStep=1d/240;level="8 tegn";}else{lonStep=1d/2880;latStep=1d/5760;level="10 tegn";}
        var nw=Unproject(left/TileSize,top/TileSize,zoom);var se=Unproject((left+ActualWidth)/TileSize,(top+ActualHeight)/TileSize,zoom);double minLon=Math.Min(nw.lon,se.lon),maxLon=Math.Max(nw.lon,se.lon),minLat=Math.Min(nw.lat,se.lat),maxLat=Math.Max(nw.lat,se.lat);var pen=new Pen(new SolidColorBrush(Color.FromArgb(150,250,204,21)),1);
        for(double lon=Math.Floor(minLon/lonStep)*lonStep;lon<=maxLon+lonStep;lon+=lonStep){var a=Project(minLat,lon,zoom);var b=Project(maxLat,lon,zoom);dc.DrawLine(pen,new Point(a.x*TileSize-left,a.y*TileSize-top),new Point(b.x*TileSize-left,b.y*TileSize-top));}
        for(double lat=Math.Floor(minLat/latStep)*latStep;lat<=maxLat+latStep;lat+=latStep){var a=Project(lat,minLon,zoom);var b=Project(lat,maxLon,zoom);dc.DrawLine(pen,new Point(a.x*TileSize-left,a.y*TileSize-top),new Point(b.x*TileSize-left,b.y*TileSize-top));}
        var ft=new FormattedText($"Maidenhead {level}",System.Globalization.CultureInfo.CurrentCulture,FlowDirection.LeftToRight,new Typeface("Segoe UI Semibold"),11,Brushes.Gold,VisualTreeHelper.GetDpi(this).PixelsPerDip);dc.DrawRectangle(new SolidColorBrush(Color.FromArgb(180,0,0,0)),null,new Rect(12,12,ft.Width+12,ft.Height+6));dc.DrawText(ft,new Point(18,15));
    }
}
