# PLECS Skill for WorkBuddy / Claude Code

> 一个「能让模型真正驱动 PLECS」的技能包：**从全新环境接入 → 从零建模 → 跑仿真 → 取波形 → 排错**，
> 全部结论来自 PLECS 4.7.5 实测，不是文档转述。

[![PLECS](https://img.shields.io/badge/PLECS-4.7.5-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Verified](https://img.shields.io/badge/冷启动验收-13%2F13-brightgreen)]()

---

## 它解决什么问题

通用大模型谈 PLECS 只能"照着帮助文档复述"，一到动手就卡在三处：

1. **接不上** —— RPC 默认关闭、MCP 没配、连不上时只会说"检查网络"
2. **建不出** —— 元件参数名/端子号全靠猜，写出的 `.plecs` 打不开
3. **查不出** —— 报错信息误导（`Unconnected terminals overlapped` 其实是线型混用）

这个技能把这三处全填上了，并且**每条结论都有实测数字背书**。

## 覆盖内容

| 主题 | 说明 |
|---|---|
| **冷启动接入** | 开 XML-RPC（默认关闭/1080）、从 GitHub 装 MCP、`mcp.json` 模板、raw xmlrpc 兜底、8 条失败对照表 |
| **从零建模** | 元件图鉴（约 60 类：参数名 + 端子号 + 语义）、可跑的生成器骨架、**真机验证过的最小模型全文** |
| **C-Script** | 代码窗口调用时序、Sample time、五种标准写法、数字 PI / PWM 状态机 / DSOGI-PLL 完整模板 |
| **`.plecs` 格式** | 私有语法、base64 通道、归属法扫描、Subsystem 五铁律、静默失败自检清单 |
| **编译缓存** | 只哈希 `Declarations` 字符串 ⇒ 改 `.h` 不重编；三个连锁现象 + 唯一可靠重编法 |
| **波形分析** | `.trace` 二进制格式、`Values` 布局、自适应步长重采样、相位参考修正 |
| **排错** | 症状表 40+ 条、分层剥洋葱定位法、错误诊断表 11 条 |

## 已验证的关键数字

| 结论 | 实测值 |
|---|---|
| 最小模型幅值 | 实测 **9.5403 V** vs 理论 **9.5403 V**（误差 **0.000 %**） |
| 最小模型相位 | 实测 **17.44°** vs 理论 **17.44°**（误差 **0.00°**） |
| `Branch` 是扇出语法 | 官方 32324 条 `Connection` 中 **6232 条**是多目的地 `Branch` |
| 矢量限幅 vs 逐轴削顶 | 削顶占比 50.2%→0.2%，畸变 13.4%→0.000% |
| LOCK 双施密特 | 修前整段故障窗为 0；修后全程 1、真失压 10.1 ms 掉锁 |

## 安装

### 方式 1：直接拷进技能目录（推荐）

```bash
git clone https://github.com/alembrt-cmyk/plecs-skill.git
cp -r plecs-skill ~/.workbuddy/skills/plecs-cscript
```

Windows:

```powershell
git clone https://github.com/alembrt-cmyk/plecs-skill.git
Copy-Item -Recurse plecs-skill "$env:USERPROFILE\.workbuddy\skills\plecs-cscript"
```

放好后重开一个会话，技能即生效（`~/.workbuddy/skills/` 是全局用户级目录，跨项目可用）。

### 方式 2：项目级

```bash
cp -r plecs-skill <你的项目>/.workbuddy/skills/plecs-cscript
```

## 快速自证（30 秒）

```bash
# 1) 造一个最小可跑模型
python scripts/plecs_builder.py --demo -o mini.plecs

# 2) 静态自检（应 rc=0）
python scripts/plecs_builder.py --check mini.plecs

# 3) 真机跑（需要 PLECS 已开 XML-RPC）
python -c "
import xmlrpc.client
P = xmlrpc.client.ServerProxy('http://localhost:1080/RPC2', allow_none=True)
print(P.plecs.statistics())            # 通了会返回版本
P.plecs.load('mini.plecs')
out = P.plecs.simulate('mini', {'SolverOpts': {'TimeSpan': 0.06, 'MaxStep': 5e-6}})
print(len(out['Time']), [len(c) for c in out['Values']])    # 12004 [12004]
P.plecs.close('mini')
"
```

## 目录结构

```
plecs-skill/
├── SKILL.md                       # 主文件：冷启动 4 阶段 + 全部核心知识
├── references/
│   ├── onboarding.md              # 全新环境接入（RPC / MCP / 自检 / 失败对照）
│   ├── component-catalog.md       # 元件图鉴（参数名 + 端子号 + 证据强度）
│   ├── minimal-model.md           # 真机验证过的最小模型全文
│   ├── plecs-file.md              # .plecs 格式 + Subsystem + .trace 格式
│   ├── code-patterns.md           # 代码模板（PI / PWM 状态机 / DSOGI-PLL）
│   ├── macro-reference.md         # C-Script 宏全集
│   └── troubleshooting.md         # 症状 → 原因 → 解决
└── scripts/
    └── plecs_builder.py           # 可跑生成器骨架（序列化 + 扇出 + 自检）
```

## 适用性

- **已验证**：PLECS **4.7.5** Standalone（Windows）
- **可能不同**：其它版本 —— RPC 命令集与 `.plecs` 字段会变，技能里已标注"哪条是 4.7.5 实测、哪些需重新校正"
- **元件库数据源**：`<PLECS安装目录>/components.plecs`（5597 个元件）+ 356 个官方示例
  换版本后重跑 `scripts/` 里的提取流程即可刷新图鉴

## 设计原则

1. **只写真跑过的** —— 每条结论标注实测环境与数字，没有实测的一律写明"未验证"
2. **错误也要写** —— 被推翻的旧结论（如"Branch 是折线途经点"）保留更正记录，避免再次踩坑
3. **不猜** —— 元件参数名来自官方库统计，端子号来自 356 个示例的 `Connection` 反推

## License

MIT