# PLECS 元件图鉴（从官方库 + 356 个示例反推）

> 数据来源：`<PLECS>\components.plecs`（5597 个元件实例，参数名权威）+ `<PLECS>\examples|demos|workspace|toolbox` 下 **356 个 `.plecs` 文件** （`Connection` 里的 `SrcTerminal/DstTerminal` 反推端子号）。
>
> **`n=` 列** = 该 Type 在官方库里出现的元件个数；**`files` 列** = 有多少个官方模型接线时用到它。
> `files` 越大 → 端子号结论越可信。`files=0` 表示只有元件定义、示例里没人接线（端子号需自行实测）。

## 三处容易误读的统计口径（先看这里）

1. **`Goto` / `Scope` / `Input` / `Port` 的 `files=0` 不是"没人用"** ——
   它们是**不靠 `Connection` 接线**的元件：
   - `Goto`/`From`/`Label` 靠 **`Tag` 字符串配对**（`Connection` 里只出现 `From` 那一端），
     所以 `Goto` 的接线证据永远是 0。
   - `Scope` 是**采集终端**：只有 `Connection` 指向它，它自己不出去；
     统计里那点 `terms=[1..7]` 来自少数"Scope 当中间件"的写法。
   - `Input`/`Port` 只在 **Subsystem 内部**用（端口的定义侧），顶层几乎不接线。

2. **`Subsystem` 的端子号 1..19 是"实例各不相同"** —— 它取决于该子系统的
   `Terminal{Index}` 声明，不是固定表。**必须读该 Subsystem 元件自己的 `Terminal` 块**。

3. **`CScript` 的 `terms=[1..8]` 只是"见过最多 8 个"** —— 实际端子数由
   `NumInputs` / `NumOutputs` 两个**宽度列表**决定：
   `"[7 5]"` = 2 个输入口（宽 7 + 宽 5），端子号就是 1、2（连续编号，1-based）。

## 怎么用这张表

1. **参数名照抄**：`Parameter { Variable "<名字>" Value "<值>" }` 里的 `Variable` 必须与表里一致。
2. **端子号看 `terms`**：`Connection { SrcComponent ... SrcTerminal N ... }` 的 `N` 只能是表里出现过的值。
3. **端子语义按惯例**：电气件 1/2 = 两端（`Direction` 决定画布方向，与编号无关）；
   受控源 1(+)/2(-)/3(信号)；测量件 1/2 = 被测两端、3 = 输出信号。
4. **参数全集不等于最小值**：只写必需参数 PLECS 能读（缺的用默认值）。

⚠ **本表不是"完整语法"**：从官方实例统计得来，可能与最新版新增参数有出入。
   遇到表里没有的 Type，去 `components.plecs` 里搜 `Type <名字>` 现查。

## 电气无源件

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `Resistor` | 162 | 90 | 1,2 | `R` |
| `Capacitor` | 8 | 64 | 1,2 | `C`, `v_init`, `Configuration` |
| `Inductor` | 102 | 87 | 1,2,3 | `L`, `i_init` |
| `SatInductor` | 27 | 0 | — | `I`, `Phi`, `i_init` |
| `VarInductor` | 14 | 0 | — | `Coupling`, `i_init` |

## 开关器件

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `Diode` | 61 | 46 | 1,2 | `Vf`, `Ron`, `thermal`, `Rth`, `T_init`, `Configuration` |
| `Igbt` | 28 | 9 | 1,2,3,4 | `Vf`, `Ron`, `s_init`, `thermal`, `Rth`, `T_init` |
| `IgbtWithDiode` | 79 | 17 | 1,2,3 | `s_init`, `thermal`, `Rth`, `T_init` |
| `Mosfet` | 7 | 14 | 1,2,3 | `Ron`, `s_init`, `thermal`, `Rth`, `T_init` |
| `Thyristor` | 14 | 5 | 1,2,3 | `Vf`, `Ron`, `s_init`, `thermal`, `Rth`, `T_init` |
| `DirectionControlledSwitch` | 11 | 0 | — | `GateLogic`, `SwitchType`, `R`, `Configuration` |

## 电源 / 测量

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `VoltageSource` | 35 | 30 | 1,2,3 | `DiscretizationBehavior`, `StateSpaceInlining` |
| `CurrentSource` | 63 | 11 | 1,2,3 | `DiscretizationBehavior`, `StateSpaceInlining` |
| `DCVoltageSource` | 6 | 0 | — | `V` |
| `ThreePhaseVoltageSource` | 1 | 16 | 1,2,3,4 | `V`, `w`, `phi`, `neutral` |
| `Voltmeter` | 86 | 113 | 1,2,3 | — |
| `Ammeter` | 50 | 88 | 1,2,3 | — |
| `ThreePhaseMeter` | 1 | 0 | — | `voltage` |
| `PlecsProbe` | 1 | 0 | — | — |

## 磁 / 变压器

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `Transformer` | 45 | 8 | 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16 | `Windings`, `n`, `Polarity`, `Lm`, `im0` |
| `MagneticPort` | 11 | 0 | — | `Index`, `Width` |

## 信号源

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `SineGenerator` | 9 | 35 | 1 | `Amplitude`, `Bias`, `Frequency`, `Phase`, `Units`, `Configuration` |
| `Step` | 1 | 57 | 1 | `Time`, `Before`, `After`, `DataType` |
| `Clock` | 2 | 11 | 1 | — |
| `PulseGenerator` | 3 | 50 | 1 | `Hi`, `Lo`, `f`, `DutyCycle`, `Delay`, `DataType` |
| `TriangleGenerator` | 7 | 0 | — | `Min`, `Max`, `f`, `DutyCycle`, `Delay` |

## 信号运算

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `Gain` | 264 | 102 | 1,2 | `K`, `Multiplication`, `DataType`, `Configuration` |
| `Sum` | 189 | 115 | 1,2,3,4,5 | `IconShape`, `Inputs`, `DataType` |
| `Product` | 116 | 88 | 1,2,3,4 | `IconShape`, `Inputs`, `DataType`, `Configuration` |
| `Constant` | 92 | 118 | 1 | `Value`, `DataType`, `Configuration` |
| `Abs` | 10 | 15 | 1,2 | — |
| `Math` | 32 | 23 | 1,2,3 | `Operator` |
| `MinMax` | 33 | 27 | 1,2,3,4 | `Operation`, `Inputs`, `Configuration` |
| `Trigonometry` | 43 | 16 | 1,2,3 | `Operator`, `Unit` |
| `Lookup2D` | 11 | 5 | 1,2,3 | `x`, `y`, `f(x,y)`, `ZeroCrossingSignals` |
| `Saturation` | 18 | 64 | 1,2,3,4 | `UpperLimit`, `LowerLimit` |
| `Relay` | 1 | 18 | 1,2 | `OnSwitchValue`, `OffSwitchValue`, `OnOutputValue`, `OffOutputValue`, `InitialState`, `DataType` |
| `Offset` | 27 | 0 | — | `Offset`, `DataType` |
| `LogicalOperator` | 47 | 68 | 1,2,3,4 | `Operator`, `Inputs`, `Configuration` |
| `RelationalOperator` | 34 | 30 | 1,2,3 | `Operator` |
| `ConstantRelationalOperator` | 67 | 0 | — | `Operator`, `Threshold`, `Configuration` |
| `HitCrossing` | 11 | 0 | — | `Offset`, `Direction`, `ShowOutput` |

## 动态 / 滤波

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `Integrator` | 9 | 40 | 1,2,3,4,5 | `ExternalReset`, `InitialConditionSource`, `x0`, `ShowStatePort`, `EnableWrapping`, `UpperLimit`, `LowerLimit`, `Configuration` |
| `TransferFunction` | 4 | 35 | 1,2 | `Numerator`, `Denominator`, `X0`, `Configuration` |
| `Delay` | 15 | 58 | 1,2 | `N`, `X0`, `Ts`, `Configuration` |
| `ZeroOrderHold` | 36 | 37 | 1,2 | `Ts`, `Configuration` |
| `Memory` | 19 | 16 | 1,2 | `X0`, `Configuration` |
| `StateSpace` | 1 | 0 | — | `A`, `B`, `C`, `D`, `X0` |

## 路由 / 复用

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `SignalMux` | 252 | 122 | 1,2,3,4,5,6,7,8,9,10 | `Width`, `Configuration` |
| `SignalDemux` | 94 | 112 | 1,2,3,4,5,6,7,8,9,10,11,12,13 | `Width`, `Configuration` |
| `SignalSelector` | 29 | 45 | 1,2 | `InputWidth`, `OutputIndices`, `Configuration` |
| `SignalSwitch` | 8 | 0 | — | `Criteria`, `Threshold` |
| `Goto` | 71 | 0 | 1 | `Tag`, `Visibility`, `Configuration` |
| `From` | 112 | 79 | 1 | `Tag`, `Visibility`, `Configuration` |
| `Label` | 1 | 3 | 1 | `Tag`, `Visibility` |
| `WireMux` | 52 | 0 | — | `Width` |
| `WireSelector` | 12 | 0 | — | `InputWidth`, `OutputIndices` |
| `Reference` | 82 | 0 | — | `TargetPortIndices`, `buffer_size`, `T_d`, `x0`, `T_period`, `DeadTimeSource`, `Rounding`, `y_init`, `TimeDelaySource` … |
| `Input` | 855 | 0 | — | `Index`, `Width`, `InitialOutput`, `HasDirectFeedthrough`, `Configuration`, `DataType` |
| `Port` | 540 | 0 | — | `Index`, `Width`, `Configuration` |
| `Output` | 437 | 48 | 1,2,3 | `Index`, `Width`, `DataType`, `Configuration`, `InitialOutput`, `OutputWhenDisabled` |

## 自定义 / 容器

| Type | n= | files | 端子号 | 参数名（`Variable`） |
|---|---|---|---|---|
| `CScript` | 52 | 41 | 1,2,3,4,5,6,7,8 | `DialogGeometry`, `NumInputs`, `NumOutputs`, `NumContStates`, `NumDiscStates`, `NumZCSignals`, `DirectFeedthrough`, `Ts`, `Parameters` … |
| `Subsystem` | 286 | 116 | 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 | `R`, `L`, `J`, `F`, `wm0`, `thm0`, `n`, `p`, `Lls` … |
| `ConfigurableSubsystem` | 105 | 0 | — | `semiSymbol`, `assert`, `n`, `N`, `L`, `R`, `Ts`, `C`, `rectifierType` … |
| `Function` | 297 | 0 | — | `f(u)` |
| `Scope` | 1 | 0 | 1,2,3,4,5,6,7 | — |

## 其他高频 Type（≥10 个实例，未归类）

| Type | n= | files | 端子号 |
|---|---|---|---|
| `Assertion` | 37 | 0 | — |
| `RotationalPort` | 27 | 0 | — |
| `ControlledTorque` | 22 | 0 | — |
| `RotationalSpeedSensor` | 21 | 0 | — |
| `Inertia` | 17 | 0 | — |
| `RotationalReference` | 16 | 0 | — |
| `RotationalDamper` | 16 | 0 | — |
| `AngleSensor` | 13 | 0 | — |

## 电气件端子语义（实测惯例）

| 元件 | 端子 | 含义 |
|---|---|---|
| `Resistor` / `Capacitor` / `Inductor` | 1, 2 | 两端，无极性（`Inductor` 偶见 3 = 饱和/抽头口） |
| `Diode` | 1 = 阳极(A), 2 = 阴极(K) | 电流 A→K |
| `IgbtWithDiode` / `Mosfet` / `Igbt` / `Thyristor` | 1 = 集电极/漏极, 2 = 发射极/源极, 3 = 门极 | `Igbt` 另有 4（Kelvin/温度，视型号） |
| `VoltageSource` / `CurrentSource` | 1 = +, 2 = −, 3 = 信号（受控型） | 理想独立源只有 1/2 |
| `ThreePhaseVoltageSource` | 1,2,3 = A/B/C, 4 = 中性点 | `neutral` 参数决定是否引出 |
| `Voltmeter` / `Ammeter` | 1,2 = 被测端, 3 = 测量值输出 | 3 是**信号**口，走 `Signal` 连线 |
| `Transformer` | 1..2n 按绕组顺序 | `Windings` 决定个数 |

## 信号件端子语义

| 元件 | 端子 | 含义 |
|---|---|---|
| `Gain` / `TransferFunction` / `Delay` / `ZeroOrderHold` / `Memory` | 1 = 输入, 2 = 输出 | |
| `Sum` | 1 = 输出, 2..N+1 = 各输入 | **输出是 1，输入从 2 开始**（易错） |
| `Product` | 1 = 输出, 2..N = 输入 | |
| `Integrator` | 1 = 输入, 2 = 输出, 3 = 外部复位, 4 = 状态口 | 视 `ExternalReset`/`ShowStatePort` 开关 |
| `SignalMux` | 1..N = 输入, N+1 = 输出 | `Width` 决定 N |
| `SignalDemux` | 1 = 输入, 2..N+1 = 输出 | |
| `SignalSelector` | 1 = 输入, 2 = 输出 | `OutputIndices` 选通道 |
| `Scope` | 1..N = 输入 | 只入不出 |
| `Output`（画布） | 1 = 输入 | `Index` = 端子序号, `Width` = 宽度 |
| `Goto` / `From` | 1 | `Tag` 配对；`Visibility` 两侧都 = 2 |
