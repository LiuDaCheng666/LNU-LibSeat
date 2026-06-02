# LNU-LibSeat v2.0.0

### 辽宁大学图书馆座位预约助手

**PySide6 图形界面 · API 扫描规划 · 单账号逐段换座 · 关闭后可恢复 · 多账号分时段**

---

## 重要提醒

> 第一次使用请先开启 **测试模式**，确认可以扫描出方案后，再执行真实预约。

> 请下载下方 **Assets** 中的 `LNU-LibSeat-v2.0.0.zip`。  
> 不要下载 `Source code (zip)`，那是 GitHub 自动生成的源码压缩包，不是可直接运行的程序。

---

## 三步开始

### 1. 下载

[下载 LNU-LibSeat-v2.0.0.zip](https://github.com/LiuDaCheng666/LNU-LibSeat/releases/download/v2.0.0/LNU-LibSeat-v2.0.0.zip)

或者滑动到页面底部，在 **Assets** 中点击：

`LNU-LibSeat-v2.0.0.zip`

### 2. 解压并双击

解压后双击：

`LNU-LibSeat.exe`

首次打开会自动弹出使用帮助。

### 3. 填写配置并开始

填写账号、校区、房间和目标时间段。  
第一次建议先打开 **测试模式**，确认能扫描出方案后再执行真实预约。

---

## 核心功能

| 功能 | 说明 |
| --- | --- |
| PySide6 图形界面 | 现代化桌面界面，支持亮色/暗色主题。 |
| API 扫描规划 | 通过后端接口快速扫描座位可用时间，生成推荐方案。 |
| 单账号逐段预约 | 适合长时间学习，先预约第一段，再提前查找下一段。 |
| 自动/确认换座 | 找到下一段后可弹窗确认，也可开启自动取消并换座。 |
| 关闭后恢复 | 运行中关闭会保存状态，重启后查询“我的预约”并询问是否恢复。 |
| 多账号分时段 | 最多 3 个账号分别预约不同时间段。 |
| 跨房间搜索 | 当前房间无合适方案时，可扫描勾选的其他房间。 |
| 首次帮助窗口 | 第一次启动自动显示使用说明，标题栏 `?` 可随时再次打开。 |

---

## 界面预览

> 如果图片没有显示，请先确认仓库里已经 push 了 `docs/screenshots/` 目录。

### 主界面

![主界面](https://raw.githubusercontent.com/LiuDaCheng666/LNU-LibSeat/main/docs/screenshots/readme-main.png)

### 首次帮助窗口

![首次帮助窗口](https://raw.githubusercontent.com/LiuDaCheng666/LNU-LibSeat/main/docs/screenshots/readme-help.png)

### 配置区域

![配置区域](https://raw.githubusercontent.com/LiuDaCheng666/LNU-LibSeat/main/docs/screenshots/readme-config.png)

### 测试模式与运行日志

![测试模式](https://raw.githubusercontent.com/LiuDaCheng666/LNU-LibSeat/main/docs/screenshots/readme-dry-run.png)

![运行日志](https://raw.githubusercontent.com/LiuDaCheng666/LNU-LibSeat/main/docs/screenshots/readme-log.png)

---

## 单账号逐段示例

假设你想从 `09:00` 学到 `21:00`，但系统无法一次预约完整时间：

1. 选择 **单账号逐段**。
2. 设置时间段 `09:00-21:00`。
3. 设置提前 `30` 分钟查找下一座位。
4. 程序先预约第一段，例如 `09:00-14:00`。
5. 到 `13:30`，程序开始扫描 `14:00` 之后的下一段。
6. 找到下一段后弹窗展示座位、房间和时间。
7. 用户确认后，程序取消当前预约并预约新座位。

---

## 关闭和恢复

单账号逐段模式运行中，如果不小心关闭程序：

- 程序会先保存当前预约、下一次扫描时间和第二段候选。
- 下次启动并登录后，会查询“我的预约”。
- 如果服务器上仍有有效预约，会让你选择：
  - 继续上次计划
  - 重新扫描
  - 停止接管

恢复时以服务器“我的预约”查询结果为准，本地状态只作为辅助。

---

## 文档

- [快速开始](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/QUICKSTART.md)
- [用户指南](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/USER_GUIDE.md)
- [配置说明](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/CONFIGURATION.md)
- [架构说明](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/ARCHITECTURE.md)
- [预约与恢复流程](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/FLOWS.md)
- [打包与发布](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/BUILD_AND_RELEASE.md)
- [常见问题](https://github.com/LiuDaCheng666/LNU-LibSeat/blob/main/docs/FAQ.md)

---

## 发布包内容

下载并解压 `LNU-LibSeat-v2.0.0.zip` 后，主要包含：

```text
LNU-LibSeat-v2.0.0/
├── LNU-LibSeat.exe
├── config_data.json
├── info/
├── _internal/
└── OIP-C.ico
```

运行时会自动生成：

- `logs/`
- `single_runtime_state.json`

---

## 免责声明

本项目仅供技术学习和个人使用。请遵守学校图书馆座位预约、签到和取消规则。由于使用本工具造成的预约失败、违约、黑名单、账号异常或其他后果，由使用者自行承担。

