# 远征杯 RSAGI Harness Starter

[![协议测试](https://github.com/TheSatchel/rsagi-harness-starter/actions/workflows/ci.yml/badge.svg)](https://github.com/TheSatchel/rsagi-harness-starter/actions/workflows/ci.yml)

面向高中生与高校学生团队的 Minecraft 具身智能比赛接入框架：API 协议、Python SDK、最小 Harness、两队模拟服务端和合同测试。

**当前版本：v0.1.0 协议原型。** 可以在本地开发、验证 Harness 接入逻辑；尚未连接真实 Minecraft、玩家图像/声音或真实模型。没有对外上线的正式比赛 API，不具备正式开赛条件。

## 一条命令运行

需要 Python 3.9 或更新版本。演示没有第三方 Python 运行依赖，不需要模型密钥、Minecraft 账号或 Docker。

```sh
git clone https://github.com/TheSatchel/rsagi-harness-starter.git
cd rsagi-harness-starter
python3 sdk/examples/demo.py
```

Windows 可以用 `py -3` 替换 `python3`。也可以从 [Releases](https://github.com/TheSatchel/rsagi-harness-starter/releases) 下载 ZIP，解压后运行相同命令。

演示会启动仅监听回环地址的临时 HTTP 模拟服务，让两个独立 SDK 客户端完成：

- 12 轮全队屏障、60 个**模拟** tick；
- 额度积攒、调用前扣除，以及重复请求只产生一次副作用；
- 10 次合成模型操作、2 次模拟模型提出的 Harness 配置调整。

输出应注明 `protocol_mock`，并包含：

```json
{
  "native_minecraft": false,
  "real_model": false,
  "human_view_capture": false,
  "strict_certified": false
}
```

这些结果只验证接入协议，不代表 AI 会生存、采矿、屠龙或已经完成公平性验收。

## 从哪里开始改

1. 阅读 [接入指南](docs/HARNESS_API.md)，了解观察引用、模型调用、动作票据与同步屏障。
2. 从 [最小 Harness](sdk/examples/baseline.py) 修改自己的控制结构。它只保留轮次、配额和不透明句柄，不建立世界笔记。
3. 运行 `python3 scripts/verify_harness_api.py` 检查合同兼容性。
4. 使用其他语言或框架时，按 [OpenAPI 协议](api/openapi.json) 对接相同 HTTP 接口。

SDK 也可选用可编辑安装：

```sh
python3 -m pip install -e sdk
```

`CompetitionClient.from_env()` 使用未来由主办方分发的 `RSAGI_API_URL` 和 `RSAGI_TEAM_TOKEN`。本仓库不分发生产凭据；本地演示自动在内存中生成 Mock 凭据，不需要手动配置。

## 协议边界

| 接口 | 用途 |
| --- | --- |
| `GET /v1/session` | 本队身份与公开参数 |
| `GET /v1/round` | 已发布轮次、余额与观察引用 |
| `POST /v1/decisions` | 预扣份额并请求一次模型调用 |
| `GET /v1/decisions/{id}` | 查询操作、usage 与动作票据 |
| `POST /v1/ready` | 提交原始模型动作票据并就绪 |
| `POST /v1/wait` | 不调用模型，积攒额度并就绪 |
| `POST /v1/harness/activate` | 激活模型提出且有来源的受限配置修订 |

每逻辑秒四轮，每轮五 tick。所有队伍完成当前轮后才统一推进。每个 POST 使用幂等键；网络结果不明时复用同一键与请求体，不能重新调用模型试答案。

512 生成 token / 10 秒每份、最多 16 份，以及 1280×720 画面，是当前 Starter 参数，**不是已经冻结的正式比赛规程**。角色调整不增加模型次数或配额。

## 感知与存储规则

- 模型的世界信息只来自对应玩家真实看到的画面、已打开界面和听到的游戏声音，保持不完全信息。
- **允许原版 F3**，各队设置统一；模型从实际 F3 画面读取，不另外提供坐标 JSON。
- 禁止 RAG、外部语义笔记、世界状态查询及传统路径规划器。原始观察和模型原始输出由主办方管理上下文。
- Harness 提交观察引用，不自行上传地图描述、记忆摘要、图片或历史消息；动作提交使用主办方保存的模型票据。

细则见 [玩家感知规则](docs/PLAYER_PERCEPTION.md) 和 [机器可读策略](config/perception-policy.json)。本地 Mock 的引用只用于协议测试，不指向真实游戏画面。真实感知入口尚未接入。

## 当前支持与后续工作

支持：认证与队伍隔离的协议模拟、额度积攒、幂等请求、五 tick 屏障、低层输入 schema，以及有来源的角色/预算配置调整。

尚未提供：真实感知和完整原生动作执行、在线训练地址、任意源码热更新、参赛进程/存储隔离、生成 token 硬封顶、八队 20 TPS 与真实生存验收。配置自组织示例不是这些能力的认证。

参赛 Harness 最终需要向主办方提交完整源码及运行中修订，并授权赛后公开到赛事 GitHub。这个 Starter 的 MIT 许可证与赛事报名时的源码授权要求分别适用；报名细则以之后公布的正式规程为准。

## 开发与反馈

```sh
python3 api/build_spec.py
python3 scripts/verify_harness_api.py
python3 scripts/package_harness_sdk.py
```

当前有 17 项接入测试。测试只使用本机回环 HTTP，禁止外部模型请求或启动 Minecraft。自动测试覆盖 Python 3.9 和 3.12；测试报告和下载包在本地生成。

协议问题或接入建议请通过 [Issues](https://github.com/TheSatchel/rsagi-harness-starter/issues) 提交，贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT](LICENSE)。欢迎参赛团队使用、修改和扩展接入代码。
