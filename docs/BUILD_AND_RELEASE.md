# 打包与发布

[返回文档中心](README.md)

## Windows 打包

在项目根目录执行：

```powershell
.\build_exe.bat
```

当前默认版本来自 [build.py](../build.py)，发行名为 `LNU-LibSeat-v2.5.3`。

默认产物：

| 产物 | 路径 |
| --- | --- |
| 发行目录 | `dist/LNU-LibSeat-v2.5.3/` |
| 压缩包 | `dist/LNU-LibSeat-v2.5.3.zip` |
| exe | `dist/LNU-LibSeat-v2.5.3/LNU-LibSeat.exe` |

## 自定义版本

```powershell
.\build_exe.bat --app-version v2.5.3
.\build_exe.bat --dist-name LNU-LibSeat-test
```

## 发布前检查

- 先用测试模式确认候选选择、多账号方案和单账号续约预览正常。
- 打开主窗口后点击标题栏 `动/低` 按钮，确认低动画模式能暂停动态渐变并写入 `config_data.json`。
- 确认 `config_data.json` 没有真实账号密码。
- 不上传 `single_runtime_state.json`、`logs/`、`env/`、`build/`、`dist/`。
- 发布说明可参考 [v2.5.3 发布说明](RELEASE_BODY_v2.5.3.md)。

## 用户提示

发布包使用前建议让用户先读首次帮助窗口。真实模式会执行预约、取消和换座；测试模式只扫描和预览，不会保存为可恢复任务。
