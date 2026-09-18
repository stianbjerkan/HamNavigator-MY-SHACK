using System.Collections.Concurrent;

namespace RadioLog;

public enum QsoStage { Idle, Calling, ReportSent, RogerSent, Completed }
public sealed record Ft8Signal(DateTime SlotUtc, string Call, string Grid, int Snr, double AudioHz, string Text)
{
    public double Dt { get; init; }
}

/// <summary>Clean-room FT8 operator core. DSP input/output is isolated so the protocol implementation can be tested without transmitting.</summary>
public sealed class Ft8Engine : IDisposable
{
    readonly ConcurrentQueue<Ft8Signal> queue = new();
    readonly HashSet<string> worked = new(StringComparer.OrdinalIgnoreCase);
    CancellationTokenSource? cts;
    QsoStage stage;
    Ft8Signal? active;
    public bool AutoEnabled { get; set; }
    public bool TransmitArmed { get; set; }
    public bool Running => cts != null;
    public event Action<string>? Status;
    public event Action<Ft8Signal>? Decoded;
    public event Action<Qso>? Logged;

    public void Start()
    {
        if (Running) return; cts = new(); stage = QsoStage.Idle;
        Status?.Invoke("Egen FT8-motor startet – mottak/sekvensering aktiv");
        _ = SlotClock(cts.Token);
    }
    public void Stop() { cts?.Cancel(); cts?.Dispose(); cts = null; active = null; stage = QsoStage.Idle; Status?.Invoke("FT8-motor stoppet"); }

    // Entry point used by the clean-room demodulator after CRC validation.
    public void AcceptDecoded(Ft8Signal signal)
    {
        Decoded?.Invoke(signal);
        if (signal.Text.StartsWith("CQ ", StringComparison.OrdinalIgnoreCase) && !worked.Contains(signal.Call)) queue.Enqueue(signal);
        if (active != null && signal.Text.Contains(active.Call, StringComparison.OrdinalIgnoreCase)) Advance(signal);
    }

    async Task SlotClock(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            var now = DateTime.UtcNow; var next = now.AddSeconds(15 - (now.Second % 15)).AddMilliseconds(-now.Millisecond);
            try { await Task.Delay(next - now, token); } catch (OperationCanceledException) { break; }
            if (AutoEnabled && stage == QsoStage.Idle) SelectNext();
        }
    }
    void SelectNext()
    {
        if (!queue.TryDequeue(out active)) { Status?.Invoke("Lytter – ingen ledig CQ i kø"); return; }
        stage = QsoStage.Calling; Send($"{active.Call} {{MYCALL}} {active.Grid}");
    }
    void Advance(Ft8Signal rx)
    {
        if (active == null) return;
        if (rx.Text.Contains(" 73", StringComparison.OrdinalIgnoreCase) || rx.Text.Contains("RR73", StringComparison.OrdinalIgnoreCase))
        {
            Send($"{active.Call} {{MYCALL}} 73"); worked.Add(active.Call); stage = QsoStage.Completed;
            Logged?.Invoke(new Qso { TimeUtc = DateTime.UtcNow, Call = active.Call, Mode = "FT8", Grid = active.Grid, RstReceived = active.Snr.ToString("+00;-00;00") });
            active = null; stage = QsoStage.Idle; return;
        }
        if (stage == QsoStage.Calling) { stage = QsoStage.ReportSent; Send($"{active.Call} {{MYCALL}} {rx.Snr:+00;-00;00}"); }
        else if (stage == QsoStage.ReportSent) { stage = QsoStage.RogerSent; Send($"{active.Call} {{MYCALL}} R{rx.Snr:+00;-00;00}"); }
    }
    void Send(string text)
    {
        if (!TransmitArmed) { Status?.Invoke("TX ikke armert – klar melding: " + text); return; }
        // The waveform sink will receive 79 generated 8-FSK symbols once codec/audio modules are enabled.
        Status?.Invoke("TX: " + text);
    }
    public void Dispose() => Stop();
}
