# 星趴 QQ 机器人（astral-party-qqbot）

星引擎 Party / 吉星派对（Astral Party）战绩查询 QQ 群机器人。多用户模式：每个群友私聊登录自己的游戏账号，群聊各自查战绩，全程自助。

## 功能

| 指令 | 场景 | 说明 |
|---|---|---|
| `/登录 手机号` / `/验证码 码` | 私聊 | 登录自己的游戏账号（凭据按 QQ 用户隔离存放） |
| `/绑定` | 群→私聊 | 一次性绑定码关联群身份（10 分钟有效） |
| `/我的` | 群/私聊 | 战绩卡片图（PIL 渲染：场次/胜率/近10场角色·伤害·转账·胜负） |
| `/查 UID` | 群/私聊 | 查任意玩家基础信息（好友协议，无需对方登录） |
| `/回放 16位回放号` | 群/私聊 | 单局四人详细战报（免登录） |
| `/手牌 观战码` | 群/私聊 | PVE 对局实时四人手牌快照（官方观战协议） |
| `/帮助` | 任意 | 菜单 |

## 部署

要求：Ubuntu 20.04+/Debian，Python 3.10+，1G 内存即可（2G 舒适）。

```bash
git clone https://github.com/<你的用户名>/astral-party-qqbot.git
cd astral-party-qqbot
pip3 install -r requirements.txt
sudo apt install -y fonts-noto-cjk
cp start.sh.example start.sh   # 填入 QQ_APPID / QQ_SECRET；CARD_BASE_URL 可选
```

QQ 开放平台创建机器人（需要个人实名认证以上），开启 C2C/群@消息权限。

systemd 服务（`sudo systemctl edit --full astral-bot`，或自建 unit）：

```ini
[Service]
Type=simple
WorkingDirectory=/home/ubuntu/astral-party-qqbot
ExecStart=/usr/bin/bash /home/ubuntu/astral-party-qqbot/start.sh
Restart=always
[Install]
WantedBy=multi-user.target
```

默认通过 QQ 富媒体接口直传小于 5 MB 的卡片，无需开放入站端口。若配置 `CARD_BASE_URL` 使用 URL 上传，需让 QQ 平台可访问该地址，并在使用内置 HTTP 服务时放行 **TCP 8420**。

首次启动后：`/登录` → `/验证码` → 群里 `/绑定` 即可用。

## 架构

- `qq_bot.py`：QQ 接入层（botpy），文字+富媒体图片被动回复
- `bot_core.py`：多账号管理（凭据隔离 userdata/accounts/<openid>/）、10 秒心跳保活、5 分钟自愈重登
- `bot_ext.py`：查询/回放/观战协议封装
- `bot_viz.py`：战绩卡片渲染（PIL + Noto Sans CJK）
- `main_ref.py`：原项目 main.py，回放统计逻辑运行时提取执行（游戏更新时替换它即可）
- `astral/` + `assets/`：协议库与数据表，来自 AstralParty_Dex（MIT）

## 多用户与"查询服务号"

bot 可指定一个常驻"查询服务号"（userdata/service.json，值为该账号持有者的 QQ openid，可用任意字符串作虚拟槽位）：`/查`、`/手牌` 优先借它的会话，避免打扰普通用户。不配也能用（自动借任一在线会话）。

## 致谢与许可

- 本仓库代码：MIT（见 LICENSE）
- `astral/`、`assets/` 源自 [AstralParty_Dex](https://github.com/)（MIT）
- QQ 接入依赖 [qq-botpy](https://github.com/tencent-connect/botpy)
- 观战协议报文定义来自游戏客户端，仅供学习交流

## 免责声明

本项目为个人学习作品，与游戏官方及腾讯无关。使用游戏非官方协议可能存在账号风险，**使用风险自负**；请勿用于商业用途或违反游戏服务条款的行为。机器人处理的用户凭据仅存放在部署者本机，部署者需对数据安全负责。


## 并发与诊断（本轮优化）

- 每条消息独立携带用户身份、回复文字和图片，不再通过全局变量传递。
- 同步查询与卡片生成移到后台线程；单个机器人进程最多同时处理 4 条指令，满载时提示稍后重试，不积压任务。请求被取消时，后台工作完成前仍占用名额。
- 账号状态操作、查询和观战共用可重入锁，防止共享连接串包。当前这些游戏业务操作会串行执行；回放下载和图片渲染在锁外运行。心跳独立发送，发送序号与写入连接的顺序保持一致。
- 同一回放使用分片锁保护下载与缓存写入。图片文件使用随机唯一名称，串行清理，最多保留 50 张；未配置 `CARD_BASE_URL` 时也会生成卡片并直传；URL 上传失败时尝试直传。
- 群聊和私聊接收日志不记录用户标识或消息正文；SDK 诊断存档只保存返回状态及是否包含内容，不保存原始登录响应。账号自动登录所需的 `userdata/accounts/*/token.json` 仍是敏感凭据文件，应限制部署目录访问权限。

此前已经生成的日志和 SDK 存档不会被本次修改清除，部署时请按自己的留存要求处理旧文件。

### 本地回归验证

安装 `requirements.txt` 后，在项目根目录运行：

```bash
python -m unittest discover -s tests -v
```

测试使用模拟 QQ API 和 SDK 响应，无需设置 QQ 凭据，不会发送短信、连接游戏服或向 QQ 发送消息。测试覆盖并发回复身份隔离、限流及取消、文字回退、日志脱敏、图片并发保存、SDK 存档脱敏、共享会话互斥和发送序号。

尚需真实部署联调：QQ 图片抓取与被动回复时限、游戏登录和观战行为。回放总体时限和缓存容量、绑定码防护及回放解析模块拆分留待后续优化。


## 战绩查询（总览 / 近期 / 角色）

| 查询内容 | 自己的账号 | 任意玩家的公开档案 |
| --- | --- | --- |
| 总览 | `/我的` | `/查 1234567` |
| 近期 | `/我的 近期` | `/查 1234567 近期` |
| 单角色 | `/我的 角色 芬妮` | `/查 1234567 角色 芬妮` |

群聊查询自己的账号需要先绑定；公开 UID 查询不要求被查询者登录。两种查询均尝试返回战绩卡片，不要求配置公网图片服务；生成或发送失败时提示降级为文字。

- `stats_query.py` 负责查询流程与输出选择，`bot_ext.py` 负责协议数据适配和回放指标补齐。
- `stats_report.py` 负责统一样本、角色与模式汇总、文本格式，`bot_viz.py` 只负责根据同一份报表绘制图片。
- 查询最多使用协议返回的前 10 场；角色筛选只在这批样本中进行，不代表角色生涯战绩。公开战绩列表缺少对局时间，按协议返回顺序展示。
- 公开协议没有累计场次、累计胜率、获赞、拥有角色数和回放号，这些字段显示 `—`。结果未知不计入胜率，缺失的伤害/转账不按零参与均值；卡片列出各指标有效样本数。
- 在线账号查询采用 30 秒刷新间隔。刷新失败或展示权限使数据不完整时保留已有档案，并明确提示包含缓存。支持北京时间今日筛选；尚无完整历史时间范围查询或 PR 评分数据。

查询视图划分、取数与绘制分离的设计参考 [Kokomi_Bot 查询命令](https://github.com/SangonomiyaKoko/Kokomi_Bot/blob/main/docs/command.md) 和[渲染流程文档](https://github.com/SangonomiyaKoko/Kokomi_Bot/blob/main/PNG.md)（参考提交 `587e041`）。本项目针对星趴协议独立实现；继续使用白底数据布局。


## ATP 指令（默认 PVE）

| 指令 | 含义 |
| --- | --- |
| `/atp me` | 自己最近记录内的 PVE 总览 |
| `/atp me recent` | 今日北京时间 00:00 至次日 00:00 内的 PVE 战绩 |
| `/atp me char 芬妮` | 最近记录内芬妮的 PVE 战绩 |
| `/atp me pvp` | 最近记录内的 PVP 战绩 |
| `/atp me pvp recent` | 今日 PVP 战绩 |
| `/atp me all` | 全部模式，档案累计与最近样本分开显示 |
| `/atp 1234567` | 公开 UID 的 PVE 战绩 |
| `/atp 1234567 pvp char 芬妮` | 公开 UID 的角色 PVP 战绩 |
| `/atp help` | 指令帮助 |

`pve/pvp/all` 可放在 `recent` 前后；角色名称放在 `char` 后，模式参数应放在 `char` 前。中文 `/我的`、`/查 UID` 保留，默认也改为 PVE；`近期`/`今日` 均对应北京时间今日。

PVE 只包括协议 `mapType=2/4`（合作挑战），PVP 为 `mapType=1`。未知模式和限时玩法不猜测归类，使用 `all` 才会纳入。筛选在下载回放之前执行，避免下载无关模式/日期的回放。

**今日结果的范围**：协议目前只提供最近 10 条可用记录，按 PVE、日期或角色筛选后可能少于 10 条；这不是完整的当日历史。所有输出都标注这一限制。无时间或时间无效的记录不归入今日，并显示被排除数量。公开 UID 协议没有时间，`recent` 会返回能力说明，不会伪报为“今日 0 场”。

默认 PVE/PVP 卡片使用筛选样本的指标，不将档案中未分模式的累计数据当作 PVE/PVP 生涯数据。北京时间使用固定 UTC+8，与部署服务器时区无关。


## 卡片变成文字、伤害/转账全为缺失时

已修复旧版将回放补数放在图片开关内的错误：`CARD_BASE_URL` 未配置时，旧版同时跳过卡片生成和回放指标解析。现在补数与输出格式独立，文字降级也保留已解析的伤害/转账。

小卡片按 [QQ 群聊富媒体上传](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_files.post.html) 和[单聊富媒体上传](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_files.post.html)的 `file_data` 方式直传。适配器复用 qq-botpy 的鉴权 HTTP 层（1.2.1 的文件上传封装只接受 URL），不向群消息接口传 `file_image`。配置 `CARD_BASE_URL` 时先试 URL，失败后尝试直传；不会把缺少 `file_info` 的响应当作上传成功。直传按 base64 请求体保守限制在 5 MB 内，超限且无可用 URL 时回退文字。

字体仍需安装：Ubuntu/Debian 执行 `sudo apt install fonts-noto-cjk`，然后重启机器人。卡片图片服务“已启动”只说明端口监听成功，不代表实际进程已设置 URL，也不代表发图成功。

在实际部署的项目目录内执行（请使用服务所用的 Python/虚拟环境）：

```bash
sudo python3 tools/diagnose_cards.py --service astral-bot
sudo journalctl -u astral-bot -n 500 --no-pager | grep -E '\[cards\]|\[stats\]|\[reply error\]'
```

诊断脚本读取 systemd MainPID 的实际环境，只输出关键配置是否存在、URL 格式是否合法、工作目录、当前检出提交和本地字体/绘图检查；不输出 URL、QQ_SECRET、登录票据、用户标识或消息正文，不调用 QQ/游戏接口。当前检出提交与本地依赖不等于运行进程已加载的代码，更新后需重启服务。

新日志区分 `stage=render`、`stage=url_upload`、`stage=upload`、`stage=send`，并保留 QQ 数字错误码。`replay_summary` 区分 `no_id`（无回放号）、`invalid_id`（格式无效）、`failed`（下载/解析异常）、`no_stats`（无对应指标）、`ok`。无回放号与补数失败也会在文字/卡片中标注。
