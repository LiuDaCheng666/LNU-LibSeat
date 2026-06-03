# LNU-LibSeat 文档中心

本文档适用于当前桌面项目 `D:\User\MC233\Desktop\LNU-LibSeat`。它和参考目录里的 `LNU-LibSeat-Automation` 是不同功能版本：当前项目以 PySide6 GUI、API 扫描规划、单账号逐段换座恢复、跨房间候选选择和多账号多方案分时段为核心。

## 文档导航

| 文档 | 适合谁 | 内容 |
| --- | --- | --- |
| [快速开始](QUICKSTART.md) | 普通用户 | 下载/源码运行、第一次配置、测试模式、开始预约。 |
| [用户使用指南](USER_GUIDE.md) | 普通用户 | 普通预约、单账号逐段、多账号多方案、跨房间和优先座位。 |
| [配置说明](CONFIGURATION.md) | 高级用户/开发者 | `config_data.json`、`config.py`、运行状态文件和关键字段。 |
| [架构说明](ARCHITECTURE.md) | 开发者 | 分层结构、模块职责、依赖关系、运行链路。 |
| [预约与恢复流程](FLOWS.md) | 用户/开发者 | 主要流程图、单账号逐段、恢复、关闭防误关。 |
| [恢复机制详解](RECOVERY_AND_STATE.md) | 开发者 | `single_runtime_state.json` 的保存、恢复和清理策略。 |
| [打包与发布](BUILD_AND_RELEASE.md) | 发布维护者 | Windows 打包、产物结构、上传 GitHub 建议。 |
| [常见问题](FAQ.md) | 所有人 | 登录、验证码、恢复、打包、GitHub 上传等问题。 |
| [v2.5.2 发布说明](RELEASE_BODY_v2.5.2.md) | 发布使用 | 本版本更新、注意事项和下载文案。 |

## 图片和截图

当前文档先使用 Mermaid 流程图，不依赖图片。若要补充真实界面截图，建议放到 [screenshots](screenshots/README.md) 目录；若要补充导出的流程图图片，建议放到 [flowcharts](flowcharts/README.md) 目录。

