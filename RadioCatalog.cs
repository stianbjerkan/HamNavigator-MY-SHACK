namespace RadioLog;

/// <summary>UI catalog. CAT implementations are selected by protocol family, never by hard-coded UI logic.</summary>
public static class RadioCatalog
{
 public static readonly RadioProfile[] All =
 [
  new("Elecraft","K2","Kenwood CAT"),new("Elecraft","K3/K3S","Kenwood CAT"),new("Elecraft","K4","Kenwood CAT"),new("Elecraft","KX2","Kenwood CAT"),new("Elecraft","KX3","Kenwood CAT"),
  new("FlexRadio","FLEX-1500","SmartSDR CAT"),new("FlexRadio","FLEX-3000","SmartSDR CAT"),new("FlexRadio","FLEX-5000","SmartSDR CAT"),new("FlexRadio","FLEX-6000 series","SmartSDR CAT"),
  new("Icom","IC-7000","CI-V"),new("Icom","IC-705","CI-V"),new("Icom","IC-7100","CI-V"),new("Icom","IC-7200","CI-V"),new("Icom","IC-7300","CI-V"),new("Icom","IC-7410","CI-V"),new("Icom","IC-7600","CI-V"),new("Icom","IC-7610","CI-V"),new("Icom","IC-7700","CI-V"),new("Icom","IC-7800","CI-V"),new("Icom","IC-7850/7851","CI-V"),new("Icom","IC-9100","CI-V"),new("Icom","IC-9700","CI-V"),
  new("JRC","JST-145/245","JRC CAT"),new("JRC","JST-135","JRC CAT"),
  new("Kenwood","TS-140/440/450","Kenwood CAT"),new("Kenwood","TS-480","Kenwood CAT"),new("Kenwood","TS-570","Kenwood CAT"),new("Kenwood","TS-590S/SG","Kenwood CAT"),new("Kenwood","TS-680/690","Kenwood CAT"),new("Kenwood","TS-850","Kenwood CAT"),new("Kenwood","TS-870","Kenwood CAT"),new("Kenwood","TS-890S","Kenwood CAT"),new("Kenwood","TS-930/940/950","Kenwood CAT"),new("Kenwood","TS-990S","Kenwood CAT"),new("Kenwood","TS-2000","Kenwood CAT"),
  new("Lab599","TX-500","Kenwood CAT"),new("QRP Labs","QDX","QDX CAT"),new("QRP Labs","QMX","QDX CAT"),
  new("Ten-Tec","Argonaut V","Ten-Tec CAT"),new("Ten-Tec","Jupiter","Ten-Tec CAT"),new("Ten-Tec","Orion","Ten-Tec CAT"),new("Ten-Tec","Omni VII","Ten-Tec CAT"),
  new("Xiegu","G90","Icom-compatible CAT"),new("Xiegu","X5105","Icom-compatible CAT"),new("Xiegu","X6100","Icom-compatible CAT"),
  new("Yaesu","FT-450/D","Yaesu CAT"),new("Yaesu","FT-817/818","Yaesu CAT"),new("Yaesu","FT-847","Yaesu CAT"),new("Yaesu","FT-857/897","Yaesu CAT"),new("Yaesu","FT-891","Yaesu CAT"),new("Yaesu","FT-920","Yaesu CAT"),new("Yaesu","FT-950","Yaesu CAT"),new("Yaesu","FT-991/A","Yaesu CAT"),new("Yaesu","FT-1000MP","Yaesu CAT"),new("Yaesu","FT-2000","Yaesu CAT"),new("Yaesu","FTDX10","Yaesu CAT"),new("Yaesu","FTDX101D/MP","Yaesu CAT"),new("Yaesu","FTDX1200","Yaesu CAT"),new("Yaesu","FTDX3000","Yaesu CAT"),new("Yaesu","FTDX5000","Yaesu CAT"),
  new("External","Hamlib NET rigctl","Rigctl TCP"),new("External","FLRig","XML-RPC"),new("External","OmniRig","COM automation"),new("External","Ham Radio Deluxe","HRD TCP"),new("External","DX Lab Commander","Commander TCP"),new("Custom","User-defined CAT","Custom")
 ];
 public static string[] Manufacturers => All.Select(x=>x.Manufacturer).Distinct().Order().ToArray();
}
