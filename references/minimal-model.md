# 最小可跑模型（真机验证通过，可直接抄）

一个 8 元件、5 条 Connection 的完整 `.plecs`：**正弦源 → 受控电压源 → RC 低通 → 电压表 → Scope + 模型级 Output**。

**验证记录（2026-11-04，PLECS 4.7.5 实测）**

| 项 | 结果 |
|---|---|
| `load` | 返回 0；`plecs.get` 读到 `Name=mini_demo` |
| `simulate`（0.06 s，MaxStep 5e-6） | 返回 `Time` 12004 点 + `Values` 1 条曲线 |
| 幅值 | 实测 **9.5403 V** vs 理论 **9.5403 V**（误差 **0.00 %**） |
| 相位滞后 | 实测 **17.44°** vs 理论 **17.44°**（误差 **0.00°**） |
| 静态自检 | 纯 ASCII ✓ / 模型级 Terminal ✓ / 无悬空 ✓ / 无重复源端子 ✓ |

理论值推导：`R=10 Ω`、`C=100 µF` ⇒ `τ = RC = 1 ms`、`f = 50 Hz`；
`|H| = 1/√(1+(2πfτ)²) = 0.95403`，`∠H = −atan(2πfτ) = −17.44°`，输入 10 V 峰值。

---

## 四个必须照做的地方（真机踩过）

1. **`SineGenerator` 输出的是信号，不是电压**。
   直接用 `Wire` 连到电路 = Wire/Signal 混用，报
   `Unconnected terminals overlapped by other elements`。
   正解：`SineGenerator.1 --(Signal)--> VoltageSource.3`（第 3 端是受控输入），
   `VoltageSource` 的 1/2 才是电气口。
2. **扇出必须写成 `Branch`**（一条 `Connection` + 多个 `Branch{...}`）。
   一个源端子只能有一条 `Connection`；拆成多条会**静默丢掉其中几条**。
   官方 32324 条 Connection 里有 **6232 条**是这种多目的地 Branch 写法。
3. **`Connection` 的 `Type` 决定电气/信号**：`Wire` = 电气，`Signal` = 信号，不能混。
4. **顶层出数靠模型级 `Terminal { Type Output; Index "1" }`**（在 `Schematic {` 之前）。
   只放画布上的 `Component { Type Output }` 时 `simulate` 返回 `{'Time': [], 'Values': []}`。

---

## 完整文件（`mini_demo.plecs`）

```text
Plecs {
  Name          "mini_demo"
  Terminal {
    Type          Output
    Index         "1"
  }
  Schematic {
    Component {
      Type          SineGenerator
      Name          "SIN"
      Show          on
      Position      [30, 160]
      Direction     right
      Flipped       off
      Parameter {
        Variable      "Amplitude"
        Value         "10"
        Show          off
      }
      Parameter {
        Variable      "Frequency"
        Value         "2*pi*50"
        Show          off
      }
      Parameter {
        Variable      "Bias"
        Value         "0"
        Show          off
      }
      Parameter {
        Variable      "Phase"
        Value         "0"
        Show          off
      }
      Parameter {
        Variable      "Units"
        Value         "1"
        Show          off
      }
    }
    Component {
      Type          VoltageSource
      Name          "V1"
      Show          on
      Position      [120, 100]
      Direction     up
      Flipped       off
      Parameter {
        Variable      "DiscretizationBehavior"
        Value         "2"
        Show          off
      }
      Parameter {
        Variable      "StateSpaceInlining"
        Value         "1"
        Show          off
      }
    }
    Component {
      Type          Resistor
      Name          "R1"
      Show          on
      Position      [190, 60]
      Direction     right
      Flipped       off
      Parameter {
        Variable      "R"
        Value         "10"
        Show          off
      }
    }
    Component {
      Type          Capacitor
      Name          "C1"
      Show          on
      Position      [260, 60]
      Direction     down
      Flipped       off
      Parameter {
        Variable      "C"
        Value         "100e-6"
        Show          off
      }
      Parameter {
        Variable      "v_init"
        Value         "0"
        Show          off
      }
    }
    Component {
      Type          Ground
      Name          "G1"
      Show          on
      Position      [260, 140]
      Direction     up
      Flipped       off
    }
    Component {
      Type          Voltmeter
      Name          "VM1"
      Show          on
      Position      [260, 15]
      Direction     down
      Flipped       off
    }
    Component {
      Type          Scope
      Name          "SC1"
      Show          on
      Position      [370, 15]
      Direction     right
      Flipped       off
    }
    Component {
      Type          Output
      Name          "OUT"
      Show          on
      Position      [370, 95]
      Direction     right
      Flipped       off
      Parameter {
        Variable      "Index"
        Value         "1"
        Show          off
      }
      Parameter {
        Variable      "Width"
        Value         "-1"
        Show          off
      }
    }
    Connection {
      Type          Signal
      SrcComponent  "SIN"
      SrcTerminal   1
      DstComponent  "V1"
      DstTerminal   3
    }
    Connection {
      Type          Wire
      SrcComponent  "V1"
      SrcTerminal   1
      DstComponent  "R1"
      DstTerminal   1
    }
    Connection {
      Type          Wire
      SrcComponent  "R1"
      SrcTerminal   2
      Branch {
        DstComponent  "C1"
        DstTerminal   1
      }
      Branch {
        DstComponent  "VM1"
        DstTerminal   1
      }
    }
    Connection {
      Type          Wire
      SrcComponent  "V1"
      SrcTerminal   2
      Branch {
        DstComponent  "C1"
        DstTerminal   2
      }
      Branch {
        DstComponent  "G1"
        DstTerminal   1
      }
      Branch {
        DstComponent  "VM1"
        DstTerminal   2
      }
    }
    Connection {
      Type          Signal
      SrcComponent  "VM1"
      SrcTerminal   3
      Branch {
        DstComponent  "SC1"
        DstTerminal   1
      }
      Branch {
        DstComponent  "OUT"
        DstTerminal   1
      }
    }
  }
}
```

---

## 生成它（用技能自带 builder）

```bash
python scripts/plecs_builder.py --demo -o mini_demo.plecs
python scripts/plecs_builder.py --check mini_demo.plecs     # 静态自检，要 rc=0
```

然后跑：

```python
import xmlrpc.client
P = xmlrpc.client.ServerProxy('http://localhost:1080/RPC2', allow_none=True)
P.plecs.load(r'mini_demo.plecs')                      # 0 = 成功
out = P.plecs.simulate('mini_demo', {'SolverOpts': {'TimeSpan': 0.06, 'MaxStep': 5e-6}})
print(len(out['Time']), [len(c) for c in out['Values']])   # 12004  [12004]
P.plecs.close('mini_demo')
```

**`Values` 的布局**（实测，容易搞错）：`Values` 是**每条曲线一行**的列表 ——
`Values[0]` 就是第 1 条曲线的全部采样点（长度 = `len(Time)`），
**不是**"每个点一行"。多曲线模型就是 `Values[k]` = 第 k 条曲线。

---

## 拿它当模板改真实拓扑

| 想加什么 | 改哪里 |
|---|---|
| 换源参数 | `SineGenerator` 的 `Amplitude` / `Frequency`（`Units=1` 时是 rad/s；Hz 用 `Units=3`） |
| 加电感 | `Comp('Inductor','L1',params={'L':'1e-3','i_init':'0'})`，端子 1/2 |
| 加开关 | `Comp('IgbtWithDiode',...)`，端子 1=C/D、2=E/S、3=G；门极必须走 `Signal` |
| 三相 | 3 个 `VoltageSource` + 各自 `SineGenerator`（相位 0/±120°），或 `ThreePhaseVoltageSource`（1/2/3 + 4=中性点） |
| 多路观测 | `SignalMux` 合并后接一个 `Scope`，或把 `Output` 的 `Width` 改大 |

元件参数名与端子号见 [component-catalog.md](component-catalog.md)。
