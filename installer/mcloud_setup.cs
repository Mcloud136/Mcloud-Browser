// MCloud-Setup.exe —— 发布包外层安装包装器（单文件，csc.exe 编译）
//
// 为什么需要它（源码级依据）：
//   * M155 的 setup.exe **没有任何进度 UI**，也没有静默/非静默开关：
//     `ProgressCalculator::Calculate()` 在 chrome/installer 里除单元测试外没有消费者。
//     所以"想要安装界面"只能由外层提供。
//   * 载荷是旁路新版本目录（install_worker.cc:295-306），运行中的 chrome.dll 不需要覆盖；
//     但根目录启动桩 chrome.exe / chrome_proxy.exe 在浏览器运行时是被锁的映像，上游走
//     in-use 分支：暂存成 new_chrome.exe / chrome_proxy.new.exe 并写一条
//     rename-chrome-exe AppCommand（install_worker.cc:867-901），而**系统级安装的收尾改名
//     整个委托给 Google Update**（upgrade_util_win.cc:505-506）。我们不发布 Google Update，
//     所以这一步没人执行 ⇒ 必须先让浏览器退出，更新才真正落到根启动桩上。
//
// 三条硬约束（都是本仓库用真实事故换来的，违反就等于把用户的会话拿去赌）：
//   1. **按安装路径识别实例，绝不按进程名**：只处理可执行文件位于本产品安装目录下的进程。
//      机器级 `Stop-Process chrome` 会连用户自己开着的浏览器一起干掉（缺陷 D52/D55/D106）。
//   2. **优雅优先**：先给每个顶层窗口发 WM_CLOSE，让 Chrome 走正常退出流程（保存会话、
//      必要时自己弹确认）；超时才升级为 TerminateProcess。
//   3. **装完零残留**：临时解包目录必须删掉，setup.exe / mini_installer.exe 不得驻留。
//
// 用法：
//   MCloud-Setup.exe                      用户级安装（默认，不弹 UAC），装完自动重启浏览器
//   MCloud-Setup.exe --system-level       系统级安装（自举提权）
//   MCloud-Setup.exe --no-launch          装完不重启浏览器
//   MCloud-Setup.exe --list-only          只报告"会关闭哪些实例"，不关闭、不安装（负向对照用）
//   MCloud-Setup.exe --package <路径>     使用外部 mini_installer（默认用内嵌的那份）
// 退出码：0=成功且已复验；1=复验不通过；2=环境不满足/用户取消；3=前置检查拒绝。
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class MCloudSetup
{
    // ---- 产品自身的安装位置（与 chrome.release / mini_installer 的落点一致）----
    private const string CompanyDir = "Chromium";              // 上游默认品牌，不改
    private const string AppDirName = "Application";
    private const string PackageResName = "mcloud_mini_installer.exe";
    private const int GracefulCloseWaitMs = 30000;
    private const int ForceKillWaitMs = 10000;

    private static readonly List<string> LogLines = new List<string>();
    private static ListBox _logBox;
    private static Label _stage;
    private static Button _closeBtn;
    private static ManualResetEvent _done;
    private static bool _quiet;

    // ------------------------------------------------------------------ Win32
    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")] private static extern bool EnumWindows(WndEnumProc cb, IntPtr lparam);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] private static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder s, int max);
    private delegate bool WndEnumProc(IntPtr hWnd, IntPtr lparam);
    private const uint WM_CLOSE = 0x0010;

    // -------------------------------------------------------------------- UI
    private static void Log(string s)
    {
        LogLines.Add(s);
        if (_quiet) { Console.WriteLine(s); return; }
        try
        {
            if (_logBox != null && _logBox.IsHandleCreated)
                _logBox.BeginInvoke((Action)(() => { _logBox.Items.Add(s); _logBox.TopIndex = _logBox.Items.Count - 1; }));
            else
                Console.WriteLine(s);
        }
        catch { Console.WriteLine(s); }
    }

    private static void SetStage(string s)
    {
        Log("— " + s);
        if (_quiet) return;
        try
        {
            if (_stage != null && _stage.IsHandleCreated)
                _stage.BeginInvoke((Action)(() => _stage.Text = s));
        }
        catch { }
    }

    // ------------------------------------------------------- 安装位置解析
    private static string UserAppDir()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            CompanyDir, AppDirName);
    }

    private static string SystemAppDir()
    {
        string pf = Environment.GetEnvironmentVariable("ProgramFiles") ?? @"C:\Program Files";
        return Path.Combine(pf, CompanyDir, AppDirName);
    }

    // 已安装副本的位置。判据用"根 chrome.exe 是否存在"，比只读注册表可靠：
    // 注册表会留下卸载后的空壳（本机就有 HKCU\Software\Chromium 的残留 pv 为空）。
    private static string InstalledAppDir(bool system)
    {
        string dir = system ? SystemAppDir() : UserAppDir();
        return File.Exists(Path.Combine(dir, "chrome.exe")) ? dir : null;
    }

    // 默认浏览器当前解析到哪个 exe —— 那才是"用户真正在用的那一份"。
    private static string DefaultBrowserTarget()
    {
        try
        {
            using (RegistryKey uc = Registry.CurrentUser.OpenSubKey(
                       @"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"))
            {
                string progId = uc == null ? null : uc.GetValue("ProgId") as string;
                if (string.IsNullOrEmpty(progId)) return null;
                foreach (RegistryKey r in new[] { (RegistryKey)Registry.LocalMachine, (RegistryKey)Registry.CurrentUser })
                {
                    using (RegistryKey k = r.OpenSubKey(
                               @"Software\Classes\" + progId + @"\shell\open\command"))
                    {
                        string cmd = k == null ? null : k.GetValue(null) as string;
                        if (string.IsNullOrEmpty(cmd)) continue;
                        int q1 = cmd.IndexOf('"');
                        if (q1 >= 0)
                        {
                            int q2 = cmd.IndexOf('"', q1 + 1);
                            if (q2 > q1) return cmd.Substring(q1 + 1, q2 - q1 - 1);
                        }
                        return cmd.Split(' ')[0];
                    }
                }
            }
        }
        catch (Exception) { /* 读不到就退回位置优先级判断，不因此中止安装 */ }
        return null;
    }

    // 返回 (appDir, isSystem, why)。两处都装着时，以"默认浏览器指向的那份"为准——
    // 这才是 Google Update 式行为：原地更新用户正在用的那份，而不是按命令行参数
    // 擅自换位置（换位置会让指向旧路径的任务栏固定项与快捷方式失效，并留下第二份）。
    private static string[] DetectInstall()
    {
        string user = InstalledAppDir(false);
        string sys = InstalledAppDir(true);
        if (user == null && sys == null) return new[] { null, "", "none" };
        if (user != null && sys == null) return new[] { user, "false", "only-user-level" };
        if (sys != null && user == null) return new[] { sys, "true", "only-system-level" };
        string target = DefaultBrowserTarget();
        if (target != null)
        {
            if (target.StartsWith(sys.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                return new[] { sys, "true", "both; default-browser points here" };
            if (target.StartsWith(user.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                return new[] { user, "false", "both; default-browser points here" };
        }
        // 两处都在且默认浏览器不属于任何一处：取版本高的那份（字符串比较对 a.b.c.d 够用）
        string uv = ProductVersionOf(Path.Combine(user, "chrome.exe"));
        string sv = ProductVersionOf(Path.Combine(sys, "chrome.exe"));
        bool pickSystem = string.Compare(sv, uv, StringComparison.OrdinalIgnoreCase) > 0;
        return new[] { pickSystem ? sys : user, pickSystem ? "true" : "false",
                       "both; neither owns default browser, picked higher version" };
    }

    // ------------------------------------------------ 关联与快捷方式快照
    private static Dictionary<string, string> SnapshotAssociations()
    {
        var snap = new Dictionary<string, string>();
        try
        {
            using (RegistryKey uc = Registry.CurrentUser.OpenSubKey(
                       @"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"))
                snap["UserChoice:https"] = uc == null ? "(none)" : (string)uc.GetValue("ProgId");
            snap["UserTarget"] = DefaultBrowserTarget() ?? "(unresolved)";
            snap["TargetExists"] = snap["UserTarget"] == "(unresolved)"
                                       ? "n/a"
                                       : (File.Exists(snap["UserTarget"]) ? "yes" : "NO");
            using (RegistryKey k = Registry.LocalMachine.OpenSubKey(
                       @"SOFTWARE\Clients\StartMenuInternet\Chromium\shell\open\command"))
                snap["CMI:Chromium"] = k == null ? "(none)" : (string)k.GetValue(null);
        }
        catch (Exception e) { snap["snapshot-error"] = e.Message; }
        return snap;
    }

    // 所有指向本产品安装目录的 .lnk（桌面 / 开始菜单 / 快速启动 / 任务栏固定）。
    private static List<string[]> ShortcutLinks()
    {
        var list = new List<string[]>();
        object shell = null;
        try { shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell")); }
        catch { return list; }
        string[] dirs =
        {
            Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonDesktopDirectory),
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu) + @"\Programs",
            Environment.GetEnvironmentVariable("APPDATA")
                + @"\Microsoft\Internet Explorer\Quick Launch",
        };
        foreach (string d in dirs)
        {
            if (string.IsNullOrEmpty(d) || !Directory.Exists(d)) continue;
            IEnumerable<string> files;
            try { files = Directory.EnumerateFiles(d, "*.lnk", SearchOption.AllDirectories); }
            catch { continue; }
            foreach (string lnk in files)
            {
                string target = LnkTarget(shell, lnk);
                if (target == null) continue;
                if (!target.Contains(CompanyDir + "\\" + AppDirName)) continue;
                list.Add(new[] { lnk, target, File.Exists(target) ? "ok" : "BROKEN" });
            }
        }
        return list;
    }

    private static string LnkTarget(object shell, string path)
    {
        try
        {
            object sc = shell.GetType().InvokeMember("CreateShortcut",
                        BindingFlags.InvokeMethod, null, shell, new object[] { path });
            object t = sc.GetType().InvokeMember("TargetPath",
                        BindingFlags.GetProperty, null, sc, null);
            return t as string;
        }
        catch { return null; }
    }

    private static bool Has(Dictionary<string, string> d, string k)
    {
        return d != null && d.ContainsKey(k) && d[k] != null;
    }

    // 更新后复算：默认浏览器链是否**从好变坏**（那是回归，判失败）；
    // 快捷方式是否指向了被我们主动放弃的旧位置（那是用户选择的后果，只报告）。
    private static bool CheckAssociations(Dictionary<string, string> before,
                                          List<string[]> linksBefore, List<string> notes)
    {
        var after = SnapshotAssociations();
        foreach (string k in after.Keys)
            notes.Add(string.Format("关联 {0}: {1} -> {2}", k,
                                    before.ContainsKey(k) ? before[k] : "?", after[k]));

        bool regressed = Has(before, "TargetExists") &&
                         before["TargetExists"] == "yes" &&
                         after["TargetExists"] == "NO";
        if (regressed)
            notes.Add("FAIL: 默认浏览器链原本解析到存在的 exe，更新后指向 " + after["UserTarget"] +
                      " 但该文件不存在 —— 这是回归，需要处理。");

        var linksAfter = ShortcutLinks();
        foreach (string[] l in linksAfter)
            if (l[2] == "BROKEN")
                notes.Add("WARN: 快捷方式目标已不存在：" + l[0] + " -> " + l[1] +
                          "（任务栏固定项无公开 API 可自动恢复；保持安装位置不变即可不再出现此情况）");
        if (linksBefore.Count != linksAfter.Count)
            notes.Add(string.Format("快捷方式数量 前={0} 后={1}", linksBefore.Count, linksAfter.Count));
        return !regressed;
    }


    private static bool IsAdmin()
    {
        using (WindowsIdentity id = WindowsIdentity.GetCurrent())
            return new WindowsPrincipal(id).IsInRole(WindowsBuiltInRole.Administrator);
    }

    // 只认"可执行文件落在本产品安装目录下"的进程。
    private static List<Process> OurBrowserProcesses(params string[] appDirs)
    {
        List<Process> hits = new List<Process>();
        foreach (Process p in Process.GetProcessesByName("chrome"))
        {
            string path = null;
            try { path = p.MainModule != null ? p.MainModule.FileName : null; }
            catch (Exception)
            {
                // 32/64 位不匹配或权限不足时读不到 MainModule：宁可**不**把它算作目标，
                // 也不能"读不到就杀"——那正是 D106 那类事故的形状。
                try { p.Dispose(); } catch { }
                continue;
            }
            if (string.IsNullOrEmpty(path)) { try { p.Dispose(); } catch { } continue; }
            foreach (string dir in appDirs)
            {
                if (!string.IsNullOrEmpty(dir) &&
                    path.StartsWith(dir.TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
                {
                    hits.Add(p);
                    break;
                }
            }
            if (!hits.Contains(p)) { try { p.Dispose(); } catch { } }
        }
        return hits;
    }

    private static List<IntPtr> TopLevelWindows(uint pid)
    {
        List<IntPtr> found = new List<IntPtr>();
        EnumWindows((h, l) =>
        {
            uint wpid;
            GetWindowThreadProcessId(h, out wpid);
            if (wpid == pid && IsWindowVisible(h) && GetWindowTextLength(h) > 0) found.Add(h);
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // ------------------------------------------------------- 优雅关闭
    private static bool CloseInstances(List<Process> procs, bool allowForce)
    {
        if (procs.Count == 0) { Log("没有正在运行的本产品实例。"); return true; }
        foreach (Process p in procs)
            Log(string.Format("将关闭：pid={0}  窗口标题={1}  路径={2}",
                              p.Id, string.Join(" | ", TitleOf((uint)p.Id)), p.MainModule.FileName));

        int windows = 0;
        foreach (Process p in procs)
            foreach (IntPtr h in TopLevelWindows((uint)p.Id)) { PostMessage(h, WM_CLOSE, IntPtr.Zero, IntPtr.Zero); windows++; }
        Log(string.Format("已发送 {0} 个 WM_CLOSE（{1} 个实例），等待正常退出……", windows, procs.Count));

        if (!WaitForExit(procs, GracefulCloseWaitMs))
        {
            List<Process> alive = Alive(procs);
            if (!allowForce)
            {
                Log("超时仍有 " + alive.Count + " 个实例未退出；当前策略不强制结束，中止以免半途而废。");
                return false;
            }
            Log("超时 " + alive.Count + " 个实例仍存活，升级为强制结束（Chrome 会在下次启动时恢复会话）。");
            foreach (Process p in alive) { try { p.Kill(); } catch (Exception e) { Log("结束 pid=" + p.Id + " 失败：" + e.Message); } }
            if (!WaitForExit(alive, ForceKillWaitMs))
            {
                Log("强制结束后仍有存活实例，放弃。");
                return false;
            }
        }
        Log("本产品实例已全部退出。");
        return true;
    }

    private static string[] TitleOf(uint pid)
    {
        List<string> t = new List<string>();
        foreach (IntPtr h in TopLevelWindows(pid))
        {
            StringBuilder sb = new StringBuilder(256);
            GetWindowText(h, sb, sb.Capacity);
            if (sb.Length > 0) t.Add(sb.ToString());
        }
        return t.ToArray();
    }

    private static bool WaitForExit(List<Process> procs, int ms)
    {
        DateTime deadline = DateTime.Now.AddMilliseconds(ms);
        while (DateTime.Now < deadline)
        {
            if (Alive(procs).Count == 0) return true;
            Thread.Sleep(500);
        }
        return Alive(procs).Count == 0;
    }

    private static List<Process> Alive(List<Process> procs)
    {
        List<Process> live = new List<Process>();
        foreach (Process p in procs)
        {
            try { p.Refresh(); if (!p.HasExited) live.Add(p); }
            catch { /* 已退出 */ }
        }
        return live;
    }

    // ------------------------------------------------------- 包与安装
    private static string ExtractPackage(string tempRoot)
    {
        Assembly asm = Assembly.GetExecutingAssembly();
        string[] names = asm.GetManifestResourceNames();
        foreach (string n in names)
        {
            if (!n.EndsWith(PackageResName, StringComparison.OrdinalIgnoreCase)) continue;
            string dest = Path.Combine(tempRoot, PackageResName);
            using (Stream s = asm.GetManifestResourceStream(n))
            using (FileStream fs = File.Create(dest))
                s.CopyTo(fs, 1 << 20);
            Log(string.Format("已从自身解出安装包：{0}（{1:N0} 字节）", dest, new FileInfo(dest).Length));
            return dest;
        }
        return null;
    }

    private static int RunAndWait(string exe, string args)
    {
        ProcessStartInfo psi = new ProcessStartInfo(exe, args);
        psi.UseShellExecute = false;
        psi.WorkingDirectory = Path.GetDirectoryName(exe);
        using (Process p = Process.Start(psi))
        {
            Log("启动：" + Path.GetFileName(exe) + " " + args);
            p.WaitForExit();
            return p.ExitCode;
        }
    }

    private static string ProductVersionOf(string exe)
    {
        try
        {
            if (!File.Exists(exe)) return "(缺失)";
            FileVersionInfo v = FileVersionInfo.GetVersionInfo(exe);
            return string.IsNullOrEmpty(v.ProductVersion) ? v.FileVersion : v.ProductVersion;
        }
        catch (Exception e) { return "(读取失败:" + e.Message + ")"; }
    }

    private static void DeleteTree(string dir)
    {
        for (int attempt = 0; attempt < 10; attempt++)
        {
            try { if (Directory.Exists(dir)) Directory.Delete(dir, true); return; }
            catch (IOException) { Thread.Sleep(500); }
            catch (UnauthorizedAccessException) { Thread.Sleep(500); }
        }
        try { if (Directory.Exists(dir)) Directory.Delete(dir, true); }
        catch (Exception e) { Log("临时目录未能删除（需人工清理）：" + dir + " — " + e.Message); }
    }

    // ------------------------------------------------------- 复验
    // 装完必须证明"用户下次双击真的得到这一版"，而不是"安装器返回 0"。
    private static bool Verify(string appDir, string wantVersion, List<string> notes)
    {
        bool ok = true;
        string rootExe = Path.Combine(appDir, "chrome.exe");
        string got = ProductVersionOf(rootExe);
        notes.Add("根 chrome.exe 版本 = " + got + "（期望 " + wantVersion + "）");
        if (!got.StartsWith(wantVersion.Split('-')[0], StringComparison.OrdinalIgnoreCase)) ok = false;

        string verDir = Path.Combine(appDir, wantVersion);
        notes.Add("版本目录 " + wantVersion + " 存在 = " + Directory.Exists(verDir));
        if (!Directory.Exists(verDir)) ok = false;

        string dll = Path.Combine(verDir, "chrome.dll");
        notes.Add("chrome.dll 存在 = " + File.Exists(dll));
        if (!File.Exists(dll)) ok = false;

        string flags = Path.Combine(verDir, "mcloud_flags.txt");
        notes.Add("mcloud_flags.txt 在版本目录 = " + File.Exists(flags));
        if (!File.Exists(flags)) ok = false;

        // D109：根目录那份是历史手工残留，v8 加载器已经忽略它；这里只做卫生清理，
        // 不作为失败条件（否则老机器上第一次升级会被无关垃圾卡住）。
        string stray = Path.Combine(appDir, "mcloud_flags.txt");
        if (File.Exists(stray))
        {
            try { File.Delete(stray); notes.Add("已清理根目录残留 mcloud_flags.txt（D109 卫生项）"); }
            catch (Exception e) { notes.Add("根目录残留 mcloud_flags.txt 未能删除：" + e.Message); }
        }

        // 上游 in-use 分支留下的暂存件：如果还在，说明改名没完成。
        foreach (string leftover in new[] { "new_chrome.exe", "chrome_proxy.new.exe" })
        {
            string p = Path.Combine(appDir, leftover);
            if (File.Exists(p)) { notes.Add("发现未消化的暂存件 " + leftover + " ⇒ 根启动桩可能仍是旧的"); ok = false; }
        }
        return ok;
    }

    // ------------------------------------------------------- 提权自举
    private static bool RelaunchElevated(string args)
    {
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(Application.ExecutablePath, args);
            psi.Verb = "runas";
            psi.UseShellExecute = true;
            Process.Start(psi);
            return true;
        }
        catch (Win32Exception) { return false; }   // 用户在 UAC 上点了"否"
        catch (Exception e) { Log("提权重启失败：" + e.Message); return false; }
    }

    // ------------------------------------------------------------------ main
    [STAThread]
    private static int Main(string[] argv)
    {
        bool systemLevel = false, noLaunch = false, listOnly = false;
        bool explicitLevel = false;
        string externalPackage = null;
        for (int i = 0; i < argv.Length; i++)
        {
            string a = argv[i].ToLowerInvariant();
            if (a == "--system-level") { systemLevel = true; explicitLevel = true; }
            else if (a == "--user-level") { systemLevel = false; explicitLevel = true; }
            else if (a == "--no-launch") noLaunch = true;
            else if (a == "--list-only") listOnly = true;
            else if (a == "--quiet") _quiet = true;
            else if (a == "--package" && i + 1 < argv.Length) externalPackage = argv[++i];
            else if (a == "--help" || a == "-h")
            {
                Console.WriteLine("用法：MCloud-Setup.exe [--system-level|--user-level] [--no-launch] " +
                                  "[--list-only] [--quiet] [--package <mini_installer.exe>]");
                return 0;
            }
            else { Console.WriteLine("未知参数：" + argv[i]); return 3; }
        }

        // 位置选择：默认**就地更新已存在的那一份**（Google Update 式）。只有显式给
        // --system-level / --user-level 才允许换安装位置，换之前把后果讲清楚。
        string[] det = DetectInstall();
        string detected = det[0];
        string wantedDir = systemLevel ? SystemAppDir() : UserAppDir();
        if (detected == null)
        {
            Log("未检测到已安装副本，按" + (systemLevel ? "系统级" : "用户级") + "全新安装。");
        }
        else if (!explicitLevel)
        {
            systemLevel = det[1] == "true";
            wantedDir = systemLevel ? SystemAppDir() : UserAppDir();
            Log("检测到已安装副本：" + detected + "（" + det[2] + "）");
            Log("  → 就地更新这一份，不换位置（换位置会让旧路径的任务栏固定项失效）。");
        }
        else if (!string.Equals(detected.TrimEnd('\\'), wantedDir.TrimEnd('\\'),
                                StringComparison.OrdinalIgnoreCase))
        {
            Log("WARN: 已检测到另一位置的安装 " + detected + "，但命令行显式要求装到 " + wantedDir);
            Log("      后果：指向旧路径的任务栏固定项与快捷方式会失效，且机器上会留下两份安装。");
        }
        string appDir = wantedDir;

        // 系统级安装必须提权；用户级不需要（也就不制造多余的 UAC 摩擦）。
        if (systemLevel && !IsAdmin())
        {
            string rest = string.Join(" ", RebuildArgs(argv, "--system-level"));
            if (!RelaunchElevated("--system-level " + rest))
            {
                Console.WriteLine("未获得管理员权限，系统级安装取消。");
                return 2;
            }
            return 0;   // 提权后的那个实例接管
        }

        if (!_quiet) BuildUi(systemLevel, appDir);

        int rc;
        string tempRoot = Path.Combine(Path.GetTempPath(), "MCloudSetup-" + Guid.NewGuid().ToString("N").Substring(0, 12));
        try
        {
            SetStage("检查运行中的实例（按安装路径识别，不按进程名）");
            // 只处理**本次要写入的那个目录**下的实例。
            // 曾经把另一个安装位置也并进关闭集合（"反正都是本产品"），那是错的：
            // 系统级安装不碰用户级目录，那样做等于无故关掉用户正在用的浏览器。
            // 另一个位置的实例不锁我们要写的任何文件，因此无需关闭。
            List<Process> ours = OurBrowserProcesses(appDir);
            if (listOnly)
            {
                if (ours.Count == 0) Log("--list-only：没有本产品实例。");
                foreach (Process p in ours)
                    Log(string.Format("--list-only：会关闭 pid={0} 路径={1}", p.Id, p.MainModule.FileName));
                rc = 0;
                Finish(rc);
                return rc;
            }
            if (!CloseInstances(ours, true)) { rc = 2; Finish(rc); return rc; }

            Directory.CreateDirectory(tempRoot);
            string pkg = externalPackage;
            if (pkg != null && !File.Exists(pkg))
            {
                Log("指定的安装包不存在：" + pkg); rc = 3; Finish(rc); return rc;
            }
            if (pkg == null)
            {
                pkg = ExtractPackage(tempRoot);
                if (pkg == null)
                {
                    Log("自身内没有安装包资源（" + PackageResName + "）。请用 --package 指定，" +
                        "或改用打包时生成的内嵌版本。");
                    rc = 3; Finish(rc); return rc;
                }
            }

            string wantVersion = ProductVersionOf(pkg).Split(' ')[0];
            if (wantVersion.Length == 0 || wantVersion.StartsWith("("))
            {
                Log("无法从安装包读出目标版本号。"); rc = 3; Finish(rc); return rc;
            }
            var assocBefore = SnapshotAssociations();
            var linksBefore = ShortcutLinks();
            Log(string.Format("更新前快照：默认浏览器解析 {0}（目标存在={1}）、指向本产品的快捷方式 {2} 个",
                              assocBefore["UserTarget"], assocBefore["TargetExists"], linksBefore.Count));
            SetStage("安装 " + wantVersion + "（" + (systemLevel ? "系统级" : "用户级") + "）");
            int irect = RunAndWait(pkg, "--system-level");   // mini_installer 自己会再派生 setup.exe 并等待
            Log("mini_installer 退出码 = " + irect);

            SetStage("复验：用户下次双击到底得到哪一版");
            List<string> notes = new List<string>();
            bool ok = Verify(appDir, wantVersion, notes);
            // 默认浏览器链"从好变坏"= 回归，判失败；快捷方式指向旧路径 = 换位置的已知后果，
            // 只报告不判失败（任务栏固定项没有公开 API 可恢复，唯一可靠的办法是不换位置）。
            if (!CheckAssociations(assocBefore, linksBefore, notes)) ok = false;
            foreach (string n in notes) Log("  · " + n);

            rc = ok ? 0 : 1;
            SetStage(ok ? "完成：已确认更新到 " + wantVersion : "复验未通过（见上方明细）");
            if (ok && !noLaunch && File.Exists(Path.Combine(appDir, "chrome.exe")))
            {
                SetStage("重启浏览器");
                try
                {
                    ProcessStartInfo psi = new ProcessStartInfo(Path.Combine(appDir, "chrome.exe"));
                    psi.UseShellExecute = true;
                    Process.Start(psi);
                }
                catch (Exception e) { Log("自动重启失败（可手动打开）：" + e.Message); }
            }
            Finish(rc);
        }
        catch (Exception e)
        {
            // 没有这一层的话，任何未预期异常都会让进程直接崩掉：GUI 版连"为什么失败"
            // 都显示不出来（D114 同口径：判据与诊断不能被旁路操作带走）。
            Log("异常：" + e.Message);
            if (e.StackTrace != null)
            {
                string st = e.StackTrace;
                Log(st.Substring(0, Math.Min(400, st.Length)));
            }
            rc = 2;
            Finish(rc);
        }
        finally
        {
            DeleteTree(tempRoot);
            // 硬约束 3：不得留下任何更新相关进程。setup.exe / mini_installer.exe 都是
            // 同步等待运行的，正常路径下此时已退出；这里再确认一次并报告，不静默忽略。
            List<string> stragglers = new List<string>();
            foreach (string n in new[] { "setup", "mini_installer" })
            {
                foreach (Process p in Process.GetProcessesByName(n))
                {
                    stragglers.Add(n + " pid=" + p.Id);
                    p.Dispose();
                }
            }
            if (stragglers.Count > 0)
                Log("WARN: 仍有更新相关进程驻留：" + string.Join(", ", stragglers.ToArray()));
            else
                Log("确认：无 setup.exe / mini_installer.exe 驻留。");
        }
        return rc;
    }

    private static string[] RebuildArgs(string[] argv, string drop)
    {
        List<string> keep = new List<string>();
        for (int i = 0; i < argv.Length; i++)
        {
            if (argv[i].ToLowerInvariant() == drop) continue;
            if (argv[i].ToLowerInvariant() == "--package" && i + 1 < argv.Length) { keep.Add(argv[i]); keep.Add("\"" + argv[i + 1] + "\""); i++; continue; }
            keep.Add(argv[i]);
        }
        return keep.ToArray();
    }

    private static void Finish(int rc)
    {
        Log("退出码 = " + rc);
        // GUI 版必须在这里停住：否则 Main 一 return，后台 UI 线程随进程一起消失，
        // 用户连"复验未通过"这行字都看不到（首版就是这个 bug）。
        // 控制台/静默版不等，保持可脚本化。
        if (_quiet || _done == null) return;
        try
        {
            if (_closeBtn != null && _closeBtn.IsHandleCreated)
                _closeBtn.BeginInvoke((Action)(() =>
                {
                    _closeBtn.Enabled = true;
                    _closeBtn.Text = rc == 0 ? "完成" : "关闭（安装未通过复验）";
                    _stage.BeginInvoke((Action)(() =>
                        _stage.ForeColor = rc == 0 ? Color.DarkGreen : Color.DarkRed));
                }));
            _done.WaitOne();
        }
        catch { }
    }

    private static void BuildUi(bool systemLevel, string appDir)
    {
        Form f = new Form();
        f.Text = "MCloud Browser 安装程序" + (systemLevel ? "（系统级）" : "");
        f.ClientSize = new Size(620, 340);
        f.FormBorderStyle = FormBorderStyle.FixedSingle;
        f.MaximizeBox = false;
        f.StartPosition = FormStartPosition.CenterScreen;
        f.TopMost = true;

        _stage = new Label();
        _stage.SetBounds(12, 10, 596, 22);
        _stage.Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold);
        _stage.Text = "准备中…";

        _logBox = new ListBox();
        _logBox.SetBounds(12, 38, 596, 250);
        _logBox.Font = new Font("Microsoft YaHei UI", 9f);
        _logBox.IntegralHeight = false;
        _logBox.HorizontalScrollbar = true;

        Label hint = new Label();
        hint.SetBounds(12, 296, 430, 36);
        hint.Text = "提示：安装会先关闭正在运行的 MCloud Browser（Chrome 会在下次启动时恢复标签页）。";

        _closeBtn = new Button();
        _closeBtn.SetBounds(452, 298, 156, 30);
        _closeBtn.Text = "安装中…";
        _closeBtn.Enabled = false;
        _closeBtn.Click += delegate { f.Close(); };

        _done = new ManualResetEvent(false);
        f.FormClosed += delegate { _done.Set(); };

        f.Controls.Add(_stage);
        f.Controls.Add(_logBox);
        f.Controls.Add(hint);
        f.Controls.Add(_closeBtn);

        Thread ui = new Thread(() => { Application.Run(f); });
        ui.IsBackground = true;
        ui.SetApartmentState(ApartmentState.STA);
        ui.Start();
        // 等窗口句柄建好，避免前期日志丢到控制台
        for (int i = 0; i < 40 && !_logBox.IsHandleCreated; i++) Thread.Sleep(50);
    }
}
