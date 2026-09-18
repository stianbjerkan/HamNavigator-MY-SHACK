using System.Windows;
namespace RadioLog;
public partial class App : Application
{
    protected override void OnStartup(StartupEventArgs e)
    {
        DispatcherUnhandledException += (_, a) =>
        {
            MessageBox.Show(a.Exception.Message, "HamNavigator – oppstartsfeil", MessageBoxButton.OK, MessageBoxImage.Error);
            a.Handled = true;
            Shutdown(1);
        };
        base.OnStartup(e);
    }
}
