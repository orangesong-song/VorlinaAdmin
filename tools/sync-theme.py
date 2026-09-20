#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从网站 main.css 同步设计 token 到后台 —— 保证"两套界面是一家"是结构性的，而非靠人眼对齐。

用法：
    python3 tools/sync-theme.py            # 写入 theme/css/tokens.css + 同步字体文件
    python3 tools/sync-theme.py --check    # 只校验（构建前/CI 用）；不一致退出码 1

为什么需要它：
    后台是**独立仓库**，不能 import 网站的 CSS。所以 token 只能"复制一份"——
    而复制就会脱节。本脚本把"复制"变成"可校验的复制"：
    网站改了金色，后台不会自动跟着变，但**至少会被报出来**，
    而不是慢慢演变成两个品牌。
"""
import io, os, re, sys, hashlib, argparse, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN = os.path.dirname(HERE)                      # vorlina-admin/
DEFAULT_SITE = os.path.join(os.path.dirname(ADMIN), 'vorlina-new')
OUT = os.path.join(ADMIN, 'theme', 'css', 'tokens.css')
FONTS_OUT = os.path.join(ADMIN, 'theme', 'fonts')

HEADER = '''/* ==========================================================================
   VORLINA · 设计令牌（后台）—— 自动生成，请勿手改
   --------------------------------------------------------------------------
   来源：{src}
   生成：python3 tools/sync-theme.py
   校验：python3 tools/sync-theme.py --check     ← 构建前跑，不一致会报错退出
   ========================================================================== */

'''


def build(site):
    """从网站 main.css 取出 @font-face 与 :root 块，拼成 tokens.css 内容。"""
    src = os.path.join(site, 'preview', 'assets', 'css', 'main.css')
    if not os.path.isfile(src):
        raise SystemExit('✗ 找不到网站样式表：' + src)
    css = io.open(src, encoding='utf-8').read()

    faces = re.findall(r'@font-face\s*\{[^}]*\}', css)
    if len(faces) != 2:
        raise SystemExit('✗ @font-face 块数不是 2（实为 %d）—— 网站字体定义变了，请检查' % len(faces))
    for f in faces:
        if '../fonts/' not in f:
            raise SystemExit('✗ @font-face 里的字体路径不再是 ../fonts/ —— 后台的相对路径会失效')

    m = re.search(r':root\s*\{[^}]*\}', css)
    if not m:
        raise SystemExit('✗ main.css 里找不到 :root 令牌块')
    root = m.group(0)

    n = len(re.findall(r'--[\w-]+\s*:', root))
    if n < 15:
        raise SystemExit('✗ :root 里只解析出 %d 个变量，疑似结构变化' % n)

    rel = os.path.relpath(src, ADMIN)
    body = HEADER.format(src=rel) + '\n'.join(faces) + '\n\n' + root + '\n'
    return body, n, faces


def font_files(site):
    """后台需要跟着同步的字体文件清单（从 @font-face 的 url 里取）。"""
    src = os.path.join(site, 'preview', 'assets', 'css', 'main.css')
    css = io.open(src, encoding='utf-8').read()
    names = sorted(set(re.findall(r"url\('\.\./fonts/([^']+)'\)", css)))
    return names


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验，不写入')
    ap.add_argument('--site', default=DEFAULT_SITE, help='网站仓库根目录')
    args = ap.parse_args()
    site = os.path.abspath(args.site)

    body, n, faces = build(site)
    names = font_files(site)
    print('═══ VORLINA 后台主题同步 ═══')
    print('  来源   : %s' % os.path.relpath(os.path.join(site, 'preview', 'assets', 'css', 'main.css'), ADMIN))
    print('  令牌   : %d 个 CSS 变量 · %d 个 @font-face' % (n, len(faces)))
    print('  字体   : %s' % ', '.join(names))
    print()

    problems = []

    # ── 令牌文件 ──
    cur = io.open(OUT, encoding='utf-8').read() if os.path.isfile(OUT) else None
    if cur == body:
        print('  ✓ theme/css/tokens.css 与网站一致')
    elif args.check:
        if cur is None:
            print('  ✗ theme/css/tokens.css 不存在（请先跑一次不带 --check 的同步）')
        else:
            print('  ✗ theme/css/tokens.css 与网站**不一致** —— 网站改过视觉令牌，后台还停在旧值：')
            a, b = (cur or '').split('\n'), body.split('\n')
            for i in range(max(len(a), len(b))):
                x = a[i] if i < len(a) else '<缺行>'
                y = b[i] if i < len(b) else '<缺行>'
                if x != y:
                    print('      第 %d 行' % (i + 1))
                    print('        后台: %s' % x[:110])
                    print('        网站: %s' % y[:110])
        problems.append('tokens.css')
    else:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        io.open(OUT, 'w', encoding='utf-8').write(body)
        print('  %s theme/css/tokens.css（%d 字节）' % ('已写入' if cur is None else '已更新', len(body)))

    # ── 字体文件 ──
    for name in names:
        s = os.path.join(site, 'preview', 'assets', 'fonts', name)
        d = os.path.join(FONTS_OUT, name)
        if not os.path.isfile(s):
            print('  ✗ 网站缺少字体文件 %s' % name)
            problems.append(name)
            continue
        if os.path.isfile(d) and sha(s) == sha(d):
            print('  ✓ 字体 %s 一致（%d 字节）' % (name, os.path.getsize(d)))
            continue
        if args.check:
            print('  ✗ 字体 %s 与网站不一致或缺失' % name)
            problems.append(name)
        else:
            os.makedirs(FONTS_OUT, exist_ok=True)
            shutil.copyfile(s, d)
            print('  %s 字体 %s（%d 字节）' % ('已复制' if not os.path.isfile(d) else '已更新', name, os.path.getsize(d)))

    print()
    if problems:
        print('结论：%d 项需要处理 → %s' % (len(problems), ', '.join(problems)))
        print('     修法：python3 tools/sync-theme.py      （然后目测后台界面是否受影响）')
        return 1
    print('结论：后台主题与网站完全一致 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
