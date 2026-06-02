# LNU-LibSeat 项目结构说明

更新日期：2026-06-02

本文用于说明当前项目的目的、目录职责、主要运行链路、打包规则，以及最近新增的单账号恢复、运行中防误关和首次帮助窗口功能。`env`、`build`、`dist`、`logs`、`__pycache__` 等目录包含虚拟环境、构建产物、日志或缓存，文件数量多且会自动变化，本文只说明目录用途，不逐一列出内部临时文件。

## 项目目的

LNU-LibSeat 是一个图书馆座位预约桌面工具，使用 PySide6 提供图形界面，结合 LibSeat 后端 API 和 Selenium 浏览器自动化完成座位扫描、预约、取消和换座。

当前支持的主要模式：

| 模式 | 用途 |
| --- | --- |
| 普通/单账号预约 | 使用第一个账号扫描目标房间和时间段，确认推荐方案后预约座位。 |
| 单账号逐段预约 | 当一段长时间无法被一个座位完整覆盖时，先预约第一段，然后在当前预约结束前若干分钟查找下一段座位，确认后取消当前预约并预约新座位。 |
| 多账号分时段 | 最多 3 个账号分别预约不同时间段，用于覆盖较长的学习时间。 |
| 测试模式 | 只通过 API 扫描并生成方案报告，不执行真实预约、取消或换座。 |

## 最新功能概览

| 功能 | 说明 | 主要文件 |
| --- | --- | --- |
| 单账号自动续段/换座 | 第一段预约成功后持续计时，在结束前 `pre_notify` 分钟扫描下一段；找到后弹窗确认，或在自动模式下直接换座。 | `ui/workers/alloc_worker.py`, `core/desktop_notify.py`, `logic/booking_manager.py` |
| 运行中防误关 | 任务运行时关闭窗口会先保存恢复信息并弹窗确认；取消关闭则继续运行。 | `ui/main_window.py`, `ui/workers/alloc_worker.py`, `ui/runtime_state.py` |
| 单账号恢复 | 重启后若存在上次运行状态，登录后查询“我的预约”，让用户选择继续上次计划、重新扫描或停止。 | `ui/main_window.py`, `ui/workers/alloc_worker.py`, `ui/runtime_state.py`, `core/desktop_notify.py` |
| 首次帮助窗口 | 第一次打开程序自动弹出使用说明；标题栏 `?` 按钮可随时再次打开。 | `ui/main_window.py`, `ui/config_store.py` |
| 主题切换 | 右上角月亮/太阳按钮切换亮色/暗色主题，切换后需要重启完全生效。 | `ui/main_window.py`, `ui/theme.py` |

## 打包命名规则

打包命名由 `build.py` 顶部常量和命令行参数控制。

默认值：

```python
APP_NAME = "LNU-LibSeat"
APP_VERSION = "v2.0.0"
DIST_NAME = f"{APP_NAME}-{APP_VERSION}"
```

默认产物：

| 产物 | 路径 |
| --- | --- |
| 发行文件夹 | `dist/LNU-LibSeat-v2.0.0/` |
| 压缩包 | `dist/LNU-LibSeat-v2.0.0.zip` |
| 可执行文件 | `dist/LNU-LibSeat-v2.0.0/LNU-LibSeat.exe` |

支持自定义参数：

```bat
build_exe.bat --dist-name 我的发行包
build_exe.bat --app-version v2.1.0
build_exe.bat --app-name MyLibSeat --app-version v2.1.0
build_exe.bat --app-name MyLibSeat --dist-name 给同学用的座位工具
```

参数说明：

| 参数 | 作用 |
| --- | --- |
| `--app-name` | 自定义 exe 名，不带 `.exe`。 |
| `--app-version` | 自定义版本号；未指定 `--dist-name` 时会影响发行文件夹和 zip 名称。 |
| `--dist-name` | 直接自定义发行文件夹和 zip 名称，优先级最高。 |

名称限制：

- 名称不能为空。
- 名称不能包含 Windows 文件名非法字符：`< > : " / \ | ? *`。
- 名称不能以英文句点或空格结尾。

## 顶层目录

| 目录 | 作用 |
| --- | --- |
| `.idea/` | JetBrains/PyCharm 项目配置目录。 |
| `build/` | PyInstaller 构建中间产物，可删除后重新生成。 |
| `core/` | 底层基础能力：API 客户端、浏览器驱动、日志、通知、验证码识别、路径解析等。 |
| `core/checkpoints/` | 验证码识别模型文件，主要是 `.onnx` 和训练权重。 |
| `dist/` | 打包后的发行文件夹和 zip。 |
| `env/` | Python 虚拟环境和第三方依赖。 |
| `info/` | 房间、区域、座位信息文本数据，用于 UI 配置和跨房间扫描。 |
| `logic/` | 业务逻辑层：登录、进房间、扫描、预约、取消、时间规划等。 |
| `logs/` | 运行日志、截图、API 探测报告、浏览器 profile、打包日志等。 |
| `ui/` | PySide6 图形界面、配置面板、日志面板、控件和后台 worker。 |
| `__pycache__/` | Python 字节码缓存，可删除。 |

## 顶层文件

| 文件 | 作用 |
| --- | --- |
| `.gitignore` | Git 忽略规则。 |
| `app.py` | 程序入口。设置资源路径、工作目录、Qt 图标，创建 `QApplication` 和主窗口。 |
| `build.py` | Windows exe 打包脚本。安装/确认依赖，调用 PyInstaller，写入发行配置并生成 zip。 |
| `build_exe.bat` | Windows 一键打包入口，会把命令行参数继续传给 `build.py`。 |
| `build_mac.py` | macOS 打包脚本，用于生成 `.app` 和 zip。 |
| `config.py` | 旧版/全局默认配置项，会被 GUI worker 注入运行时配置。 |
| `config_data.json` | GUI 当前配置数据，开发态位于项目根；打包后位于 exe 同级可写目录。 |
| `single_runtime_state.json` | 单账号逐段模式运行时自动生成的恢复状态文件；仅运行中需要，默认不存在。 |
| `lib_test.md` | 项目开发和调试过程记录，偏历史资料。 |
| `LICENSE` | 开源许可证。 |
| `LNU-LibSeat项目结构说明.md` | 本说明文档。 |
| `OIP-C.ico` | Windows exe 和 Qt 窗口图标。 |
| `requirements.txt` | Python 依赖列表。 |
| `run.bat` | Windows 启动脚本。首次运行会创建 `env` 并安装依赖，然后用 `pythonw.exe app.py` 启动 GUI。 |

## core 目录

| 文件 | 作用 |
| --- | --- |
| `core/__init__.py` | 标记 `core` 为 Python 包。 |
| `core/api_client.py` | LibSeat REST API 客户端。负责 token 提取、请求签名、房间布局、可用时间、预约相关接口调用。 |
| `core/captcha.py` | 基础验证码识别封装。 |
| `core/captcha_click1_yolo4_siamese.py` | 单击类验证码求解器，使用 YOLO 候选检测和 Siamese 匹配。 |
| `core/captcha_yolo4_siamese.py` | 三击类验证码求解器，使用 YOLO 候选检测和 Siamese 匹配。 |
| `core/desktop_notify.py` | 桌面通知、确认弹窗和恢复选择弹窗。用于首次预约确认、换座确认、无座提醒、恢复任务选择。 |
| `core/driver.py` | Selenium Edge 浏览器驱动初始化、参数构建、驱动下载和缓存处理。 |
| `core/logger.py` | 日志系统。支持文件日志、GUI 日志 handler、账号标签和格式化输出。 |
| `core/network_sniffer.py` | Chrome DevTools Protocol 网络嗅探器，用于捕获 API 请求和响应。 |
| `core/notifications.py` | 邮件通知模块，构造并发送预约成功邮件。 |
| `core/paths.py` | 路径解析。区分开发态、PyInstaller 冻结态、资源目录和可写数据目录。 |
| `core/utils.py` | 小工具函数，目前主要提供北京时间获取。 |
| `core/yolo_onnx.py` | YOLOv8 ONNX 推理工具。 |

## logic 目录

| 文件 | 作用 |
| --- | --- |
| `logic/__init__.py` | 标记 `logic` 为 Python 包。 |
| `logic/api_planner.py` | API-only 座位扫描和规划。构造可预约时间段、跨房间候选、多账号排程和报告。 |
| `logic/auth.py` | Selenium 登录流程，处理账号密码登录和基础验证码。 |
| `logic/booker.py` | Selenium 预约核心。负责点击座位、选择时间、处理验证码、提交预约和识别失败反馈。 |
| `logic/booking_manager.py` | 预约管理。进入“我的预约”、读取当前预约、取消预约、返回座位图。单账号恢复和换座依赖它。 |
| `logic/navigator.py` | 页面导航。进入指定校区、房间或区域。 |
| `logic/scanner.py` | Selenium 座位可用时间扫描器，逐个点击座位读取可预约时间段。当前主流程优先使用 API 扫描。 |
| `logic/scheduler.py` | 时间分配算法。根据座位可用性生成单账号或多账号预约方案。 |

## ui 目录

| 文件 | 作用 |
| --- | --- |
| `ui/__init__.py` | 标记 `ui` 为 Python 包。 |
| `ui/config_store.py` | GUI 配置读写。新增 `first_launch_help_shown` 用于控制首次帮助窗口是否已显示。 |
| `ui/main_window.py` | 主窗口。组合配置面板、日志面板、状态栏、标题栏按钮、主题切换、首次帮助、关闭防误关和恢复检测。 |
| `ui/runtime_state.py` | 单账号逐段运行状态读写。负责保存、读取、清理 `single_runtime_state.json`。 |
| `ui/theme.py` | UI 主题、颜色、字体、阴影、圆角和亮暗主题切换。 |

## ui/panels 目录

| 文件 | 作用 |
| --- | --- |
| `ui/panels/__init__.py` | 标记 `ui.panels` 为 Python 包。 |
| `ui/panels/config_panel.py` | 左侧配置面板。包含账号、校区、房间、时间范围、模式、跨房间、优先座位、单账号设置、测试模式、邮箱等配置 UI。 |
| `ui/panels/log_panel.py` | 右侧日志面板，显示终端风格运行日志。 |

## ui/widgets 目录

| 文件 | 作用 |
| --- | --- |
| `ui/widgets/__init__.py` | 标记 `ui.widgets` 为 Python 包。 |
| `ui/widgets/account_card.py` | 账号卡片和账号面板，支持最多 3 个账号；单账号模式只显示第 1 个账号。 |
| `ui/widgets/action_button.py` | 开始/停止操作按钮和操作栏。 |
| `ui/widgets/animated_frame.py` | 动态渐变边框容器，用于部分配置区域的视觉强调。 |
| `ui/widgets/time_range.py` | 时间段选择控件。 |
| `ui/widgets/toggle_group.py` | 分段按钮控件，用于模式或策略切换。 |

## ui/workers 目录

| 文件 | 作用 |
| --- | --- |
| `ui/workers/__init__.py` | 标记 `ui.workers` 为 Python 包。 |
| `ui/workers/alloc_worker.py` | 后台执行线程。连接 GUI 和业务逻辑，执行登录、API 扫描、预约、多账号分段、单账号逐段、换座、恢复状态保存、关闭恢复信息保存和日志输出。 |

## info 目录

`info/` 下的 `.txt` 文件保存不同房间或区域的座位信息。文件名就是房间或区域名，供 UI 下拉框、跨房间候选和页面导航使用。

当前主要文件：

| 文件 | 作用 |
| --- | --- |
| `info/4楼阅览室.txt` | 4楼阅览室数据。 |
| `info/5楼阅览室.txt` | 5楼阅览室数据。 |
| `info/6楼阅览室.txt` | 6楼阅览室数据。 |
| `info/704.txt` | 704 房间数据。 |
| `info/706.txt` | 706 房间数据。 |
| `info/707.txt` | 707 房间数据。 |
| `info/708.txt` | 708 房间数据。 |
| `info/七楼走廊.txt` | 七楼走廊数据。 |
| `info/三楼智慧研修空间.txt` | 三楼智慧研修空间数据。 |
| `info/三楼理科书库.txt` | 三楼理科书库数据。 |
| `info/三楼走廊.txt` | 三楼走廊数据。 |
| `info/二楼书库北.txt` | 二楼书库北数据。 |
| `info/二楼书库南.txt` | 二楼书库南数据。 |
| `info/二楼背诵长廊.txt` | 二楼背诵长廊数据。 |
| `info/五楼走廊.txt` | 五楼走廊数据。 |
| `info/六楼走廊.txt` | 六楼走廊数据。 |
| `info/四楼北自习室.txt` | 四楼北自习室数据。 |
| `info/四楼南自习室.txt` | 四楼南自习室数据。 |
| `info/四楼自习室406.txt` | 四楼自习室406 数据。 |
| `info/四楼走廊.txt` | 四楼走廊数据。 |
| `info/智慧空间.txt` | 智慧空间数据。 |

## 运行时数据文件

| 文件 | 写入位置 | 作用 |
| --- | --- | --- |
| `config_data.json` | 开发态：项目根；打包后：exe 同级目录 | 保存用户填写的账号、房间、时间、模式、跨房间、优先座位、主题偏好、首次帮助标记等。 |
| `single_runtime_state.json` | 开发态：项目根；打包后：exe 同级目录 | 单账号逐段模式运行时保存当前预约、下一次扫描时间、第二段候选、恢复阶段等。任务完成或用户拒绝恢复后会清理。 |
| `logs/lnu_seat.log` | `logs/` | 主运行日志。 |
| `logs/api_booking_plan_*.json` | `logs/` | 单账号 API 方案报告。 |
| `logs/api_multi_booking_plan_*.json` | `logs/` | 多账号 API 分段方案报告。 |

## 主要运行链路

```text
app.py
  -> ui/main_window.py
      -> ui/config_store.py
      -> ui/runtime_state.py
      -> ui/panels/config_panel.py
      -> ui/panels/log_panel.py
      -> ui/workers/alloc_worker.py
          -> core/api_client.py
          -> core/desktop_notify.py
          -> core/driver.py
          -> core/notifications.py
          -> logic/api_planner.py
          -> logic/auth.py
          -> logic/booker.py
          -> logic/booking_manager.py
          -> logic/navigator.py
```

## 单账号逐段流程

```text
用户点击开始
  -> 登录并进入目标房间
  -> 提取 token
  -> API 扫描目标时间段
  -> 弹窗确认第一段方案
  -> Selenium 预约第一段
  -> 保存 single_runtime_state.json
  -> 循环等待到 当前结束时间 - pre_notify
      -> API 扫描下一段
      -> 找到下一段后保存 pending_next_slot
      -> 弹窗确认，或自动模式直接确认
      -> 进入“我的预约”
      -> 取消当前预约
      -> 返回座位图/切换房间
      -> 预约下一段
      -> 更新当前预约状态
  -> 覆盖目标结束时间后清理恢复状态
```

例子：

- 用户目标时间是 `09:00-21:00`。
- 第一段推荐为 `09:00-14:00`。
- 单账号设置为提前 `30` 分钟。
- 程序会在 `13:30` 开始扫描 `14:00` 之后的下一段座位。
- 找到后弹窗展示下一段座位、房间、时间；用户确认后执行取消当前预约并预约新座位。

## 单账号关闭恢复流程

```text
运行中关闭窗口
  -> 保存 config_data.json
  -> 保存 single_runtime_state.json
  -> 弹窗确认是否退出

下次启动单账号模式
  -> 读取 single_runtime_state.json
  -> 登录账号
  -> 进入“我的预约”
  -> 查询服务器当前有效预约
  -> 展示服务器预约 + 上次保存信息 + 上次第二段推荐
  -> 用户选择：
       继续上次计划：继续计时；若已有第二段推荐则重新扫描验证并优先考虑该座位
       重新扫描：接管当前预约，但忽略上次第二段推荐
       停止：保留当前预约，不继续自动换座
```

恢复时以服务器“我的预约”查询结果为准；本地状态只作为辅助信息和房间名兜底。

## 首次帮助窗口

首次打开程序时，`ui/main_window.py` 会自动弹出使用帮助，内容包括：

- 普通预约怎么用。
- 单账号逐段预约怎么用。
- 多账号分时段怎么用。
- 跨房间、优先座位、测试模式的含义。
- 主题切换说明。
- 关闭和恢复机制。
- 运行注意事项。

用户点击“我知道了”后，`config_data.json` 中的 `first_launch_help_shown` 会被写为 `true`，后续不再自动弹出。标题栏 `?` 按钮可随时重新打开帮助。

## 配置字段摘要

| 字段 | 说明 |
| --- | --- |
| `accounts` | GUI 保存的账号列表。 |
| `campus` | 目标校区。 |
| `room` | 目标房间。 |
| `day_start` / `day_end` | 目标时间范围。 |
| `mode` | `multi` 表示多账号分时段；`single` 表示单账号逐段。 |
| `dry_run` | 测试模式开关。 |
| `cross_room` | 是否启用跨房间扫描。 |
| `cross_room_rooms` | 每个校区勾选的跨房间候选。 |
| `receiver_email` | 邮件接收地址。 |
| `pre_notify` | 单账号模式下提前多少分钟扫描下一段。 |
| `auto_cancel` | 单账号模式下是否自动取消并换座。 |
| `priority_mode` | `longest_first` 表示最长时段优先；`prefer_first` 表示优先座位优先。 |
| `preferred_seats` | 按 `校区/房间` 保存的优先座位列表。 |
| `theme` | `auto`、`light` 或 `dark`。 |
| `first_launch_help_shown` | 首次帮助窗口是否已显示。 |

## Python 代码直接依赖关系摘要

| 文件 | 主要内部依赖 |
| --- | --- |
| `app.py` | `core/paths.py`, `ui/main_window.py` |
| `core/api_client.py` | `core/logger.py` |
| `core/captcha.py` | `core/logger.py` |
| `core/captcha_click1_yolo4_siamese.py` | `core/paths.py`, `core/yolo_onnx.py` |
| `core/captcha_yolo4_siamese.py` | `core/paths.py`, `core/yolo_onnx.py` |
| `core/desktop_notify.py` | `core/logger.py` |
| `core/driver.py` | `config.py`, `core/logger.py` |
| `core/logger.py` | `config.py` |
| `core/network_sniffer.py` | `core/logger.py` |
| `core/notifications.py` | `config.py`, `core/logger.py` |
| `logic/api_planner.py` | `core/logger.py` |
| `logic/auth.py` | `core/captcha.py`, `core/logger.py` |
| `logic/booker.py` | `core/captcha_click1_yolo4_siamese.py`, `core/captcha_yolo4_siamese.py`, `core/logger.py` |
| `logic/booking_manager.py` | `core/logger.py` |
| `logic/navigator.py` | `core/logger.py` |
| `logic/scanner.py` | `core/logger.py`, `logic/booker.py`, `logic/navigator.py` |
| `logic/scheduler.py` | `core/logger.py` |
| `ui/config_store.py` | `core/paths.py` |
| `ui/main_window.py` | `ui/config_store.py`, `ui/runtime_state.py`, `ui/panels/config_panel.py`, `ui/panels/log_panel.py`, `ui/theme.py`, `ui/workers/alloc_worker.py` |
| `ui/runtime_state.py` | `core/paths.py` |
| `ui/panels/config_panel.py` | `ui/config_store.py`, `ui/theme.py`, `ui/widgets/account_card.py`, `ui/widgets/action_button.py`, `ui/widgets/animated_frame.py`, `ui/widgets/time_range.py`, `ui/widgets/toggle_group.py` |
| `ui/panels/log_panel.py` | `ui/theme.py` |
| `ui/widgets/account_card.py` | `ui/theme.py` |
| `ui/widgets/action_button.py` | `ui/theme.py` |
| `ui/widgets/animated_frame.py` | `ui/theme.py` |
| `ui/widgets/time_range.py` | `ui/theme.py` |
| `ui/widgets/toggle_group.py` | 无项目内依赖 |
| `ui/workers/alloc_worker.py` | `ui/runtime_state.py`, `core/api_client.py`, `core/desktop_notify.py`, `core/driver.py`, `core/notifications.py`, `logic/api_planner.py`, `logic/auth.py`, `logic/booker.py`, `logic/booking_manager.py`, `logic/navigator.py` |

## 打包相关注意事项

- Windows 打包入口是 `build_exe.bat`。
- 重新执行 build 后，当前源码修改会进入新的 exe；旧的已打包产物不会自动更新。
- `build.py` 会把 `OIP-C.ico` 写入 exe，并复制到发行目录和 `_internal`。
- `.onnx` 验证码模型会被打入发行包。
- `config_data.json` 会写入发行目录作为可编辑配置文件；账号等敏感信息首次分发时应保持为空。
- `single_runtime_state.json` 不需要预置，运行单账号逐段任务时会自动生成。
- 如果 Windows 资源管理器仍显示旧图标，多半是图标缓存；换文件名、刷新资源管理器或重启后通常会更新。

