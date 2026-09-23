# -*- coding: utf-8 -*-
"""
vadmin-013 · 本地桩加 /media 同形路由（让后台上传流程能在本地端到端跑通）

与 Worker 一一对应：
  GET    /media/list            → .local-drafts/media/ 里的文件
  POST   /media/upload          → multipart，存 .local-drafts/media/<name>
  GET    /media/file/img/<name> → 直出；miss 则回源 vorlina.net/assets/img/<name>
  DELETE /media/file/img/<name> → 删本地
"""
import io

F = '/Volumes/我的文件/WorkBuddy/sitebuilding/vorlina-admin/tools/serve-local.py'
s = io.open(F, encoding='utf-8').read()


def rep(old, new, tag, cnt=1):
    global s
    n = s.count(old)
    assert n == cnt, '[%s] 期望 %d 处，实际 %d 处' % (tag, cnt, n)
    s = s.replace(old, new, cnt)
    print('  ok', tag)


# ① 常量：媒体目录 + 允许的类型
rep("""OVERLAY = os.path.join(HERE, '.local-drafts')                         # 本地「cms 分支」
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8778""",
    """OVERLAY = os.path.join(HERE, '.local-drafts')                         # 本地「cms 分支」
MEDIA_DIR = os.path.join(OVERLAY, 'media')                            # 本地「R2 桶」
MEDIA_TYPES = {
    'image/webp': 'webp', 'image/jpeg': 'jpg', 'image/png': 'png',
    'image/avif': 'avif', 'image/gif': 'gif', 'image/svg+xml': 'svg',
    'application/pdf': 'pdf',
}
MEDIA_MAX = 8 * 1024 * 1024
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8778""",
    '常量')

# ② 工具函数（插在 sha_of 之前）
rep("""def sha_of(data: bytes) -> str:""",
    '''def media_safe_name(raw: str) -> str:
    """与 Worker mediaSafeName 同规则：挡路径穿越与危险字符，保留中文。"""
    import re
    n = str(raw or '').strip().replace('/', '-').replace('\\\\', '-')
    n = re.sub(r'[:*?"<>|\\x00-\\x1f]+', '', n)
    n = re.sub(r'\\.\\.+', '.', n)
    i = n.rfind('.')
    stem = n[:i] if i > 0 else n
    ext = n[i + 1:].lower() if i > 0 else ''
    ext = re.sub(r'[^a-z0-9]', '', ext)
    stem = re.sub(r'^[-\\s]+|[-\\s]+$', '', stem.lstrip('.'))
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
        head, _, body = ch.partition(b'\\r\\n\\r\\n')
        body = body.rstrip(b'\\r\\n-')
        fname, ftype = '', 'application/octet-stream'
        for line in head.split(b'\\r\\n'):
            low = line.lower()
            if b'filename=' in low:
                fname = line.split(b'filename=')[1].strip(b'"').decode('utf-8', 'replace')
            if low.startswith(b'content-type:'):
                ftype = line.split(b':', 1)[1].strip().decode('latin-1')
        return {'filename': fname, 'type': ftype.lower(), 'body': body}
    return None


def sha_of(data: bytes) -> str:''',
    '工具函数')

# ③ GET 路由
rep("""        if u.path == '/commits':
            return self.do_GET_commits()
        if u.path == '/':""",
    """        if u.path == '/commits':
            return self.do_GET_commits()
        if u.path == '/media/list':
            return self.do_GET_media_list()
        if u.path.startswith('/media/file/'):
            return self.do_GET_media_file(u.path[len('/media/file/'):])
        if u.path == '/':""",
    'GET 路由')

# ④ POST /media/upload
rep("""    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/changes':
            return self._json(404, {'message': 'no route'})""",
    """    def do_POST(self):
        u = urlparse(self.path)
        if u.path == '/media/upload':
            return self.do_POST_media_upload()
        if u.path != '/changes':
            return self._json(404, {'message': 'no route'})""",
    'POST 路由')

# ⑤ DELETE
rep("""    def do_PUT(self):
        u = urlparse(self.path)""",
    """    def do_DELETE(self):
        u = urlparse(self.path)
        if not u.path.startswith('/media/file/'):
            return self._json(404, {'message': 'no route'})
        name = os.path.basename(u.path[len('/media/file/'):])
        p = os.path.join(MEDIA_DIR, name)
        if os.path.isfile(p):
            os.remove(p)
            return self._json(200, {'ok': True, 'deleted': 'img/' + name})
        return self._json(404, {'ok': False, 'error': 'not_found'})

    def do_PUT(self):
        u = urlparse(self.path)""",
    'DELETE 路由')

# ⑥ 三个处理函数（追加到文件末尾）
FN = '''

# ── 媒体库（与 Worker /media/* 同形）────────────────────────────────
def _media_items():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    out = []
    for n in os.listdir(MEDIA_DIR):
        p = os.path.join(MEDIA_DIR, n)
        if not os.path.isfile(p):
            continue
        out.append({'key': 'img/' + n, 'name': n, 'size': os.path.getsize(p),
                    'uploaded': '', 'url': '/media/file/img/' + n})
    return sorted(out, key=lambda x: x['name'])


def _media_list(self):
    return self._json(200, {'ok': True, 'items': _media_items()})


def _media_file(self, rel):
    name = os.path.basename(rel)
    p = os.path.join(MEDIA_DIR, name)
    if not os.path.isfile(p):
        # 回源线上官网（仓库已有的图）—— 与 Worker 行为一致
        try:
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


def _media_upload(self):
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


Handler.do_GET_media_list = _media_list
Handler.do_GET_media_file = _media_file
Handler.do_POST_media_upload = _media_upload
'''

s = s.rstrip('\n') + '\n' + FN
print('  ok 追加处理函数')

io.open(F, 'w', encoding='utf-8').write(s)
print('已写入', F)
