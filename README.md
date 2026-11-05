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
cp start.sh.example start.sh   # 填入 QQ_APPID / QQ_SECRET / CARD_BASE_URL
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

云防火墙放行 **TCP 8420**（战绩卡片图片服务，QQ 平台来抓图用）。

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
- 同一回放使用分片锁保护下载与缓存写入。图片文件使用随机唯一名称，串行清理，最多保留 50 张；未配置 `CARD_BASE_URL` 时直接回复文字，跳过卡片生成。
- 群聊和私聊接收日志不记录用户标识或消息正文；SDK 诊断存档只保存返回状态及是否包含内容，不保存原始登录响应。账号自动登录所需的 `userdata/accounts/*/token.json` 仍是敏感凭据文件，应限制部署目录访问权限。

此前已经生成的日志和 SDK 存档不会被本次修改清除，部署时请按自己的留存要求处理旧文件。

### 本地回归验证

安装 `requirements.txt` 后，在项目根目录运行：

```bash
python -m unittest discover -s tests -v
```

测试使用模拟 QQ API 和 SDK 响应，无需设置 QQ 凭据，不会发送短信、连接游戏服或向 QQ 发送消息。测试覆盖并发回复身份隔离、限流及取消、文字回退、日志脱敏、图片并发保存、SDK 存档脱敏、共享会话互斥和发送序号。

尚需真实部署联调：QQ 图片抓取与被动回复时限、游戏登录和观战行为。战绩缓存刷新、回放总体时限和缓存容量、绑定码防护及回放解析模块拆分留待后续优化。
