# 打包与发布

[返回文档中心](README.md)

## Windows 打包

在项目根目录执行：

```powershell
.\build_exe.bat
```

默认输出：

| 产物 | 路径 |
| --- | --- |
| 发行目录 | `dist/LNU-LibSeat-v2.0.0/` |
| 压缩包 | `dist/LNU-LibSeat-v2.0.0.zip` |
| exe | `dist/LNU-LibSeat-v2.0.0/LNU-LibSeat.exe` |

## 自定义名称

```powershell
.\build_exe.bat --app-version v2.1.0
.\build_exe.bat --dist-name 给同学用的座位工具
.\build_exe.bat --app-name MyLibSeat --app-version v2.1.0
```

## 打包会包含什么

会包含：

- 当前源码修改。
- `core/`、`logic/`、`ui/` 代码。
- 验证码 ONNX 模型。
- `info/` 房间数据。
- `OIP-C.ico` 图标。
- 清洁版运行配置。

不会预置：

- `env/` 虚拟环境。
- `logs/` 运行日志。
- `single_runtime_state.json` 恢复状态。
- 已生成的旧 `dist/` 产物。

## 上传 GitHub 建议

推荐上传：

- 源码目录：`core/`、`logic/`、`ui/`、`info/`。
- 顶层脚本：`app.py`、`run.bat`、`build.py`、`build_exe.bat`、`requirements.txt`。
- 文档：`README.md`、`docs/`、`LNU-LibSeat项目结构说明.md`。

不推荐上传：

- `env/`
- `build/`
- `dist/`
- `logs/`
- `__pycache__/`
- 含真实账号密码的 `config_data.json`
- `single_runtime_state.json`

## 为什么不上传 env

`env/` 体积大、平台绑定强，换电脑后不一定能用。正确方式是上传 `requirements.txt`，让使用者运行 `run.bat` 自动创建环境。

