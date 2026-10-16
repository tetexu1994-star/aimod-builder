using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Threading;
using System.Windows.Forms;

namespace AIModBuilder
{
    static class Program
    {
        private static Process serverProcess = null;
        private static NotifyIcon trayIcon = null;
        private static string appDir = "";
        private const string MutexName = "AIModBuilder_App_SingleInstance_Mutex";
        private const string Url = "http://localhost:8765";

        [STAThread]
        static void Main()
        {
            bool createdNew;
            using (Mutex mutex = new Mutex(true, MutexName, out createdNew))
            {
                if (!createdNew)
                {
                    OpenBrowser(Url);
                    return;
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                appDir = AppDomain.CurrentDomain.BaseDirectory;
                Directory.SetCurrentDirectory(appDir);

                StartServer();
                SetupTray();

                new Thread(() =>
                {
                    WaitForServerAndOpenBrowser();
                }) { IsBackground = true }.Start();

                Application.Run();
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
                AppDomain.CurrentDomain.ProcessExit += (s, e) => StopServer();
            }
            catch (Exception ex)
            {
                MessageBox.Show("启动服务失败: " + ex.Message + "\n请确保 runtime 文件夹完整。", "AI Mod Builder", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Application.Exit();
            }
        }

        static void WaitForServerAndOpenBrowser()
        {
            for (int i = 0; i < 30; i++)
            {
                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8765/api/health");
                    req.Timeout = 800;
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    {
                        if (resp.StatusCode == HttpStatusCode.OK)
                        {
                            break;
                        }
                    }
                }
                catch
                {
                    Thread.Sleep(300);
                }
            }

            OpenBrowser(Url);
            if (trayIcon != null)
            {
                trayIcon.ShowBalloonTip(3000, "AI Mod Builder", "工作台已就绪，正在浏览器中打开！\n若关闭网页可随时双击托盘图标重新打开。", ToolTipIcon.Info);
            }
        }

        static void SetupTray()
        {
            trayIcon = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Text = "AI Mod Builder (运行中)",
                Visible = true
            };

            ContextMenu menu = new ContextMenu();
            menu.MenuItems.Add("🌐 打开工作台", (s, e) => OpenBrowser(Url));
            menu.MenuItems.Add("📁 打开程序目录", (s, e) => Process.Start("explorer.exe", appDir));
            menu.MenuItems.Add("-");
            menu.MenuItems.Add("🔄 重启服务", (s, e) => RestartService());
            menu.MenuItems.Add("❌ 退出程序", (s, e) => ExitApp());

            trayIcon.ContextMenu = menu;
            trayIcon.DoubleClick += (s, e) => OpenBrowser(Url);
        }

        static void OpenBrowser(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch
            {
                Process.Start("explorer.exe", url);
            }
        }

        static void RestartService()
        {
            StopServer();
            Thread.Sleep(500);
            StartServer();
            new Thread(() => WaitForServerAndOpenBrowser()) { IsBackground = true }.Start();
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

        static void ExitApp()
        {
            if (trayIcon != null)
            {
                trayIcon.Visible = false;
                trayIcon.Dispose();
            }
            StopServer();
            Application.Exit();
        }
    }
}
