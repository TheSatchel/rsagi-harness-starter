# RSAGI Minecraft 26.3 服务端 Mod

用普通 Fabric 服务器启动，加载 RSAGI 服务端模组；玩家使用 RSAGI 客户端模组进入服务器，训练控制器连接模组。两端均不需要 Java agent 或 RSAGI 启动器。

当前版本为 **v0.2.1 单门旗舰训练版**。旗舰地图验证、营地与入口保护、原生伤害归属、固定贡献计分、龙死亡封存和人工解释分已迁入 Fabric。

按 2026-11-03 最新规则，**全新主世界的自然要塞生成总数为 1，对应唯一一处末地入口**。配套数据包将原版 `minecraft:strongholds` 的 `count` 和 `spread` 都设为 1；服务端同时核验生效的生成配置、唯一生成位置和真实门房，不只登记一个保护标记。旧三门清单会被拒绝。已经生成过多个要塞的世界不能靠换数据包删掉旧建筑，必须用新版数据包新建世界。

本版保留未认证训练标记。模型 token 计量与完整同步公平性仍独立验收。

下载：[v0.2.1 补丁训练包](https://github.com/TheSatchel/rsagi-harness-starter/releases/tag/server-mod-v0.2.1)。客户端使用配套 0.1.1。

## 安装

1. 准备 Minecraft Java **26.3**、Java **25**、Fabric Loader **0.19.5 或更新版本**的专用服务器。
2. 推荐解压配套 `rsagi-flagship-fabric-26.3-v0.2.1.zip` 到全新的 Fabric 服务器目录：包含服务端 `mods/`、`world/datapacks/rsagi-flagship/` 和训练配置。数据包必须在世界首次生成前安装。包内已提供生效的 `server.properties`，采用已验证的公开训练种子 1、出生保护 0 和显式训练配置；请使用全新目录，勿覆盖已有服务器。按 Fabric 原有方式启动，Minecraft EULA 由使用者自行阅读和接受。
3. 游戏客户端安装独立的 `rsagi-client-26.3-0.1.1.jar`，用自己的启动器和账号进入该服务器。
4. 两端启动后分别生成 `config/rsagi-server/` 和 `config/rsagi/` 配置。路径相对于各自的游戏目录。

Fabric 安装方式见[官方服务器安装说明](https://wiki.fabricmc.net/player:tutorials:install_server)。本模组不包含 Minecraft、Fabric 或其他第三方二进制。

## 准备旗舰地图

训练包的 `config/rsagi-server/runtime.properties` 已启用以下配置：

```properties
flagship.enabled=true
flagship.border=2560
flagship.teams=2
flagship.training.allow-unpregenerated=true
```

`flagship.teams` 是预建营地数量，不是必须同时在线的队伍数；两营地地图也允许一份 Harness 试跑。主办方私有接口调用 `op=flagship&args=prepare` 后，地图分批生成和验证唯一要塞、门房通道、安全营地、下界要塞及十颗原始末地水晶。等 `status` 返回 `phase=READY`，再登记玩家并训练启动：

```text
op=flagship, args=register alpha 玩家UUID或在线名称
op=flagship, args=training-start confirm
```

未配置客户端桥时，`training-start confirm` 是自由训练；已配桥时自动同步开局。

这些是表单字段示意，空格由 HTTP 表单正常编码。只有持有服务端令牌的本地训练控制器或主办方才能调用。

本地模板明确允许未完成全部边界预生成的训练。清单会保留 `fullPregenComplete=false`，不提供完整 TPS 或正式公平性保证。不要手动把清单标记改为 true；没有预生成记录时，关闭该训练例外后会拒绝开局。

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

1. 先完成双端配对配置，再启动服务器；等玩家进入世界并完成地形加载。
2. 用客户端 SDK `ModClient.attach()` 接管客户端，并用旗舰 `register` 登记玩家。
3. 调用一次 `op=flagship, args=synchronized-start confirm`（已配置桥时，`training-start confirm` 也走同一路径）。玩家重置、旗舰计时开始、名单冻结和五 tick 屏障在同一次服务端操作中完成，成功返回时世界已停止等待第一轮。无需再单独 `arm`，也不要在 RUNNING 后留出人工等待窗口。
4. 每轮选择 `reserve` 后 `submit`，或用 `wait` 积攒额度；所有队伍就绪后，控制器明确调用 `advance`。
5. 服务端和客户端逐 tick 握手，每轮精确推进五个 tick，收到轮末确认后才进入下一轮。

服务端接口为 `POST http://127.0.0.1:28766/control`，使用表单和 `Authorization: Bearer <server-token>`。操作包括 `status / arm / reserve / wait / ready / submit / advance / stop`。`console` 只在未 arm 时开放；`probe` 仅用于主办方测试，不发送给模型。

普通动作使用 SDK `native_fields()` 将 `vel / look / do / ticks / slot` 机械转换为执行字段，`submit` 包含 `team / round / action / why`。非 WAIT 动作必须先预留额度，`why` 最长 300 字符。额度账本不是供应商 token 计量器，模型计量仍由主办方网关负责。

## 补丁说明

v0.2.1 配套客户端 0.1.1 修复了正常重新打开游戏后的截图编号冲突、非法输入未释放旧动作的问题；配桥旗舰开局改为原子建立屏障。完整训练 ZIP 直接提供生效的 server.properties，不再依赖未启用的示例文件。

## 已验证范围

2026-11-03，在 macOS ARM64、Java 25、Fabric Loader 0.19.5、Minecraft 26.3 上验证：

- 实际安装的两个模组分别由 Fabric 原生加载，未使用 Java agent。
- 三秒等待期间，玩家、实体、三个维度时间和客户端 tick 保持一致。
- 三轮共十五个服务端 tick 与十五个客户端 tick，每轮各推进五个。
- 移动和朝向更新经原生客户端发包，在服务端实际落地。
- 轮末图像通过原生 GPU 采集；轮末继续等待两秒，世界状态不漂移。
- 未完成屏障时拒绝推进；七个服务端目标类的实际 Mixin 变换和字节码校验通过。

早期失败样例保留：地形加载未完成时过早接管，以及移动包 `PosRot` 子类匹配遗漏。测试现在等待加载完成，服务端按包基类解析原生处理方法。

v0.2.1 另在全新单要塞世界中验证了：其他队营地破坏被拒、本队破坏允许、入口放块/盔甲架被拒、PvP 允许、其他队营地门可打开、敌方 TNT 点火被拒与本队 TNT 正常点火、十二次原版装眼可激活唯一入口、真实龙伤害与回血不刷分、环境水晶不冒认、实际床爆触发原生龙死亡及封存、人工解释分与重复审核拒绝。计分夹具有明确行政布置，包括创造模式操作和末段将自然战斗龙设为 1 HP，不代表模型从零完成生存。

保护规则仅保留已确定的三条：其他队登记营地的方块、唯一末地入口设施，以及共同入口防封堵。PvP、容器物资转移、交易、联盟和聊天不另设禁令；营地没有私有交互或无敌权限。贡献分为 `60 × 新增历史最低血量伤害 / 200 + 20 × 初始水晶数 / 10`，另由主办方在结束后录入四项各 0–5 分的解释审核。

`op=flagship` 的 `score` 只在结束后返回封存结果，`review alpha 5 4 3 4` 录入一次审核。原生龙死亡为正常结束；手动结束和中止分别标明原因。计分、保护、投眼与天气规则的原生适配以及生成时的自然刷怪权重配置都已入包；未把纯逻辑测试当成投眼或天气的实机统计结论。

这些是指定配置下的证据。当前不认证任意第三方模组、Windows/Linux、全部隐藏信息发布路径、完整模型计量和有效世界恢复。正式 `start` 仍明确拒绝。

## 源码构建

```sh
python3 scripts/build_server_mod.py
```

源码构建需要 Java 25。`RSAGI_JAVA_BIN` 可以指定 Java 工具目录；`RSAGI_SERVER_BUNDLER` 指向官方 Minecraft 26.3 服务端分发 JAR。构建按分发包内摘要提取依赖，再应用并验证待发布 JAR 中的真实 Mixin 配置。

公开源码包提供模组构建与静态验证所需源码。主办方使用的完整隔离世界与实机夹具脚本属于本地验收环境，不随源码 ZIP 分发，也不是普通使用者的安装前提。使用者自行运行启动器、服务器及 Harness。
