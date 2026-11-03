# 冷启动接入 PLECS（全新环境，从零到能跑）

目标：在一台**没装过任何东西**的机器上，让模型能真正驱动 PLECS ——
读模型、改参数、跑仿真、拿波形。按顺序做，每一步都有**验收判据**，别跳。

## 0. 前置：PLECS 本体

1. 装 PLECS（Standalone 版；本项目实测 **4.7.5**，装在 `D:\PLECS`）。
2. 打开一次，确认能进主界面、能新建模型。
3. 找到元件库文件（后文要用）：
   ```
   <PLECS安装目录>\components.plecs     ← 全部元件 Type / 参数的权威定义
   ```
   本机 = `D:\PLECS\components.plecs`（7.5 MB，5597 个元件，纯 ASCII）。

> PLECS 版本差异会影响 RPC 命令与 `.plecs` 字段（4.7.5 实测：`scope` RPC 只有 5 个命令）。
> 版本不对时，先按 4.7 的行为试，再逐条实测校正，别照抄文档。

## 1. 开 RPC（必须，否则一切自动化都不可能）

**PLECS 的 RPC 接口默认关闭**（官方原文：*"The RPC interface in PLECS is disabled by default."*）。

- 菜单 `Preferences → Simulation → 勾选 Start XML-RPC server`
- 默认端口 **1080**，界面右下角会显示端口号
- **只接受本机连接**（127.0.0.1），不能远程

**验收**（用系统 Python 即可，无需第三方库）：

```python
import xmlrpc.client
p = xmlrpc.client.ServerProxy('http://localhost:1080/RPC2', allow_none=True)
print(p.plecs.statistics())        # 返回版本 + 已打开模型列表
```

- 成功：`{'version': [4, 7, 5, '...'], 'models': [...]}`
- 失败：`ConnectionRefusedError: [WinError 10061] 由于目标计算机积极拒绝`
  ⇒ **RPC 没开**（90% 是这个），或端口不是 1080。先回第 1 步，别怀疑别处。

## 2. 接 MCP（推荐；不接也能用第 3 档兜底）

MCP 服务器让模型拿到 `plecs_*` 工具（比手写 xmlrpc 稳，且自带 `.trace` 解析）。

### 2a. 先看本机有没有现成的

```
~/.workbuddy/mcp-servers/plecs/          ← 有 server.py 就是已装
```
并检查 `~/.workbuddy/mcp.json` 的 `mcpServers.plecs` 是否存在。

### 2b. 没有就从 GitHub 装

```bash
# 仓库（已开源，tag v0.3.2）
git clone https://github.com/alembrt-cmyk/plecs-mcp.git ~/.workbuddy/mcp-servers/plecs
cd ~/.workbuddy/mcp-servers/plecs
python -m venv .venv
.venv/Scripts/python.exe -m pip install -U pip
.venv/Scripts/python.exe -m pip install "mcp[cli]>=1.6.0,<2" pyyaml
```

> ⚠ **不要 `pip install mcp==2.x`** —— 2.x 把 `FastMCP` 改名 `MCPServer` 且 API 变动，
> 本项目锁 1.x（`pyproject.toml` 已声明 `mcp[cli]>=1.6.0,<2`）。
> 内网代理挡 github 时，可加前缀 `https://ghfast.top/` 再 clone。
> 也可以直接 `pip install <whl>`：仓库打了个 whl，但**必须确认它含 4 个 py 模块**
> （旧的打包缺陷会让 whl 里只有无关目录 —— 装完 `python -c "import server"` 验证）。

### 2c. 写 mcp.json

`~/.workbuddy/mcp.json`（**注意不是** `~/.workbuddy/.mcp.json`）：

```json
{
  "mcpServers": {
    "plecs": {
      "command": "C:\\Users\\<你>\\.workbuddy\\mcp-servers\\plecs\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\<你>\\.workbuddy\\mcp-servers\\plecs\\server.py",
               "--transport", "stdio"],
      "env": {
        "PLECS_HOST": "localhost",
        "PLECS_PORT": "1080",
        "PLECS_TIMEOUT": "15",
        "PLECS_LONG_TIMEOUT": "600",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

要点：
- `command` 用 **venv 的 python 绝对路径**（系统 python 常缺 `mcp` 包）。
- `PLECS_LONG_TIMEOUT` 是长仿真通道（默认 600 s）；短命令用 `PLECS_TIMEOUT`（15 s）。
- 改完 mcp.json 后**去连接器管理页点"信任"**，否则工具不出现。

### 2d. 验收（三连，缺一不可）

```
1) plecs_list_methods        → 能列出 RPC 方法
2) plecs_load  <模型路径>     → 返回 0 / 模型 id
3) plecs_simulate <model>    → 返回 {Time, Values}（顶层有 Outport 时）
```

`simulate` 返回 `{'Time': [], 'Values': []}` **不代表失败** —— 见第 4 节。

## 3. 不装 MCP 也能干（raw xmlrpc 兜底，8 行）

```python
import xmlrpc.client, json
P = xmlrpc.client.ServerProxy('http://localhost:1080/RPC2', allow_none=True)

P.plecs.load(r'D:\path\model.plecs')
print(P.plecs.get('model'))                                  # 读参数（[键,值] 列表）
out = P.plecs.simulate('model', {'SolverOpts': {'TimeSpan': 0.01}})
print(type(out), len(out.get('Time', [])) if isinstance(out, dict) else out)
P.plecs.close('model')                                       # 释放（别强杀进程）
```

这条通道**必须**知道的三件事：
1. **时长键是 `SolverOpts.TimeSpan`**（`StopTime` 已废弃）。
2. **同一连接不可并发**：仿真进行中再发别的命令会 `CannotSendRequest`。
   要查状态就**另开一个 `ServerProxy`**。
3. **仿真运行时绝不可 `close`**，否则把 RPC 服务搞死。

## 4. 为什么 `simulate` 有时返回空

顶层**没有模型级 Output 端子**时，`simulate` 恒返回 `{'Time': [], 'Values': []}`（键在、点 0）。

两种 Terminal 别混（详见 `plecs-file.md` 第 1 节）：

| | 模型级 `Terminal`（`Plecs {` 直下，`Schematic` 之前） | 画布 `Component { Type Output }` |
|---|---|---|
| 作用 | **决定 `simulate` 返回的 Values 列** | 画布上的输出端子（可连线/给子系统当出口） |
| 缺了 | 返回空 | 不报错，但若模型级在，仍能出数 |

⇒ **想用 RPC 拿数据，必须加模型级 `Terminal { Type Output; Index "1" }`。**
官方 405 个文件里两者都有的只有 2 个，其余 389 个一个都没有 ——
**所以"官方 demo 也返回空"是正常的，不能当"MCP 坏了"的证据。**

拿不到数组时的替代路径：`scope.SaveTraces`（自动加 `.trace` 后缀）→ 离线解 `.trace`
（MCP 的 `plecs_trace_read` 直接出逐曲线 min/max/avg/pp/rms）。

## 5. 常见失败对照表

| 现象 | 真因 | 修法 |
|---|---|---|
| `WinError 10061 积极拒绝` | RPC 没开 / 端口不对 | Preferences 勾 Start XML-RPC server；确认 1080 |
| MCP 工具列表里没有 `plecs_*` | mcp.json 写错 / 未点"信任" / venv 缺 `mcp` 包 | 检查 3 处；`python -c "import mcp"` 验证 |
| `simulate` 返回 `Time: []` | 顶层无模型级 Output Terminal | 加 `Terminal { Type Output; Index "1" }` |
| `CannotSendRequest` / `ResponseNotReady` | 同一 RPC 连接并发 | 另开 `ServerProxy` 查状态 |
| 仿真卡住、后续命令全超时 | 仿真仍在跑（`simulate` 阻塞） | 等它跑完；查 `statistics().models[*].state` |
| 下次启动弹「Model Recovery」且 RPC 卡死 | 上次 `taskkill /F` 强杀留下 autosave | **绝不强杀**；用 RPC `close`；弹框手动关掉再重试 |
| 改完 `.h` 仿真结果不变 | C-Script 编译缓存（只哈希 Declarations 字符串） | 关模型重开 → 改 Declarations（哪怕加注释）→ Ctrl+S |
| 打开模型整片乱码 | `.plecs` 里有裸非 ASCII 字节 | 全改英文；写盘 `encoding='ascii'` |

## 6. 最小自证：30 秒确认整条链路通

```bash
# 1) 造一个最小可跑模型（用技能自带的 builder）
python scripts/plecs_builder.py --demo -o /tmp/mini.plecs
# 2) 起 PLECS 并跑（同一进程内，别分开）
```
模型内容见 `references/minimal-model.md`（源 + RC + Scope + 模型级 Output），
验收：`simulate` 返回非空 `Values`，且 `Values` 的曲线是预期正弦/指数。

链路全绿之后，再照 SKILL.md 的「从零到跑通」节建真实拓扑。