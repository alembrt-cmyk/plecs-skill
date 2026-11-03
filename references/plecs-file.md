# `.plecs` 文件格式手册（离线读写 / 生成 / 自检）

`.plecs` 是 **PLECS 私有大括号格式**（非 XML、**LF 行尾**）。掌握它就能在 PLECS 之外
**读元件、批量改参数、生成新模型、做静态自检**——是自动化与"静默失败"防线的地基。

> 行尾实测（406 个官方/workspace 文件）：**LF 403 个**、CRLF 1 个、混合 2 个。
> 官方样板是 LF；PLECS 两种都能读，但**写盘统一用 LF**（`newline='\n'`）。
> 原文"CRLF 行尾"是错的 —— 只有 `workspace\components.plecs` 这类早期库文件才是 CRLF。

## 1. 语法总览

- 语句形如 `Key<空白>value`，value 是三种之一：裸标量（`Ts  1e-5`）、`"..."` 引号串、
  `键 base64 "..."`（base64 通道）。
- 引号串/`base64` 串**可跨行续写**：后续行是纯 `"..."`，语义 = **纯拼接**（无分隔符）。
  取值/写值都要按"一段或多段"匹配，否则会漏段：
  ```
  Value "line1\n" "line2\n" "line3"
  ```
- **多行 C 代码进 `Value` 前必须把真换行换成字面 `\n`**（只转义 `\` 和 `"` 的
  `esc()` 不够），否则报「字符串未闭合」。
- 结构骨架（**键名是 `Schematic`，不是 `Circuit`**——405 个官方文件里 `Circuit {` 出现 **0** 次）：
  ```
  Plecs {
      Terminal { Type Output; Index "1" }        ← 模型级端子（在 Schematic 之前）
      Schematic {
          Component { ... }                      ← 元件
          Connection { ... }                     ← 连线
      }
      ...
  }
  DemoSignature { ... }                          ← Plecs 的兄弟节点（不是子节点！）
  ```
  ⚠ 「模型根」要取 `Plecs` 子块，不是 document root（否则 `DemoSignature` 会被当成模型内容）。
  ⚠ `Subsystem` 内部**还有一层 `Schematic`**（`Subsystem` 元件块内直接就嵌 `Schematic {`，
  没有 `Circuit` 中转）⇒ 组件深度要按 `Component`/`Schematic` 祖先数算，不能按直接子节点数。

### ★ 模型级 `Terminal` vs 画布上的 `Component{Type Output}` —— 两件事，别混

这是最容易搞错的一处：**同名同 Type，但位置和语义完全不同**。

| | 模型级 `Terminal` | 画布 `Component { Type Output }` |
|---|---|---|
| 位置 | `Plecs {` 直下，`Schematic {` **之前** | `Schematic {` 内部 |
| 写法 | `Terminal { Type Output; Index "1" }`（无 Name/Position） | `Component { Type Output; Name "Out"; Position [...]; Parameter{Index}; Parameter{Width} }` |
| 作用 | **决定 RPC `simulate` 返回的 `Values` 列** | 画布上的输出端子（可连线、可给子系统当出口） |
| 缺了会怎样 | `simulate` 返回 `{'Time': [], 'Values': []}`（键在、点 0） | 什么都没有（但如果模型级 Terminal 在，仍能出数） |

官方实测分布（405 个文件）：
- **只有模型级 Terminal、没有画布 Output**：`PLECSRTBoxLib`（24 个）、`TIC2000_Lib`（5 个）、
  `STM32_Lib`（6 个）、`data_logging`（2 个）—— 这些是 code-gen / PIL 库，输出只给宿主用。
- **两者都有**：`buck_converter_with_parameter_sweep`、`rainflow_counting`（各 1 个）。
- **一个都没有**：其余 389 个（含 `rms_value`、`cscript_example_sampled_delay`）——
  所以**官方 demo 返回空是正常的，不能拿来当"MCP 坏了"的证据**。

### ★★ 铁律：文件必须是纯 ASCII（裸中文不是"显示乱码"，是整片乱码）

**实测（2026-11-03，用户报「我打开全是乱码」）**：
```
官方 .plecs（抽查 60 个）：裸非 ASCII 字节 = 0 个
我的第一版（中文注释 + 中文标注）：    140 个  →  PLECS 打开整片乱码
```
更狠的一次核对：扫 263 个官方文件，**非 ASCII 字节总计 0**。

⇒ **PLECS 不把 `.plecs` 当 UTF-8 读。** 任何非 ASCII 内容必须走 base64 通道；
文件里除 base64 段外，**其余字节必须 < 128**。中文注释、中文 `Annotation`、
中文元件 `Name` 直接裸写 = 打开就是乱码（不是"参数页显示乱码"那种纯显示层问题）。

**生成器末尾必须加硬关卡**（写盘前 raise，别指望人工检查）：
```python
try:
    body.encode('ascii')
except UnicodeEncodeError as e:
    raise SystemExit('!! .plecs 里有非 ASCII 字符，PLECS 会乱码：%r' % (e,))
io.open(out, 'w', encoding='ascii', newline='\n').write(body)
```

**验收（逐字节，别用编辑器看）**：
```python
bad = [(i, b) for i, b in enumerate(open(p, 'rb').read()) if b >= 128]   # 必须是 []
```

### base64 修饰符（多字节安全的唯一通道）

- 非 ASCII 文本一律写成 `键 base64 "…"`（内容是 **UTF-8** 字节的 base64）。
  `base64` 是**任意字符串键都能用的修饰符**，不限于 `Name`。
- 反向踩坑：**裸引号里放 UTF-8 中文**时，若该位置恰好被当作属性解析，PLECS 会按
  **单字节（CP1252）**解释 ⇒ 掩码参数页显示 `ä¸ç¸µ…` 乱码（这种是纯显示层，仿真不受影响）。
  但**注释/Annotation 里的中文不是这个待遇 —— 那是整片乱码**。两者别混。
  `Name`/`MaskType`/`Prompt`/`MaskDescription`/`InitializationCommands` 全部走 base64。
- **注意** `Declarations/StartFcn/OutputFcn/UpdateFcn` 里的代码字符串**不是 base64**，
  是带转义引号的普通字符串（所以导出时要按普通串解），**且同样不能含裸非 ASCII**
  （中文注释写进 C 代码 = 一样乱码/编译异常）。

## 2. 元件扫描：必须用「归属法」，不能用花括号配平

**配平法只能拿到顶层元件**——典型模型里 24 个 MOSFET、3 个变压器全在 `Subsystem` 内部，
配平法把他们**整块吞掉、一个都扫不到**，且**不报错**（典型假阴性，比报错更危险）。

正确做法（顺序读行、与嵌套层数无关）：

1. 遇 `^\s*Component\s*\{$` → 开一个新元件记录；
2. 其后**第一个** `Type`、`Name` 归它；后每个 `Variable "x"` + 紧邻的
   `Value "y"` 也归它，直到下一个 `Component {`。

关键字段：
- `Component {` 后几行就是 `Type` / `Name`（`Name` 可能是 base64）；
- 参数一律形如 `Parameter { Variable "x" / Value "y" / Show off }`；
- **参数值可能是变量名而不是数字**（如 `Ron` 的 Value 是 `"Rgon"`）。
  判等要按**数值**比较；遇到非数值字符串就**当作"需要改"**，别用纯字符串比较。

## 3. 批量改参数脚本的要求（幂等 + 安全）

- **幂等**：重复跑结果相同；
- **默认 dry-run**：先打印计划改动，`--apply` 才写盘；
- **写盘前自动备份**：`<file>.bak-<用途>-<时间戳>`；
- **写盘前先确认 PLECS 没在运行**（若在运行，明确告知用户"关掉重开、期间不要保存"——
  PLECS 一保存就把补丁覆盖掉）；
- **只重写目标语句所在行**，保留 CRLF/缩进/列对齐/base64 76 字分段；
- 写后**回读校验**（diff 行数应该恰好等于预期改动数）。
- 改完**必须关掉 PLECS 重开**（模型/块对象被缓存）。
- 文件名 ≠ 模型 `Name` 时会撞车：`build_xxx(name=...)` 必须把内部 `Name` 一起改掉，
  否则多开同名模型时 `load`/`simulate` 会跑到别的实例上，二分结论全是假的。

## 4. 连线 / 端子 / 标签（画乱图与报错的总源头）

- **一个源端子只能有一条 `Connection`**（多个 → 诊断 `Cannot create connection to terminal N`，
  或**静默只保留第一条**）。
- ★★ **扇出 = 一条 `Connection` + 多个 `Branch{}`**（`Branch` 内含 `DstComponent/DstTerminal`）：
  ```text
  Connection { Type Signal
               SrcComponent "Sum2"  SrcTerminal 1
               Points [150, 215]
               Branch { DstComponent "Product1"  DstTerminal 3 }
               Branch { DstComponent "Fcn"       DstTerminal 1 } }
  ```
  **官方证据**：356 个官方 `.plecs` 共 32324 条 `Connection`，其中 **6232 条**是这个写法
  （`Branch{}` 里有 `DstComponent`）；只有 10 条是"Branch 只有 Points、无 Dst"的纯折线。
  ⇒ `Branch` **既能装途经点 `Points`、也能装真正的目的地**，是官方扇出语法。
  ⚠ 旧版本技能写的"Branch 是折线途经点、扇出必须用 Goto/From" **是错的**，已更正。
  两种扇出怎么选：**就近多分用 `Branch`**；**跨区域/跨图用同名 `Label`（电气）或 `Goto/From`（信号）**。
- **电气扇出用同名 `Label`；`Goto/From` 只能走信号**。给电气端口接 Goto →
  `Cannot create connection to terminal 1 of …/Goto`。
- **`Connection.Type` 的 `Wire` / `Signal` 不能混**：信号口用 `Wire` 连 `Goto` 报的是
  `Unconnected terminals overlapped by other elements`（像排版问题，实为类型问题）。
- `Label` / `Goto` 的端子朝向由 `Direction` 决定（right=端子朝左、left=朝右、
  down=朝上、up=朝下）；让标签"迎着来线"才能消掉小台阶。
- 连线别跨图拉长对角线（会撞「悬空端子被导线压住」）；布局要紧凑，跨图信号用 Goto/From。
- Goto/From 两侧 `Visibility` 都要 = 2，且**不要 LabelPosition**（一侧 1 一侧 2 报
  `No matching Goto block found`）。

## 5. Subsystem 封装五条铁律

见主文件同名节（端子 Index 连续编号 / Position 落在 Frame 外 5 单位 /
`Subsystem.Direction=up` / 电气用 Label / Wire-Signal 不混）。补充：
- **改掩码参数的 RPC 路径 = `模型名/子系统名`**，值必须传**字符串**。
- 排端子语义最有效的方法：同一模型并排摆 8 个只改一个变量的小方块，**一次截图全部读出**；
  别逐次猜。

## 6. 静默失败自检清单（改完生成器**必跑**）

把模型 dump 成 `(组件, 端子)` 元组集合，做三查：

1. 每个组件的端子都出现过（查悬空）；
2. `Goto` / `From` 名称两两配对（查孤对）；
3. 无"幽灵组件"（定义但未接线、或名称撞车）。

再加三条全局检查：
- **顶层出数**：必须有模型级 `Terminal { Type Output; Index "1" }`（在 `Schematic {` 之前），
  否则 RPC `simulate` 返回 `{Time: [], Values: []}`（键在、点 0）。
  ⚠ 只放画布上的 `Component { Type Output }` **不够** —— 实测就是这样返回空的。
- **纯 ASCII**：`sum(1 for b in open(p,'rb').read() if b >= 128) == 0`，否则打开乱码。
- **子系统的信号口**：端口宽度列表 `NumInputs`/`NumOutputs` 与 Demux/Mux 宽度对账
  （`Width` 不一致时 PLECS 有时不报错，直接把多余通道静默丢弃或补 0）。

## 7. 验证"UI 显示"的手段（掩码/对话框）

`close` 全部同名模型（`load` 只切焦点不重载磁盘，残留实例显示旧内容）→ `load` →
窗口最大化置顶 → 截屏 → **先用纯色 `(255,255,204)` 框出画布**→ 在画布内做暗像素
行/列投影得方块 bbox → `SetCursorPos` + 双击中心 → 按标题等对话框窗口截图。
（像素投影要限定在画布内，否则窗口边框会污染结果。）

抓图通用坑：
- `PrintWindow(PW_RENDERFULLCONTENT)` 在被遮挡时会抓到**别的窗口的内容**——不可信；
- `SetForegroundWindow` 从后台进程无效；要 `ShowWindow(SW_MAXIMIZE)` +
  `SetWindowPos(HWND_TOPMOST)` + 敲一下 Alt 解锁，再 `ImageGrab.grab(bbox=窗口矩形)`；
- 判断"画面是否乱"用**像素统计**而不是肉眼：统计"覆盖 >50% 画布高/宽"的直线数量，
  干净 = 0 条竖线 + 1 条横线（画布上边框）。

## 8. `.trace` 波形文件格式（已定案）

大端裸二进制、无魔数：

```
i32 ver(=2) | i32 nTrace | nTrace×{str name, i32 nSig, nSig×str}
| i32 nLabel | nLabel×str
| 文件级唯一时间基: 5×i32 0 + i32 nPoints + 2×i32 0 + (nPoints-1)×f64
| 逐曲线: [1~8B 前缀][f64 ymax][f64 ymin] 12B0 + i32 nPoints + 8B0 | (nPoints-1)×f64
```

- `str` = i32 字节长 + **UTF-16BE**。
- ★ 曲线块头长度有 **8B 抖动** ⇒ 必须以尾部 `12B0 + 自描述点数 + 8B0` 为**锚点**
  + 回溯到「正好吃到文件末尾」。
- ★ 上一条曲线的 `ymin` 若是整值（如 `-3.0` = `0xC008000000000000`），其尾随零字节
  会和本块 12B 零连成一片 → 产生偏 8 字节的**假锚点**。
  修法：**点数 n≥2 的候选优先，n==0 的模糊候选排到最后**。
- `ymax/ymin` 偏移不固定（40/32/48 都可能）→ 依次试并取第一组
  「有限、量级正常、ymax≥ymin」的；这只影响展示，统计量一律按数据算。
- ★ **`SaveTraces` 会自动追加 `.trace` 后缀**（传 `…/ssfinal` → 落地 `ssfinal.trace`）。
- ★ 解析出的字段名是 `.v`/`.t`（不是 `.y`）；借助逐曲线 `trace_label`/`signal` 认通道。

## 9. `.plecs` 里高频出现的错误诊断

| 报错 | 真因 | 修法 |
|---|---|---|
| `No port for terminal N` | 端子 `Index` 编号撞车（不连续/从 1 重开） | Index 连续编号；电气 Port 后信号口从 5 起 |
| `Unconnected terminals overlapped by other elements` | `Connection.Type` 混用（Wire vs Signal），**不是**排版问题 | 对照两模型 dump `(类型,组件,端子)` 集合差 |
| `Cannot create connection to terminal N` | 同一端子给了多个 `Connection` | 扇出改 Goto/From（信号）或同名 Label（电气） |
| `Cannot create connection to terminal 1 of …/Goto` | 给电气端口接了 Goto | 电气用 Label |
| `No matching Goto block found` | Goto/From 两侧 `Visibility` 不一致（应都为 2）或有 LabelPosition | 统一 Visibility、去掉 LabelPosition |
| `字符串未闭合` | `Value "..."` 里塞了真换行 | 真 `\n` → 字面 `\n` |
| **打开模型"全是乱码"**（连元件名/注释都烂掉） | 文件里有**裸非 ASCII 字节**（中文注释、中文 Annotation、中文 Name） | 全改英文；写盘 `encoding='ascii'` + `encode('ascii')` 关卡；验收 `b>=128` 计数为 0 |
| 掩码对话框显示 `ä¸ç¸µ…`（**只有属性页乱，模型本身正常**） | 裸引号里放 UTF-8 中文，被按单字节 CP1252 解释 | 改 `键 base64 "…"`（UTF-8） |
| 仿真"成功"但某路输出恒 0 | 静默失败（漏连/端口宽度错/无顶层 Terminal） | 跑第 6 节自检清单 |
| 改了 `.h` 结果半点不变 | 编译缓存未失效 | 见主文件「编译缓存」节 |
| 启动弹「Model Recovery」卡住 RPC | 上次被强杀（`taskkill /F`）留下 autosave | 走 `close` 释放；别强杀 |