# RSAGI Minecraft 26.3 服务端 Mod

用普通 Fabric 服务器启动，加载 RSAGI 服务端模组；玩家使用 RSAGI 客户端模组进入服务器，训练控制器连接模组。两端均不需要 Java agent 或 RSAGI 启动器。

这是原生同步训练底座 v0.1.0。它已通过一名真实渲染玩家的双模组运行测试，尚未迁完 Paper 旗舰的地图保护与计分规则，不能作为正式旗舰服务器开赛。

下载：[服务端 Mod 训练底座 v0.1.0](https://github.com/TheSatchel/rsagi-harness-starter/releases/tag/server-mod-v0.1.0)。

## 安装

1. 准备 Minecraft Java **26.3**、Java **25**、Fabric Loader **0.19.5 或更新版本**的专用服务器。
2. 将 `rsagi-server-26.3-0.1.0.jar` 放入服务器 `mods/`，按 Fabric 原有方式启动服务器。Minecraft EULA 由服务器使用者自行阅读和接受。
3. 游戏客户端安装独立的 `rsagi-client-26.3-0.1.0.jar`，用自己的启动器和账号进入该服务器。
4. 两端启动后分别生成 `config/rsagi-server/` 和 `config/rsagi/` 配置。路径相对于各自的游戏目录。

Fabric 安装方式见[官方服务器安装说明](https://wiki.fabricmc.net/player:tutorials:install_server)。本模组不包含 Minecraft、Fabric 或其他第三方二进制。

## 双端配对

客户端的 `config/rsagi/runtime.properties` 默认：

```properties
control.port=25672
control.bind=127.0.0.1
```

客户端配对令牌在 `config/rsagi/token`，不写入提示词。异机连接时，在客户端配置中将监听地址改为游戏机器的局域网地址，再重新启动客户端。

服务端的 `config/rsagi-server/runtime.properties` 配置：

```properties
control.port=28766
client.control.url=http://127.0.0.1:25672/control
client.token.file=/absolute/path/to/client/config/rsagi/token
```

`client.control.url` 是客户端模组的地址，需要包含 `/control`。如果客户端在另一台机器上，将地址替换为该机器的局域网地址，并在服务器本地的一个私有文件中保存客户端配对令牌，将 `client.token.file` 指向这个文件。修改配置后重启服务器。

未配置客户端地址时，只能做服务端 WAIT 步进；配置后首版绑定一队、一名渲染玩家，按每个客户端 tick 对应一个服务端 tick 握手。HTTP 调用在独立线程执行，游戏所有者线程不等待模型或网络请求。

服务端另有 `config/rsagi-server/token`，属于主办方或本地训练控制器，不能发给参赛模型。服务端控制 API 只监听回环地址。它包含调试真值，不能充当玩家观察；模型观察仍取自客户端真实 GPU 画面与原版字幕原文。

## 训练控制顺序

1. 等玩家进入世界并完成地形加载。
2. 用客户端 SDK `ModClient.attach()` 接管客户端。
3. 主办方以 `alpha:玩家UUID` 绑定精确在线名单，调用服务端 `arm`。此后拒绝迟到玩家加入。
4. 每轮选择 `reserve` 后 `submit`，或用 `wait` 积攒额度；所有队伍就绪后，控制器明确调用 `advance`。
5. 服务端和客户端逐 tick 握手，每轮精确推进五个 tick，收到轮末确认后才进入下一轮。

服务端接口为 `POST http://127.0.0.1:28766/control`，使用表单和 `Authorization: Bearer <server-token>`。操作包括 `status / arm / reserve / wait / ready / submit / advance / stop`。`console` 只在未 arm 时开放；`probe` 仅用于主办方测试，不发送给模型。

普通动作使用 SDK `native_fields()` 将 `vel / look / do / ticks / slot` 机械转换为执行字段，`submit` 包含 `team / round / action / why`。非 WAIT 动作必须先预留额度，`why` 最长 300 字符。额度账本不是供应商 token 计量器，模型计量仍由主办方网关负责。

## 已验证范围

2026-11-03，在 macOS ARM64、Java 25、Fabric Loader 0.19.5、Minecraft 26.3 上验证：

- 实际安装的两个模组分别由 Fabric 原生加载，未使用 Java agent。
- 三秒等待期间，玩家、实体、三个维度时间和客户端 tick 保持一致。
- 三轮共十五个服务端 tick 与十五个客户端 tick，每轮各推进五个。
- 移动和朝向更新经原生客户端发包，在服务端实际落地。
- 轮末图像通过原生 GPU 采集；轮末继续等待两秒，世界状态不漂移。
- 未完成屏障时拒绝推进；七个服务端目标类的实际 Mixin 变换和字节码校验通过。

早期失败样例保留：地形加载未完成时过早接管，以及移动包 `PosRot` 子类匹配遗漏。测试现在等待加载完成，服务端按包基类解析原生处理方法。

这些是指定配置下的证据。当前不认证任意第三方模组、Windows/Linux、全部隐藏信息发布路径、完整模型计量、完整旗舰保护与评分，以及有效世界恢复。原生末影龙死亡的结束挂钩已编写，其 Fabric 实机结算尚未在本报告验收。

## 构建与复现

```sh
python3 scripts/build_server_mod.py
python3 scripts/fabric_pair_smoke.py
```

源码构建需要 Java 25。`RSAGI_JAVA_BIN` 可以指定 Java 工具目录；`RSAGI_SERVER_BUNDLER` 指向官方 Minecraft 26.3 服务端分发 JAR。构建按分发包内摘要提取依赖，再应用并验证待发布 JAR 中的真实 Mixin 配置。

复现脚本仅供主办方隔离测试，需要当前开发环境的 Minecraft 客户端依赖；它不会读取启动器账号，但会创建独立世界和离线测试角色。使用者自行运行游戏时不需要这个脚本。
