using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

namespace AIModBuilder
{
    static class Program
    {
        private static Process serverProcess = null;
        private static Process appWindowProcess = null;
        private static string appDir = "";
        private const string MutexName = "AIModBuilder_App_SingleInstance_Mutex";
        private const string Url = "http://127.0.0.1:8765";

        [STAThread]
        static void Main()
        {
            bool createdNew;
            using (Mutex mutex = new Mutex(true, MutexName, out createdNew))
            {
                if (!createdNew)
                {
                    return;
                }

                appDir = AppDomain.CurrentDomain.BaseDirectory;
                Directory.SetCurrentDirectory(appDir);

                StartServer();
                WaitForServer();
                LaunchAppWindow();
                StopServer();
            }
        }

        static void StartServer()
        {
            string pythonExe = "";
            string[] candidates = new string[]
            {
                Path.Combine(appDir, "runtime", "pythonw.exe"),
                Path.Combine(appDir, "runtime", "python.exe"),
                "pythonw.exe",
                "python.exe"
            };

            foreach (var cand in candidates)
            {
                if (File.Exists(cand) || cand.IndexOfAny(new char[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar }) < 0)
                {
                    pythonExe = cand;
                    break;
                }
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = "-m agmod.ui --no-browser",
                    WorkingDirectory = appDir,
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                serverProcess = Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("启动服务失败: " + ex.Message, "AI Mod Builder", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Environment.Exit(1);
            }
        }

        static void WaitForServer()
        {
            for (int i = 0; i < 40; i++)
            {
                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(Url + "/api/health");
                    req.Timeout = 600;
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    {
                        if (resp.StatusCode == HttpStatusCode.OK)
                        {
                            return;
                        }
                    }
                }
                catch
                {
                    Thread.Sleep(200);
                }
            }
        }

        static void LaunchAppWindow()
        {
            string profileDir = Path.Combine(Path.GetTempPath(), "AIModBuilder_AppProfile");
            string browserExe = FindAppBrowser();

            if (!string.IsNullOrEmpty(browserExe))
            {
                string args = string.Format(
                    "--app=\"{0}\" --window-size=1420,900 --user-data-dir=\"{1}\" --app-id=AIModBuilder --disable-extensions",
                    Url,
                    profileDir
                );

                ProcessStartInfo psi = new ProcessStartInfo
                {
                    FileName = browserExe,
                    Arguments = args,
                    UseShellExecute = false
                };

                try
                {
                    appWindowProcess = Process.Start(psi);
                    if (appWindowProcess != null)
                    {
                        appWindowProcess.WaitForExit();
                        return;
                    }
                }
                catch { }
            }

            try
            {
                Process p = Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
                if (p != null) p.WaitForExit();
            }
            catch { }
        }

        static string FindAppBrowser()
        {
            string[] paths = new string[]
            {
                @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                @"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                @"C:\Program Files\Google\Chrome\Application\chrome.exe",
                @"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + @"\Microsoft\Edge\Application\msedge.exe",
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + @"\Google\Chrome\Application\chrome.exe"
            };

            foreach (var p in paths)
            {
                if (File.Exists(p)) return p;
            }
            return "";
        }

        static void StopServer()
        {
            try
            {
                if (serverProcess != null && !serverProcess.HasExited)
                {
                    serverProcess.Kill();
                }
            }
            catch { }
        }
    }
}
