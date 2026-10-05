// lite browser 卸载程序
// 作者：lvzian
// 编译：csc /target:winexe /win32icon:lite_browser.ico uninstaller.cs

using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly: AssemblyTitle("lite browser 卸载程序")]
[assembly: AssemblyProduct("lite browser")]
[assembly: AssemblyCompany("lvzian")]
[assembly: AssemblyCopyright("Copyright (C) 2026 lvzian")]
[assembly: AssemblyDescription("lite browser 卸载程序")]
[assembly: AssemblyVersion("1.6.95.0")]
[assembly: AssemblyFileVersion("1.6.95.0")]

namespace LiteBrowserUninstall
{
    static class Const
    {
        public const string AppName = "lite browser";
        public const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\lite browser";
        public static readonly Color Face = Color.FromArgb(0xEC, 0xE9, 0xD8);
        public static readonly Color CaptionTop = Color.FromArgb(0x4C, 0x9B, 0xF7);
        public static readonly Color CaptionMid = Color.FromArgb(0x0B, 0x5F, 0xE6);
        public static readonly Color CaptionBottom = Color.FromArgb(0x0A, 0x46, 0xB8);

        public static Font UIFont(float size)
        {
            try { return new Font("Microsoft YaHei UI", size); }
            catch { return new Font("Tahoma", size); }
        }
    }

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

    class ConfirmForm : Form
    {
        public bool PurgeData;
        public bool Confirmed;

        public ConfirmForm(string installDir)
        {
            Text = "卸载 " + Const.AppName;
            Font = Const.UIFont(9F);
            BackColor = Const.Face;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(440, 200);

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 52;
            header.Paint += delegate(object sender, PaintEventArgs e)
            {
                Graphics g = e.Graphics;
                using (LinearGradientBrush brush = new LinearGradientBrush(
                    new Rectangle(0, 0, header.Width, header.Height), Const.CaptionTop, Const.CaptionBottom, 90f))
                {
                    ColorBlend blend = new ColorBlend(3);
                    blend.Colors = new Color[] { Const.CaptionTop, Const.CaptionMid, Const.CaptionBottom };
                    blend.Positions = new float[] { 0f, 0.45f, 1f };
                    brush.InterpolationColors = blend;
                    g.FillRectangle(brush, new Rectangle(0, 0, header.Width, header.Height));
                }
                using (SolidBrush white = new SolidBrush(Color.White))
                using (Font titleFont = new Font(Const.UIFont(12F).FontFamily, 12F, FontStyle.Bold))
                {
                    g.DrawString("卸载 " + Const.AppName, titleFont, white, new PointF(16, 12));
                }
            };
            Controls.Add(header);

            Label message = new Label();
            message.Text = "将从下面的位置移除 " + Const.AppName + "：\n" + installDir;
            message.SetBounds(18, 66, 404, 40);
            Controls.Add(message);

            CheckBox purge = new CheckBox();
            purge.Text = "同时删除个人数据（书签、历史记录、下载记录与设置）";
            purge.SetBounds(18, 108, 404, 22);
            purge.Checked = false;
            Controls.Add(purge);

            Label hint = new Label();
            hint.Text = "不勾选时，用户数据会保留，重新安装后可继续使用。";
            hint.ForeColor = Color.FromArgb(0x6A, 0x6A, 0x6A);
            hint.SetBounds(18, 130, 404, 18);
            Controls.Add(hint);

            XPButton ok = new XPButton();
            ok.Text = "卸载(&U)";
            ok.SetBounds(244, 160, 84, 26);
            ok.Click += delegate { Confirmed = true; PurgeData = purge.Checked; Close(); };
            Controls.Add(ok);

            XPButton cancel = new XPButton();
            cancel.Text = "取消";
            cancel.SetBounds(334, 160, 84, 26);
            cancel.Click += delegate { Close(); };
            Controls.Add(cancel);
        }
    }

    static class Uninstaller
    {
        public static void RemoveShortcuts()
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                SafeDelete(Path.Combine(desktop, Const.AppName + ".lnk"));
                SafeDelete(Path.Combine(programs, Const.AppName + ".lnk"));
                SafeDelete(Path.Combine(programs, "卸载 " + Const.AppName + ".lnk"));
            }
            catch { }
        }

        public static void RemoveRegistry()
        {
            try { Registry.CurrentUser.DeleteSubKeyTree(Const.UninstallKey, false); }
            catch { }
        }

        public static void RemoveUserData()
        {
            try
            {
                string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
                string dir = Path.Combine(appdata, "LiteBrowser");
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
            }
            catch { }
        }

        public static void RemoveDirectory(string dir)
        {
            if (!Directory.Exists(dir)) return;
            // 安全检查：只删除确认是 lite browser 安装目录的文件夹，避免误删
            bool looksLikeInstall =
                File.Exists(Path.Combine(dir, "lite browser.exe")) ||
                File.Exists(Path.Combine(dir, "uninstall.exe"));
            if (!looksLikeInstall) return;

            for (int attempt = 0; attempt < 8; attempt++)
            {
                try
                {
                    if (!Directory.Exists(dir)) return;
                    Directory.Delete(dir, true);
                    return;
                }
                catch
                {
                    System.Threading.Thread.Sleep(500);
                }
            }
        }

        private static void SafeDelete(string path)
        {
            try { if (File.Exists(path)) File.Delete(path); }
            catch { }
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            bool silent = false;
            bool cleanup = false;
            bool purge = false;
            string dir = null;

            foreach (string raw in args)
            {
                string a = raw.Trim().ToLowerInvariant();
                if (a == "/s" || a == "/silent") silent = true;
                else if (a == "/cleanup") cleanup = true;
                else if (a == "/purgedata") purge = true;
                else if (a.StartsWith("/dir=")) dir = raw.Trim().Substring(5).Trim('"');
            }

            string self = Application.ExecutablePath;
            string selfDir = Path.GetDirectoryName(self);

            if (cleanup)
            {
                string target = dir != null && dir.Length > 0 ? dir : selfDir;
                Uninstaller.RemoveShortcuts();
                Uninstaller.RemoveRegistry();
                if (purge) Uninstaller.RemoveUserData();
                Uninstaller.RemoveDirectory(target);
                ScheduleSelfDelete(self);
                if (!silent)
                {
                    MessageBox.Show("卸载完成。" + (purge ? "\n个人数据已删除。" : "\n个人数据已保留。"),
                        Const.AppName, MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                Environment.Exit(0);
            }

            if (!silent)
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                ConfirmForm form = new ConfirmForm(selfDir);
                Application.Run(form);
                if (!form.Confirmed) Environment.Exit(2);
                purge = form.PurgeData;
            }

            string temp = Path.Combine(Path.GetTempPath(),
                "lite-browser-uninstall-" + Guid.NewGuid().ToString("N").Substring(0, 8) + ".exe");
            try { File.Copy(self, temp, true); }
            catch { temp = self; }

            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = temp;
            info.Arguments = "/CLEANUP /DIR=\"" + selfDir + "\"" +
                             (purge ? " /PURGEDATA" : "") + (silent ? " /S" : "");
            info.UseShellExecute = false;
            try { Process.Start(info); }
            catch (Exception ex)
            {
                if (!silent) MessageBox.Show("卸载失败：" + ex.Message, Const.AppName);
                Environment.Exit(1);
            }
            Environment.Exit(0);
        }

        private static void ScheduleSelfDelete(string path)
        {
            try
            {
                ProcessStartInfo info = new ProcessStartInfo();
                info.FileName = "cmd.exe";
                info.Arguments = "/c timeout /t 2 /nobreak >nul & del /f /q \"" + path + "\"";
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(info);
            }
            catch { }
        }
    }
}
