using System.IO.Ports;
using System.Text;
namespace RadioLog;
public static class CatFrequencyReader
{
 public static Task<double?> ReadAsync(Settings s)=>Task.Run(()=>Read(s));
 static double? Read(Settings s){var profile=RadioCatalog.All.FirstOrDefault(x=>x.Manufacturer==s.RadioManufacturer&&x.Model==s.RadioModel);if(profile==null)return null;try{using var p=new SerialPort(s.Port,s.BaudRate,Parity.None,8,StopBits.One){ReadTimeout=700,WriteTimeout=700};p.Open();return profile.Protocol.Contains("CI-V")||profile.Protocol.Contains("Icom-compatible")?ReadIcom(p,IcomAddress(s.RadioModel)):ReadAscii(p);}catch{return null;}}
 static double? ReadAscii(SerialPort p){p.DiscardInBuffer();p.Write("FA;");var b=new StringBuilder();var end=DateTime.UtcNow.AddMilliseconds(800);while(DateTime.UtcNow<end){try{int c=p.ReadChar();if(c>=0)b.Append((char)c);if(c==';')break;}catch(TimeoutException){break;}}string t=b.ToString();int at=t.IndexOf("FA",StringComparison.OrdinalIgnoreCase);if(at<0)return null;string d=new(t.Skip(at+2).TakeWhile(char.IsDigit).ToArray());return long.TryParse(d,out var hz)?hz/1_000_000d:null;}
 static double? ReadIcom(SerialPort p,byte address){p.DiscardInBuffer();byte[] q={0xFE,0xFE,address,0xE0,0x03,0xFD};p.Write(q,0,q.Length);var data=new List<byte>();var end=DateTime.UtcNow.AddMilliseconds(800);while(DateTime.UtcNow<end){try{byte v=(byte)p.ReadByte();data.Add(v);if(v==0xFD&&data.Count>6)break;}catch(TimeoutException){break;}}int cmd=data.FindIndex(x=>x==0x03);if(cmd<0||data.Count<cmd+6)return null;long hz=0,m=1;for(int i=cmd+1;i<cmd+6;i++){hz+=((data[i]&15)+((data[i]>>4)&15)*10)*m;m*=100;}return hz/1_000_000d;}
 static byte IcomAddress(string m)=>m switch{"IC-705"=>0xA4,"IC-7100"=>0x88,"IC-7300"=>0x94,"IC-7610"=>0x98,"IC-9700"=>0xA2,"IC-9100"=>0x7C,"IC-7200"=>0x76,"IC-7410"=>0x80,"IC-7600"=>0x7A,_=>0x94};
}
