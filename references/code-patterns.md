# PLECS C-Script 代码模板

每个模板都给出：**Setup 配置 → 四段代码 → 要点**。可直接粘贴，按需改变量名。

---

## 模板 1：连续数学 / 非线性函数

**Setup**：Number of inputs = 2，Number of outputs = 1，Sample time = `0`，其余全 0。

```c
/* ---------- Code declarations ---------- */
#include <math.h>
#define offset InputSignal(0,0)
#define freq   InputSignal(0,1)

/* ---------- Start ---------- */
/* 无状态，留空 */

/* ---------- Output ---------- */
OutputSignal(0,0) = sin(freq*CurrentTime) + offset;
```

要点：连续采样下每个求解器步长都会执行，可自由使用 `<math.h>`。

---

## 模板 2：数字 PI 控制器（无一环延迟，推荐）

**Setup**：inputs = 1，outputs = 1，disc. states = 1，Sample time = `1/fs`，Parameters = `kp, ki, 1/fs`。

```c
/* ---------- Code declarations ---------- */
static double kp, ki, Ts, ik;
#define ek    InputSignal(0,0)
#define ik_1  DiscState(0)

/* ---------- Start ---------- */
kp = ParamRealData(0,0);
ki = ParamRealData(1,0);
Ts = ParamRealData(2,0);
ik_1 = 0;

/* ---------- Output ---------- */
ik = ik_1 + Ts*ek;                 /* 后向矩形法离散积分 */
OutputSignal(0,0) = kp*ek + ki*ik;

/* ---------- Update ---------- */
ik_1 = ik;                         /* 只做状态递推 */
```

后向矩形法：`i_k = i_{k-1} + Ts*e_k`，`y_k = kp*e_k + ki*i_k`。

### 2b. 会引入一环延迟的写法（知道它长什么样，好避开）

```c
/* Update：控制律写在 update，输出滞后一个采样周期 */
double ik = ik_1 + Ts*ek;
yk = kp*ek + ki*ik;
ik_1 = ik;

/* Output */
OutputSignal(0,0) = yk;            /* 输出的是上一步算的结果 */
```

后果：`fs` 降到 10 kHz 时 buck 电路会明显失稳。要么把控制律挪到 Output（模板 2），要么提高采样频率。

### 2c. 需要抗饱和时

在 `Update` 里对 `ik_1` 限幅，或在 Output 里先算未限幅输出再回夹：

```c
ik = ik_1 + Ts*ek;
double y_raw = kp*ek + ki*ik;
if (y_raw > YMAX)      { y_raw = YMAX;  ik = (YMAX - kp*ek)/ki; }
else if (y_raw < YMIN) { y_raw = YMIN;  ik = (YMIN - kp*ek)/ki; }
OutputSignal(0,0) = y_raw;
```

---

## 模板 3：连续 PI（用连续状态解 ODE）

**Setup**：Sample time = `0`，cont. states = 1，disc. states = 0，去掉参数 `1/fs`。

```c
/* ---------- Code declarations ---------- */
static double kp, ki;
#define e       InputSignal(0,0)
#define I       ContState(0)
#define I_deriv ContDeriv(0)

/* ---------- Start ---------- */
kp = ParamRealData(0,0);
ki = ParamRealData(1,0);
I  = 0;

/* ---------- Derivative ---------- */
I_deriv = e;                       /* dI/dt = e(t) */

/* ---------- Output ---------- */
OutputSignal(0,0) = kp*e + ki*I;
```

要点：每定义一个连续状态就会生成 `ContState(i)` / `ContDeriv(i)`，只需要在 Derivative 里写微分方程，数值积分交给求解器。
**注意**：若要的是"可复位积分器"，官方建议直接用 Integrator 块 + external reset，反馈走它的 state port 以避免代数环，不要自己写 C-Script。

---

## 模板 4：带计算延迟的数字控制（混合采样）

模拟 MCU "读输入 → 算 → 写输出" 的有限延迟。

**Setup**：Sample time = `[1/fs, 0; -2, 0]`，disc. states = 1，Parameters = `kp, ki, 1/fs, td/fs`（`td∈(0,1)`，0.1 表示 0.1·Ts）。

```c
/* ---------- Code declarations ---------- */
#include <float.h>
#define NEVER DBL_MAX
static double kp, ki, Ts, Td, yk;
#define ek    InputSignal(0,0)
#define ik_1  DiscState(0)

/* ---------- Start ---------- */
kp = ParamRealData(0,0);
ki = ParamRealData(1,0);
Ts = ParamRealData(2,0);
Td = ParamRealData(3,0);
ik_1 = 0;
NextSampleHit = NEVER;             /* 保证第一个 hit 来自固定拍 */

/* ---------- Update ---------- */
double ik = ik_1 + Ts*ek;
yk = kp*ek + ki*ik;
ik_1 = ik;
NextSampleHit = CurrentTime + Td;  /* 延迟 Td 后再触发一次输出 */

/* ---------- Output ---------- */
OutputSignal(0,0) = yk;
```

要点：`td = 0` 和 `td = 1` 是退化情形，需单独处理。把 `fs` 设成 10 kHz，分别取 `td = 0.1` 和 `0.9` 可直观看到延迟对稳定性的影响。

---

## 模板 5：PWM 状态机调制器

只在开关跳变时被调用，一个周期仅 2 次（加死区后 4 次），远比"调制波 vs 三角载波持续比较"高效——后者求解器必须在每个跳变点附近取中间步来定位精确跳变时刻。

**Setup**：inputs = 1，outputs = 1，disc. states = 1，Sample time = `[1/fs, 0; -2, 0]`，**勾选 Input has direct feedthrough**，Parameters = `1/fs`。

### 5a. 理想对称 PWM（双极性，输出 ∈ {-1, 1}）

```c
/* ---------- Code declarations ---------- */
#include <float.h>
#define NEVER DBL_MAX
#define DMIN  1e-6

typedef enum { Start, Low, High } state_type;
static state_type NEXT_STATE;
static double TS;

#define m     InputSignal(0,0)
#define OUT   OutputSignal(0,0)
#define STATE DiscState(0)

/* ---------- Start ---------- */
TS = ParamRealData(0,0);
STATE = Start;
NextSampleHit = NEVER;

/* ---------- Output ---------- */
double m1, m2;
static double t1, t2;              /* static：跨次调用保留 */

switch ((state_type) STATE) {
case Start:
    m1 = (m + 1)/2;                /* 从 [-1,1] 映射到 [0,1] */
    m2 = 1 - m1;
    if (m1 <= DMIN)      { OUT = -1; NEXT_STATE = Start; NextSampleHit = NEVER; }
    else if (m2 <= DMIN) { OUT =  1; NEXT_STATE = Start; NextSampleHit = NEVER; }
    else {
        t1 = CurrentTime + m1/2*TS;
        t2 = t1 + m2*TS;
        OUT = 1;
        NEXT_STATE = Low;
        NextSampleHit = t1;
    }
    break;
case Low:
    OUT = -1; NEXT_STATE = High; NextSampleHit = t2;
    break;
case High:
    OUT = 1; NEXT_STATE = Start; NextSampleHit = NEVER;   /* 交回固定拍 */
    break;
}

/* ---------- Update ---------- */
STATE = NEXT_STATE;
```

状态转移：`Start --(t1)--> Low --(t2)--> High --(下一个 1/fs 固定拍)--> Start`

### 5b. 带消隐（死区）时间的 PWM

状态机扩为 `Start → Blank1 → Low → Blank2 → High`，新增掩码参数 `dr`（死区时间比）和 `dmin`（最小占空比），Parameters = `1/fs, dr, dmin`。推荐起始值 `dmin = 0.02`、`dr = 0.01`。

```c
/* ---------- Code declarations ---------- */
#include <float.h>
#define NEVER DBL_MAX

typedef enum { Start, Blank1, Low, Blank2, High } state_type;
static state_type NEXT_STATE;
static double TS, DEADTIME, DMIN;

#define m     InputSignal(0,0)
#define OUT   OutputSignal(0,0)
#define STATE DiscState(0)

/* ---------- Start ---------- */
TS       = ParamRealData(0,0);
DEADTIME = ParamRealData(1,0);
DMIN     = ParamRealData(2,0);
STATE = Start;
NextSampleHit = NEVER;

/* ---------- Output ---------- */
double m1, m2, upper;
static double t1, t2, t3, t4;

switch ((state_type) STATE) {
case Start:
    upper = 1 - 2*DEADTIME - DMIN;
    m1 = (m + 1)/2   - DEADTIME;   /* 扣掉死区 */
    m2 = 1 - (m+1)/2 - DEADTIME;
    if (m1 < DMIN)  m1 = DMIN;     /* 下限：防止算成负值 */
    if (m2 < DMIN)  m2 = DMIN;
    if (m1 > upper) m1 = upper;    /* 上限 */
    if (m2 > upper) m2 = upper;

    t1 = CurrentTime + m1/2*TS;
    t2 = t1 + DEADTIME*TS;
    t3 = t2 + m2*TS;
    t4 = t3 + DEADTIME*TS;

    OUT = 1; NEXT_STATE = Blank1; NextSampleHit = t1;
    break;
case Blank1:  OUT =  0; NEXT_STATE = Low;  NextSampleHit = t2; break;
case Low:     OUT = -1; NEXT_STATE = Blank2; NextSampleHit = t3; break;
case Blank2:  OUT =  0; NEXT_STATE = High; NextSampleHit = t4; break;
case High:    OUT =  1; NEXT_STATE = Start; NextSampleHit = NEVER; break;
}

/* ---------- Update ---------- */
STATE = NEXT_STATE;
```

占空比被限制在零以上之后，Start 状态里那两个条件循环就不需要了。

---

## 模板 6：模拟真实 MCU 执行时序（多速率计数器法）

思路（TI 单相离网逆变器应用手册做法）：把 Sample time 设成 **MCU 时钟周期**，C-Script 以连续模式跑，等同于 MCU 主循环；再用计数器分频派生各控制频率。这样写出的代码结构与 C2000 工程一一对应，便于移植。

> ⚠ **手册原文的数字有错，必须自己核对**（详见主文件「模拟真实 MCU 执行」节的对照表）。
> 手册写"83ns → 120MHz"，但 600 计数 = 20 kHz、120 计数 = 100 kHz 反推出的是 **12 MHz**
> （1/83ns = 12.05 MHz）。"120MHz"与"死区 83.3ns"两句是错的，其余三行自洽。
> **换算公式**：`计数 = 1/(f_target × Ts)`。若你的 MCU 真是 120 MHz，
> Ts 取 `8.33e-9`，计数按比例 ×10（600→6000、120→1200）。

**Setup**：Sample time = `8.3e-8`（= 83 ns，对应手册那个 ~12 MHz 的模型；按你自己 MCU 时钟改），
inputs/outputs 按需（手册实例为 **2 路输入**（`[1 1]`）、**21 路输出**（`[1 1 … 1]`，多数用于观测内部变量））。

```c
/* ---------- Code declarations ---------- */
#define V_AC_OUT InputSignal(0,0)   /* 第 1 个输入端口：交流输出电压 */
#define I_L      InputSignal(1,0)   /* 第 2 个输入端口：电感电流 */

static double V_OUT_REF, I_L_REF;
static double V_OUT_Temp, V_RMS_Out;
static double V_RMS_Array[1600];    /* 4 个 50Hz 周期 @ 20kHz 采样 */
static int    V_sample_Counter = 0;
static int    V_RMS_Tempcounter = 0;
static int    DT_Counter = 0;

/* ---------- Start ---------- */
V_OUT_REF = 220;                    /* 输出电压有效值基准 */
I_L_REF   = 0;
for (int i = 0; i < 1600; i++) V_RMS_Array[i] = 70;   /* 初值 70 抑制启动浪涌 */

/* ---------- Update：所有采样 / 控制 / 调制都在这里 ---------- */
/* 1) 20 kHz 交流电压采样 + 真 RMS */
V_sample_Counter++;
if (V_sample_Counter >= 600) {      /* 分频比按实际系统时钟换算 */
    V_sample_Counter = 0;
    V_OUT_Temp = V_AC_OUT;
    V_RMS_Array[V_RMS_Tempcounter] = V_OUT_Temp;
    V_RMS_Tempcounter++;
    if (V_RMS_Tempcounter >= 1600) V_RMS_Tempcounter = 0;

    double sum = 0;
    for (int i = 0; i < 1600; i++) sum += V_RMS_Array[i]*V_RMS_Array[i];
    V_RMS_Out = sqrt(sum/1600);

    /* 2) 电压环：PI + 100Hz 陷波（中心频率 628 rad/s，带宽 5Hz） */
    /* 3) 陷波输出 × 正弦表 → 电流基准 I_L_REF */
}

/* 4) 100 kHz 电流环（另一路计数器分频）：PI + 抗饱和 */

/* 5) 正弦波 / 锯齿波发生器：查表 + 计数器，正弦表长度取 2000 */

/* 6) 死区：后台计数器——连续采样下没有"延时函数"，只能这样加 */
DT_Counter++;
if (DT_Counter >= 11) {             /* 有效值 10；10 × 83ns = 830 ns
                                       （手册原文写"83.3ns"是错的，
                                        那是 120 MHz 下的数，与 Ts 差 10 倍） */
    DT_Counter = 0;
    /* 执行被延后的开关动作 */
}

/* ---------- Output：只做输出 ---------- */
OutputSignal(20,0) = V_RMS_Out;     /* 观测：输出电压真 RMS —— 注意是第 21 路（0 基 20）*/
/* 其余端口：PWM 信号、内部变量观测 */
```

### 这套方法的经验数值与注意事项

- **RMS 窗口长度是精度与延迟的权衡**：数组越长精度越高、更新越慢、额外延迟越大（RMS 滞后会导致输出电压冲过基准）；数组太短会在 RMS 值里引入 50 Hz 纹波，引起控制振荡。手册实测 **4 个工频周期**对本模型最合适。
- **死区只能"延长"不能"缩短"**：后台计数器方案通过推迟关断/导通实现，导通时间可以被拉长，无法被压缩。
- **图腾柱调制**：误差信号的**正负**决定低频桥开关状态，误差与锯齿波的**交点**决定高频桥。过零附近要设阈值，否则会产生 PWM 毛刺（增大阈值可削弱）。
- **电流环 PI 必须加抗饱和**。
- 手册实测：满载启动 THD 2.7%、稳定时间 660 ms；半载→10% 负载 THD 2.6%、259 ms。

---

## 模板 7：复用外部 C 代码 / 移植到 DSP

```c
/* ---------- Code declarations ---------- */
#include "my_controller.c"   /* 模型文件所在目录自动加入 include 搜索路径，可写相对路径 */
```

要点：这是"仿真代码即 DSP 代码"的关键。把控制算法写成独立的 `.c/.h` 放在模型同目录，C-Script 只做适配层（宏映射输入、调用算法、写输出），同一份文件就能直接进 C2000 工程。

---

## 交付检查清单

写完一个 C-Script 后逐条自查：

- [ ] Sample time 选对了吗？（连续 / 离散周期 / 可变 / 混合）
- [ ] 离散状态的个数设了吗？状态在 `Update` 里更新吗？
- [ ] `Output` 里读输入 → 勾了 **Input has direct feedthrough** 吗？
- [ ] 用 `-2` 采样 → `NextSampleHit` 在 `Start` 里初始化成 `NEVER` 了吗？每次都会赋成大于当前时间的值吗？
- [ ] 跨 `Output`/`Update` 共享的变量声明成全局或 `static` 了吗？
- [ ] 输出只在 `Output` 里写吗？
- [ ] 输出有跳变吗？需要 `IsMajorStep` 门控或注册 `ZCSignal` 吗？
- [ ] 数字控制有没有引入不必要的一环延迟？
- [ ] 用到了指针算术访问信号吗？（禁止）

---

## 模板 8：三相 DSOGI-PLL（双 SOGI 锁相环）

> **已拆分为独立源文件，新项目直接用文件版**：`dsogi_pll/dsogi_pll.h`、`dsogi_pll.c` + 三个 `cscript_*.c` 窗口文件 + `test_main.c`。
> 下面这份内联代码是**旧版**（后向欧拉 + 偏激进增益），保留仅作原理参考。两处关键修正见本节末尾「实测修正」，别直接抄。

输入三相相电压，输出锁相角 θ、估计频率、正序 dq 分量。**三相必须用 DSOGI，不能用单 SOGI**——单 SOGI 只吃单相，三相不平衡时锁相角会带 2 倍频纹波；DSOGI 靠正序提取（PNSC）抑制掉负序。

信号链：`三相 → Clarke(αβ) → 双 SOGI-QSG → PNSC(正序) → Park(dq) → PI → 1/s → θ`，ω 反馈回 SOGI 中心频率（频率自适应）。

**Setup**：inputs = 3（va / vb / vc 各一个端子），outputs = 6，disc. states = **9**（Tustin 需额外存上一拍输入），Sample time = `1/fs`（如 10 kHz），**勾选 Input has direct feedthrough**，Parameters = `fn, fs, k_sogi, kp, ki`。建议放进 Subsystem 并把 fn/fs/k_sogi/kp/ki 做成掩码参数。

**如何在 PLECS 里 include 外部文件**（长期维护的正确姿势）：

| 窗口 | 内容 |
|---|---|
| Code declarations | `#include "dsogi_pll.c"` 换行 `#include "cscript_declarations.h"` |
| Start | `#include "cscript_start.c"` |
| Output | `#include "cscript_output.c"` |
| Update | `#include "cscript_update.c"` |

**拆分原则**：`InputSignal` / `OutputSignal` / `DiscState` / `ParamRealData` 依赖 PLECS 生成的包裹函数上下文，**放进外部函数体里不保证能编译**。正确切法是——算法写成纯 C（一个宏都不碰），窗口里只留「读宏 → 调函数 → 写宏」。这样算法部分能在 VS 里独立编译、打断点、跑单元测试，也能直接搬进 C2000。

### 实测修正（fs=10 kHz、k_sogi=√2、50 Hz 电网，GCC -O2 实跑）

1. **SOGI 必须用 Tustin（双线性）而不是后向欧拉。** 后向欧拉在 200 点/周波下给 SOGI 带来约 2% 幅值衰减和约 2° 相位滞后，实测 `vd` 稳态只有 304.2 V（应为 311 V），锁相角有 2.25° 静差。换 Tustin 后 `vd = 310.987`（误差 0.004%）。代价：需额外两个离散状态存上一拍输入。
   ```
   h = Ts/2;  q = ω·h;  p = k·q;  det = 1 + p + q²
   r1 = (1-p)·x1⁻ - q·x2⁻ + p·(u + u⁻);   r2 = q·x1⁻ + x2⁻
   x1 = (r1 - q·r2)/det;   x2 = (q·r1 + (1+p)·r2)/det
   ```
2. **增益不能照搬「忽略 SOGI 的 SRF-PLL」整定公式。** 那套公式给出 kp=200/ki=20000（ωn=141），实测能锁但启动瞬态达 8.9 Hz、耗时 0.19 s；ωn 超过约 **150** 会直接失稳、频率打到 ±15 Hz 限幅。原因是 SOGI 的极点（k=√2 时约 −222±j222）与环路同量级，会参与闭环吃掉相位裕度。
   **推荐起点：kp = 100，ki = 5000**（ωn≈70.7、ζ≈0.707），启动锁定 ≈60 ms，+30° 相位阶跃恢复 ≈84 ms。可用区间 ωn∈[60,100]、ζ∈[0.7,1.0]。改了 `k_sogi` 要重扫——k 越小 SOGI 极点越慢，允许的 ωn 也越低。

```c
/* ==================== Code declarations ==================== */
#include <math.h>
#define TWO_PI 6.283185307179586
#define SQRT3  1.7320508075688772
#define DF_MAX 15.0            /* 允许偏离额定频率 ±15 Hz */

#define va  InputSignal(0,0)
#define vb  InputSignal(1,0)
#define vc  InputSignal(2,0)

#define THETA OutputSignal(0,0)   /* 锁相角 rad，[0, 2π)      */
#define FREQ  OutputSignal(1,0)   /* 估计频率 Hz              */
#define VD    OutputSignal(2,0)   /* 正序 d 轴 = 相电压峰值   */
#define VQ    OutputSignal(3,0)   /* 正序 q 轴，锁定后 ≈ 0    */
#define VA_P  OutputSignal(4,0)   /* 正序 α⁺                  */
#define VB_P  OutputSignal(5,0)   /* 正序 β⁺                  */

static double fn, Ts, k_sogi, kp, ki, w_nom;

/* 离散状态：0/1 = SOGI_α 的 x1/x2(q)
             2/3 = SOGI_β 的 x1/x2(q)
             4 = PI 积分项   5 = θ   6 = ω(上一次估计) */
#define S_A1 DiscState(0)
#define S_A2 DiscState(1)
#define S_B1 DiscState(2)
#define S_B2 DiscState(3)
#define S_I  DiscState(4)
#define S_TH DiscState(5)
#define S_W  DiscState(6)

/* Output 算完、Update 提交用的暂存 */
static double g_a1, g_a2, g_b1, g_b2, g_I, g_th, g_w;

/* ==================== Start ==================== */
fn     = ParamRealData(0,0);
Ts     = 1.0/ParamRealData(1,0);
k_sogi = ParamRealData(2,0);
kp     = ParamRealData(3,0);
ki     = ParamRealData(4,0);
w_nom  = TWO_PI*fn;

S_A1 = S_A2 = S_B1 = S_B2 = 0.0;
S_I  = 0.0;
S_TH = 0.0;
S_W  = w_nom;

/* ==================== Output ==================== */
double valpha, vbeta;
double a_c, b_c, den;
double n_a1, n_a2, n_b1, n_b2;
double va_p, vb_p, s_t, c_t, vd, vq, vqn, amp;
double w_max, w_min, w_out, I_new, th_new;

/* 1) Clarke（幅值不变） */
valpha = (2.0/3.0)*va - (1.0/3.0)*vb - (1.0/3.0)*vc;
vbeta  = (vb - vc)/SQRT3;

/* 2) DSOGI 正交信号发生器（后向欧拉，中心频率用上一次的 ω） */
a_c = Ts*k_sogi*S_W;
b_c = Ts*S_W;
den = 1.0 + a_c + b_c*b_c;
n_a1 = (S_A1 + a_c*valpha - b_c*S_A2)/den;
n_a2 = S_A2 + b_c*n_a1;
n_b1 = (S_B1 + a_c*vbeta  - b_c*S_B2)/den;
n_b2 = S_B2 + b_c*n_b1;

/* 3) 正序提取 PNSC */
va_p = 0.5*(n_a1 - n_b2);
vb_p = 0.5*(n_a2 + n_b1);

/* 4) Park（用上一拍的 θ，这是标准做法） */
s_t = sin(S_TH);
c_t = cos(S_TH);
vd  = va_p*c_t + vb_p*s_t;
vq  = -va_p*s_t + vb_p*c_t;

/* 5) 归一化：让 kp/ki 与电网幅值无关 */
amp = sqrt(va_p*va_p + vb_p*vb_p);
vqn = (amp > 1e-3) ? vq/amp : 0.0;

/* 6) PI → ω（clamping 抗饱和） */
w_max = TWO_PI*(fn + DF_MAX);
w_min = TWO_PI*(fn - DF_MAX);
I_new = S_I + Ts*vqn;
w_out = w_nom + kp*vqn + ki*I_new;
if      (w_out > w_max) { w_out = w_max; if (vqn > 0.0) I_new = S_I; }
else if (w_out < w_min) { w_out = w_min; if (vqn < 0.0) I_new = S_I; }

/* 7) 相位积分并折返到 [0, 2π) */
th_new = S_TH + Ts*w_out;
while (th_new >= TWO_PI) th_new -= TWO_PI;
while (th_new <  0.0)    th_new += TWO_PI;

/* 8) 写输出 */
THETA = th_new;  FREQ = w_out/TWO_PI;
VD = vd;  VQ = vq;  VA_P = va_p;  VB_P = vb_p;

/* 9) 暂存，交给 Update 提交 */
g_a1 = n_a1; g_a2 = n_a2;
g_b1 = n_b1; g_b2 = n_b2;
g_I  = I_new; g_th = th_new; g_w = w_out;

/* ==================== Update ==================== */
S_A1 = g_a1; S_A2 = g_a2;
S_B1 = g_b1; S_B2 = g_b2;
S_I  = g_I;  S_TH = g_th;  S_W = g_w;
```

### 增益整定

归一化后闭环是标准二阶：`kp = 2ζωn`，`ki = ωn²`，其中 `ωn = 4/(ζ·ts)`（ts 为 2% 整定时间）。

| ts (ζ=0.707) | ωn | kp | ki |
|---|---|---|---|
| 30 ms | 189 | 267 | 35600 |
| 40 ms | 141 | 200 | 20000 |
| 50 ms | 113 | 160 | 12800 |

`k_sogi` 默认 **1.414**（√2）：越小滤波越强、响应越慢，常用 0.7~2。

### LOCK 判据：用「两个施密特」设计（并网/穿越场景的关键）

PLL 的 `LOCK` 输出**不是跟踪能力指标**，而是"可并网/可继续保持并网"的**许可信号**。
若 LOCK 参与并网逻辑，它一旦抖动就可能误脱网。判据要同时满足三条才能算"健康"：

| 判据 | 获得门限（严格） | 保持门限（宽松） |
|---|---|---|
| 正序幅值 \|v+\| | > 30% 额定峰值 | > 10% 额定峰值 |
| 相位误差 \|vq\|/\|v+\| | < 0.05（≈2.9°） | < 0.40（≈23.6°） |
| 频差 \|f−fn\| | < 1 Hz | < 8 Hz |

**两个施密特**：
1. **门限施密特**——"获得"用严格值（防误合闸），"保持"用宽松值（防瞬态误触发）。
2. **计数器施密特**——`cap = T_ON + T_OFF`；判据成立时 `min(+ts, cap)`，
   违反时 `max(−ts, 0)`；`LOCK = (cnt >= T_ON)`。
   ⇒ **获得需 T_ON 连续成立、解除需 T_OFF 连续违反**（真正的抗扰窗）。

**经典错误写法**（看起来有 T_OFF 抗扰窗，实际没有）：

```c
cnt = min(cnt + ts, T_ON);        /* ✗ 封顶刚好 = 阈值 */
lock = (cnt >= T_ON);             /* 任何一拍违反 → 立刻跌破 → 立刻解锁 */
```

封顶值必须 **> 阈值**（如 `cap = T_ON + T_OFF`），否则"解除延迟 = T_OFF"的承诺完全没实现。
实测：旧写法下故障起始的 SOGI 幅值阶跃暂态（`vq_norm` 冲到 21.3°、`|Δf|` 6.9 Hz）
**一枪打死 LOCK**，整段故障窗保持 0（用户报"重新锁定要 0.5 s"）；
改为双施密特后，扰动在穿越曲线内时 LOCK 全程 = 1、一次不掉，
真失压（5% 额定）仍在故障后约 10 ms 内掉锁（安全边界完好）。

**连带要点**：
- **保持门限必须罩住"幅值阶跃引发的 SOGI 暂态"**（不是相位失跟）——按各场景实测峰值
  整定（实测 0.36~0.76 区间）；**改门限后必须重跑全套场景**。
- **T_ON 与"解除时间"无关**（解除时间由 T_OFF 决定）⇒ T_ON 可以从 30 ms 砍到 5 ms，
  不牺牲安全性，却能显著加快恢复。
- **判断跟踪能力要看相位误差与频率，不要看 LOCK**。
- **测相位误差时必须把"源施加的相位跳变"计入参考**：源若在故障窗内用
  `v = Vpk·k·sin(θ+Δ)`，期间真实相位就是 `ωt + Δ − 90°`；不修正时量出的误差
  恰好 ≈ Δ，看起来像"永远追不上"，实际是完美跟上。

### 验证

平衡三相 220 Vrms（峰值 311 V）输入，锁定后：`FREQ → 50`、`VD → 311`、`VQ → ≈0`、`VA_P/VB_P` 是幅值 311 的正交正弦。再把 a 相幅值砍 30% 造不平衡，`VD` 的 2 倍频纹波应远小于单 SOGI 时的值——这就是 DSOGI 的价值。

### 变体

- **要负序分量**：`vα⁻ = 0.5*(n_a1 + n_b2)`，`vβ⁻ = 0.5*(n_b1 - n_a2)`，加两个输出端子即可。
- **想用连续状态**：不推荐。整条链得搬进 `Derivative` 才能在里面读输入，容易踩 direct feedthrough。变步长仿真里直接跑这个离散块就行。
- **多路复用接线**：若想用 1 个输入端子 + Signal Multiplexer，把 `va/vb/vc` 改成 `InputSignal(0,0)/InputSignal(0,1)/InputSignal(0,2)`、Number of inputs 改为 1 即可。
