# RSAGI Minecraft 客户端 Mod

此 Mod 用于手动启动的 Minecraft 26.3 客户端。进入世界后，Harness 或测试机通过带令牌认证的 HTTP 接口连接客户端，提交低层输入，推进客户端 tick，并读取实际 GPU 渲染画面及原版字幕文字。

下载：[客户端 v0.1.1](https://github.com/TheSatchel/rsagi-harness-starter/releases/tag/client-mod-v0.1.1)。修复正常重开后的截图冲突及非法输入残留。

## 安装与启动

1. 在你使用的启动器中准备 Minecraft **26.3**、Fabric Loader **0.19.5 或更高版本**以及 **Java 25**。
2. 将构建产物 `mod/build/rsagi-client-26.3-0.1.1.jar` 放入该实例游戏目录的 `mods/`。
3. 用启动器正常启动该实例。登录账号、选择服务器或进入世界均由使用者完成。
4. 在日志中确认出现 `RSAGI_MOD_WAITING_FOR_CONNECTION`，然后读取该实例游戏目录下的 `config/rsagi/` 配置。
5. 启动 Harness 或测试机连接流程，在玩家已进入世界后调用 `attach()`。

安装依赖由 Fabric Loader 提供。这个 Mod 的入口及运行钩子使用 Fabric 与 Mixin，普通启动方式沿用启动器的窗口、音频及原版输入设置。启动后处于 `WAITING_FOR_CONNECTION`，使用者可以操作菜单并进入世界。`attach()` 开始控制，`detach()` 恢复人工输入。

当前开发与构建验证环境为 macOS ARM64、Java 25 与固定版本 Minecraft 26.3。构建脚本同时验证具体客户端 JAR 的 SHA-256。

## 连接配置

首次启动生成以下文件，路径相对于当前游戏实例目录。

| 文件 | 用途 |
| --- | --- |
| `config/rsagi/token` | 随机生成的 64 位十六进制配对令牌 |
| `config/rsagi/runtime.properties` | HTTP 监听地址与端口 |
| `config/rsagi/frames/` | 控制期间捕获的玩家画面 |

默认配置为同一台机器上的连接。

```properties
control.port=25672
control.bind=127.0.0.1
```

另一个测试机需要直接连接时，退出 Minecraft，将 `control.bind` 改为当前游戏机器的局域网地址，然后重新启动。以下配置采用示例地址，实际使用时替换为游戏机器的地址。

```properties
control.port=25672
control.bind=192.168.1.20
```

测试机使用同一配对令牌，并将 `RSAGI_MOD_URL` 指向游戏机器。HTTP 控制和画面读取均要求 `Authorization: Bearer <token>`。令牌提供控制权限，应仅交给本次使用的 Harness 或测试机。实例目录支持 POSIX 文件权限时，Mod 将令牌文件设为仅当前用户可读写。

使用仓库提供的 Python 连接示例，可在仓库根目录执行以下命令。用实例中 `config/rsagi/token` 的内容替换占位文本。

```sh
export RSAGI_MOD_URL='http://127.0.0.1:25672'
export RSAGI_MOD_TOKEN='替换为实例生成的配对令牌'
python3 sdk/examples/mod_connect.py
```

示例默认读取状态。使用 `python3 sdk/examples/mod_connect.py --step` 会在当前已进入的世界中连接控制，短暂转动视角，保存 `rsagi-player-view.png`，然后解除控制。

自定义 Harness 可使用 `sdk/src/rsagi_harness/mod_client.py` 中的 `ModClient`。一次 `step(action, why, ticks=5)` 需要简短的操作理由，支持 1 至 5 个客户端 tick。`capture()` 返回 PNG 及其校验信息，`receipt["sound_hints"]` 提供原版字幕产生的本地化文字和方向箭头。控制期间字幕文字作为声音观察返回，字幕文字及背景从图像渲染中移除。

## 当前训练边界

Mod 管理当前客户端的低层输入、客户端 tick 许可及画面读取。多人服务器自身的时间推进与计费验收需要配套服务协调。当前状态明确返回 `mode=MOD_LOCAL_TRAINING`、`server_sync_verified=false`、`metering_enforced=false`、`strictCertified=false`，用于本地训练与接入测试。

使用者通过 Minecraft 菜单或启动器退出游戏。控制状态下调用 `detach()` 可先恢复人工操作。

## 从源码构建

在仓库根目录执行以下命令。

```sh
python3 scripts/build_mod.py
```

脚本读取当前已安装、经过哈希固定的 Minecraft 26.3 依赖以及项目 Java 25 工具链，并按 `mod/dependencies.json` 中的 SHA-256 下载或验证 Fabric、Mixin 与 ASM。缓存位于 `.runtime/fabric-mod-deps/`。

输出包括可安装 JAR 和 `mod/build/mixin-verification-26.3.txt`。静态测试从待发布 JAR 读取实际 Mixin 配置，用真实 Mixin 转换器应用全部九个目标类，再使用 Java 25 Class-File API 验证变换后的字节码。其中包括原版字幕内部类构造、亮度、刷新和过期清理的四处时钟调用。静态验证过程仅处理字节码资源。

项目测试另有显式隐藏窗口模式，由 `-Drsagi.client.headless=true` 及对应的进程环境启用。普通启动器安装采用上述默认启动流程。
