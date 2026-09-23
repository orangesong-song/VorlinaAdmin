#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VORLINA Admin · 本地开发服务器
════════════════════════════════════════════════════════════
为什么要这个东西：后台的内容真源是**仓库里的 JSON**，而读写仓库需要 GitHub token。
生产环境由 Worker 持 token 走 GitHub Contents API；但**开发时不该为了看一眼数据就去部署 Worker**。

所以这里做一个「接口同形」的替身：
    本服务器 GET /content 返回的东西，与 Worker GET /content 返回的**一模一样**
    （GitHub Contents API 的 file 对象：content 是 base64，带 sha）。
    ⇒ 前台只有 CONTENT_BASE 一个常量不同，Worker 上线后改一行即可，代码不用动。

两条刻意的设计：
1. **只认白名单里的文件** —— 不做任意路径访问（防目录穿越，也防手滑读到不该读的）。
2. **写操作落到 overlay（.local-drafts/），绝不写官网工作区** ——
   生产写的是 cms 分支（不碰 main），本地就把「分支」换成「覆盖层」。
   效果一样：刷新能读到刚保存的东西；不同点只是它不会弄脏 vorlina-new 的工作区。

用法：
    python3 tools/serve-local.py [端口]     # 默认 8778
    前台访问 http://127.0.0.1:8778/index.html
"""
import base64
import hashlib
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # vorlina-admin/
SITE = os.path.normpath(os.path.join(HERE, '..', 'vorlina-new'))      # 官网真源
OVERLAY = os.path.join(HERE, '.local-drafts')                         # 本地「cms 分支」
MEDIA_DIR = os.path.join(OVERLAY, 'media')                            # 本地「R2 桶」
MEDIA_TYPES = {
    'image/webp': 'webp', 'image/jpeg': 'jpg', 'image/png': 'png',
    'image/avif': 'avif', 'image/gif': 'gif', 'image/svg+xml': 'svg',
    'application/pdf': 'pdf',
}
MEDIA_MAX = 8 * 1024 * 1024
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8778

# ── 白名单：后台允许读写的仓库内 JSON（相对官网根目录）──────────
ALLOWED = [
    'data/products.json',
    'build/data/insights.json',
    'build/data/imagery.json',
    'build/data/contraindications.json',
    'build/version.txt',
    'content/home.json',
    'content/common.json',
] + ['content/pages/%s.json' % s for s in [
    'applications', 'customization', 'factory', 'certifications',
    'support', 'contact', 'terms', 'privacy', 'sitemap',
]]


def media_safe_name(raw: str) -> str:
    """与 Worker mediaSafeName 同规则：挡路径穿越与危险字符，保留中文。"""
    import re
    n = str(raw or '').strip().replace('/', '-').replace('\\', '-')
    n = re.sub(r'[:*?"<>|\x00-\x1f]+', '', n)
    n = re.sub(r'\.\.+', '.', n)
    i = n.rfind('.')
    stem = n[:i] if i > 0 else n
    ext = n[i + 1:].lower() if i > 0 else ''
    ext = re.sub(r'[^a-z0-9]', '', ext)
    stem = re.sub(r'^[-\s]+|[-\s]+$', '', stem.lstrip('.'))
    if not stem:
        stem = 'file'
    return stem[:80] + ('.' + ext if ext else '')


def media_parse_multipart(raw: bytes, ctype: str):
    """够用就好：只取 name=file 的那一段（后台上传只有一个文件字段）。"""
    b = None
    for part in ctype.split(';'):
        part = part.strip()
        if part.lower().startswith('boundary='):
            b = part[len('boundary='):].strip('"')
    if not b:
        return None
    sep = ('--' + b).encode('latin-1')
    chunks = raw.split(sep)
    for ch in chunks:
        if b'name="file"' not in ch:
            continue
        head, _, body = ch.partition(b'\r\n\r\n')
        body = body.rstrip(b'\r\n-')
        fname, ftype = '', 'application/octet-stream'
        for line in head.split(b'\r\n'):
            low = line.lower()
            if b'filename=' in low:
                fname = line.split(b'filename=')[1].strip(b'"').decode('utf-8', 'replace')
            if low.startswith(b'content-type:'):
                ftype = line.split(b':', 1)[1].strip().decode('latin-1')
        return {'filename': fname, 'type': ftype.lower(), 'body': body}
    return None


# ── 媒体库（与 Worker /media/* 同形）────────────────────────────────
def _media_items():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    out = []
    for n in os.listdir(MEDIA_DIR):
        if n == '.trash':
            continue
        p = os.path.join(MEDIA_DIR, n)
        if not os.path.isfile(p):
            continue
        out.append({'key': 'img/' + n, 'name': n, 'size': os.path.getsize(p),
                    'uploaded': '', 'url': '/media/file/img/' + n})
    return sorted(out, key=lambda x: x['name'])

def sha_of(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def read_file_from(root: str, rel: str):
    p = os.path.join(root, rel)
    if os.path.isfile(p):
        with open(p, 'rb') as f:
            return f.read()
    return None


def read_file(rel: str):
    """先查 overlay（本地已保存的草稿），再查真源。缺失返回 None。"""
    for root in (OVERLAY, SITE):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            with open(p, 'rb') as f:
                return f.read()
    return None


def file_obj(rel: str, data: bytes):
    return {
        'path': rel,
        'encoding': 'base64',
        'size': len(data),
        'sha': sha_of(data),
        'content': base64.b64encode(data).decode('ascii'),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=HERE, **kw)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,PUT,POST,OPTIONS')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/content':
            rel = (parse_qs(u.query).get('path') or [''])[0]
            if rel not in ALLOWED:
                return self._json(403, {'message': '不在白名单里：' + (rel or '(空)')})
            data = read_file(rel)
            if data is None:
                return self._json(404, {'message': '真源里没这个文件：' + rel})
            return self._json(200, file_obj(rel, data))
        if u.path == '/commits':
            return self.do_GET_commits()
        if u.path == '/media/list':
            return self.do_GET_media_list()
        if u.path.startswith('/media/file/'):
            return self.do_GET_media_file(u.path[len('/media/file/'):])
        if u.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/media/upload':
            return self.do_POST_media_upload()
        if u.path != '/changes':
            return self._json(404, {'message': 'no route'})
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            req = json.loads(raw.decode('utf-8'))
        except Exception as e:
            return self._json(400, {'message': 'bad json: ' + str(e)})
        files = []
        for rel in (req.get('paths') or []):
            if rel not in ALLOWED:
                continue
            main = read_file_from(SITE, rel)
            cms = read_file(rel)          # 先 overlay 后真源 = 本地的「cms 分支」
            mo = {'sha': sha_of(main), 'size': len(main)} if main is not None else None
            co = {'sha': sha_of(cms), 'size': len(cms)} if cms is not None else None
            files.append({'path': rel, 'main': mo, 'cms': co,
                          'changed': (mo is None) != (co is None) or (mo and co and mo['sha'] != co['sha'])})
        return self._json(200, {'ok': True, 'files': files})

    def do_GET_commits(self):
        # 本地桩：没有提交历史可读，返回一条合成记录，形状与 Worker 一致
        return self._json(200, {'ok': True, 'commits': [
            {'sha': 'local000', 'date': '', 'message': '本地开发桩（无提交历史）', 'author': 'serve-local'}
        ]})

    def do_DELETE(self):
        u = urlparse(self.path)
        if not u.path.startswith('/media/file/'):
            return self._json(404, {'message': 'no route'})
        name = os.path.basename(u.path[len('/media/file/'):])
        p = os.path.join(MEDIA_DIR, name)
        if os.path.isfile(p):
            # ⚠️ 不用 os.remove：本机（NAS 卷 + 系统安全机制）会拦住删除并抛错。
            #    桩只是本地替身，语义等价地移进 .trash/ 即可（Worker 端是真 R2 delete）。
            trash = os.path.join(MEDIA_DIR, '.trash')
            os.makedirs(trash, exist_ok=True)
            os.replace(p, os.path.join(trash, name))
            return self._json(200, {'ok': True, 'deleted': 'img/' + name})
        return self._json(404, {'ok': False, 'error': 'not_found'})

    # ── 媒体库（与 Worker /media/* 同形）──────────────────────────
    def do_GET_media_list(self):
        return self._json(200, {'ok': True, 'items': _media_items()})

    def do_GET_media_file(self, rel):
        name = os.path.basename(rel)
        p = os.path.join(MEDIA_DIR, name)
        if not os.path.isfile(p):
            try:                      # 回源线上官网（仓库已有的图）—— 与 Worker 行为一致
                import urllib.request
                req = urllib.request.Request('https://vorlina.net/assets/img/' + name,
                                             headers={'User-Agent': 'vorlina-admin-local'})
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = r.read()
                    ctype = r.headers.get('Content-Type', 'application/octet-stream')
            except Exception:
                return self._json(404, {'ok': False, 'error': 'not_found', 'key': rel})
        else:
            with open(p, 'rb') as f:
                data = f.read()
            ext = name.rsplit('.', 1)[-1].lower()
            ctype = {'webp': 'image/webp', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                     'png': 'image/png', 'gif': 'image/gif', 'svg': 'image/svg+xml',
                     'pdf': 'application/pdf'}.get(ext, 'application/octet-stream')
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'public, max-age=3600')
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_POST_media_upload(self):
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b''
        part = media_parse_multipart(raw, self.headers.get('Content-Type') or '')
        if not part:
            return self._json(400, {'ok': False, 'error': 'bad_form'})
        if part['type'] not in MEDIA_TYPES:
            return self._json(415, {'ok': False, 'error': 'bad_type', 'type': part['type'],
                                    'allow': list(MEDIA_TYPES)})
        if len(part['body']) > MEDIA_MAX:
            return self._json(413, {'ok': False, 'error': 'too_large',
                                    'size': len(part['body']), 'max': MEDIA_MAX})
        name = media_safe_name(part['filename'] or 'file')
        os.makedirs(MEDIA_DIR, exist_ok=True)
        with open(os.path.join(MEDIA_DIR, name), 'wb') as f:
            f.write(part['body'])
        return self._json(200, {'ok': True, 'name': name, 'key': 'img/' + name,
                                'size': len(part['body']), 'type': part['type'],
                                'url': '/media/file/img/' + name,
                                'gh': {'ok': True, 'path': 'assets/img/' + name,
                                       'overwritten': False, 'note': '本地桩：不同步写仓库'}})

    def do_PUT(self):
        u = urlparse(self.path)
        if u.path != '/content':
            return self._json(404, {'message': 'no route'})
        n = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(n) if n else b'{}'
        try:
            req = json.loads(raw.decode('utf-8'))
        except Exception as e:
            return self._json(400, {'message': '请求体不是合法 JSON：' + str(e)})
        rel = req.get('path') or ''
        b64 = req.get('content') or ''
        if rel not in ALLOWED:
            return self._json(403, {'message': '不写入白名单外的文件：' + rel})
        try:
            data = base64.b64decode(b64)
        except Exception as e:
            return self._json(400, {'message': 'content 不是合法 base64：' + str(e)})
        # 写前先验 JSON 语法 —— 把「坏 JSON 进了仓库」挡在本地这一步
        if rel.endswith('.json'):
            try:
                json.loads(data.decode('utf-8'))
            except Exception as e:
                return self._json(400, {'message': 'JSON 语法错误，已拒绝保存：' + str(e)})
        dest = os.path.join(OVERLAY, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        print('[save] %s (%d bytes) %s' % (rel, len(data), req.get('message') or ''))
        return self._json(200, {'content': file_obj(rel, data), 'commit': {'message': req.get('message') or ''}})

    def log_message(self, fmt, *args):
        if '/content' in str(args[0]) if args else False:
            super().log_message(fmt, *args)


def main():
    missing = [p for p in ALLOWED if not os.path.isfile(os.path.join(SITE, p))]
    if missing:
        print('⚠️ 官网侧缺失（后台对应模块会显示「读不到」）：')
        for m in missing:
            print('   -', m)
    print('本地内容桩已就绪：http://127.0.0.1:%d/index.html' % PORT)
    print('  真源   %s' % SITE)
    print('  overlay %s （保存落这里，官网工作区不会被碰）' % OVERLAY)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()





