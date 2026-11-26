using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

// Ventana de Scripting (antes Trelby): translúcida (acrílico de DWM) con WebView2 del sistema, misma receta que ST-Lite.
// Levanta server.py (oculto) si no está corriendo y lo cierra al salir.
static class Program
{
    const int Port = 5170;
    static readonly string Url = "http://127.0.0.1:" + Port + "/index.html";
    static Process _server;

    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr h, int attr, ref int v, int size);
    [DllImport("dwmapi.dll")] static extern int DwmExtendFrameIntoClientArea(IntPtr h, ref MARGINS m);
    [StructLayout(LayoutKind.Sequential)] struct MARGINS { public int l, r, t, b; }
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int left, top, right, bottom; }
    [StructLayout(LayoutKind.Sequential)] struct NCCALCSIZE_PARAMS { public RECT r0, r1, r2; public IntPtr pos; }
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);

    static bool PortOpen()
    {
        try { using var c = new TcpClient(); var r = c.BeginConnect("127.0.0.1", Port, null, null);
              return r.AsyncWaitHandle.WaitOne(300) && c.Connected; } catch { return false; }
    }

    [STAThread]
    static void Main()
    {
        ApplicationConfiguration.Initialize();
        if (!PortOpen())
        {
            // la carpeta de la app es la de arriba de ventana\out
            var appDir = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", ".."));
            _server = Process.Start(new ProcessStartInfo("pythonw", "server.py --no-window")
            { WorkingDirectory = appDir, UseShellExecute = false, CreateNoWindow = true });
            for (int i = 0; i < 50 && !PortOpen(); i++) System.Threading.Thread.Sleep(100);
        }
        Application.Run(new Win());
        try { if (_server != null && !_server.HasExited) _server.Kill(true); } catch { }
    }

    class Win : Form
    {
        readonly WebView2 wv = new WebView2();
        public Win()
        {
            Text = "Scripting"; Size = new Size(1600, 950); StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.Black;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            wv.Dock = DockStyle.Fill; wv.DefaultBackgroundColor = Color.Transparent;
            Padding = new Padding(0, Grip, 0, 0);   // franja fina arriba para estirar la ventana
            Controls.Add(wv);
            Load += async (s, e) => await Init();
            Resize += (s, e) => { Padding = new Padding(0, WindowState == FormWindowState.Maximized ? 0 : Grip, 0, 0); SendState(); };
        }
        const int Grip = 4;
        // sin WS_SYSMENU, DWM no dibuja sus botones de ventana encima de los de la página
        protected override CreateParams CreateParams { get { var cp = base.CreateParams; cp.Style &= ~0x00080000; return cp; } }
        protected override bool ProcessCmdKey(ref Message msg, Keys k) { if (k == (Keys.Alt | Keys.F4)) { Close(); return true; } return base.ProcessCmdKey(ref msg, k); }
        void SendState() { try { wv.CoreWebView2?.PostWebMessageAsString(WindowState == FormWindowState.Maximized ? "max" : "normal"); } catch { } }

        // Sin barra de título nativa: la barra de pestañas de la página hace de barra de título.
        protected override void WndProc(ref Message m)
        {
            const int WM_NCCALCSIZE = 0x83, WM_NCHITTEST = 0x84;
            if (m.Msg == WM_NCCALCSIZE && m.WParam != IntPtr.Zero)
            {
                var p = Marshal.PtrToStructure<NCCALCSIZE_PARAMS>(m.LParam);
                int top = p.r0.top;
                base.WndProc(ref m);                       // bordes laterales/inferior normales
                p = Marshal.PtrToStructure<NCCALCSIZE_PARAMS>(m.LParam);
                // maximizada, Windows corre la ventana fuera de pantalla el grosor del borde
                p.r0.top = top + (WindowState == FormWindowState.Maximized ? GetSystemMetrics(33) + GetSystemMetrics(92) : 0);
                Marshal.StructureToPtr(p, m.LParam, false);
                m.Result = IntPtr.Zero; return;
            }
            base.WndProc(ref m);
            if (m.Msg == WM_NCHITTEST && (int)m.Result == 1 && WindowState != FormWindowState.Maximized)
            {
                var pt = PointToClient(new Point((short)((long)m.LParam & 0xFFFF), (short)(((long)m.LParam >> 16) & 0xFFFF)));
                if (pt.Y < Grip) m.Result = (IntPtr)(pt.X < 12 ? 13 : pt.X > ClientSize.Width - 12 ? 14 : 12); // HTTOPLEFT/HTTOPRIGHT/HTTOP
            }
        }
        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            int dark = 1, acrylic = 3; // DWMWA_USE_IMMERSIVE_DARK_MODE=20, SYSTEMBACKDROP_TYPE=38 (3 = acrílico)
            DwmSetWindowAttribute(Handle, 20, ref dark, 4);
            DwmSetWindowAttribute(Handle, 38, ref acrylic, 4);
            var m = new MARGINS { l = -1, r = -1, t = -1, b = -1 };
            DwmExtendFrameIntoClientArea(Handle, ref m);
            SetWindowPos(Handle, IntPtr.Zero, 0, 0, 0, 0, 0x0027); // SWP_FRAMECHANGED|NOMOVE|NOSIZE|NOZORDER
        }
        async System.Threading.Tasks.Task Init()
        {
            var data = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Trelby-HTML");
            var opts = new CoreWebView2EnvironmentOptions(
                "--enable-low-end-device-mode --disable-features=CalculateNativeWinOcclusion,msEdgeShopping,msWebOOUI " +
                "--renderer-process-limit=1 --disable-background-networking --js-flags=--max-old-space-size=512");
            var env = await CoreWebView2Environment.CreateAsync(null, data, opts);
            await wv.EnsureCoreWebView2Async(env);
            var c = wv.CoreWebView2;
            c.Settings.AreDevToolsEnabled = false; c.Settings.IsStatusBarEnabled = false;
            c.Settings.IsGeneralAutofillEnabled = false; c.Settings.IsPasswordAutosaveEnabled = false;
            c.MemoryUsageTargetLevel = CoreWebView2MemoryUsageTargetLevel.Low;
            c.Settings.IsNonClientRegionSupportEnabled = true;   // CSS app-region: drag mueve la ventana
            c.WebMessageReceived += (o, a) =>
            {
                var msg = a.TryGetWebMessageAsString();
                if (msg == "min") WindowState = FormWindowState.Minimized;
                else if (msg == "max") WindowState = WindowState == FormWindowState.Maximized ? FormWindowState.Normal : FormWindowState.Maximized;
                else if (msg == "close") Close();
                else if (msg == "state") SendState();
            };
            // la página detecta window.chrome.webview y activa sola el CSS "glass"
            c.DocumentTitleChanged += (o, a) => Text = c.DocumentTitle;
            c.NewWindowRequested += (o, a) => { a.Handled = true; try { Process.Start(new ProcessStartInfo(a.Uri) { UseShellExecute = true }); } catch { } };
            Resize += (o, a) => { try { if (WindowState == FormWindowState.Minimized) { var _ = c.TrySuspendAsync(); } else if (c.IsSuspended) c.Resume(); } catch { } };
            c.Navigate(Url);
        }
    }
}
