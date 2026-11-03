---
name: plecs-cscript
description: PLECS 建模与 C-Script 开发指南——**从零搭建可跑通的 PLECS 模型**（含新环境接入：开 RPC、从 GitHub 装 MCP、写 mcp.json）、用 C 代码实现自定义控制器/数字环路/PWM 状态机、直接读写 .plecs 与 .trace、以及用 RPC 自动化跑仿真并取波形。当用户提到 PLECS 安装或接入、PLECS 连不上/WinError 10061、MPC/MCP 配置、从零建 PLECS 模型、元件参数名或端子号、C-Script 块、自定义控制器、数字控制/多环路、PWM 调制器/状态机/死区、InputSignal/OutputSignal/DiscState/ContState/ContDeriv/ParamRealData/NextSampleHit 等宏、Sample time 设置、模型编译不过/报错、.plecs 解析或批量改参数、Subsystem 封装/端子/连线、编译缓存或模型重编、RPC 自动化、.trace 波形导出、或要把 C 控制代码移植到 DSP/MCU 时使用。
agent_created: true
---

# PLECS 建模与 C-Script 开发指南

C-Script 是 PLECS 组件库里唯一能直接写 C 代码、并与求解器引擎在同一层级交互的模块。自带即时编译器，无需安装任何编译器、无需手动编译，代码被动态链接进仿真。

## ★ 全新环境从零到跑通（按顺序做，每步有验收）

**照 [references/onboarding.md](references/onboarding.md) 走**。四个阶段，缺一不可：

| # | 阶段 | 做什么 | 验收判据 |
|---|---|---|---|
| 1 | **装 PLECS** | 装 Standalone 版（本项目实测 4.7.5） | 能进主界面、能新建模型 |
| 2 | **开 RPC**（必须） | `Preferences → Simulation → 勾 Start XML-RPC server` | `statistics()` 返回版本（见下） |
| 3 | **接 MCP**（推荐） | 本机没有就 `git clone https://github.com/alembrt-cmyk/plecs-mcp.git`，装 `mcp[cli]>=1.6.0,<2`，写 `~/.workbuddy/mcp.json` | 工具列表出现 `plecs_*` |
| 4 | **跑最小模型** | `python scripts/plecs_builder.py --demo -o mini.plecs` → load → simulate | `Values` 非空，且与解析解对得上 |

RPC 自检（无需 MCP，8 行）：
```python
import xmlrpc.client
P = xmlrpc.client.ServerProxy('http://localhost:1080/RPC2', allow_none=True)
print(P.plecs.statistics())     # {'version':[4,7,5,...], 'models':[...]} = 通了
```

**`WinError 10061 积极拒绝` = RPC 没开**（不是代码错、不是端口错），先回第 2 阶段。

**最小可跑模型全文**（8 元件，真机验证：幅值误差 0.00 %、相位误差 0.00°）见
[references/minimal-model.md](references/minimal-model.md)。
**元件参数名与端子号**（从官方库 + 356 个示例反推）见
[references/component-catalog.md](references/component-catalog.md)。
**生成器骨架**（可跑的序列化 + 自检 + 扇出）见 `scripts/plecs_builder.py`。

> ★ 建新模型最容易踩的三个真机坑，先记住：
> ① `SineGenerator` 输出的是**信号**，必须进 `VoltageSource` 的**第 3 端**（受控输入），
>    直接 `Wire` 连电路 → 报 `Unconnected terminals overlapped by other elements`；
> ② **扇出写成 `Branch`**（一条 `Connection` + 多个 `Branch{}`），一个源端子只能有一条 `Connection`；
> ③ 顶层出数要**模型级** `Terminal { Type Output; Index "1" }`（在 `Schematic {` 之前）。

## 先判断该不该用 C-Script

**适合用**
- 复杂的非线性 / 分段函数（用框图搭会又乱又难维护）
- 调制器、脉冲发生器——需要**精确且灵活的时序控制**
- 数字控制环路（PI/PR/重复控制/多环路），尤其是要模拟定频采样、计算延迟、抗饱和
- 要复现 DSP/MCU 的真实执行时序，或把仿真代码直接搬到 C2000
- 状态机（开关模式生成、控制器模式切换、保护逻辑）

**别用**
- 只是个普通积分器 → 用 Integrator 块。带复位需求时用 Integrator + external reset，反馈走它的 **state port** 以避免代数环警告（官方明确建议）
- 纯线性传递函数 → 用 Transfer Function / 状态空间块，让求解器处理更稳
- 已有现成库元件（Sawtooth PWM、2/6-Pulse Generator 等）能满足时

## 核心机制：代码窗口与调用时序

C-Script 内部被自动包装成若干 C 函数，求解器在不同阶段调用。理解这张表是写对代码的前提：

| 代码窗口 | 调用时机 | 该写什么 |
|---|---|---|
| `Code declarations` | 编译期（全局头文件） | `#include`、宏定义、`static` 全局变量、枚举、helper 函数。**这里定义的变量是全局且持久的** |
| `Start` | 仿真开始时一次 | 初始化连续/离散状态、读取参数、初始化数组与计数器 |
| `Output` | 每个时间步**至少一次**，minor step 也可能多次 | **唯一能写 `OutputSignal` 的地方**。可在这里做无延迟的控制计算 |
| `Update` | 主步长中 output 之后，**每个采样周期只调一次** | 更新离散状态（`DiscState`）、采样保持、后台计数器 |
| `Derivative` | 求解器积分循环内 | 更新连续状态导数 `ContDeriv(i)` |
| `Terminate` | 仿真结束/中止/出错时 | 释放 Start 里申请的资源（文件句柄、内存） |
| `Store/Restore Custom State` | 结束前 / Start 后 | 保存恢复快照（连续/离散状态自动存，自定义数据用 Write/ReadCustomState*） |

**铁律**
1. 输出只能在 `Output` 里写。
2. 离散状态（积分累加值、计数器、状态机当前态）**必须**在 `Update` 里更新——`Output` 会被多次调用，在那儿累加会算错。
3. 跨 `Output`/`Update` 共享的中间变量要声明成全局（`static` 或 Code declarations 里的普通变量），且需跨次调用保留值的局部变量要加 `static`。
4. 若 `Output` 里要读输入，必须勾选 **Input has direct feedthrough**（否则读不到，还会影响执行顺序、产生代数环）。

## Sample time：决定模块何时被调用

| 设置值 | 名称 | 含义 | 典型场景 |
|---|---|---|---|
| `0` 或 `[0,0]` | 连续 | 每个 major 和 minor 步都执行 | 连续/分段连续函数、有连续状态、注册了零穿越信号 |
| `[0,-1]` | 半连续 | 只在 major 步执行 | 只产生离散输出值且不需要零穿越 |
| `Ts` 或 `[Ts,To]` | 离散周期 | 固定间隔执行，`To∈[0,Ts)` | 定频数字控制（如 `1/fs`） |
| `-2` 或 `[-2,0]` | 离散可变 | 由模块自己指定下次执行时刻 | 事件驱动、PWM 状态机 |
| n×2 矩阵 | 多重采样 | 混合系统 | 如 `[1/fs,0; -2,0]`：定频拍 + 事件拍 |

多重采样用 `IsSampleHit(i)` 判断第 i 行（0 基）是否命中，`SampleTimePeriod(i)`/`SampleTimeOffset(i)` 读周期与偏移。

## ★ 硬约束：载波频率必须 ≪ 采样率（否则"PWM"会退化成方波）

**离散 C-Script 每 `Ts` 只能输出一个电平**，块外看到的是**保持 `Ts` 的阶梯信号**。
所以「在块内推进三角载波 + 与调制波比较」这种写法，有一个很容易踩的死区：

```c
phase = prev->phase + p->fc * p->Ts;        /* 每拍只推进 fc·Ts */
while (phase >= 1.0) phase -= 1.0;
tr = (phase < 0.5) ? 2.0*phase : 2.0 - 2.0*phase;
if (ma > tr) {...P+...} else if (ma < -tr) {...N-...} else {...P0...}
```

- `fc == fs` → `fc·Ts == 1.0` → 相位每拍走满一圈回到 0 → **`tr` 恒等于 0**
- `fc == fs/2` → `fc·Ts == 0.5` → `tr` 只在 0 / 1 两点跳
- 这两种情况下比较退化成 `sign(ma)`：`ma>0 → P+`、`ma<0 → N-`，
  输出是**跟随调制波过零点的方波**，完全没有 PWM，而且**不会报任何错**
- 危害：开关损耗 ≈ 0、谐波巨大、闭环退化成 bang-bang（但平均电流可能"看起来对"，
  因为 bang-bang 照样能跟踪参考）；若模型里还有损耗计算元件，前提直接被推翻

**判据**：`fc·Ts` 取 `1/8 ~ 1/32`（即 `fs/fc ≥ 8`），占空比分辨率才够。
自检方法：**把 `tr` 序列打出来看**——若恒为同一值或只在两点间跳，就是退化了。

**要在 `fc ≈ 1/Ts`（如 35 kHz）下出真 PWM，只能改架构**：
1. **推荐**：C-Script 只输出 `ma/mb/mc`（连续直通），**载波比较 + 死区交给 PLECS 原生
   元件**（三角波源 + Comparator + Dead Time）
2. 把 C-Script 的 `Ts` 提到 `1/(fsw·NOS)`（如 NOS=20），控制环每 NOS 拍才更新一次
   （`p->Ts` 要拆成控制周期与调制周期两个；仿真会明显变慢）
3. 单纯降 `SPWM_CFG_FC` 到 `fs/20`：能立刻看到 PWM，但开关频率随之下降，
   工况/损耗全部失真 —— 只在"只想验证调制逻辑"时用

**同理**：任何"块内自产高频载波/锯齿/时钟"的做法都要先算 `fc·Ts`；
要高频事件就用 `-2` 可变采样 + `NextSampleHit`（见五种标准写法第 5 条）。

## ★ 调制波"不像正弦"的两个独立原因（症状不同，别混着调）

调试 `ma` 波形时，先分清下面两件事——它们经常同时出现，但改法完全不同。

### 原因 1：±1 处出现**平顶** → 过调制 + 用了逐轴削顶

出在 `αβ → abc` 之前的限幅环节。**错误写法**（很常见，因为"看起来也限住了"）：

```c
/* ✗ 逐轴硬限幅：破坏了矢量的圆形轨迹 */
if (valpha >  1.0) valpha =  1.0; else if (valpha < -1.0) valpha = -1.0;
if (vbeta  >  1.0) vbeta  =  1.0; else if (vbeta  < -1.0) vbeta  = -1.0;
```

dq 电压矢量幅值 `|V| > Vdc_half`（过调制）时，αβ 轨迹半径 > 1，
**逐轴削顶把圆切成"圆角方"** → 三相调制波出现平顶 → 低次谐波。

**正确写法**（等比缩放，保住正弦形状）：

```c
/* ✓ 矢量限幅 */
double vm = sqrt(valpha*valpha + vbeta*vbeta);
if (vm > 1.0) { valpha /= vm; vbeta /= vm; }
```

实测差距（`Vd = Vq = Vdc_half`，即 `|V| = 1.414·Vdc_half`）：

| 指标 | 逐轴削顶 | 矢量限幅 |
|---|---|---|
| 削顶样本占周期比例 | **50.2 %** | **0.2 %**（仅峰值点） |
| 波形畸变（残差/基波） | **13.4 %** | **0.000 %** |
| 基波幅值（应为 1） | 1.157 | 1.000 |

**两条铁律**
- 同一个模块里**所有**产生调制波的路径（开环 / 闭环 / 限幅旁路）必须用**同一种**限幅方式。
  实践中容易漏：开环写了矢量限幅、闭环却写了逐轴削顶。
- **矢量限幅 ≠ 电压够用**。限幅后波形是干净的正弦，但若峰值**长期贴 1.0**，
  说明已进电压饱和区（基波被压低）→ 要降给定或抬 `Vdc`。
  核对余量：`电网相电压峰值 / (Vdc/2)`，本类项目常见只余 4~5 %。

**离线验证做法**（不需要 PLECS）：构造两个 dq PI 都饱和的工况
（`id_ref = iq_ref = 极大值`、`vbus_ref = 0` 旁路外环、`noc=1` 使每拍都是控制拍），
扫 θ 一整周取 `ma1`，然后用 DFT 算「残差/基波」比值 + 统计削顶样本占比。
前者应 ≈ 0，后者应 ≈ 0（只有峰值点）。这个测试能把限幅写错这件事钉死。

### 原因 2：规则**台阶**（每级持续一个 `Ts`）→ 控制率太低

控制拍之间调制波是**零阶保持**的，所以一个基波周期里只有 `fs / fo` 个不同的值。
**这是采样率问题，不是限幅问题**——峰值不会被削平，只是一级一级地爬。

| `fs`（对 60 Hz 基波） | 采样点/周期 | 观感 |
|---|---|---|
| 1 kHz | **16.7** | 台阶明显、像楼梯 |
| 10 kHz | 167 | 基本平滑 |
| ≥ 20 kHz | ≥ 333 | 看不出台阶 |

反过来也有用：**看到台阶的密度就能反推 `fs`**——数一个基波周期里有几级，
除以基波频率就是当前实际生效的控制率。这是排查"改了 `fs` 但没生效"的最快手段。

提 `fs` 后电流环带宽上限（≈ `fs/10`）随之打开，按 `Kp ≈ L·ωn`、`Ki ≈ R·ωn`
重新整定；`fs` 太低时（如 1 kHz，带宽仅 100 Hz ≈ 1.7× 基波）跟踪误差大，
需要的调制电压更高，**反而会加剧原因 1 的饱和**——两者会互相放大。

> 注意别把原因 2 当成"代码 bug"去改限幅。判断口诀：
> **平顶 → 限幅/过调制；等距台阶 → 控制率。**

## Setup 面板

`Number of inputs` / `Number of outputs` / `Number of cont. states` / `Number of disc. states` / `Number of zero-crossings` / `Input has direct feedthrough` / `Sample time` / `Parameters`。

`Parameters` 框里填的变量（如 `kp, ki, 1/fs`）在代码中用 `ParamRealData(i,j)` 读取，i 是参数序号、j 是**线性索引**（多维需自己换算）。也可以放字符串，用 `ParamStringData(i)` 读。

## 常用宏（精简版，完整表见 references/macro-reference.md）

```c
InputSignal(i,j)      // 读第 i 个输入端子的第 j 个信号
OutputSignal(i,j)     // 读写第 i 个输出端子的第 j 个信号（仅 Output 里可写）
DiscState(i)          // 离散状态
ContState(i)          // 连续状态（minor step 不可改）
ContDeriv(i)          // 连续状态导数（Derivative 里写）
CurrentTime           // 当前仿真时间
NextSampleHit         // 下次执行时刻（-2 采样时用）
IsMajorStep           // 是否主步长
IsSampleHit(i)        // 第 i 路采样是否命中
ZCSignal(i)           // 零穿越信号
ParamRealData(i,j)    // 读参数
SetErrorMessage("s")  // 报错并终止仿真（字符串必须在静态内存）
```

⚠️ 输入输出信号**不是连续内存**，禁止 `&OutputSignal(0,0)+1` 这类指针算术，必须逐个用宏访问。

## 五种标准写法

完整可抄的代码模板见 [references/code-patterns.md](references/code-patterns.md)。摘要：

1. **连续数学函数** — Sample time `0`，无状态，`math.h` + `OutputSignal`。
2. **数字 PI（无延迟版）** — Sample time `1/fs`，1 个离散状态；控制律写在 `Output`，`Update` 里只做 `ik_1 = ik`。写在 `Update` 会引入一环延迟，`fs` 低时可能失稳。
3. **连续 PI** — Sample time `0`，1 个连续状态，`Derivative` 里 `I_deriv = e`。
4. **带计算延迟的数字控制** — Sample time `[1/fs,0; -2,0]`，`Start` 里 `NextSampleHit = DBL_MAX`，`Update` 里算完后 `NextSampleHit = CurrentTime + Td`。
5. **PWM 状态机** — Sample time `[1/fs,0;-2,0]`，1 个离散状态存 `STATE`，`enum` 定义状态，`Output` 里 switch 并设置 `NextSampleHit`，`Update` 里 `STATE = NEXT_STATE`。只在开关跳变时被调用，比"调制波 vs 三角载波比较"方案高效得多。

## 模拟真实 MCU 执行（TI 参考做法）

把 Sample time 设成 **MCU 时钟周期**（不是"主频×1e-9 随手写"），C-Script 就以连续模式跑，
等同于 MCU 主循环。然后用**计数器分频**派生各个控制频率。

⚠ **这一节的数字必须自己算一遍，别照抄手册**。TI ZHCADZ0 的原文自相矛盾：

| 手册说法 | 反推 | 结论 |
|---|---|---|
| "sample time 83ns → 120MHz" | 1/83 ns = **12.05 MHz** | 正文算错 |
| 对话框截图 `8.3e-8` | = 83 ns = 12 MHz | 与正文的 83ns 同源 |
| "计数器 600 → 20 kHz" | 20 kHz × 600 = **12 MHz** | ✓ 自洽 |
| "计数器 120 → 100 kHz" | 100 kHz × 120 = **12 MHz** | ✓ 自洽 |
| "死区 83.3 ns = 10 个计数" | 10 / 83.3 ns = **120 MHz** | ✗ 与上面三行差 10 倍 |

⇒ **手册的实际模型是 12 MHz 时钟**（600:120 = 20k:100k = 5:1 全部对得上），
只有"120MHz"和"死区 83.3ns"这两句是错的（应是 8.33 ns 或 10×8.33=83.3 ns，
按 12 MHz 算死区其实是 10×83 ns = **830 ns**）。
按 120 MHz 建模仿真会慢 10 倍、且计数全错。

**换算公式**：`计数 = 1 / (f_target × Ts)`，`f_target = 1/(Ts × 计数)`。
本例 Ts = 8.3e-8 → 电压环 20 kHz 计数 602（手册取 600）、电流环 100 kHz 计数 120。
代码实现照手册写法即可，但**采样时间要按你自己的 MCU 时钟填**（280039 实际是 120 MHz，
那 Ts 就该是 8.33e-9、计数 ×10）。

配套要点：采样/控制/调制/死区全部放在 `Update`，`Output` 只做信号输出；真 RMS 用数组窗口（4 个 50 Hz 周期 @ 20 kHz → 数组长 1600），窗口越大精度越高但延迟越大、过小会引入 50 Hz 纹波导致振荡；PI 要加**抗饱和**；图腾柱调制中误差符号决定低频桥、与锯齿波交点决定高频桥，过零附近要设阈值抑制干扰。

## 排错

见 [references/troubleshooting.md](references/troubleshooting.md)。最高频的五个：
1. 离散状态在 `Output` 里更新 → 积分值算错 → 挪到 `Update`
2. `Output` 读输入没勾 direct feedthrough
3. `NextSampleHit` 未更新或 ≤ 当前时间 → 仿真中止
4. 数字控制输出滞后一环 → 控制律从 `Update` 移到 `Output`，或提高 `fs`
5. **"PWM 出来是方波/没有载波纹波"** → `fc·Ts` 是整数（尤其 `fc == fs`），
   载波采样退化，见上文「硬约束：载波频率必须 ≪ 采样率」。这个坑**不报错**，
   只能靠打印 `tr` 序列或看输出电平分布（只在 P+/N- 之间对半翻）发现

## 多环路 + 模式切换的写法约定

- **「旁路某个环」= 完全不调用它的 PI 函数**，而不是「把参考置 0 照常调用」。
  后者会让积分器被任意反馈污染、累积出任意值，重新启用时第一拍就是巨大冲击。
  测试方法：预置非零积分值 + 灌一个荒谬的反馈，跑几百拍后积分器必须**一字不差**保持。
- **模式开关用编译期宏**（在 declarations 头文件里 `#define XXX_OPENLOOP 0/1`），
  比用某个输入引脚的符号当开关安全——不会和"手动给定"等其他语义撞车，
  也不会因外部接线忘了改而误触发。
- **复用引脚省掉改接线时，务必在引脚声明处把两种语义都注出来**，
  否则半年后没人知道那个 `IdRef` 常数在开环下是调制比。
- 过调制限幅优先用**矢量等比缩放**（`m>1` 时 `m_d/=m, m_q/=m`），
  而不是对 α/β 或逐相硬限幅——前者保持纯正弦，后者会削顶、引入低次谐波。


## ★ 直接改 `.plecs` 文件（批量替换元件参数）

`.plecs` 是纯文本，可以直接用脚本改（`Ron`/`Lm`/`Ts` 这类参数、批量把理想件改非理想）。**完整格式手册见 [references/plecs-file.md](references/plecs-file.md)**。必须遵守：

1. **元件块要用「归属法」扫，不能用花括号配平。** 配平只能拿到顶层元件——典型模型里 24 个 MOSFET、
   3 个变压器全在 `Subsystem` 内部，配平法会把它们**整块吞掉、一个都扫不到**（某实模型只扫到 54/211 个
   组件），而且**不报错**，表现为"没有需要改的地方"这种**假阴性**（比报错更危险）。
   正确做法：顺序读行，遇 `^\s*Component\s*\{$` 开一个新元件记录；其后**第一个** `Type`、`Name` 归它；
   此后每个 `Variable "x"` + 紧邻的 `Value "y"` 也归它，直到下一个 `Component {`。与嵌套层数无关。
2. `Component {` 后几行就是 `Type` / `Name`；非 ASCII 名字是 `Name  base64 "..."`，要 base64 解码。
   参数一律形如 `Parameter { Variable "x" / Value "y" / Show off }`。
3. **参数值可能是变量名而不是数字**（例：`Ron` 的 Value 是 `"Rgon"`，另一个器件的 `s_init` 是 `"Rgoff"`）。
   判等要按**数值**比较；遇到非数值字符串就**当作"需要改"**，别用纯字符串比较。
4. 脚本要**幂等 + 默认 dry-run + 写盘前自动备份**（`<file>.bak-<用途>-<时间戳>`）。
   写盘前先确认 PLECS 没在运行；若在运行，明确告知用户"关掉重开、期间不要保存"——
   否则 PLECS 一存就把补丁覆盖掉。
5. 改完**必须关掉 PLECS 重开**（模型/块对象被缓存）。

### 元件参数名的实测全集（405 个官方文件统计，照这个写不会报「官方没见过」）

| 元件 | 参数（`Parameter{}` 里的 `Variable`） | 备注 |
|---|---|---|
| `Gain` | `K` + `Multiplication` + `DataType`（**三个都在**，1987/1987 例） | 写"只有 K"是错的；少数还带 `Tag`/`Width`/`IconShape`/`J` |
| `Sum` | `Inputs` + `DataType` + `IconShape` | `Inputs` 是符号串 `"++"` / `"+-"` |
| `Integrator` | `x0` + `ExternalReset` + `InitialConditionSource` + `ShowStatePort` + `EnableWrapping`（+`UpperLimit`/`LowerLimit`） | 初值是 **`x0`**，不是 `InitialCondition` |
| `Step` | `Time` + `Before` + `After` + `DataType` | |
| `SineGenerator` | `Amplitude` + `Frequency` + `Bias` + `Phase` + `Units` | `Frequency` 是 **rad/s** 时 `Units` 取 1；Hz 用 3 |
| `TransferFunction` | `Numerator` + `Denominator` + `X0` | 大写 `X0`（与 Integrator 的 `x0` 不同） |
| `CScript` | `NumInputs`/`NumOutputs`/`NumContStates`/`NumDiscStates`/`NumZCSignals`/`DirectFeedthrough`/`Ts`/`Parameters` + `Declarations`/`StartFcn`/`OutputFcn`/`UpdateFcn`/`DerivativeFcn`/`TerminateFcn`/`StoreCustomStateFcn`/`RestoreCustomStateFcn`/`LangStandard`/`GnuExtensions`/`RuntimeCheck`/`DialogGeometry` | 20 个，一个都不能少 |
| `Scope` | **不走 `Parameter{}`**——全是裸字段：`Axes`/`TimeRange`/`XAxisLabel`/`SingleTimeAxis`/`ScrollingMode`/`Open`/`Ts`/`SampleLimit`/`State`/`SavedViews`/`HeaderState`/`PlotPalettes`/`Axis{...}`/`Fourier{...}` | 405 个文件里**没有一个**用 `Parameter{}` 包 Scope 字段 |
| `Output` | `Index` + `Width` | |

⚠ 判"参数是否合法"要按**参数名全集**比，不能按"我见过几个"比——
`Gain` 只写 `K` 虽然 PLECS 能读（缺的用默认值），但你的校验器若断言"Gain 只有 K"，
会把官方文件判成非法。**校验器的真理源是官方 405 个文件的并集，不是记忆。**

## ★★ 编译缓存：改了 `.c/.h` 却"看起来没生效"的头号原因

PLECS 的 C-Script 即时编译器**只哈希 `Code declarations` 里的字符串**——即那个
`#include "xxx.h"` 字面量。**改被 include 的头文件内容不改变这个字符串 ⇒ 不触发重编**，
内存里跑的还是上一次成功编译的产物（步骤与新代码一致、点、数全对不上时，先怀疑这个）。

由此产生三个连锁现象（都实测过）：

| 现象 | 机制 |
|---|---|
| 改了头文件，仿真结果丝毫不变 / 或与"旧版本"完全一致 | 用的是旧编译产物 |
| "以前能跑"的 git 提交，checkout 回来编译报错 | 切分支/关重开/Ctrl+S 触发**强制重编**，缺宏才暴露；当时靠缓存假活 |
| 作者自己都记不清某次改动到底有没有生效 | 同上 |

**唯一可靠的重编触发方式**：
1. **关闭模型 → 重新打开 → Ctrl+S**（首选）；
2. 或**改动 `Declarations` 字符串本身**（哪怕加一行注释 `/* rc-YYYYMMDD */` 都会换哈希）；
3. 或切换 git 分支后再打开（同 1，靠文件时间戳变化）。

⚠ 单纯关掉重开**不一定**够——只要 PLECS 进程还在，编译器缓存可能仍在。最硬的做法：
改完 `Declarations`（哪怕是加注释）再重开。**别指望"改 .h 就会重编"。**

**推论（写胶合层宪法）**：只要模型里有 `#include "xxx.h"`，就必须保证
**头文件 ↔ .c ↔ 模型配置（端口/状态数/采样）**三者同时是一致版本；
任何一次"只改了其中两处"都会变成一颗定时炸弹——平时被缓存掩盖，某个时刻
（重开/保存/切分支）集体引爆。**提交前跑一遍编译自检（见下）**。

## ★ 静默失败：PLECS 不报错但结果全错的三类坑

PLECS 对"接线/配置错误"经常**静默给 0 或给错值，仿真"成功"结束**。
这类问题比报错危险得多——没有堆栈、没有红色文字，只能靠自检发现：

0. **同一源端子要接多个目的地 → 写成一条 `Connection` + 多个 `Branch { ... }`**。
   拆成多条各自带 `DstComponent` 的 Connection 时，**PLECS 只保留其中一条，
   其余目的地静默变成 0**（不报错、不警告）。症状：模型跑通、波形也对，
   但某个观察支路/第二个消费方永远是 0。
   ```text
   Connection { Type Signal
                SrcComponent "Plant" SrcTerminal 2
                Points [730, 230]
                Branch { DstComponent "RC"  DstTerminal 2 }
                Branch { DstComponent "Out" DstTerminal 1 } }
   ```
   ★ **证据（官方 356 个 .plecs 实测）**：32324 条 `Connection` 里 **6232 条**是多目的地
   `Branch` 写法，`Branch{}` 内含 `DstComponent/DstTerminal` —— 这就是**官方扇出语法**。
   （旧版本技能误记成"Branch 是折线途经点、扇出只能用 Goto/From"，已更正：`
   Branch` 既可带 `Points` 也可带 `DstComponent`，两者是不同层级的字段。）
   排查手法：`grep -c "^      Branch {"` 与 `grep -c DstComponent` 对账；
   或 dump 连接后查"同一 (源组件, 源端子) 是否出现多次"。
1. **漏一条 Connection** → 悬空端子喂给 Demux/C-Script，输出**全 0**。
   实例：`From.1 → Demux.1` 漏连，11 路输出恒 0，仿真正常结束。
   防法：生成器改完必跑**静态连接自检**——把模型 dump 成 `(组件, 端子)` 元组集合，
   查①每个组件端子都出现②`Goto/From` 名称两两配对③无"幽灵组件"。
2. **C-Script 的 `NumInputs`（端口宽度列表）漏写/写错** → 对应输入**恒 0**。
   注意它是**宽度列表**不是个数：`"3"` = 一个宽 3 的端口；`"[7 5]"` = 两个端口（宽 7 + 宽 5）。
   写 `"0"` 会明确报错（`Not a positive integer value`），但"宽 3 写成宽 1"不报错。
3. **顶层出数必须有模型级 `Terminal { Type Output; Index "1" }` 块**（在 `Schematic` 之前）。
   只放画布上的 `Component { Type Output ... }` 时 RPC `simulate` 返回 `{'Time': [], 'Values': []}`——
   键都在、点数 0，极具迷惑性（**实测踩过**：加了画布 Outport 仍然返回空，误判成"MCP 取数通道坏了"）。
   两者是不同东西：画布 Output 是给连线和子系统用的，模型级 Terminal 才是 RPC 出数的开关。
   官方 405 个文件里两者都有的只有 2 个（`buck_converter_with_parameter_sweep`、`rainflow_counting`），
   其余 389 个**一个都没有** —— 所以别拿"官方 demo 也返回空"当证据，它本来就不出数。
   写文件时画布 Output 的写法是 `Parameter{ Index "1" } + Parameter{ Width "-1" }`；
   读回时 PLECS 把 `Index` 显示成 `Port`（`plecs_get` 只看到 `Width`/`Port` 两个参数，别以为 `Index` 被丢了）。

⇒ **写 `.plecs` 生成器的标准流程**：生成 → 静态自检（连接/配对/端子）→ 真机 load →
simulate → **数值对账**（不能只看"跑完了"）。

## ★★ Subsystem 封装五条铁律（真机对照实验反推，改模块必看）

把一堆元件封成可复用 Subsystem 模块时，五条规则全踩过坑，全都有"报错信息误导"的脾气：

1. **端子 `Index` 是全部端子共用的一条连续编号**。4 个电气 Port 之后，
   下一个信号 Output 必须写 **5**。写 1 会和 Port 1 撞车，表现为
   「最后一个电气端口消失」→ `No port for terminal 4`。参照库里的 `abc <-> dq`：Port 1,2,3 + Output 4 + Input 5。
2. **`Terminal.Position` 必须落在 `Frame` 外面约 5 单位**。正好贴边时端子会被丢到
   **别的边**上（A/B/C 全挤到底边）。库里都是 `Frame ±25` 配端子 `±30`。
   `Direction` 写朝外法线：右边 `right`、左边 `left`、下边 `down`、上边 `up`。
3. **`Subsystem.Direction` 写 `up`**（库里全是 up）。写 `right` 会把整块连端子转 90°。
4. **电气扇出用同名 `Label`；`Goto/From` 只能走信号**。给电气端口接 Goto →
   `Cannot create connection to terminal 1 of …/Goto`。
   ★ **扇出还有第二种写法：`Branch{}`**（一条 `Connection` + 多个 `Branch`）
   —— 这是官方最常用的（356 个示例里 6232 条）。`Label/Goto` 适合跨区域长距离，
   `Branch` 适合就近多分。**别把 `Branch` 当折线途经点**：`Branch` 里既能放
   `Points`（途经点）也能放 `DstComponent/DstTerminal`（真正的目的地）。
5. **`Connection.Type` 的 `Wire` / `Signal` 不能混**。把信号输出用 `Wire` 连 `Goto` →
   报的却是 `Unconnected terminals overlapped by other elements`
   （看着像排版问题，实为类型问题）。排查手法：两个模型 dump 成 `(类型, 组件, 端子)`
   元组做集合差，一秒定位。

另：改**掩码参数**的 RPC 路径是 `模型名/子系统名`（如 `demo/SRC_BLOCK`），
且值必须传**字符串**（传 float 报 `invalid method parameters`）。

## ★ 自动化跑仿真（PLECS RPC / MCP）

- **RPC 默认关闭**，必须先 `Preferences → Simulation → Start XML-RPC server` 勾上
  （默认端口 **1080**，界面右下角会显示）。没开时报
  `WinError 10061 由于目标计算机积极拒绝`——**先确认这一步，再怀疑别处**。
  官方原文：*"The RPC interface in PLECS is disabled by default. It must be enabled in the
  PLECS preferences before a connection can be established."* 且**只接受本机连接**。
  连接成功用 `plecs.statistics()` 验证（返回版本 + 已打开模型列表）。
- **RPC 通道**：`simulate` 阻塞；**时长键是 `SolverOpts.TimeSpan`**（旧的 `StopTime` 已废弃，
  官方原话 "is obsolete... we strongly advise against using it"）；
  仿真运行时**绝不可 close**；改磁盘 `.plecs` ≠ 改内存模型（init 参数用 RPC 改）。
- **scope 命令只有 5 个 —— 但这是「RPC 通道」的限制，Octave 脚本有 8 个**。
  RPC 实测可用：`ClearTraces` / `HoldTrace` / `RemoveTrace` / `SaveTraces` / `LoadTraces`。
  官方手册的 Octave 脚本节还列了 `ExportCSV` / `ExportBitmap` / `GetCursorData`，
  但**从 RPC 调它们会报 `Invalid scope command`**（4.7.5 实测）。
  ⇒ 定量取数走 `SaveTraces` → 离线解析 `.trace`，别指望 RPC 直接导 CSV。
- **`SaveTraces` 自动追加 `.trace` 后缀**：传 `…/out` 实际落地 `out.trace`；
  按传入路径判断存在性会误判"没生成"。
- **顶层无 Outport 时 `simulate` 恒返回空**（有 Outport 才返回 `{Time, Values}`）。
- **绝不 `taskkill /F` 强杀 PLECS**：强杀会留下比磁盘新的 autosave，下次启动弹
  「Model Recovery」**模态框**，该框**阻塞 RPC**（后续 load 卡满超时）。
  要释放模型用 RPC `close`。
- **Bash 沙箱可能连不上回环端口**（PLECS XML-RPC 127.0.0.1）；用命令行启动 PLECS +
  立刻发 RPC 时，**启动与调用必须在同一条命令内完成**（进程随命令会话结束被杀）。
- **`.trace` 是私有二进制但有解析器**（MCP `plecs_trace_read` 可直接出
  逐曲线 min/max/avg/pp/rms 并导 CSV）——不要再让用户从 GUI 手工导 CSV。

## ★ 报错 "Inconsistent source conditions ... short-circuited voltage source"

**这是拓扑/理想元件问题，不是 C 代码问题**——先去查 `.plecs` 的元件参数，别先怀疑控制器。

- 触发条件：PLECS 每次**开关状态切换**后都要求网络有 KVL 一致解。若存在**零阻抗回路**
  （理想电压源 + 理想开关 `Ron=0` + 理想变压器 `Lm=inf`），切换后无解 → **立即硬中止**。
- **报错时刻本身就是线索**：若 `t_报错` 恰好等于**死区时间**（= 第一个控制拍之后门极首次翻高的时刻），
  说明 t=0~死区期间全管关断（无回路、放行）→ **短路是"第一批门极闭合"造出来的**。
- 修复顺序：① 所有理想开关给 `Ron`（1e-3 量级）；② 理想变压器给 `Lm`（1e-3~1e-2），需要时再加
  绕组串联电阻/漏感；③ 给"理想电压源支路"串一点 R/L。
- **常见误操作**：想"把电网断开"就把 `ThreePhaseVoltageSource` 的 `V` 改成 `0`。它内部是**三个理想
  0 V 源接星点 = 三相直接短路**，比接着电网还糟。断网要么**删线**，要么插一个 `t=0` 断开的断路器。
- 同一拓扑从"母线电容"换成"母线电容 + 理想电压源"后，原本只表现为**缓慢放电**的坏通路会升级成
  **硬中止**。这类报错往往是在做好事：它把一直存在的坏通路暴露了出来。

## 参考资料

- 官方文档（宏与采样时间最权威）：https://docs.plexim.com/plecs/5.0/c-scripts/
- Plexim 教程 *Introduction to the C-Script Block*（PI 控制器三版本 + 计算延迟）：https://www.plexim.com/sites/default/files/tutorials_categorized/plecs/cscript_controller.pdf
- Plexim 教程 *Efficient PWM Generation*（状态机调制器 + 死区推导）：https://www.plexim.com/sites/default/files/tutorials_categorized/plecs/cscript_modulator.pdf
- Plexim Demo Model：*Inverter with C-Script-Based PWM Modulator*
- TI 中文应用手册《使用 PLECS 仿真实现具有数字控制功能的单相离网逆变器》(ZHCADZ0) — 全数字控制 + 图腾柱调制 + 真 RMS，每块都有代码，可直接照抄结构
- 本技能附带的参考文件：
  - [references/onboarding.md](references/onboarding.md) — **全新环境接入**：开 RPC、从 GitHub 装 MCP、写 mcp.json、三步自检、失败对照表
  - [references/minimal-model.md](references/minimal-model.md) — **最小可跑模型全文**（真机验证：幅值/相位误差 0.00%）
  - [references/component-catalog.md](references/component-catalog.md) — **元件图鉴**：Type / 参数名 / 端子号（官方库 + 356 示例反推）
  - [references/plecs-file.md](references/plecs-file.md) — `.plecs` 私有格式、Subsystem 封装、批量改参、静默失败自检、`.trace` 二进制格式
  - [references/code-patterns.md](references/code-patterns.md) — 可直接粘贴的代码模板（含 DSOGI-PLL）
  - `scripts/plecs_builder.py` — **可跑的 .plecs 生成器骨架**（序列化 + Branch 扇出 + ASCII 关卡 + 静态自检）

## 给用户写代码时的默认做法

用户只描述功能（如"做个 MPPT""实现 SVPWM"）时，按以下顺序交付：
1. 先说清 **Sample time 怎么设**、需要几个输入/输出、几个离散/连续状态、是否勾 direct feedthrough、Parameters 框填什么；
2. 再按 Code declarations / Start / Output / Update 四段给出可直接粘贴的代码；
3. 最后提示该方案的时序陷阱（是否会引入延迟、是否要注册零穿越、死区怎么加）；
4. 尽量附一个**能离线跑的纯 C 验证程序**（用户本机有 gcc 时）。

### 离线验证 C-Script 的技巧（强烈推荐）

把 PLECS 宏映射成普通数组，就能在 gcc 下跑"**PLECS 实际拿到的那份代码**"：

```c
static double g_in[2][6], g_out[3][12], g_ds[5];
#define InputSignal(p,k)  (g_in[(p)][(k)])      /* 用二维数组，保证是左值 */
#define OutputSignal(p,k) (g_out[(p)][(k)])
#define DiscState(i)      (g_ds[(i)])
#include "_decl_inline.c"        /* 从 .plecs 反解出的真实 declarations */
static void plecs_start(void)
#include "cscript_start_xxx.c"   /* 窗口内容本身就是裸块 {…}，接在函数头后即函数体 */
```

再按窗口名建 `plecs_output()` / `plecs_update()` 两个函数分别 include 对应片段，
用一个 `while` 模拟"Output 可能被调多次、Update 每拍一次"的调度，就能在 PC 上
复现状态提交时序、专门测「Output 里改 DiscState」这类 bug。

要点：
- 反解 `.plecs` 的 `Value` 字段时注意 PLECS 用 `\n` `\"` `\\` 转义，
  且**多行 Value 被拆成多段引号**（`Value "line1\n" "line2\n" "line3"`），
  取值/写值都要按"一段或多段"匹配，否则会漏段。
- 窗口片段是**裸块 `{...}`**（不含函数签名），所以 `#include` 到函数头后面正好。
- 想验证端口引脚号，可以拿 `&MACRO - &g_out[0][0]` 反算。

### 编译自检：验证 include 链是否自洽（改胶合层后**必做**）

PLECS 报错行号可能是负数（相对整份生成文件的偏移）且 `#include` 的文件不会自动检查，
所以要在 PLECS 之外先复刻一次"PLECS 的翻译单元"：

1. 用**桩**替换 PLECS 宏，让代码能离开 PLECS 编译：
   ```c
   static double g_in[2][6], g_out[4][16], g_ds[66];
   #define InputSignal(p,k)  (g_in[(p)][(k)])
   #define OutputSignal(p,k) (g_out[(p)][(k)])
   #define DiscState(i)      (g_ds[(i)])
   #define ParamRealData(i,j) (1.0)
   /* …其余宏按需补桩 */
   ```
2. 按模型 `Declarations` 里的 **include 顺序**把 `.h` 与三个窗口片段拼进一个翻译单元。
   ⚠ **`cscript_{start,output,update}.c` 是"函数体片段"**（以 `{` 开头、不含签名），
   必须各自包一层函数再 include：
   ```c
   static void plecs_start(void)
   #include "cscript_start_xxx.c"
   ```
3. `gcc -std=c99 -Wall -Wextra -I<工程根> -o check.exe _compile_check.c -lm`。
   **0 error 才算过**——这是「头文件 ↔ .c ↔ 模型」三者一致性的最快仲裁，
   能提前拦住"编译缓存掩盖的缺宏"问题（报错量不相等时逐条对齐宏名/端口即可）。

### 从 .plecs 导出真实窗口内容与块配置（保持"文件版"与模型一致）

模型里的 `Declarations/Start/Output/Update` 是**带转义引号的普通字符串**（非 base64），
可用小脚本导出成独立的 `.c` 文件（`_dump_cscript_code.py`）；块配置（端口宽度列表、
状态数、Sample time、DirectFeedthrough）另一路导出（`_dump_cscript_cfg.py`）。
**保留这两个查看手段**，否则"窗口里粘的是什么"只能靠猜——而模型里粘贴的内容与
磁盘上的 `.c` 文件一旦分叉，就会出现"代码明明改了、跑的还是旧行为"的幽灵问题
（与编译缓存叠加时尤其难查）。

