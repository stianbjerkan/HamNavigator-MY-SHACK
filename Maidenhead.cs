namespace RadioLog;
public static class Maidenhead
{
 public static string Encode(double lat,double lon,int length=10)
 {
  length=length is 4 or 6 or 8 or 10?length:10;lat=Math.Clamp(lat,-89.999999,89.999999)+90;lon=((lon+180)%360+360)%360;
  int a=(int)(lon/20),b=(int)(lat/10);lon-=a*20;lat-=b*10;int c=(int)(lon/2),d=(int)lat;lon-=c*2;lat-=d;var s=$"{(char)('A'+a)}{(char)('A'+b)}{c}{d}";if(length==4)return s;
  int e=(int)(lon*12),f=(int)(lat*24);lon-=e/12d;lat-=f/24d;s+=$"{(char)('A'+e)}{(char)('A'+f)}";if(length==6)return s;
  int g=(int)(lon*120),h=(int)(lat*240);lon-=g/120d;lat-=h/240d;s+=$"{g}{h}";if(length==8)return s;
  int i=(int)(lon*2880),j=(int)(lat*5760);return s+$"{(char)('A'+Math.Clamp(i,0,23))}{(char)('A'+Math.Clamp(j,0,23))}";
 }
 public static bool TryCenter(string? grid,out double lat,out double lon)
 {
  lat=lon=0;if(string.IsNullOrWhiteSpace(grid))return false;grid=grid.Trim().ToUpperInvariant();if(grid.Length is not(4 or 6 or 8 or 10))return false;
  char a=grid[0],b=grid[1],c=grid[2],d=grid[3];if(a<'A'||a>'R'||b<'A'||b>'R'||!char.IsDigit(c)||!char.IsDigit(d))return false;
  double lonSize=2,latSize=1;lon=-180+(a-'A')*20+(c-'0')*lonSize;lat=-90+(b-'A')*10+(d-'0')*latSize;
  if(grid.Length>=6){char e=grid[4],f=grid[5];if(e<'A'||e>'X'||f<'A'||f>'X')return false;lonSize/=24;latSize/=24;lon+=(e-'A')*lonSize;lat+=(f-'A')*latSize;}
  if(grid.Length>=8){char g=grid[6],h=grid[7];if(!char.IsDigit(g)||!char.IsDigit(h))return false;lonSize/=10;latSize/=10;lon+=(g-'0')*lonSize;lat+=(h-'0')*latSize;}
  if(grid.Length>=10){char i=grid[8],j=grid[9];if(i<'A'||i>'X'||j<'A'||j>'X')return false;lonSize/=24;latSize/=24;lon+=(i-'A')*lonSize;lat+=(j-'A')*latSize;}
  lon+=lonSize/2;lat+=latSize/2;return true;
 }
}
