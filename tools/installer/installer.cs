// lite browser test 安装程序
// 作者：lvzian
// 编译：csc /target:winexe /win32icon:lite_browser.ico installer.cs
//
// 安装包结构：本 exe 末尾追加了 payload(zip) + 12 字节尾部标记
//    [ exe ][ zip 数据 ][ Int64 长度 ][ 'L','T','B','S' ]

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("lite browser test 安装程序")]
[assembly: AssemblyProduct("lite browser test")]
[assembly: AssemblyCompany("lvzian")]
[assembly: AssemblyCopyright("Copyright (C) 2026 lvzian")]
[assembly: AssemblyDescription("lite browser test 安装程序（Chromium 内核的仿 Windows XP 风格浏览器，测试版）")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace LiteBrowserSetup
{
    // ------------------------------------------------------------------ //
    // 运行参数
    // ------------------------------------------------------------------ //
    class Options
    {
        public bool Silent;
        public string Dir;
        public bool NoDesktop;
        public bool NoStartMenu;
        public bool NoRun;

        public static Options Parse(string[] args)
        {
            Options o = new Options();
            foreach (string raw in args)
            {
                string a = raw.Trim();
                string lower = a.ToLowerInvariant();
                if (lower == "/s" || lower == "/silent" || lower == "-s") o.Silent = true;
                else if (lower.StartsWith("/dir=")) o.Dir = a.Substring(5).Trim('"');
                else if (lower == "/nodesktop") o.NoDesktop = true;
                else if (lower == "/nostartmenu") o.NoStartMenu = true;
                else if (lower == "/norun") o.NoRun = true;
            }
            return o;
        }
    }

    // ------------------------------------------------------------------ //
    // 常量与工具
    // ------------------------------------------------------------------ //
    static class Const
    {
        public const string AppName = "lite browser test";
        public const string Version = "1.0.test";
        public const string Publisher = "lvzian";
        public const string ExeName = "lite browser test.exe";
        public const string UninstallName = "uninstall.exe";
        public const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\lite browser test";

        public static readonly Color Face = Color.FromArgb(0xEC, 0xE9, 0xD8);
        public static readonly Color Border = Color.FromArgb(0xAC, 0xA8, 0x99);
        public static readonly Color FieldBorder = Color.FromArgb(0x7F, 0x9D, 0xB9);
        public static readonly Color CaptionTop = Color.FromArgb(0x4C, 0x9B, 0xF7);
        public static readonly Color CaptionMid = Color.FromArgb(0x0B, 0x5F, 0xE6);
        public static readonly Color CaptionBottom = Color.FromArgb(0x0A, 0x46, 0xB8);

        public static string DefaultDir()
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            return Path.Combine(Path.Combine(local, "Programs"), AppName);
        }

        public static Font UIFont(float size)
        {
            try { return new Font("Microsoft YaHei UI", size); }
            catch { return new Font("Tahoma", size); }
        }
    }

    // ------------------------------------------------------------------ //
    // XP 风格控件
    // ------------------------------------------------------------------ //
    class XPButton : Button
    {
        private bool hot;
        private bool down;

        public XPButton()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 0;
            Font = Const.UIFont(9F);
            Height = 25;
            Width = 88;
            Cursor = Cursors.Hand;
        }

        protected override void OnMouseEnter(EventArgs e) { hot = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hot = false; down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { down = true; Invalidate(); base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { down = false; Invalidate(); base.OnMouseUp(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle r = new Rectangle(0, 0, Width - 1, Height - 1);

            Color top = Color.White;
            Color bottom = Color.FromArgb(0xE2, 0xDF, 0xD2);
            if (down) { top = Color.FromArgb(0xDC, 0xD7, 0xC6); bottom = Color.FromArgb(0xEF, 0xEB, 0xDD); }
            else if (hot) { top = Color.FromArgb(0xFF, 0xFD, 0xF5); bottom = Color.FromArgb(0xFF, 0xE3, 0x9B); }

            using (LinearGradientBrush brush = new LinearGradientBrush(r, top, bottom, 90f))
            using (Pen pen = new Pen(Color.FromArgb(0x00, 0x3C, 0x74)))
            {
                g.FillRectangle(brush, r);
                g.DrawRectangle(pen, r);
            }
            TextRenderer.DrawText(g, Text, Font, r, ForeColor,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
    }

    class XPProgress : Control
    {
        private int value;
        public int Value
        {
            get { return value; }
            set { this.value = Math.Max(0, Math.Min(100, value)); Invalidate(); }
        }

        public XPProgress()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
            Height = 18;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Rectangle r = new Rectangle(0, 0, Width - 1, Height - 1);
            using (SolidBrush back = new SolidBrush(Color.White))
            using (Pen pen = new Pen(Color.FromArgb(0xA0, 0xA0, 0xA0)))
            {
                g.FillRectangle(back, r);
                g.DrawRectangle(pen, r);
            }
            int inner = Width - 4;
            int filled = (int)(inner * (value / 100.0));
            if (filled > 0)
            {
                Rectangle bar = new Rectangle(2, 2, filled, Height - 5);
                using (LinearGradientBrush brush = new LinearGradientBrush(
                    new Rectangle(0, bar.Top, bar.Width, bar.Height),
                    Color.FromArgb(0xC7, 0xEF, 0xA8), Color.FromArgb(0x47, 0xA6, 0x2A), 90f))
                {
                    g.FillRectangle(brush, bar);
                }
            }
        }
    }

    class LunaHeader : Panel
    {
        public string Title = Const.AppName;
        public string Subtitle = "";

        public LunaHeader()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint |
                     ControlStyles.OptimizedDoubleBuffer, true);
            Height = 62;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            Rectangle r = new Rectangle(0, 0, Width, Height);
            using (LinearGradientBrush brush = new LinearGradientBrush(
                new Rectangle(0, 0, Width, Height), Const.CaptionTop, Const.CaptionBottom, 90f))
            {
                ColorBlend blend = new ColorBlend(3);
                blend.Colors = new Color[] { Const.CaptionTop, Const.CaptionMid, Const.CaptionBottom };
                blend.Positions = new float[] { 0f, 0.45f, 1f };
                brush.InterpolationColors = blend;
                g.FillRectangle(brush, r);
            }
            using (SolidBrush white = new SolidBrush(Color.White))
            using (Font titleFont = new Font(Const.UIFont(13F).FontFamily, 13F, FontStyle.Bold))
            using (Font subFont = Const.UIFont(9F))
            {
                g.DrawString(Title, titleFont, white, new PointF(16, 8));
                if (Subtitle.Length > 0)
                    g.DrawString(Subtitle, subFont, white, new PointF(18, 36));
            }
            using (Pen pen = new Pen(Color.FromArgb(0x08, 0x31, 0xA0)))
                g.DrawLine(pen, 0, Height - 1, Width, Height - 1);
        }
    }

    // ------------------------------------------------------------------ //
    // 主窗体
    // ------------------------------------------------------------------ //
    class SetupForm : Form
    {
        private readonly Options options;
        private LunaHeader header;
        private Panel pageWelcome;
        private Panel pageProgress;
        private Panel pageDone;
        private TextBox editDir;
        private CheckBox checkDesktop;
        private CheckBox checkStartMenu;
        private CheckBox checkRun;
        private XPButton btnInstall;
        private XPButton btnCancel;
        private XPButton btnBrowse;
        private XPButton btnFinish;
        private XPProgress progress;
        private Label labelProgress;
        private Label labelError;
        private string installedDir;

        public SetupForm(Options opt)
        {
            options = opt;
            Text = Const.AppName + " 安装程序";
            Font = Const.UIFont(9F);
            BackColor = Const.Face;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(520, 372);

            header = new LunaHeader();
            header.Title = Const.AppName + " " + Const.Version;
            header.Subtitle = "基于 Chromium 内核的仿 Windows XP 风格浏览器（测试版）";
            header.SetBounds(0, 0, ClientSize.Width, 62);
            Controls.Add(header);

            BuildWelcome();
            BuildProgress();
            BuildDone();

            ShowPage(pageWelcome);
        }

        // ---------------- 页面 1：欢迎 ---------------- //
        private void BuildWelcome()
        {
            pageWelcome = new Panel();
            pageWelcome.SetBounds(0, 62, ClientSize.Width, ClientSize.Height - 62);
            pageWelcome.BackColor = Const.Face;

            Label info = new Label();
            info.Text = "安装程序将把 " + Const.AppName + " 安装到下面的目录，并创建快捷方式。";
            info.SetBounds(18, 14, 480, 20);
            pageWelcome.Controls.Add(info);

            Label label = new Label();
            label.Text = "安装位置(&D)：";
            label.SetBounds(18, 44, 90, 20);
            pageWelcome.Controls.Add(label);

            editDir = new TextBox();
            editDir.SetBounds(112, 41, 306, 23);
            editDir.Text = options.Dir != null && options.Dir.Length > 0 ? options.Dir : Const.DefaultDir();
            pageWelcome.Controls.Add(editDir);

            btnBrowse = new XPButton();
            btnBrowse.Text = "浏览(&B)...";
            btnBrowse.SetBounds(424, 40, 78, 25);
            btnBrowse.Click += delegate { BrowseFolder(); };
            pageWelcome.Controls.Add(btnBrowse);

            Label space = new Label();
            space.Text = "所需空间 322 MB　·　当前用户安装，无需管理员权限";
            space.ForeColor = Color.FromArgb(0x6A, 0x6A, 0x6A);
            space.SetBounds(18, 72, 480, 18);
            pageWelcome.Controls.Add(space);

            GroupBox group = new GroupBox();
            group.Text = "选项";
            group.SetBounds(18, 100, 484, 96);
            pageWelcome.Controls.Add(group);

            checkDesktop = new CheckBox();
            checkDesktop.Text = "创建桌面快捷方式";
            checkDesktop.Checked = !options.NoDesktop;
            checkDesktop.Enabled = !options.NoDesktop;
            checkDesktop.SetBounds(16, 24, 300, 20);
            group.Controls.Add(checkDesktop);

            checkStartMenu = new CheckBox();
            checkStartMenu.Text = "创建开始菜单快捷方式";
            checkStartMenu.Checked = !options.NoStartMenu;
            checkStartMenu.Enabled = !options.NoStartMenu;
            checkStartMenu.SetBounds(16, 48, 300, 20);
            group.Controls.Add(checkStartMenu);

            checkRun = new CheckBox();
            checkRun.Text = "安装完成后运行 " + Const.AppName;
            checkRun.Checked = !options.NoRun;
            checkRun.Enabled = !options.NoRun;
            checkRun.SetBounds(16, 72, 320, 20);
            group.Controls.Add(checkRun);

            Label note = new Label();
            note.Text = "支持 Chrome 扩展与油猴脚本；书签、历史与下载记录使用 AES-256-GCM 加密保存。";
            note.ForeColor = Color.FromArgb(0x6A, 0x6A, 0x6A);
            note.SetBounds(18, 204, 484, 18);
            pageWelcome.Controls.Add(note);

            btnInstall = new XPButton();
            btnInstall.Text = "安装(&I)";
            btnInstall.SetBounds(330, 262, 84, 26);
            btnInstall.Click += delegate { StartInstall(); };
            pageWelcome.Controls.Add(btnInstall);

            btnCancel = new XPButton();
            btnCancel.Text = "取消";
            btnCancel.SetBounds(420, 262, 82, 26);
            btnCancel.Click += delegate { Close(); };
            pageWelcome.Controls.Add(btnCancel);

            Controls.Add(pageWelcome);
        }

        // ---------------- 页面 2：进度 ---------------- //
        private void BuildProgress()
        {
            pageProgress = new Panel();
            pageProgress.SetBounds(0, 62, ClientSize.Width, ClientSize.Height - 62);
            pageProgress.BackColor = Const.Face;
            pageProgress.Visible = false;

            labelProgress = new Label();
            labelProgress.Text = "正在解压文件...";
            labelProgress.SetBounds(18, 24, 480, 20);
            pageProgress.Controls.Add(labelProgress);

            progress = new XPProgress();
            progress.SetBounds(18, 50, 484, 18);
            pageProgress.Controls.Add(progress);

            labelError = new Label();
            labelError.ForeColor = Color.FromArgb(0xC6, 0x36, 0x2B);
            labelError.SetBounds(18, 78, 484, 60);
            labelError.Visible = false;
            pageProgress.Controls.Add(labelError);

            Label tip = new Label();
            tip.Text = "安装过程中请勿关闭窗口。";
            tip.ForeColor = Color.FromArgb(0x6A, 0x6A, 0x6A);
            tip.SetBounds(18, 150, 480, 18);
            pageProgress.Controls.Add(tip);

            Controls.Add(pageProgress);
        }

        // ---------------- 页面 3：完成 ---------------- //
        private void BuildDone()
        {
            pageDone = new Panel();
            pageDone.SetBounds(0, 62, ClientSize.Width, ClientSize.Height - 62);
            pageDone.BackColor = Const.Face;
            pageDone.Visible = false;

            Label done = new Label();
            done.Text = "安装完成";
            done.Font = new Font(Const.UIFont(12F).FontFamily, 12F, FontStyle.Bold);
            done.ForeColor = Color.FromArgb(0x00, 0x3C, 0x74);
            done.SetBounds(18, 22, 300, 26);
            pageDone.Controls.Add(done);

            Label detail = new Label();
            detail.Name = "detail";
            detail.SetBounds(18, 56, 484, 60);
            pageDone.Controls.Add(detail);

            btnFinish = new XPButton();
            btnFinish.Text = "完成(&F)";
            btnFinish.SetBounds(410, 262, 92, 26);
            btnFinish.Click += delegate { Close(); };
            pageDone.Controls.Add(btnFinish);

            Controls.Add(pageDone);
        }

        private void ShowPage(Panel page)
        {
            pageWelcome.Visible = page == pageWelcome;
            pageProgress.Visible = page == pageProgress;
            pageDone.Visible = page == pageDone;
        }

        private void BrowseFolder()
        {
            FolderBrowserDialog dialog = new FolderBrowserDialog();
            dialog.Description = "请选择 " + Const.AppName + " 的安装位置";
            dialog.SelectedPath = editDir.Text;
            if (dialog.ShowDialog(this) == DialogResult.OK)
                editDir.Text = dialog.SelectedPath;
        }

        // ---------------- 安装流程 ---------------- //
        private void StartInstall()
        {
            string dir = editDir.Text.Trim();
            if (dir.Length == 0) { MessageBox.Show(this, "请填写安装位置。", Const.AppName); return; }
            try { dir = Path.GetFullPath(dir); }
            catch { MessageBox.Show(this, "安装位置无效。", Const.AppName); return; }
            installedDir = dir;

            ShowPage(pageProgress);
            btnCancel.Enabled = false;
            Application.DoEvents();

            Thread worker = new Thread(new ThreadStart(DoInstall));
            worker.IsBackground = true;
            worker.Start();

            System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
            timer.Interval = 120;
            timer.Tick += delegate
            {
                progress.Value = Installer.Progress;
                labelProgress.Text = Installer.Status;
                if (Installer.Finished)
                {
                    timer.Stop();
                    if (Installer.Error != null)
                    {
                        labelError.Text = "安装失败：" + Installer.Error;
                        labelError.Visible = true;
                        btnCancel.Text = "关闭";
                        btnCancel.Enabled = true;
                    }
                    else
                    {
                        AfterInstall();
                    }
                }
            };
            timer.Start();
        }

        private void DoInstall()
        {
            try
            {
                Installer.Extract(installedDir);
                Installer.CreateShortcuts(installedDir, checkDesktop.Checked, checkStartMenu.Checked);
                Installer.WriteRegistry(installedDir);
                Installer.Status = "安装完成";
                Installer.Progress = 100;
            }
            catch (Exception ex)
            {
                Installer.Error = ex.Message;
            }
            finally
            {
                Installer.Finished = true;
            }
        }

        private void AfterInstall()
        {
            Label detail = (Label)pageDone.Controls["detail"];
            detail.Text = Const.AppName + " 已安装到：\n" + installedDir + "\n\n" +
                "可以从开始菜单、桌面快捷方式启动，也可以在「设置 → 关于」中查看版本与作者信息。";
            ShowPage(pageDone);
            if (checkRun.Checked)
            {
                try { Process.Start(Path.Combine(installedDir, Const.ExeName)); }
                catch { }
            }
        }
    }

    // ------------------------------------------------------------------ //
    // 安装核心
    // ------------------------------------------------------------------ //
    static class Installer
    {
        public static volatile int Progress;
        public static volatile string Status = "准备中...";
        public static volatile bool Finished;
        public static volatile string Error;

        public static void Extract(string targetDir)
        {
            Directory.CreateDirectory(targetDir);
            Status = "正在读取安装数据...";
            Progress = 1;

            long length;
            Stream payload = Payload.Open(out length);

            Status = "正在解压文件...";
            using (payload)
            using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
            {
                long totalBytes = 0;
                foreach (ZipArchiveEntry e in archive.Entries) totalBytes += e.Length;

                long done = 0;
                byte[] buffer = new byte[131072];
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string name = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                    string path = Path.Combine(targetDir, name);
                    if (entry.Name.Length == 0)
                    {
                        Directory.CreateDirectory(path);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using (Stream src = entry.Open())
                    using (FileStream dst = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        int read;
                        while ((read = src.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            dst.Write(buffer, 0, read);
                            done += read;
                            Progress = totalBytes > 0 ? 3 + (int)(done * 90 / totalBytes) : 50;
                            Status = "正在解压：" + entry.Name;
                        }
                    }
                }
            }

            Status = "正在创建快捷方式...";
            Progress = 95;
            ClearMarkOfTheWeb(targetDir);
        }

        private static void ClearMarkOfTheWeb(string dir)
        {
            // 去掉“来自网络”标记，避免系统对下载文件的额外限制
            try
            {
                foreach (string file in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                {
                    try { File.Delete(file + ":Zone.Identifier"); }
                    catch { }
                }
            }
            catch { }
        }

        public static void CreateShortcuts(string dir, bool desktop, bool startMenu)
        {
            string target = Path.Combine(dir, Const.ExeName);
            if (desktop)
            {
                string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory),
                    Const.AppName + ".lnk");
                MakeShortcut(path, target, dir);
            }
            if (startMenu)
            {
                string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                MakeShortcut(Path.Combine(programs, Const.AppName + ".lnk"), target, dir);
                MakeShortcut(Path.Combine(programs, "卸载 " + Const.AppName + ".lnk"),
                    Path.Combine(dir, Const.UninstallName), dir);
            }
        }

        private static void MakeShortcut(string path, string target, string workdir)
        {
            try
            {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                object shell = Activator.CreateInstance(shellType);
                object link = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod,
                    null, shell, new object[] { path });
                Type linkType = link.GetType();
                linkType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, link, new object[] { target });
                linkType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, link, new object[] { workdir });
                linkType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, link, new object[] { target + ",0" });
                linkType.InvokeMember("Description", BindingFlags.SetProperty, null, link,
                    new object[] { Const.AppName + " - 作者 " + Const.Publisher });
                linkType.InvokeMember("Save", BindingFlags.InvokeMethod, null, link, null);
            }
            catch { }
        }

        public static void WriteRegistry(string dir)
        {
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(Const.UninstallKey))
            {
                key.SetValue("DisplayName", Const.AppName);
                key.SetValue("DisplayVersion", Const.Version);
                key.SetValue("Publisher", Const.Publisher);
                key.SetValue("DisplayIcon", Path.Combine(dir, Const.ExeName));
                key.SetValue("InstallLocation", dir);
                key.SetValue("UninstallString", "\"" + Path.Combine(dir, Const.UninstallName) + "\"");
                key.SetValue("QuietUninstallString", "\"" + Path.Combine(dir, Const.UninstallName) + "\" /S");
                key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                key.SetValue("EstimatedSize", EstimateSize(dir), RegistryValueKind.DWord);
            }
        }

        private static int EstimateSize(string dir)
        {
            try
            {
                long total = 0;
                foreach (string file in Directory.GetFiles(dir, "*", SearchOption.AllDirectories))
                    total += new FileInfo(file).Length;
                return (int)(total / 1024);
            }
            catch { return 0; }
        }
    }

    // ------------------------------------------------------------------ //
    // 读取自身末尾的 payload
    // ------------------------------------------------------------------ //
    class SubStream : Stream
    {
        private readonly Stream inner;
        private readonly long start;
        private readonly long length;
        private long position;

        public SubStream(Stream inner, long start, long length)
        {
            this.inner = inner;
            this.start = start;
            this.length = length;
            this.position = 0;
        }

        public override bool CanRead { get { return true; } }
        public override bool CanSeek { get { return true; } }
        public override bool CanWrite { get { return false; } }
        public override long Length { get { return length; } }
        public override long Position
        {
            get { return position; }
            set { position = value; }
        }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count)
        {
            long remain = length - position;
            if (remain <= 0) return 0;
            if (count > remain) count = (int)remain;
            inner.Seek(start + position, SeekOrigin.Begin);
            int read = inner.Read(buffer, offset, count);
            position += read;
            return read;
        }
        public override long Seek(long offset, SeekOrigin origin)
        {
            long target = origin == SeekOrigin.Begin ? offset :
                          origin == SeekOrigin.Current ? position + offset : length + offset;
            position = Math.Max(0, Math.Min(length, target));
            return position;
        }
        public override void SetLength(long value) { throw new NotSupportedException(); }
        public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    }

    static class Payload
    {
        public static Stream Open(out long length)
        {
            string path = Application.ExecutablePath;
            FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            if (fs.Length < 12) throw new Exception("安装包不完整。");
            byte[] tail = new byte[12];
            fs.Seek(-12, SeekOrigin.End);
            fs.Read(tail, 0, 12);
            if (tail[8] != (byte)'L' || tail[9] != (byte)'T' || tail[10] != (byte)'B' || tail[11] != (byte)'S')
                throw new Exception("安装包数据损坏（缺少 payload）。");
            length = BitConverter.ToInt64(tail, 0);
            long offset = fs.Length - 12 - length;
            if (offset < 0) throw new Exception("安装包数据损坏（长度异常）。");
            return new SubStream(fs, offset, length);
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            Options options = Options.Parse(args);
            if (options.Silent)
            {
                try
                {
                    string dir = options.Dir != null && options.Dir.Length > 0 ? options.Dir : Const.DefaultDir();
                    dir = Path.GetFullPath(dir);
                    Installer.Extract(dir);
                    Installer.CreateShortcuts(dir, !options.NoDesktop, !options.NoStartMenu);
                    Installer.WriteRegistry(dir);
                    Console.WriteLine("installed:" + dir);
                    Environment.Exit(0);
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine("failed:" + ex.Message);
                    Environment.Exit(1);
                }
            }

            Application.Run(new SetupForm(options));
        }
    }
}
