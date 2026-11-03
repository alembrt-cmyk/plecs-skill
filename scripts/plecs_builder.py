#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PLECS .plecs 生成器骨架 —— 从零造一个能 load + simulate 的模型。

用法：
    python plecs_builder.py --demo  -o mini.plecs      # 最小可跑示例（源+RC+Scope+Out）
    python plecs_builder.py --check mini.plecs          # 静态自检（悬空/Goto/顶层Terminal）
    python plecs_builder.py --dump  mini.plecs          # 解出元件与连线清单

设计原则（都是踩坑换来的）：
  1. 纯 ASCII：写盘前 `encode('ascii')` 硬关卡 —— 有裸中文 = 打开整片乱码。
  2. LF 行尾：`newline='\\n'`。官方样板是 LF（406 个文件里 403 个）。
  3. 顶层出数必须有模型级 `Terminal { Type Output; Index "1" }`（在 Schematic 之前），
     只放画布 Component{Type Output} 时 RPC simulate 返回空数组。
  4. 扇出只能靠 Goto/From（信号）或同名 Label（电气）；Connection 里的 Branch 是折线途经点。
  5. 一个端子只允许一条 Connection。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 数据模型


@dataclass
class Comp:
    """一个元件。terms: 端子号 -> ('electrical'|'signal', direction)"""
    type: str
    name: str
    position: Tuple[float, float] = (0.0, 0.0)
    direction: str = 'right'          # right/left/up/down
    flipped: bool = False
    params: Dict[str, str] = field(default_factory=dict)
    mask_type: Optional[str] = None   # 仅 Subsystem
    terminals: List[dict] = field(default_factory=list)  # 仅 Subsystem


@dataclass
class Conn:
    """一条 Connection。一个源端子 → 1..N 个目的地。

    ★ 扇出用 `Branch`（官方 32324 条 Connection 里 6232 条是多目的地 Branch 写法）。
      一个源端子只允许**一条** Connection；多个目的地必须写成 Branch。
    """
    src: Tuple[str, int]
    dsts: List[Tuple[str, int]] = field(default_factory=list)
    kind: str = 'Wire'                # Wire(电气) / Signal(信号)
    points: List[Tuple[float, float]] = field(default_factory=list)
    # Branch 的途经点（与 dsts 一一对应，可为空）
    branch_points: List[List[Tuple[float, float]]] = field(default_factory=list)


class Model:
    def __init__(self, name: str = 'demo'):
        self.name = name
        self.comps: List[Comp] = []
        self.conns: List[Conn] = []
        self.term_outputs: List[int] = []      # 模型级 Terminal Index 列表
        self.init_commands: Optional[str] = None
        self.solver_maxstep: Optional[float] = None
        self.timespan: Optional[float] = None

    # --- 构件 ---
    def add(self, c: Comp) -> Comp:
        for x in self.comps:
            if x.name == c.name:
                raise ValueError('duplicate component name: %s' % c.name)
        self.comps.append(c)
        return c

    def wire(self, src: Tuple[str, int], dst: Tuple[str, int],
             kind: str = 'Wire', points: Sequence[Tuple[float, float]] = ()) -> Conn:
        """单目的地连线。"""
        c = Conn(src, [dst], kind, list(points))
        self.conns.append(c)
        return c

    def signal(self, src, dst, points=()) -> Conn:
        return self.wire(src, dst, 'Signal', points)

    def fanout(self, src: Tuple[str, int], dsts: Sequence[Tuple[str, int]],
               kind: str = 'Signal', points=()) -> Conn:
        """一源多目的地 —— 写成一条 Connection + 多个 Branch。"""
        if len(dsts) < 2:
            return self.wire(src, dsts[0], kind, points)
        c = Conn(src, list(dsts), kind, list(points))
        self.conns.append(c)
        return c

    def output_terminal(self, index: int = 1):
        self.term_outputs.append(index)

    # ------------------------------------------------------------ 序列化
    def render(self) -> str:
        L: List[str] = []
        L.append('Plecs {')
        L.append('  Name          "%s"' % _esc(self.name))
        for idx in sorted(self.term_outputs):
            L.append('  Terminal {')
            L.append('    Type          Output')
            L.append('    Index         "%d"' % idx)
            L.append('  }')
        if self.init_commands is not None:
            L.append('  InitCommands  %s' % _quoted(self.init_commands))
        L.append('  Schematic {')
        for c in self.comps:
            L.extend(_render_comp(c))
        for cn in self.conns:
            L.extend(_render_conn(cn))
        L.append('  }')
        L.append('}')
        L.append('')
        return '\n'.join(L)

    def write(self, path: str) -> None:
        body = self.render()
        # ★ ASCII 硬关卡：裸非 ASCII = PLECS 打开整片乱码
        try:
            body.encode('ascii')
        except UnicodeEncodeError as e:
            raise SystemExit('!! .plecs 含非 ASCII 字符，PLECS 会乱码：%r' % (e,))
        d = os.path.dirname(os.path.abspath(path))
        if d and not os.path.isdir(d):
            os.makedirs(d)
        io.open(path, 'w', encoding='ascii', newline='\n').write(body)

    # ------------------------------------------------------------ 自检
    def check(self) -> List[str]:
        errs: List[str] = []
        names = {c.name for c in self.comps}
        # 1) 顶层出数
        if not self.term_outputs:
            errs.append('缺模型级 Terminal{Type Output}：RPC simulate 会返回空数组')
        # 2) 连线端点存在；同一源端子只允许一条 Connection
        seen = {}
        gotos = {}
        froms = {}
        for cn in self.conns:
            nm, tm = cn.src
            if nm not in names:
                errs.append('Connection 引用了不存在的组件 %r' % nm)
            else:
                key = (nm, tm)
                if key in seen:
                    errs.append('源端子 %s.%d 被多条 Connection 引用'
                                '（多个目的地请用 fanout/Branch）' % (nm, tm))
                seen[key] = cn.kind
            for dn, dt in cn.dsts:
                if dn not in names:
                    errs.append('Connection 引用了不存在的组件 %r' % dn)
                seen[(dn, dt)] = cn.kind
        # 3) Goto/From Tag 配对
        for c in self.comps:
            tag = c.params.get('Tag')
            if c.type == 'Goto':
                gotos.setdefault(tag, 0)
                gotos[tag] += 1
            elif c.type == 'From':
                froms.setdefault(tag, 0)
                froms[tag] += 1
            if c.type in ('Goto', 'From') and c.params.get('Visibility') != '2':
                errs.append('%s(%s) 的 Visibility 必须是 2（否则 No matching Goto block found）'
                            % (c.type, c.name))
        for tag in froms:
            if tag not in gotos:
                errs.append('From(Tag=%r) 找不到对应 Goto' % tag)
        # 4) 悬空端子（除 Scope/Goto/Label 这类非 Connection 件）
        skip = {'Scope', 'Goto', 'Label', 'FreeText', 'FixedText', 'Annotation'}
        for c in self.comps:
            if c.type in skip or c.type == 'Subsystem':
                continue
            n_terms = _expected_terms(c)
            if n_terms is None:
                continue
            used = {tm for (nm, tm) in seen if nm == c.name}
            if not used:
                errs.append('%s(%s) 完全没有接线' % (c.type, c.name))
            missing = [i for i in range(1, n_terms + 1) if i not in used]
            if missing:
                errs.append('%s(%s) 端子 %s 未接线（期望 1..%d）'
                            % (c.type, c.name, missing, n_terms))
        return errs


def _expected_terms(c: Comp) -> Optional[int]:
    """按元件类型返回应有的端子数（None = 不检查）。"""
    if c.type == 'CScript':
        return None          # 由 NumInputs/NumOutputs 宽度列表决定，单独算
    if c.type == 'Sum':
        n = len(c.params.get('Inputs', '++').strip('"'))
        return 1 + n
    if c.type == 'Product':
        return 1 + int(c.params.get('Inputs', '2'))
    if c.type == 'SignalMux':
        return int(c.params.get('Width', '2')) + 1
    if c.type == 'SignalDemux':
        return int(c.params.get('Width', '2')) + 1
    table = {
        'Resistor': 2, 'Capacitor': 2, 'Inductor': 2, 'Diode': 2,
        'IgbtWithDiode': 3, 'Mosfet': 3, 'Thyristor': 3,
        'VoltageSource': 3, 'CurrentSource': 3, 'DCVoltageSource': 2,
        'ThreePhaseVoltageSource': 4, 'Voltmeter': 3, 'Ammeter': 3,
        'SineGenerator': 1, 'Step': 1, 'Clock': 1, 'PulseGenerator': 1,
        'Gain': 2, 'Constant': 1, 'Integrator': 2, 'TransferFunction': 2,
        'Abs': 2, 'Delay': 2, 'ZeroOrderHold': 2, 'Memory': 2,
        'SignalSelector': 2, 'RelationalOperator': 3, 'Saturation': 2,
        'Output': 1, 'Ground': 1,
    }
    return table.get(c.type)


def _esc(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


def _quoted(s: str) -> str:
    """多行字符串 → PLECS 的多段引号写法（真换行必须转成字面 \\n）。"""
    out = []
    for line in s.split('\n'):
        out.append('"%s\\n"' % _esc(line))
    return '\n            '.join(out)


def _render_comp(c: Comp) -> List[str]:
    L = ['    Component {',
         '      Type          %s' % c.type,
         '      Name          "%s"' % _esc(c.name)]
    if c.mask_type:
        L.append('      MaskType      %s' % _quoted(c.mask_type))
    L.append('      Show          on')
    L.append('      Position      [%s]' % ', '.join(_num(x) for x in c.position))
    L.append('      Direction     %s' % c.direction)
    L.append('      Flipped       %s' % ('on' if c.flipped else 'off'))
    for t in c.terminals:
        L.append('      Terminal {')
        L.append('        Type          %s' % t.get('type', 'Port'))
        L.append('        Index         "%s"' % t.get('index'))
        L.append('        Position      [%s]' % ', '.join(_num(x) for x in t.get('position', (0, 0))))
        L.append('        Direction     %s' % t.get('direction', 'right'))
        L.append('      }')
    for var, val in c.params.items():
        L.append('      Parameter {')
        L.append('        Variable      "%s"' % _esc(var))
        L.append('        Value         "%s"' % _esc(str(val)))
        L.append('        Show          off')
        L.append('      }')
    L.append('    }')
    return L


def _render_conn(cn: Conn) -> List[str]:
    L = ['    Connection {',
         '      Type          %s' % cn.kind,
         '      SrcComponent  "%s"' % _esc(cn.src[0]),
         '      SrcTerminal   %d' % cn.src[1]]
    if cn.points:
        L.append('      Points        [%s]' %
                 ', '.join('%s, %s' % (_num(x), _num(y)) for x, y in cn.points))
    if len(cn.dsts) == 1:
        dn, dt = cn.dsts[0]
        L.append('      DstComponent  "%s"' % _esc(dn))
        L.append('      DstTerminal   %d' % dt)
    else:
        # ★ 扇出：一个 Connection + N 个 Branch
        for i, (dn, dt) in enumerate(cn.dsts):
            L.append('      Branch {')
            if i < len(cn.branch_points) and cn.branch_points[i]:
                L.append('        Points        [%s]' %
                         '; '.join('%s, %s' % (_num(x), _num(y))
                                   for x, y in cn.branch_points[i]))
            L.append('        DstComponent  "%s"' % _esc(dn))
            L.append('        DstTerminal   %d' % dt)
            L.append('      }')
    L.append('    }')
    return L


def _num(x) -> str:
    if isinstance(x, float) and x == int(x):
        return str(int(x))
    return str(x)


# ---------------------------------------------------------------- 最小示例


def build_demo(name: str = 'mini_demo') -> Model:
    """正弦源 → R-C 低通 → 电压表（信号）→ Scope；并引出模型级 Output。

    ★ 拓扑要点（真机踩过）：
      `SineGenerator` 输出的是**信号**，不是电压 —— 必须送进 `VoltageSource` 的第 3 端
      （受控输入），两端 1/2 才是电气口。直接把 SineGenerator 接 Wire = Wire/Signal 混用，
      报 `Unconnected terminals overlapped by other elements`。
    """
    m = Model(name)

    # 信号源 → 受控电压源的信号输入（Signal 连线）
    m.add(Comp('SineGenerator', 'SIN', position=(30, 160), direction='right',
               params={'Amplitude': '10', 'Frequency': '2*pi*50', 'Bias': '0',
                       'Phase': '0', 'Units': '1'}))
    m.add(Comp('VoltageSource', 'V1', position=(120, 100), direction='up',
               params={'DiscretizationBehavior': '2', 'StateSpaceInlining': '1'}))
    m.signal(('SIN', 1), ('V1', 3))

    # 主电路：V1 → R1 → C1 → 地
    m.add(Comp('Resistor', 'R1', position=(190, 60), direction='right',
               params={'R': '10'}))
    m.add(Comp('Capacitor', 'C1', position=(260, 60), direction='down',
               params={'C': '100e-6', 'v_init': '0'}))
    m.add(Comp('Ground', 'G1', position=(260, 140), direction='up', params={}))
    m.add(Comp('Voltmeter', 'VM1', position=(260, 15), direction='down', params={}))
    m.add(Comp('Scope', 'SC1', position=(370, 15), direction='right', params={}))
    m.add(Comp('Output', 'OUT', position=(370, 95), direction='right',
               params={'Index': '1', 'Width': '-1'}))

    # 电气连线（Wire）。扇出用 fanout（= 一条 Connection + 多个 Branch）
    m.wire(('V1', 1), ('R1', 1), 'Wire')
    # C1.1（上端）同时接 R1.2 与 VM1.1 ⇒ 一个源端子扇出
    m.fanout(('R1', 2), [('C1', 1), ('VM1', 1)], 'Wire')
    # V1.2（下端/地）接 C1.2 / G1.1 / VM1.2
    m.fanout(('V1', 2), [('C1', 2), ('G1', 1), ('VM1', 2)], 'Wire')
    # 信号：VM1.3 给 Scope 和 Output 两处
    m.fanout(('VM1', 3), [('SC1', 1), ('OUT', 1)], 'Signal')

    m.output_terminal(1)
    m.timespan = 0.05
    m.solver_maxstep = 1e-5
    return m


# ---------------------------------------------------------------- 解析/自检


COMP_RE = re.compile(r'^(\s*)Component\s*\{\s*$')
TYPE_RE = re.compile(r'^\s*Type\s+([A-Za-z0-9_]+)\s*$')
NAME_RE = re.compile(r'^\s*Name\s+(?:base64\s+)?"([^"]*)"\s*$')
VAR_RE = re.compile(r'^\s*Variable\s+"([^"]+)"\s*$')
VAL_RE = re.compile(r'^\s*Value\s+(?:base64\s+)?"?([^"]*)"?\s*$')
SRC_RE = re.compile(r'SrcComponent\s+"([^"]*)"[\s\S]*?SrcTerminal\s+"?(\d+)"?')
DST_RE = re.compile(r'DstComponent\s+"([^"]*)"[\s\S]*?DstTerminal\s+"?(\d+)"?')


def parse(path: str):
    """归属法解析（不依赖花括号配平，能进 Subsystem）。

    返回 (comps, links)。links = [(src_name, src_term, [(dst_name, dst_term), ...]), ...]
    一条 Connection 里的 Branch 归并为同一源端子的多目的地。
    """
    text = io.open(path, encoding='ascii', errors='replace').read()
    lines = text.splitlines()
    comps, cur = [], None
    for i, ln in enumerate(lines):
        if COMP_RE.match(ln):
            cur = Comp('', '')
            comps.append(cur)
            continue
        if cur is None:
            continue
        mt = TYPE_RE.match(ln)
        if mt and not cur.type:
            cur.type = mt.group(1)
            continue
        mn = NAME_RE.match(ln)
        if mn and not cur.name:
            cur.name = mn.group(1)
            continue
        mv = VAR_RE.match(ln)
        if mv:
            var = mv.group(1)
            for k in range(1, 4):
                if i + k < len(lines):
                    mval = VAL_RE.match(lines[i + k])
                    if mval:
                        cur.params[var] = mval.group(1)
                        break

    # Connection 块（配平扫描，仅用于解析）
    links = []
    for blk in _blocks(text, 'Connection'):
        ms = SRC_RE.search(blk)
        if not ms:
            continue
        src = (ms.group(1), int(ms.group(2)))
        dsts = [(m.group(1), int(m.group(2))) for m in DST_RE.finditer(blk)]
        links.append((src, dsts))
    return comps, links


def _blocks(text: str, head: str):
    """抽出所有 head { ... } 块（花括号配平）。"""
    out = []
    i = 0
    while True:
        k = text.find(head, i)
        if k < 0:
            return out
        j = text.find('{', k)
        if j < 0:
            return out
        depth = 0
        for p in range(j, len(text)):
            if text[p] == '{':
                depth += 1
            elif text[p] == '}':
                depth -= 1
                if depth == 0:
                    out.append(text[k:p + 1])
                    i = p + 1
                    break
        else:
            return out


def check_file(path: str) -> int:
    raw = io.open(path, 'rb').read()
    bad = [(i, b) for i, b in enumerate(raw) if b >= 128]
    print('== 自检: %s (%d B) ==' % (path, len(raw)))
    ok = True
    if bad:
        ok = False
        print('  ✗ 非 ASCII 字节 %d 个（首个位于 offset %d）→ PLECS 会整片乱码'
              % (len(bad), bad[0][0]))
    else:
        print('  ✓ 纯 ASCII')

    text = raw.decode('ascii', errors='replace')
    if re.search(r'^\s*Terminal\s*\{\s*$', text, re.M) and 'Index' in text:
        print('  ✓ 有模型级 Terminal{Type Output}')
    else:
        ok = False
        print('  ✗ 缺模型级 Terminal{Type Output} → simulate 返回空数组')

    comps, links = parse(path)
    n_dst = sum(len(d) for _, d in links)
    n_br = sum(1 for _, d in links if len(d) > 1)
    print('  元件 %d 个，Connection %d 条（其中扇出 %d 条，共 %d 个目的地）'
          % (len(comps), len(links), n_br, n_dst))

    names = {c.name for c in comps if c.name}
    seen = {}
    for (sn, st), dsts in links:
        if sn not in names:
            ok = False
            print('  ✗ 连线引用了不存在的组件 %r' % sn)
        key = (sn, st)
        if key in seen:
            ok = False
            print('  ✗ 源端子 %s.%d 被多条 Connection 引用（应合并成 Branch）' % key)
        seen[key] = 1
        for dn, dt in dsts:
            if dn not in names:
                ok = False
                print('  ✗ 连线引用了不存在的组件 %r' % dn)
            seen[(dn, dt)] = 1

    # 悬空检查（按元件类型期望端子数）
    skip = {'Scope', 'Goto', 'Label', 'FreeText', 'FixedText', 'Annotation',
            'CScript', 'Subsystem', 'ConfigurableSubsystem'}
    for c in comps:
        if not c.name or c.type in skip:
            continue
        exp = _expected_terms(c)
        if exp is None:
            continue
        used = {t for (n, t) in seen if n == c.name}
        if not used:
            ok = False
            print('  ✗ %s(%s) 完全没有接线' % (c.type, c.name))
            continue
        miss = [i for i in range(1, exp + 1) if i not in used]
        if miss:
            ok = False
            print('  ✗ %s(%s) 端子 %s 未接线（期望 1..%d）' % (c.type, c.name, miss, exp))

    print('  → %s' % ('全部通过' if ok else '有问题，见上'))
    return 0 if ok else 1


def dump_file(path: str) -> None:
    comps, links = parse(path)
    print('== 元件 (%d) ==' % len(comps))
    for c in comps:
        print('  %-14s %-18s %s' % (c.type or '?', c.name or '?',
                                    {k: v for k, v in list(c.params.items())[:6]}))
    print('\n== 连线 (%d Connection) ==' % len(links))
    for (sn, st), dsts in links:
        if len(dsts) == 1:
            print('  %s.%d -> %s.%d' % (sn, st, dsts[0][0], dsts[0][1]))
        else:
            print('  %s.%d -+-> %s' % (sn, st, ', '.join('%s.%d' % d for d in dsts)))


# ---------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description='PLECS .plecs generator skeleton')
    ap.add_argument('--demo', action='store_true', help='生成最小可跑示例')
    ap.add_argument('-o', '--out', default='mini_demo.plecs')
    ap.add_argument('--check', metavar='FILE', help='静态自检')
    ap.add_argument('--dump', metavar='FILE', help='解出元件与连线')
    ap.add_argument('--name', default=None, help='模型名（默认与文件名一致）')
    a = ap.parse_args(argv)

    if a.check:
        return check_file(a.check)
    if a.dump:
        dump_file(a.dump)
        return 0
    if a.demo:
        nm = a.name or os.path.splitext(os.path.basename(a.out))[0]
        m = build_demo(nm)
        errs = m.check()
        if errs:
            print('模型自检发现问题：')
            for e in errs:
                print('  ✗', e)
            return 1
        m.write(a.out)
        print('written %s (%d B)' % (a.out, os.path.getsize(a.out)))
        print('next: python plecs_builder.py --check %s' % a.out)
        return 0
    ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())