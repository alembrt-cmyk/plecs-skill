# PLECS C-Script 排错手册

## 症状 → 原因 → 解决

| 症状 | 原因 | 解决 |
|---|---|---|
| 积分值 / 计数器明显偏大，随步长变化而变 | 离散状态在 `Output` 里更新。Output 在一个主步长内可能被调多次，累加被执行了多次 | 所有 `DiscState` 更新挪到 `Update`；`Output` 里只做计算和写输出 |
| 输出响应慢半拍，采样频率降低后系统失稳 | 控制律写在 `Update`，输出滞后一个采样周期（update 在 output 之后调用） | 把控制律移到 `Output`，`Update` 只保留 `ik_1 = ik;` |
| 报代数环（algebraic loop）警告，或 `Output` 里读到的输入是旧值 | 在 `Output` 里读输入但没勾 **Input has direct feedthrough** | Setup 里勾上。这个标志同时影响模块执行顺序 |
| 仿真中止，报 NextSampleHit 相关错误 | 用了 `-2` 采样但没给 `NextSampleHit` 赋值，或赋的值 ≤ 当前时间 | `Start` 里初始化 `NextSampleHit = NEVER`(`DBL_MAX`)；每次 Output/Update 都要设成大于当前时间的值；周期末设回 `NEVER` 交给固定拍 |
| 模块被疯狂调用 / CPU 占用异常 | `-2` 状态下 `NextSampleHit` 停留在当前时刻附近 | 状态机最后一个状态务必 `NextSampleHit = NEVER` |
| 波形出现毛刺、求解器步长被压得很小 | 输出在 minor step 发生了跳变或尖锐折点 | 用 `IsMajorStep` 门控输出更新；或注册 `ZCSignal` 让求解器精确定位跳变 |
| 零穿越事件检测不到 | 没在 Setup 里设置 `Number of zero-crossings`，或没给 `ZCSignal` 赋值 | 设置个数并在 `Output` 中赋值（大小步长都要更新） |
| 连续状态改不动 | 在 minor step 修改了 `ContState` | `ContState` 只能在 major step 改；导数一律在 `Derivative` 里通过 `ContDeriv` 写 |
| 代码逻辑"时间应该递增"的假设出错 | 求解器在同一主步长内多次调用 Output，minor step 期间时间会前后跳 | 不要假设单调；需要"每步恰好一次"的代码放 `Update` |
| 参数值读出来不对 | `ParamRealData(i,j)` 的 j 是**线性索引**，多维数组需要自己换算 | `idx = row + numRows*(col + numCols*page)`；维度用 `ParamNumDims`/`ParamDim` 查 |
| `Parameter index 0 out of range (vector is empty)`（在 start 函数里） | Setup 的 **Parameters 框根本没填**，是个空向量，代码却调了 `ParamRealData(0,...)` | 在 Parameters 框把参数列出来，逗号或换行分隔，如 `fn, fs, k_sogi, kp, ki`。若填的是变量名，还要确认这些变量在子系统掩码/上层有定义，否则会报另一条 "undefined variable" |
| `DiscState(i) out of range` 之类状态越界 | Setup 里 `Number of disc. states` 设得比代码用到的最大索引小 | 状态个数与代码对齐（改算法结构时最容易漏，比如 SOGI 从 7 个状态加到 9 个） |
| 报错行号是负数（如 `line -55`） | 用了 `#include` 外部文件，PLECS 的行号是相对整个生成文件的偏移 | 别按行号定位，看报错文字；要定位的话临时把 include 的内容展开贴回窗口跑一遍 |
| `DiscState(i) out of range`，或仿真跑起来数值诡异 | **把状态个数填进了 cont. states 而不是 disc. states**（两个框挨着，极易填反） | 离散算法（数字控制、SOGI、状态机、计数器）一律填 disc. states；cont. states 只在用 `ContState`/`ContDeriv` 解微分方程时才非零，否则求解器会对一堆从没赋过导数的状态做无意义积分 |
| 锁相成功，但 θ 比某相电压滞后/超前固定 90° | **不是 bug，是相位参考约定**。θ 锁的是 αβ 空间矢量角度，不是某相电压相位。PLECS 正弦源默认 A 相 = sin，代入 Clarke 得 vα=A·sin(ωt)、vβ=−A·cos(ωt)，矢量角 = ωt−90° | 不做并网控制就不用改（环路自洽）。要 θ=ωt 的话：把 A 相源初相改 +90°（cos 约定），或在输出处减 π/2 并重新折返到 [0,2π)。**验证锁相别拿 θ 对比相电压，拿 α⁺ 和该相电压画在一起，应完全重合** |
| 报错信息是乱码或崩溃 | `SetErrorMessage` 的 msg 不是静态内存 | 字符串必须是字符串字面量或 static 数组；调用后跟 `return` |
| 访问 `&OutputSignal(0,0)+1` 结果错误 | 输入输出信号不在连续内存中 | 禁止指针算术，逐个用 `OutputSignal(i,j)` |
| 数字控制里想加"延时"却加不上 | 连续采样模式下没有延时函数可以调用 | 用后台计数器（模板 6），或改用混合采样 `[1/fs,0;-2,0]` + `NextSampleHit`（模板 4） |
| RMS / 平均值类计算引起输出振荡或超调 | 滑动窗口长度不合适 | 窗口太长 → 延迟大 → 输出冲过基准；太短 → 残留工频纹波 → 控制振荡。手册实测 4 个工频周期较合适 |
| 过零附近 PWM 有毛刺 | 调制信号过零时比较结果抖动 | 在过零附近设阈值（图腾柱调制的标准做法） |
| 只是想要个可复位积分器，用 C-Script 遇到代数环 | 官方不建议这种需求用 C-Script | 用 Integrator 块 + external reset，反馈走它的 **state port** |
| **改了 `.c/.h`，仿真结果丝毫不变**（或永远停在旧值） | **PLECS 编译缓存**：只哈希 `Declarations` 字符串，`#include "xxx.h"` 字面量没变就不重编 | 关闭模型 → 重开 → Ctrl+S；或改 `Declarations` 字符串本身（加一行注释即可换哈希）。**别指望"改 .h 就会重编"** |
| **"以前能跑"的版本 checkout 回来却编译报错** | 同一个缓存：当时靠旧编译产物假活，切分支/重开/保存触发强制重编才暴露缺宏 | 提交前跑编译自检（见主文件「编译自检」节）；回退点只挑通过自检的提交 |
| 仿真"成功"结束，但某路输出**恒 0** | **静默失败**：漏一条 Connection（悬空端子）、端口宽度列表写错、或顶层缺 `Terminal{Type Output}` | 跑静态自检：dump `(组件,端子)` 查悬空 / Goto-From 配对 / 幽灵组件；顶层必须有模型级 Output Terminal（否则 RPC 返回 `{Time:[],Values:[]}`） |
| `plecs_simulate` 返回 `{'Time': [], 'Values': []}`（键在、点数 0） | 模型**没有模型级 `Terminal{Type Output}`**（在 `Schematic` 之前那个）。画布上的 `Component{Type Output}` **不算** | 在 `Schematic {` 之前插 `Terminal { Type Output; Index "1" }`。⚠ 别拿官方 demo 对照"它也是空"——405 个官方文件里 389 个本来就没有，空是正常的 |
| 报错 `No port for terminal N` / 端子被丢到别的边 | Subsystem 端子 `Index` 编号撞车（需连续编号），或 `Position` 正好贴 Frame 边 | Index 连续（电气 Port 后信号口从 5 起）；Position 落在 Frame 外约 5 单位；`Subsystem.Direction=up` |
| 报错 `Unconnected terminals overlapped by other elements`（看着像排版问题） | `Connection.Type` 的 `Wire`/`Signal` 混用 | 两模型 dump `(类型,组件,端子)` 做集合差；电气扇出用同名 Label，信号走 Goto/From |
| 生成器改完，画面出现贯穿全图的长直线 | 用 `Branch` 当扇出（它是折线途经点，不是扇出） | 扇出只用 Goto/From；生成器里对"一源多目标"直接 raise 拦截 |
| 掩码对话框里中文全成 `ä¸ç¸µ…` 乱码（但仿真正常） | 裸引号里直接放 UTF-8 中文，PLECS 按单字节 CP1252 解释 | 非 ASCII 一律写 `键 base64 "…"`（UTF-8 编码）；MaskType/Prompt/MaskDescription 都走这条 |
| **打开模型"全是乱码"**（元件名、注释、标注全烂） | 文件含**裸非 ASCII 字节**（中文注释/中文 Annotation/中文 Name）。PLECS 不按 UTF-8 读 `.plecs` | 全改英文；写盘 `encoding='ascii'` + `encode('ascii')` 硬关卡；验收 `sum(b>=128)==0`。官方 263 个文件非 ASCII 字节总数为 0 |
| `Value` 字符串未闭合 | 多行 C 代码塞进引号时用了真换行 | 真 `\n` 换成字面 `\n` 再写（转义函数要处理这条，不能只转 `\` 和 `"`） |
| 启动 PLECS 弹「Model Recovery」模态框，RPC 全部卡满超时 | 上次被 `taskkill /F` 强杀，留下比磁盘新的 autosave | **绝不强杀**；释放模型用 RPC `close`。已弹出时先关掉模态框再重试 |
| `SaveTraces` 后按传入路径找不到文件 | PLECS 自动追加 `.trace` 后缀 | 按 `路径 + '.trace'` 判断存在性 |
| 脚本连不上 PLECS RPC（10061） | ①**RPC 默认关闭**（最常见）②沙箱挡回环端口 ③PLECS 随命令行会话结束被杀 | ①`Preferences → Simulation → Start XML-RPC server`（端口 1080，界面右下角可见）；连接用 `plecs.statistics()` 验证 ②用免沙箱模式 ③**启动与 RPC 必须在同一条命令内完成** |
| `plecs_scope` 报 `Invalid scope command` | `ExportCSV`/`ExportBitmap`/`GetCursorData` 只在 **Octave 脚本**里可用，**RPC 通道不支持** | 用 `SaveTraces` 存 `.trace` 再离线解析（RPC 只有 5 个命令：Clear/Hold/Remove/Save/LoadTraces） |
| 仿真运行中调 `close` 把服务搞死 | 跑仿真时不可关模型 | 先查 `statistics().models` 的 `state`，running 时用独立连接查询、不 close |

## 调试技巧

1. **多用几个输出端口做观测**。TI 的应用手册在逆变器模型里开了 20+ 路输出，全是用来把内部变量（RMS 值、误差、计数器、中间控制量）拉到 Scope 上看的。开发期非常值得这么做。
2. **勾上 Enable runtime checks**。越界访问、参数类型错误会被立刻捕获。性能敏感时再关掉。
3. **先用极端参数验证**。验证 PWM 调制器时，把开关频率降到 1 kHz、仿真 20 ms，波形一眼能看清对错，再调回 25 kHz。
4. **对照官方参考模型**。Plexim 的每个教程都配了分阶段参考模型（`cscript_controller_1/2/3/4.plecs`、`cscript_modulator_1/2.plecs`），逐阶段比对最快。
5. **参数化而不是硬编码**。把 `fs`、`kp`、`ki`、死区比、最小占空比都做成子系统掩码参数再传给 C-Script，扫参数时不用改代码。
6. **代码放在 Subsystem 里**。C-Script 块放进 Subsystem，才能在 Subsystem 上定义掩码参数（如 Switching frequency），并把 `1/fs` 作为自定义参数传进去。

### 静默失败排查：分层剥洋葱 + 一次只改一个变量

对"仿真成功但输出全 0 / 行为诡异"这类**零报错**问题，不要猜，用**分层模型**逐级证明机制：

1. `_st1`：无任何 include，直接输出常数（999）→ 证明"块被调用了、输出通道通了"；
2. `_st2`：include declarations + Start 写 DiscState + Output 读出（得 123/456）
   → 证明 include 链、Start、DiscState 都正常；
3. `_b2`：完整算法直连 Out → 出真实波形 ⇒ 证明算法本身没错。

到这里若"完整拓扑版"仍全 0 ⇒ **问题一定在拓扑/接线**，不在代码。
再用**静态集合差**（dump `(组件,端子)`）一秒定位缺的那条 Connection；
中间避免"一次改两个变量"（否则无法归因）。

### 波形回放：卡在自适应步长就重采样

PLECS 是自适应步长（暂态窗口步长极小）→ 直接按原采样点统计"判据成立占比 / 断时长"会严重失真。
**先重采样到固定网格**（如 `1/fsw` 或控制周期）再统计；用"状态重放"复算去抖计数器
（把每拍的判据与计数器按新网格跑一遍），才能还原真实的触发/解除时间。
另外**分析窗口别跳过最凶的开头**（故障/启动起始的 20 ms 常被旧脚本的 `WIN=(0.12,0.48)` 跳过，
导致门限整定误判）。

## 建模不连续性的通用规则

- 输出信号在 minor step 期间应连续平滑；跳变/折点只允许在 major step 出现。
- 用 `IsMajorStep` 判断当前是否为 major step。
- 若某段代码必须"每个 major step 恰好执行一次"，放 `Update`。
- 需要求解器精确定位跳变时刻时，注册零穿越信号 `ZCSignal(i)` 而不是靠缩小步长硬扛。
