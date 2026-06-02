# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
APP_NAME = "LNU-LibSeat"
APP_VERSION = "v2.0.0"
APP_ICON = "OIP-C.ico"
DIST_NAME = f"{APP_NAME}-{APP_VERSION}"
DIST_ROOT = ROOT / "dist"
DIST_DIR = DIST_ROOT / DIST_NAME
BUILD_WORK = ROOT / "build" / "pyinstaller"
INVALID_PACKAGE_NAME_CHARS = set('<>:"/\\|?*')

REQUIRED_PACKAGES = [
    "pyinstaller",
    "selenium>=4.20.0",
    "webdriver-manager>=4.0.2",
    "requests>=2.31.0",
    "Pillow>=10.1.0",
    "ddddocr",
    "PySide6>=6.7.0",
    "mss>=9.0.1",
    "opencv-python>=4.8.0",
    "numpy>=1.24.0",
    "onnxruntime>=1.17.0",
]

EXCLUDE_MODULES = [
    "torch",
    "torchvision",
    "timm",
    "scipy",
    "matplotlib",
    "pandas",
    "ultralytics",
    "tensorboard",
    "tensorflow",
]

CLEAN_CONFIG = {
    "accounts": [],
    "campus": "崇山校区图书馆",
    "room": "三楼智慧研修空间",
    "day_start": "09:00",
    "day_end": "22:00",
    "mode": "multi",
    "dry_run": False,
    "cross_room": True,
    "cross_room_rooms": {},
    "receiver_email": "",
    "pre_notify": 30,
    "auto_cancel": False,
    "priority_mode": "longest_first",
    "preferred_seats": {},
    "theme": "auto",
}


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("[run]", " ".join(str(part) for part in cmd))
    subprocess.check_call(cmd, cwd=str(cwd or ROOT))


def default_dist_name(app_name: str, app_version: str) -> str:
    return f"{app_name}-{app_version}" if app_version else app_name


def validate_package_name(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} cannot be empty.")
    invalid = sorted(char for char in value if char in INVALID_PACKAGE_NAME_CHARS)
    if invalid:
        raise ValueError(f"{label} contains invalid filename characters: {' '.join(invalid)}")
    if value.endswith((".", " ")):
        raise ValueError(f"{label} cannot end with a dot or space.")
    return value


def configure_package_names(app_name: str, app_version: str, dist_name: str | None) -> None:
    global APP_NAME, APP_VERSION, DIST_NAME, DIST_DIR

    APP_NAME = validate_package_name(app_name, "--app-name")
    APP_VERSION = app_version.strip()
    if APP_VERSION:
        APP_VERSION = validate_package_name(APP_VERSION, "--app-version")
    DIST_NAME = validate_package_name(
        default_dist_name(APP_NAME, APP_VERSION) if dist_name is None else dist_name,
        "--dist-name",
    )
    DIST_DIR = DIST_ROOT / DIST_NAME


def build_python() -> Path:
    if sys.platform == "win32":
        venv_python = ROOT / "env" / "Scripts" / "python.exe"
    else:
        venv_python = ROOT / "env" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


def ensure_build_deps(py: Path, index_url: str | None) -> None:
    cmd = [str(py), "-m", "pip", "install", "--upgrade"] + REQUIRED_PACKAGES
    if index_url:
        cmd += ["-i", index_url]
    run(cmd)


def add_data_arg(src: Path, dst: str) -> str:
    sep = ";" if sys.platform == "win32" else ":"
    return f"{src}{sep}{dst}"


def validate_icon_file() -> None:
    icon_path = ROOT / APP_ICON
    if not icon_path.exists():
        raise FileNotFoundError(f"App icon not found: {icon_path}")

    with icon_path.open("rb") as f:
        header = f.read(6)
    if len(header) != 6 or header[:4] != b"\x00\x00\x01\x00":
        raise ValueError(f"App icon is not a valid .ico file: {icon_path}")
    if int.from_bytes(header[4:6], "little") < 1:
        raise ValueError(f"App icon contains no icon images: {icon_path}")


def pyinstaller_cmd(py: Path) -> list[str]:
    cmd = [
        str(py),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        APP_NAME,
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_WORK),
        "--specpath",
        str(BUILD_WORK),
        "--icon",
        str(ROOT / APP_ICON),
        "--add-data",
        add_data_arg(ROOT / APP_ICON, "."),
        "--collect-all",
        "ddddocr",
        "--collect-all",
        "onnxruntime",
        "--collect-all",
        "cv2",
        "--collect-all",
        "numpy",
        "--collect-submodules",
        "selenium",
        "--collect-submodules",
        "webdriver_manager",
        "--collect-submodules",
        "mss",
        "--collect-data",
        "certifi",
    ]
    for model in sorted((ROOT / "core" / "checkpoints").glob("*.onnx")):
        cmd += ["--add-data", add_data_arg(model, "core/checkpoints")]
    for module in EXCLUDE_MODULES:
        cmd += ["--exclude-module", module]
    cmd.append(str(ROOT / "app.py"))
    return cmd


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def write_runtime_files() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    icon_src = ROOT / APP_ICON
    if icon_src.exists():
        shutil.copy2(icon_src, DIST_DIR / APP_ICON)

    copy_tree(ROOT / "info", DIST_DIR / "info")
    (DIST_DIR / "logs").mkdir(exist_ok=True)

    with open(DIST_DIR / "config_data.json", "w", encoding="utf-8") as f:
        json.dump(CLEAN_CONFIG, f, ensure_ascii=False, indent=2)

    readme = """LNU-LibSeat 使用说明

1. 双击 LNU-LibSeat.exe 启动主程序。
2. 请整文件夹一起压缩和发送，不要只移动 exe；_internal 是运行依赖目录。
3. config_data.json 会保存用户填写的账号、房间、邮箱和偏好；首次分发时已留空账号信息。
4. logs 目录保存运行日志和 API 方案报告。
5. 目标电脑需要安装 Microsoft Edge。首次运行如需下载匹配的浏览器驱动，需要联网。
6. 邮箱栏留空时不会发送邮件。
"""
    with open(DIST_DIR / "使用说明.txt", "w", encoding="utf-8") as f:
        f.write(readme)


def clean_previous_output() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    old = DIST_ROOT / APP_NAME
    if old.exists():
        shutil.rmtree(old)
    old_build = BUILD_WORK / APP_NAME
    if old_build.exists():
        shutil.rmtree(old_build)
    zip_path = DIST_ROOT / f"{DIST_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    tmp_zip_path = zip_path.with_suffix(zip_path.suffix + ".tmp")
    if tmp_zip_path.exists():
        tmp_zip_path.unlink()


def rename_pyinstaller_output() -> None:
    generated = DIST_ROOT / APP_NAME
    if not generated.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {generated}")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    generated.rename(DIST_DIR)


def make_zip() -> Path:
    zip_path = DIST_ROOT / f"{DIST_NAME}.zip"
    tmp_zip_path = zip_path.with_suffix(zip_path.suffix + ".tmp")
    if zip_path.exists():
        zip_path.unlink()
    if tmp_zip_path.exists():
        tmp_zip_path.unlink()

    dirs = [DIST_DIR, *sorted(p for p in DIST_DIR.rglob("*") if p.is_dir())]
    files = sorted(p for p in DIST_DIR.rglob("*") if p.is_file())
    print(f"[info] Creating zip: {zip_path}", flush=True)
    print(f"[info] Compressing {len(files)} files. This may take a while...", flush=True)

    try:
        with tmp_zip_path.open("wb") as raw:
            with ZipFile(raw, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
                for path in dirs:
                    arcname = path.relative_to(DIST_ROOT).as_posix().rstrip("/")
                    zf.write(path, arcname + "/")
                for index, path in enumerate(files, start=1):
                    arcname = path.relative_to(DIST_ROOT).as_posix()
                    zf.write(path, arcname)
                    if index == len(files) or index % 250 == 0:
                        print(f"[zip] {index}/{len(files)} files", flush=True)
            raw.flush()
            os.fsync(raw.fileno())

        print("[info] Validating temporary zip...", flush=True)
        validate_distribution(tmp_zip_path)
        os.replace(tmp_zip_path, zip_path)
        print("[info] Validating final zip...", flush=True)
        validate_distribution(zip_path)
    except Exception:
        if tmp_zip_path.exists():
            tmp_zip_path.unlink()
        raise

    return zip_path


def expected_zip_file_entries() -> set[str]:
    return {
        path.relative_to(DIST_ROOT).as_posix()
        for path in DIST_DIR.rglob("*")
        if path.is_file()
    }


def expected_zip_dir_entries() -> set[str]:
    return {
        path.relative_to(DIST_ROOT).as_posix().rstrip("/") + "/"
        for path in [DIST_DIR, *DIST_DIR.rglob("*")]
        if path.is_dir()
    }


def read_zip_entries(zip_path: Path) -> tuple[set[str], set[str]]:
    with ZipFile(zip_path, "r") as zf:
        bad_file = zf.testzip()
        if bad_file:
            raise ValueError(f"Zip entry failed CRC check: {bad_file}")
        entries = set(zf.namelist())
    file_entries = {entry for entry in entries if not entry.endswith("/")}
    dir_entries = {entry for entry in entries if entry.endswith("/")}
    return file_entries, dir_entries


def validate_distribution(zip_path: Path) -> None:
    required_files = [
        DIST_DIR / f"{APP_NAME}.exe",
        DIST_DIR / APP_ICON,
        DIST_DIR / "_internal" / APP_ICON,
        DIST_DIR / "_internal" / "_tcl_data" / "init.tcl",
        DIST_DIR / "_internal" / "_tk_data" / "tk.tcl",
        DIST_DIR / "_internal" / "core" / "checkpoints" / "click1_siamese_yolo4_best.onnx",
        DIST_DIR / "_internal" / "core" / "checkpoints" / "click3_yolo_plan_bg_char60_best.onnx",
    ]
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("Distribution is missing required files:\n" + "\n".join(missing))

    required_entries = [
        f"{DIST_NAME}/{APP_NAME}.exe",
        f"{DIST_NAME}/{APP_ICON}",
        f"{DIST_NAME}/_internal/{APP_ICON}",
        f"{DIST_NAME}/_internal/_tcl_data/init.tcl",
        f"{DIST_NAME}/_internal/_tk_data/tk.tcl",
        f"{DIST_NAME}/_internal/core/checkpoints/click1_siamese_yolo4_best.onnx",
        f"{DIST_NAME}/_internal/core/checkpoints/click3_yolo_plan_bg_char60_best.onnx",
    ]
    file_entries, dir_entries = read_zip_entries(zip_path)
    entries = file_entries | dir_entries
    missing_entries = [entry for entry in required_entries if entry not in entries]
    if missing_entries:
        raise FileNotFoundError("Zip is missing required entries:\n" + "\n".join(missing_entries))

    expected_files = expected_zip_file_entries()
    missing_files = sorted(expected_files - file_entries)
    extra_files = sorted(file_entries - expected_files)
    if missing_files:
        raise FileNotFoundError("Zip is missing files from the dist folder:\n" + "\n".join(missing_files[:50]))
    if extra_files:
        raise ValueError("Zip contains unexpected files:\n" + "\n".join(extra_files[:50]))

    expected_dirs = expected_zip_dir_entries()
    missing_dirs = sorted(expected_dirs - dir_entries)
    if missing_dirs:
        raise FileNotFoundError("Zip is missing directories from the dist folder:\n" + "\n".join(missing_dirs[:50]))


def build(
    index_url: str | None,
    *,
    app_name: str = APP_NAME,
    app_version: str = APP_VERSION,
    dist_name: str | None = None,
) -> None:
    configure_package_names(app_name, app_version, dist_name)

    if sys.platform != "win32":
        print("[warn] This script is intended for Windows exe packaging.")

    py = build_python()
    print(f"[info] Build Python: {py}")
    print(f"[info] EXE name: {APP_NAME}.exe")
    print(f"[info] Dist folder/zip name: {DIST_NAME}")
    ensure_build_deps(py, index_url)
    validate_icon_file()

    clean_previous_output()
    run(pyinstaller_cmd(py))
    print("[info] PyInstaller finished. Preparing runtime files and zip package...", flush=True)
    rename_pyinstaller_output()
    write_runtime_files()
    zip_path = make_zip()

    print()
    print("=" * 70)
    print("Build complete")
    print(f"Folder: {DIST_DIR}")
    print(f"Zip:    {zip_path}")
    print(f"Run:    {DIST_DIR / (APP_NAME + '.exe')}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LNU-LibSeat Windows exe package.")
    parser.add_argument(
        "--index-url",
        default=os.environ.get("PIP_INDEX_URL"),
        help="Optional pip index URL, for example https://pypi.tuna.tsinghua.edu.cn/simple",
    )
    parser.add_argument(
        "--app-name",
        default=APP_NAME,
        help=f"Executable name without .exe. Default: {APP_NAME}",
    )
    parser.add_argument(
        "--app-version",
        default=APP_VERSION,
        help=f"Version used in the default dist name. Default: {APP_VERSION}",
    )
    parser.add_argument(
        "--dist-name",
        default=None,
        help="Folder name under dist and zip filename without .zip. Default: <app-name>-<app-version>",
    )
    args = parser.parse_args()
    build(
        args.index_url,
        app_name=args.app_name,
        app_version=args.app_version,
        dist_name=args.dist_name,
    )


if __name__ == "__main__":
    main()
