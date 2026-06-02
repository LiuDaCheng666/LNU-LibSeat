<div align="center">

<table border="0" cellpadding="0" cellspacing="0">
<tr>
<td width="180" align="center" valign="middle">
<img src="OIP-C.ico" width="120" alt="LNU-LibSeat icon">
</td>
<td valign="middle" align="left">

# LNU-LibSeat

### 辽宁大学图书馆座位预约助手 · v2.0.0

基于 PySide6 图形界面、LibSeat API 扫描规划和 Selenium 自动预约，支持单账号逐段换座、多账号分时段、跨房间搜索、运行恢复和首次帮助引导。

<p>
<img src="https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white" alt="Python">
<img src="https://img.shields.io/badge/PySide6-GUI-41CD52?logo=qt&logoColor=white" alt="PySide6">
<img src="https://img.shields.io/badge/Selenium-4.x-43B02A?logo=selenium&logoColor=white" alt="Selenium">
<img src="https://img.shields.io/badge/API--Planner-LibSeat-4a7cf7" alt="API Planner">
<img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

</td>
</tr>
</table>

</div>

---

> [!IMPORTANT]
> 本项目会执行真实预约、取消和换座操作。第一次配置请先开启“测试模式”，确认扫描方案合理后再执行真实预约。

> [!WARNING]
> 请遵守图书馆预约、签到和取消规则。使用者需要自行承担预约失败、未签到、违约或黑名单等后果。

> [!TIP]
> 第一次启动会自动弹出使用帮助。之后可以点击标题栏右上角的 `?` 按钮再次查看。

---

## 这是什么

LNU-LibSeat 是一个面向辽宁大学图书馆座位预约系统的桌面工具。它不是单纯的定时抢座脚本，而是更偏“长时间学习座位规划”的预约助手：

- 先通过 API 快速扫描座位可用时间。
- 再让用户确认推荐方案。
- 最后通过 Selenium 浏览器流程完成真实预约。
- 单账号模式下，可在当前预约结束前自动查找下一段座位，并在确认后取消当前预约、预约新座位。
- 误关程序后，下次启动可查询“我的预约”并继续上次计划。

## 适合谁

| 使用者 | 典型需求 | 推荐模式 |
| --- | --- | --- |
| 普通预约用户 | 只想预约一段固定时间，例如 `09:00-12:00` | 单账号预约 |
| 长时间自习用户 | 想覆盖 `09:00-21:00`，但单个座位无法连续覆盖 | 单账号逐段 |
| 多账号分段用户 | 希望多个账号分别覆盖不同时间段 | 多账号分时段 |
| 调试/观察用户 | 想先看看有哪些可用座位，不想执行真实操作 | 测试模式 |

---

## 核心能力

<table width="100%">
<tr>
<td width="33%" valign="top">
<h3>API 扫描规划</h3>
通过后端接口扫描房间、座位和可预约时间段，生成推荐方案和 JSON 报告，减少逐个点击座位的等待。
</td>
<td width="33%" valign="top">
<h3>单账号逐段换座</h3>
先预约第一段，再按“提前 N 分钟”查找下一段。找到后弹窗确认，或开启自动模式直接换座。
</td>
<td width="33%" valign="top">
<h3>关闭后可恢复</h3>
运行中关闭会先保存状态。重启登录后查询“我的预约”，可选择继续上次计划、重新扫描或停止。
</td>
</tr>
<tr>
<td width="33%" valign="top">
<h3>多账号分时段</h3>
最多 3 个账号分别预约不同时间段，适合覆盖较长的学习安排。
</td>
<td width="33%" valign="top">
<h3>跨房间搜索</h3>
目标房间没有合适方案时，可扫描勾选的其他房间，并按时间长度和策略推荐。
</td>
<td width="33%" valign="top">
<h3>首次帮助和主题</h3>
首次打开自动展示使用说明。支持亮色/暗色主题切换，重启后完整生效。
</td>
</tr>
</table>

---

## 快速开始

### 方式一：运行打包版

1. 下载或构建 `dist/LNU-LibSeat-v2.0.0.zip`。
2. 解压到任意目录。
3. 双击 `LNU-LibSeat.exe`。
4. 阅读首次帮助窗口。
5. 填写账号、校区、房间和目标时间段。
6. 第一次建议开启“测试模式”，点击开始查看方案。
7. 确认无误后关闭测试模式，执行真实预约。

### 方式二：源码运行

```powershell
cd LNU-LibSeat
.\run.bat
```

`run.bat` 会自动创建 `env` 虚拟环境、安装依赖并启动 GUI。

已安装依赖时，也可以运行：

```powershell
env\Scripts\python.exe app.py
```

---

## 界面预览

### 主界面

![主界面](docs/screenshots/readme-main.png)

### 首次帮助窗口

![首次帮助窗口](docs/screenshots/readme-help.png)

### 单账号、多账号、跨房间和优先座位配置

![配置区域](docs/screenshots/readme-config.png)

### 测试模式和 API 方案日志

![测试页面](docs/screenshots/readme-dry-run.png)

### 运行日志检测

![运行日志](docs/screenshots/readme-log.png)

### 主题切换

<table width="100%">
<tr>
<td width="50%" align="center">
<img src="docs/screenshots/readme-theme-switch.png" alt="主题切换" width="95%">
</td>
<td width="50%" align="center">
<img src="docs/screenshots/readme-light-theme.png" alt="亮色主题" width="95%">
</td>
</tr>
</table>

---

## 单账号逐段预约示例

假设你想从 `09:00` 坐到 `21:00`，但系统单个座位最长只能预约一段，或没有座位能完整覆盖全天。

1. 选择“单账号逐段”。
2. 设置时间段 `09:00-21:00`。
3. 设置“提前 30 分钟开始查找下一座位”。
4. 程序先预约第一段，例如 `09:00-14:00`。
5. 到 `13:30`，程序开始扫描 `14:00` 之后的下一段。
6. 找到后弹窗展示下一段座位、房间和时间。
7. 点击确认后，程序取消当前预约并预约新座位。

如果勾选“自动取消并换座”，找到下一段后会跳过确认直接执行。第一次使用不建议开启自动模式。

---

## 关闭和恢复

单账号逐段运行时，程序会保存运行状态：

```mermaid
flowchart TD
    A["运行中关闭窗口"] --> B["保存 config_data.json"]
    B --> C["保存 single_runtime_state.json"]
    C --> D["弹窗确认是否退出"]
    D -- "继续运行" --> E["取消关闭"]
    D -- "保存并退出" --> F["停止本地计时和浏览器"]
    F --> G["下次启动单账号模式"]
    G --> H["登录并查询我的预约"]
    H --> I{"服务器有有效预约?"}
    I -- "有" --> J["选择继续上次计划 / 重新扫描 / 停止"]
    I -- "无" --> K["按当前配置重新开始"]
```

恢复时以服务器“我的预约”查询结果为准。本地保存的信息只用于展示上次记录、恢复计时计划和优先验证上次第二段候选。

---

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [文档中心](docs/README.md) | 所有文档入口。 |
| [快速开始](docs/QUICKSTART.md) | 从运行到第一次测试。 |
| [用户使用指南](docs/USER_GUIDE.md) | 普通预约、单账号逐段、多账号分时段。 |
| [配置说明](docs/CONFIGURATION.md) | 配置文件和字段含义。 |
| [架构说明](docs/ARCHITECTURE.md) | 模块职责和运行链路。 |
| [预约与恢复流程](docs/FLOWS.md) | Mermaid 流程图。 |
| [恢复机制详解](docs/RECOVERY_AND_STATE.md) | `single_runtime_state.json` 和恢复策略。 |
| [打包与发布](docs/BUILD_AND_RELEASE.md) | PyInstaller 打包和 GitHub 上传建议。 |
| [常见问题](docs/FAQ.md) | 常见问题和排查建议。 |

---

## 项目结构

```text
LNU-LibSeat/
├── app.py                         # 程序入口
├── run.bat                        # 一键源码运行
├── build.py                       # Windows 打包脚本
├── build_exe.bat                  # Windows 一键打包入口
├── config.py                      # 默认/旧版配置
├── config_data.json               # GUI 配置数据
├── core/                          # API、驱动、通知、验证码、日志等基础能力
├── logic/                         # 登录、导航、预约、取消、规划等业务逻辑
├── ui/                            # PySide6 GUI、面板、控件和后台 worker
│   ├── main_window.py             # 主窗口、帮助、主题、关闭恢复检测
│   ├── runtime_state.py           # 单账号恢复状态读写
│   ├── panels/
│   ├── widgets/
│   └── workers/alloc_worker.py    # 核心后台流程
├── info/                          # 房间和座位信息
├── docs/                          # 项目文档
├── logs/                          # 运行日志和 API 报告
└── requirements.txt               # Python 依赖
```

---

## 打包

```powershell
.\build_exe.bat
```

默认产物：

| 产物 | 路径 |
| --- | --- |
| 发行目录 | `dist/LNU-LibSeat-v2.0.0/` |
| 压缩包 | `dist/LNU-LibSeat-v2.0.0.zip` |
| exe | `dist/LNU-LibSeat-v2.0.0/LNU-LibSeat.exe` |

自定义版本或发行名：

```powershell
.\build_exe.bat --app-version v2.1.0
.\build_exe.bat --dist-name 给同学用的座位工具
```

---

## 上传 GitHub 前的建议

推荐上传源码、文档和 `requirements.txt`。不建议上传：

- `env/`
- `build/`
- `dist/`
- `logs/`
- `__pycache__/`
- `single_runtime_state.json`
- 含真实账号密码的 `config_data.json`

`env/` 不需要上传，别人运行 `run.bat` 会自动重建环境。

---

## 免责声明

本项目仅供技术学习和个人使用。请遵守学校图书馆座位预约、签到和取消规则。由于使用本工具造成的预约失败、违约、黑名单、账号异常或其他后果，由使用者自行承担。

## License

[MIT](LICENSE)
