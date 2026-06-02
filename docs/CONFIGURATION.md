# 配置说明

[返回文档中心](README.md)

## 配置文件位置

| 文件 | 开发态位置 | 打包后位置 | 说明 |
| --- | --- | --- | --- |
| `config_data.json` | 项目根目录 | exe 同级目录 | GUI 保存的用户配置。 |
| `single_runtime_state.json` | 项目根目录 | exe 同级目录 | 单账号逐段运行时恢复状态，默认不存在。 |
| `config.py` | 项目根目录 | 程序内部资源 | 旧版/全局默认配置，worker 会注入 GUI 配置。 |

## `config_data.json` 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `accounts` | list | 账号和密码列表。 |
| `campus` | str | 目标校区。 |
| `room` | str | 目标房间。 |
| `day_start` | str | 目标开始时间，例如 `09:00`。 |
| `day_end` | str | 目标结束时间，例如 `21:00`。 |
| `mode` | str | `single` 单账号逐段；`multi` 多账号分时段。 |
| `dry_run` | bool | 测试模式，不执行真实预约/取消/换座。 |
| `cross_room` | bool | 是否启用跨房间搜索。 |
| `cross_room_rooms` | dict | 每个校区勾选的跨房间候选。 |
| `receiver_email` | str | 邮件接收地址。 |
| `pre_notify` | int | 单账号提前多少分钟扫描下一段。 |
| `auto_cancel` | bool | 单账号是否自动取消并换座。 |
| `priority_mode` | str | `longest_first` 或 `prefer_first`。 |
| `preferred_seats` | dict | 按 `校区/房间` 保存的优先座位。 |
| `theme` | str | `auto`、`light` 或 `dark`。 |
| `first_launch_help_shown` | bool | 首次帮助窗口是否已经显示。 |

## `single_runtime_state.json`

该文件由程序自动维护，不建议手动编辑。

常见字段：

| 字段 | 说明 |
| --- | --- |
| `active` | 是否存在可恢复任务。 |
| `mode` | 固定为 `single`。 |
| `phase` | 当前阶段，例如 `waiting_next_scan`、`pending_change_confirmation`、`changing`。 |
| `account` | 运行时账号，用于避免恢复到错误账号。 |
| `current_booking` | 当前预约座位、房间、起止时间。 |
| `pending_next_slot` | 已扫描到但尚未完成换座的下一段候选。 |
| `notify_at` | 下一次扫描时间。 |
| `config` | 运行时配置快照。 |

程序完成目标时间、用户拒绝换座、无下一段座位或停止恢复时，会清理或更新该状态。

## 敏感信息提醒

上传 GitHub 前请检查：

- `config_data.json` 不应包含真实账号密码。
- `single_runtime_state.json` 不应上传。
- `logs/` 中可能包含运行记录，不建议上传。
- `env/`、`build/`、`dist/` 不建议上传。

