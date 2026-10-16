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
        private static Process appWindowProcess = null;
        private static string appDir = "";
        private const string MutexName = "AIModBuilder_App_SingleInstance_Mutex";
        private const string Url = "http://127.0.0.1:8765";

        static void Log(string msg)
        {
            try
            {
                File.AppendAllText(Path.Combine(appDir, "launcher.log"), DateTime.Now.ToString("HH:mm:ss.fff") + " " + msg + "\r\n");
            }
            catch { }
        }

        [STAThread]
        static void Main()
        {
            appDir = AppDomain.CurrentDomain.BaseDirectory;
            Directory.SetCurrentDirectory(appDir);
            Log("=== AIModBuilder starting ===");

            bool createdNew;
            using (Mutex mutex = new Mutex(true, MutexName, out createdNew))
            {
                if (!createdNew)
                {
                    Log("Another instance is already running.");
                    // Activate existing instance by launching URL or app
                    LaunchAppWindow();
                    return;
                }

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                StartServer();
                if (WaitForServer())
                {
                    LaunchAppWindow();
                }
                StopServer();
                Log("=== AIModBuilder exiting cleanly ===");
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

            Log("Using python binary: " + pythonExe);

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
                Log("Server started PID: " + (serverProcess != null ? serverProcess.Id.ToString() : "null"));
            }
            catch (Exception ex)
            {
                Log("StartServer failed: " + ex);
                MessageBox.Show("启动服务失败: " + ex.Message, "AI Mod Builder", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Environment.Exit(1);
            }
        }

        static bool WaitForServer()
        {
            Log("Waiting for server ready...");
            for (int i = 0; i < 50; i++)
            {
                if (serverProcess != null && serverProcess.HasExited)
                {
                    Log("Server exited prematurely with code: " + serverProcess.ExitCode);
                    MessageBox.Show("后端服务异常退出，请检查 runtime 环境。", "AI Mod Builder", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return false;
                }

                try
                {
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(Url + "/api/health");
                    req.Timeout = 600;
                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                    {
                        if (resp.StatusCode == HttpStatusCode.OK)
                        {
                            Log("Server is healthy (attempt " + i + ")");
                            return true;
                        }
                    }
                }
                catch
                {
                    Thread.Sleep(200);
                }
            }

            Log("Server wait timeout!");
            MessageBox.Show("服务启动超时，请重试。", "AI Mod Builder", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return false;
        }

        static void LaunchAppWindow()
        {
            string profileDir = Path.Combine(Path.GetTempPath(), "AIModBuilder_AppProfile");

            // Clean stale lockfile if left behind by abnormal termination
            try
            {
                string lockfile = Path.Combine(profileDir, "lockfile");
                if (File.Exists(lockfile))
                {
                    File.Delete(lockfile);
                }
            }
            catch { }

            string browserExe = FindAppBrowser();
            Log("App browser found: " + browserExe);

            if (!string.IsNullOrEmpty(browserExe))
            {
                string userDirArg = profileDir.Contains(" ") ? ("\"--user-data-dir=" + profileDir + "\"") : ("--user-data-dir=" + profileDir);
                string args = string.Format(
                    "--app={0} {1} --window-size=1420,900 --disable-extensions --no-first-run --no-default-browser-check",
                    Url,
                    userDirArg
                );

                Log("Starting browser process: " + browserExe + " " + args);

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
                        Log("Browser process started, PID: " + appWindowProcess.Id);

                        // Check if it exited immediately (e.g. delegated to existing Edge/Chrome instance or conflict)
                        if (appWindowProcess.WaitForExit(600))
                        {
                            Log("Browser process handed off/exited with code: " + appWindowProcess.ExitCode + ". Entering tray mode to keep backend alive.");
                            RunFallbackTrayMode();
                            return;
                        }

                        // Normal execution: dedicated application window is open!
                        // Wait until the user closes this window.
                        appWindowProcess.WaitForExit();
                        Log("User closed the application window.");
                        return;
                    }
                }
                catch (Exception ex)
                {
                    Log("App window launch error: " + ex.Message);
                }
            }

            // Fallback: If dedicated window could not be maintained, run in default browser with tray icon
            Log("Running fallback browser mode with tray icon...");
            RunFallbackTrayMode();
        }

        static void RunFallbackTrayMode()
        {
            try
            {
                Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
            }
            catch { }

            NotifyIcon tray = new NotifyIcon
            {
                Icon = SystemIcons.Application,
                Text = "AI Mod Builder (运行中)",
                Visible = true
            };

            ContextMenu menu = new ContextMenu();
            menu.MenuItems.Add("🌐 打开工作台", (s, e) => {
                try { Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true }); } catch { }
            });
            menu.MenuItems.Add("-");
            menu.MenuItems.Add("❌ 退出程序", (s, e) => {
                tray.Visible = false;
                tray.Dispose();
                StopServer();
                Application.Exit();
            });

            tray.ContextMenu = menu;
            tray.DoubleClick += (s, e) => {
                try { Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true }); } catch { }
            };

            Application.Run();
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
            Log("Stopping backend server...");
            try
            {
                if (serverProcess != null && !serverProcess.HasExited)
                {
                    serverProcess.Kill();
                    Log("Server terminated.");
                }
            }
            catch (Exception ex)
            {
                Log("StopServer error: " + ex.Message);
            }
        }
    }
}
