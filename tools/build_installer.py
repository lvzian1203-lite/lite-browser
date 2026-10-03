#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建 lite browser test 安装包（单文件 exe）。

流程：
  1. csc 编译 uninstaller.cs -> uninstall.exe
  2. 打包 dist/lite browser test 全部文件 + uninstall.exe -> payload.zip
  3. csc 编译 installer.cs -> setup.exe
  4. 把 payload.zip 追加到 setup.exe 末尾，并写入 12 字节尾部标记
  5. 输出到目标目录（默认 D:\\dshStar）

用法：
    python tools/build_installer.py [--out "D:\\dshStar\\lite browser test"]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "lite browser test"
TOOLS = ROOT / "tools" / "installer"
ICON = ROOT / "assets" / "lite_browser.ico"
APP_NAME = "lite browser test"
VERSION = "1.0.test"

CSC_CANDIDATES = [
    Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
]

TRAILER_MAGIC = b"LTBS"


def find_csc() -> Path:
    for candidate in CSC_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("csc")
    if found:
        return Path(found)
    raise SystemExit("未找到 C# 编译器 csc.exe（需要 .NET Framework 4.x）")


def compile_cs(csc: Path, source: Path, target: Path, windowed: bool = True) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(csc),
        "/nologo",
        "/target:" + ("winexe" if windowed else "exe"),
        "/optimize+",
        "/platform:anycpu",
        "/r:System.IO.Compression.dll",
        "/r:System.IO.Compression.FileSystem.dll",
        f"/win32icon:{ICON}",
        f"/out:{target}",
        str(source),
    ]
    print("  编译:", source.name)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not target.exists():
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(f"编译失败：{source.name}")
    if result.stdout.strip():
        print("   ", result.stdout.strip()[:400])


def build_payload(stage: Path, payload: Path, uninstaller: Path) -> int:
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)

    print("  复制程序文件 ...")
    for item in DIST.iterdir():
        target = stage / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)

    shutil.copy2(uninstaller, stage / "uninstall.exe")
    readme = ROOT / "README.md"
    if readme.exists():
        shutil.copy2(readme, stage / "README.md")
    codec_test = ROOT / "docs" / "codec-test.html"
    if codec_test.exists():
        shutil.copy2(codec_test, stage / "解码自检.html")
    samples = ROOT / "samples"
    if samples.is_dir():
        shutil.copytree(samples, stage / "samples", dirs_exist_ok=True)

    print("  压缩 ...")
    count = 0
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage).as_posix())
                count += 1
    return count


def append_payload(setup: Path, payload: Path, target: Path) -> None:
    data = payload.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "wb") as out:
        out.write(setup.read_bytes())
        out.write(data)
        out.write(struct.pack("<q", len(data)))
        out.write(TRAILER_MAGIC)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human(size: float) -> str:
    return f"{size / 1024 / 1024:.1f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 lite browser test 安装包")
    parser.add_argument("--out", type=Path, default=ROOT, help="输出目录")
    parser.add_argument("--portable", action="store_true", help="同时生成便携版 zip")
    args = parser.parse_args()

    if not DIST.is_dir():
        raise SystemExit(f"未找到 {DIST}，请先运行 build_exe.bat 打包程序")

    work = ROOT / "build-installer"
    work.mkdir(parents=True, exist_ok=True)

    csc = find_csc()
    print(f"[1/5] 使用编译器 {csc}")

    print("[2/5] 编译卸载程序")
    uninstaller = work / "uninstall.exe"
    compile_cs(csc, TOOLS / "uninstaller.cs", uninstaller)

    print("[3/5] 打包程序数据")
    payload = work / "payload.zip"
    file_count = build_payload(work / "stage", payload, uninstaller)

    print("[4/5] 编译安装程序")
    setup = work / "setup.exe"
    compile_cs(csc, TOOLS / "installer.cs", setup)

    print("[5/5] 生成安装包")
    name = f"{APP_NAME}-{VERSION}-安装程序.exe"
    target = args.out / name
    append_payload(setup, payload, target)

    lines = [
        f"文件：{target}",
        f"大小：{human(target.stat().st_size)}（压缩前 {human(sum(f.stat().st_size for f in (work / 'stage').rglob('*') if f.is_file()))}）",
        f"文件数：{file_count}",
        f"SHA256：{sha256(target)}",
    ]

    if args.portable:
        portable = args.out / f"{APP_NAME}-{VERSION}-便携版.zip"
        with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted((work / "stage").rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(work / "stage").as_posix())
        lines.append(f"便携版：{portable} ({human(portable.stat().st_size)})")
        lines.append(f"便携版 SHA256：{sha256(portable)}")

    print("\n".join(["", "=" * 60] + lines + ["=" * 60]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
