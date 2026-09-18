using System.Runtime.InteropServices;
namespace RadioLog;
public sealed record AudioDevice(int Id,string Name,bool IsInput)
{
 public string DisplayName
 {
  get
  {
   if(!Ft8AdvancedPanel.EnglishActive)return Name;
   return Name.Replace("Mikrofon","Microphone",StringComparison.OrdinalIgnoreCase)
    .Replace("Høyttalere","Speakers",StringComparison.OrdinalIgnoreCase)
    .Replace("Hodetelefoner","Headphones",StringComparison.OrdinalIgnoreCase)
    .Replace("Linjeinngang","Line input",StringComparison.OrdinalIgnoreCase)
    .Replace("Windows standardinngang","Windows default input",StringComparison.OrdinalIgnoreCase)
    .Replace("Windows standardutgang","Windows default output",StringComparison.OrdinalIgnoreCase);
  }
 }
 public override string ToString()=>$"{Id}: {DisplayName}";
}
public static class AudioDevices
{
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct WaveInCaps{public ushort ManufacturerId,ProductId;public uint DriverVersion;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Name;public uint Formats;public ushort Channels,Reserved;}
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] struct WaveOutCaps{public ushort ManufacturerId,ProductId;public uint DriverVersion;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string Name;public uint Formats;public ushort Channels,Reserved;public uint Support;}
 [DllImport("winmm.dll",CharSet=CharSet.Unicode)]static extern uint waveInGetNumDevs();[DllImport("winmm.dll",CharSet=CharSet.Unicode)]static extern uint waveOutGetNumDevs();
 [DllImport("winmm.dll",CharSet=CharSet.Unicode)]static extern uint waveInGetDevCapsW(UIntPtr id,out WaveInCaps caps,uint size);[DllImport("winmm.dll",CharSet=CharSet.Unicode)]static extern uint waveOutGetDevCapsW(UIntPtr id,out WaveOutCaps caps,uint size);
 public static List<AudioDevice> Inputs()=>Read(true);public static List<AudioDevice> Outputs()=>Read(false);
 static List<AudioDevice> Read(bool input)
 {
  var r=new List<AudioDevice>();uint n=input?waveInGetNumDevs():waveOutGetNumDevs();
  if(input){uint size=(uint)Marshal.SizeOf<WaveInCaps>();for(uint i=0;i<n;i++)if(waveInGetDevCapsW((UIntPtr)i,out var c,size)==0)r.Add(new((int)i,c.Name,true));if(r.Count==0)r.Add(new(-1,"Windows standardinngang",true));}
  else{uint size=(uint)Marshal.SizeOf<WaveOutCaps>();for(uint i=0;i<n;i++)if(waveOutGetDevCapsW((UIntPtr)i,out var c,size)==0)r.Add(new((int)i,c.Name,false));if(r.Count==0)r.Add(new(-1,"Windows standardutgang",false));}
  return r;
 }
 public static AudioDevice? Best(IEnumerable<AudioDevice> ds){int Score(AudioDevice d){string n=d.Name.ToUpperInvariant();int s=0;if(n.Contains("DAX"))s+=100;if(n.Contains("SIGNALINK"))s+=100;if(n.Contains("USB"))s+=80;if(n.Contains("CODEC"))s+=70;if(n.Contains("RADIO"))s+=60;if(n.Contains("MICROPHONE ARRAY"))s-=50;if(n.Contains("SPEAKER"))s-=20;return s;}return ds.OrderByDescending(Score).ThenBy(x=>x.Id).FirstOrDefault();}
}
