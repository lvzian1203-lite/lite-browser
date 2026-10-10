#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""lite browser 数据解密工具。

把 lite browser 加密保存的书签、历史记录、下载记录导出为明文 JSON。

用法：
    python tools/decrypt_data.py                     # 解密默认数据目录到当前目录下的 decrypted/
    python tools/decrypt_data.py --out D:\\备份        # 指定输出目录
    python tools/decrypt_data.py --data-dir D:\\data   # 指定数据目录
    python tools/decrypt_data.py --password 你的口令     # 数据受口令保护时使用
    python tools/decrypt_data.py --list                # 只查看数据目录与加密状态

说明：
    * 默认数据目录为 %APPDATA%\\LiteBrowser（绿色便携模式为程序目录下的 data）；
    * 主密钥保存在 <数据目录>\\master.key，默认由 Windows DPAPI 保护，
      因此需要在**同一个 Windows 账户**下执行本工具；
    * 若在设置中设置了加密口令，请用 --password 传入该口令。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from litebrowser.console import configure_output  # noqa: E402
from litebrowser.crypto import CRYPTO_AVAILABLE, DataVault, VaultError  # noqa: E402

DATA_FILES = {
    "bookmarks.dat": "bookmarks.json",
    "history.dat": "history.json",
    "downloads.dat": "downloads.json",
}


def default_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "LiteBrowser"


def print_status(data_dir: Path, vault: DataVault) -> None:
    print(f"数据目录  : {data_dir}")
    print(f"密钥文件  : {vault.key_path}  ({'存在' if vault.key_path.exists() else '不存在'})")
    print(f"加密库    : {'可用' if CRYPTO_AVAILABLE else '缺失（数据为明文）'}")
    print(f"加密状态  : {vault.describe()}")
    folder = data_dir / "data"
    if folder.is_dir():
        files = sorted(p.name for p in folder.iterdir() if p.is_file())
        print(f"数据文件  : {', '.join(files) if files else '（无）'}")
    for legacy in ("bookmarks.json", "history.json", "downloads.json"):
        path = data_dir / legacy
        if path.exists():
            print(f"旧版明文  : {path}")


def main() -> int:
    # 输出被重定向时改用 UTF-8：本工具可能在英文系统上运行（见 litebrowser/console.py）
    configure_output()
    parser = argparse.ArgumentParser(
        description="lite browser 数据解密工具（导出明文 JSON）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="数据目录（默认 %%APPDATA%%\\LiteBrowser）")
    parser.add_argument("--out", type=Path, default=None, help="输出目录（默认 ./decrypted）")
    parser.add_argument("--password", default=None, help="加密口令（设置过口令时需要）")
    parser.add_argument("--list", action="store_true", help="只显示状态，不解密")
    args = parser.parse_args()

    data_dir = (args.data_dir or default_data_dir()).expanduser()
    out_dir = (args.out or Path.cwd() / "decrypted").expanduser()

    print("=" * 64)
    print(" lite browser 数据解密工具")
    print("=" * 64)

    if not data_dir.exists():
        print(f"错误：数据目录不存在：{data_dir}")
        return 1

    vault = DataVault(data_dir)
    if not vault.available:
        print("警告：当前 Python 环境缺少 cryptography，无法解密。")
        print("      请先执行：pip install cryptography")
        return 1

    unlocked = vault.unlock(args.password)
    if not unlocked and vault.mode != "none":
        # 已有密钥但需要口令
        if vault.locked and not args.password:
            print("该数据受口令保护，请使用 --password 你的口令 重试。")
            return 2
        print("解密失败：口令不正确，或密钥不是由当前 Windows 账户创建的。")
        return 2

    if not unlocked:
        print("未找到密钥文件，数据可能以明文保存。")

    print_status(data_dir, vault)
    if args.list:
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for blob_name, target_name in DATA_FILES.items():
        blob_path = data_dir / "data" / blob_name
        legacy_path = data_dir / target_name
        text = vault.read_text(blob_path, legacy_path)
        if text is None:
            if blob_path.exists():
                print(f"跳过 {blob_name}：无法解密（口令或账户不匹配）")
            continue
        target = out_dir / target_name
        try:
            payload = json.loads(text)
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except ValueError:
            target.write_text(text, encoding="utf-8")
        except OSError as exc:
            print(f"写入失败 {target}：{exc}")
            continue
        count += 1
        print(f"已导出 {target_name:16s} -> {target}")

    print("-" * 64)
    print(f"完成：共导出 {count} 个文件到 {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
