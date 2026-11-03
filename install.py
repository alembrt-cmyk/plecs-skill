#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本技能安装到 WorkBuddy / Claude Code 的技能目录。

用法：
    python install.py                   # 装到 ~/.workbuddy/skills/plecs-cscript（用户级，推荐）
    python install.py --project <目录>   # 装到 <目录>/.workbuddy/skills/plecs-cscript（项目级）
    python install.py --target <路径>    # 装到指定目录（自定义）
    python install.py --list            # 只显示会复制哪些文件
"""
from __future__ import annotations

import argparse
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_NAME = 'plecs-cscript'
SKIP_DIRS = {'__pycache__', '.git', '.venv', 'venv'}
SKIP_EXT = {'.pyc', '.pyo'}


def collect():
    files = []
    for root, dirs, fns in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in fns:
            if os.path.splitext(fn)[1] in SKIP_EXT:
                continue
            if fn == 'install.py' or fn in ('README.md', 'LICENSE', '.gitignore'):
                continue
            fp = os.path.join(root, fn)
            files.append(os.path.relpath(fp, HERE))
    return sorted(files)


def default_target():
    home = os.path.expanduser('~')
    return os.path.join(home, '.workbuddy', 'skills', SKILL_NAME)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Install the PLECS skill')
    ap.add_argument('--project', metavar='DIR',
                    help='install project-level under DIR/.workbuddy/skills/')
    ap.add_argument('--target', metavar='PATH', help='install to an explicit directory')
    ap.add_argument('--list', action='store_true', help='only list files')
    ap.add_argument('--force', action='store_true', help='overwrite existing files')
    a = ap.parse_args(argv)

    files = collect()
    if a.list:
        print('files to install (%d):' % len(files))
        for f in files:
            print('  ', f)
        return 0

    if a.target:
        dst = a.target
    elif a.project:
        dst = os.path.join(os.path.abspath(a.project), '.workbuddy', 'skills', SKILL_NAME)
    else:
        dst = default_target()

    print('source :', HERE)
    print('target :', dst)
    print('files  :', len(files))

    if os.path.isdir(dst) and not a.force:
        # 已存在：只覆盖技能本体，保留用户可能改过的其它文件前先问
        print('\n!! 目标已存在。用 --force 覆盖，或先手动备份。')
        print('   现有内容：', sorted(os.listdir(dst))[:10])
        return 2

    for rel in files:
        s = os.path.join(HERE, rel)
        d = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)

    print('\nOK 已安装 %d 个文件。' % len(files))
    print('重启 WorkBuddy（或新开会话）后技能生效。')
    print('验证：会话里问「PLECS 怎么接入」应命中 plecs-cscript。')
    return 0


if __name__ == '__main__':
    sys.exit(main())