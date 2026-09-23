#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归套件去硬编码：EXPECT.version 写死 '20260920a'，真源升版后必然假红。
   版本串是派生值 —— 测试也要从 build/version.txt 现算（与本站「派生值不许写死」同一条纪律）。"""
import io, os

F = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools', 'verify-content.js'))
s = io.open(F, encoding='utf-8').read()
n = 0

def rep(old, new, times=1):
    global s, n
    c = s.count(old)
    assert c == times, '锚点命中 %d，预期 %d：%s' % (c, times, old[:50])
    s = s.replace(old, new, times)
    n += 1

rep("const puppeteer = require('puppeteer-core');",
    """const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');""")

rep("""const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';""",
    """/* 版本串现算：官网每次发版都会升，写死在测试里只会制造假红（2026-09-23 实测如此） */
const SITE = path.resolve(__dirname, '..', '..', 'vorlina-new');
const VERSION = fs.readFileSync(path.join(SITE, 'build', 'version.txt'), 'utf8').trim();

const SB = 'https://jjmaularjtmhptbfnovd.supabase.co';""")

rep("  version: '20260920a',", "  version: VERSION,")

io.open(F, 'w', encoding='utf-8').write(s)
print('完成：%d 处替换（版本串改为现算 %s）' % (n, VERSION := __import__('re').search(r"const VERSION = .*", s) and 'ok'))
