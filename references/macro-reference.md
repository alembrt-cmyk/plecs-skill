# PLECS C-Script 宏完整参考

R = 只读，R/W = 可读写，W = 只写。基于 PLECS 5.0 官方文档。

## 端子与数量

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `NumInputTerminals` | int | R | 输入端子数 |
| `NumOutputTerminals` | int | R | 输出端子数 |
| `NumInputSignals(int i)` | int | R | 第 i 个输入端子的信号元素数（宽度） |
| `NumOutputSignals(int i)` | int | R | 第 i 个输出端子的信号元素数 |
| `NumContStates` | int | R | 连续状态个数 |
| `NumDiscStates` | int | R | 离散状态个数 |
| `NumZCSignals` | int | R | 零穿越信号个数 |
| `NumParameters` | int | R | 用户参数个数 |
| `NumSampleTimes` | int | R | 采样时间个数 |

## 时间、采样、步长

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `CurrentTime` | double | R | 当前仿真时间；Start 里返回仿真起始时间 |
| `NextSampleHit` | double | R/W | 下次执行时刻。仅对注册了 discrete-variable 采样的模块有意义；可在 Output 或 Update 赋值；**最迟在 Update 调用后必须大于当前时间**，否则仿真中止 |
| `IsMajorStep` | int | R | 处于 major time step 返回 1 |
| `IsSampleHit(int i)` | int | R | 第 i 路采样（0 基行号）是否在当前步命中 |
| `SampleTimePeriod(int i)` | — | R | 第 i 个采样时间的周期；继承型返回实际解析值 |
| `SampleTimeOffset(int i)` | — | R | 第 i 个采样时间的偏移 |

## 信号

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `InputSignal(int i, int j)` | double | R | 第 i 个输入端子的第 j 个元素。**在 Output 里读输入必须勾选 "Input has direct feedthrough"** |
| `OutputSignal(int i, int j)` | double | R/W | 第 i 个输出端子的第 j 个元素。**只能在 Output function 中写** |

⚠️ 输入输出信号**不在连续内存中**，指针算术（`&OutputSignal(0,0)` 再偏移）是错误用法。

## 状态

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `ContState(int i)` | double | R/W | 第 i 个连续状态。**minor step 期间不可修改** |
| `ContDeriv(int i)` | double | R/W | 第 i 个连续状态的导数，在 Derivative 中写 |
| `DiscState(int i)` | double | R/W | 第 i 个离散状态。**minor step 期间不可修改**。Start 里初始化，Update 里更新 |

## 零穿越

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `ZCSignal(int i)` | double | R/W | 第 i 个零穿越信号 |

在 Output 里根据输入/状态/时间赋值；求解器监视信号变号并缩小步长，使下一个 major step 落在第一次过零之后，从而精确定位不连续点。典型用法：

```c
ZCSignal(0) = InputSignal(0,0) - 1.;
```

配合 `IsMajorStep` 使用：输出只在 major step 改变，零穿越信号在大小步长都更新。

## 参数

| 宏 | 类型 | 访问 | 含义 |
|---|---|---|---|
| `ParamNumDims(int i)` | int | R | 第 i 个参数的维数 |
| `ParamDim(int i, int j)` | int | R | 第 i 个参数第 j 维的大小；字符串返回以 char 计的长度 |
| `ParamRealData(int i, int j)` | double | R | 第 i 个参数第 j 个元素，**j 是线性索引**。参数是字符串时会运行时报错 |
| `ParamStringData(int i)` | char* | R | 指向 UTF-8 零结尾 C 字符串；参数非字符串时返回 NULL 或报错 |

多维参数线性索引：
```c
int elIdx = rowIdx + numRows * (colIdx + numCols * pageIdx);
double v = ParamRealData(0, elIdx);
```

## 自定义状态（Store / Restore Custom State）

| 宏 | 说明 |
|---|---|
| `WriteCustomStateDouble(double val)` | 写入一个 double |
| `WriteCustomStateInt(int val)` | 写入一个 int |
| `WriteCustomStateData(void *data, int len)` | 写入 len 字节原始数据 |
| `ReadCustomStateDouble()` | 读出一个 double |
| `ReadCustomStateInt()` | 读出一个 int |
| `ReadCustomStateData(void *data, int len)` | 读出 len 字节 |

⚠️ 优先用 `Double`/`Int` 版本，别用 `void*` 版本——后者无法处理大小端。存 double 向量应循环调用 `WriteCustomStateDouble`。

## 诊断

| 宏 | 说明 |
|---|---|
| `SetErrorMessage(char *msg)` | 当前步结束后终止仿真并报错，`msg` 必须指向静态内存，通常后接 `return` |
| `SetWarningMessage(char *msg)` | 报警告；C-Script 函数返回时警告状态自动重置 |

## 已弃用（PLECS 3.7 起）

仅适用于**单输入端子 + 单输出端子**的 C-Script，仍被支持但不建议新代码使用：

| 弃用宏 | 等价写法 |
|---|---|
| `NumInputs` | `NumInputSignals(0)` |
| `NumOutputs` | `NumOutputSignals(0)` |
| `Input(int i)` | `InputSignal(0, i)` |
| `Output(int i)` | `OutputSignal(0, i)` |

## 建模不连续性的规则

- 输出信号在 minor step 期间应当**连续且平滑**；跳变和尖锐折点只允许出现在 major step。
- 用 `IsMajorStep` 判断当前是否为 major step。
- 不要假设 Output 两次调用之间时间是单调递增的——求解器可能在同一 major step 内多次调用，minor step 期间时间会前后跳。
- 需要"每个 major step 恰好执行一次"的代码，放 `Update`。
