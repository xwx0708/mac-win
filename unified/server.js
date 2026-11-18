// 统一文件页的页面服务（零依赖）：提供页面文件和 /__ 开头的接口
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const PORT = Number(process.env.PORT) || 5511;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

// 打开本机文件不走 HTTP：由 App 主进程（main.js）经 IPC 处理，只接受本 App 窗口的请求。

// ── 设备：Tailscale 里这个账号下已授权的全部设备 + 互联服务的连接状态
const { execFile } = require('child_process');
const TS = ['C:\\Program Files\\Tailscale\\tailscale.exe', '/Applications/Tailscale.app/Contents/MacOS/Tailscale'].find((p) => fs.existsSync(p)) || 'tailscale';
const LINK_DIR = path.join(ROOT, '..', 'link');
// 本机互联服务的接口端口：以 link/config.json 的 local_api_port 为准，读不到才用默认值
const LINK_API = (() => { try { return JSON.parse(fs.readFileSync(path.join(LINK_DIR, 'config.json'), 'utf8')).local_api_port || 47111; } catch { return 47111; } })();
const sendJson = (res, code, obj) => res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }).end(JSON.stringify(obj));

function linkApi(method, p, headers = {}, body = null) {
  return new Promise((resolve) => {
    const r = http.request({ host: '127.0.0.1', port: LINK_API, path: p, method, headers, timeout: 8000, maxHeaderSize: 8 * 1024 * 1024 }, (res) => {
      let data = ''; res.setEncoding('utf8');
      res.on('data', (c) => { data += c; });
      res.on('end', () => resolve({ code: res.statusCode, headers: res.headers, body: data }));
    });
    r.on('error', (e) => resolve({ fail: e.code === 'ECONNREFUSED' ? 'down' : e.code === 'ETIMEDOUT' ? 'timeout' : 'protocol', detail: e.message }));
    r.on('timeout', () => { r.destroy(Object.assign(new Error('timeout'), { code: 'ETIMEDOUT' })); });
    if (body) r.write(body); r.end();
  });
}

function tailscaleStatus() {
  return new Promise((resolve) => execFile(TS, ['status', '--json'], { timeout: 8000, windowsHide: true, env: { ...process.env, TERM: 'dumb' } },
    (err, out) => { try { resolve(err ? null : JSON.parse(out)); } catch { resolve(null); } }));
}

async function devices(res) {
  const [st, linkSt] = await Promise.all([tailscaleStatus(), linkApi('GET', '/status')]);
  if (!st) return sendJson(res, 503, { error: '读不到 Tailscale 状态' });
  let cfg = {}; try { cfg = JSON.parse(fs.readFileSync(path.join(LINK_DIR, 'config.json'), 'utf8')); } catch {}
  let link = null; try { if (linkSt && linkSt.code === 200) link = JSON.parse(linkSt.body); } catch {}
  if (!st.Self || !st.Self.ID) return sendJson(res, 503, { error: 'Tailscale 状态里没有本机信息（可能还没登录）' });
  const one = (n, self) => ({
    id: n.ID, self,
    name: (n.DNSName || '').split('.')[0] || n.HostName, host: n.HostName, os: (n.OS || '').toLowerCase(),
    online: self ? true : !!n.Online, lastSeen: n.LastSeen || null, ip: (n.TailscaleIPs || []).find((ip) => !ip.includes(':')) || '',
    allowed: !!(cfg.allowed_devices || {})[n.ID], label: (cfg.allowed_devices || {})[n.ID] || '',
    sharedDir: (cfg.shared_dirs || {})[n.ID] || '',
    linked: self ? !!link : !!(link && link.peer && link.peer.device_id === n.ID && link.connected),
    rtt: link && link.peer && link.peer.device_id === n.ID ? link.rtt_ms : null,
  });
  sendJson(res, 200, {
    taken: new Date().toISOString(),
    linkService: !!link,
    devices: [one(st.Self, true), ...Object.values(st.Peer || {}).map((p) => one(p, false))],
  });
}

// ── 文件操作：本机和对方都经本机互联服务（对方走 Tailscale 长连接），页面不直接碰文件
// 每个请求都带 X-Source（人工操作，来自 App），互联服务据此记操作记录。
const PAGE = 500, LIST_CAP = 5000, CHUNK = 1 << 20;
const asciiJson = (o) => JSON.stringify(o).replace(/[\u007f-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
const SOURCE = asciiJson({ kind: 'human', via: 'app' });
class OpError extends Error { constructor(code, msg) { super(msg); this.code = code; } }

// 把互联服务的出错原因翻成看得懂的中文
function explain(code, msg) {
  const m = String(msg || '');
  const tail = m.includes(': ') ? m.slice(m.indexOf(': ') + 2) : m;
  if (code === 503 || /还没连上|连接已断开/.test(m)) return '对方离线：两台电脑之间的长连接现在没有连上';
  if (/VersionConflict/.test(m)) return tail;
  if (/FileNotFoundError|No such file/.test(m)) return '文件或文件夹不存在：' + tail;
  if (/FileExistsError/.test(m)) return '目标已存在，不会覆盖：' + tail;
  if (/PermissionError/.test(m) || code === 403) return '没有权限：' + tail;
  if (/NotADirectoryError/.test(m)) return '不是文件夹：' + tail;
  return m || `出错（${code}）`;
}

// 本机设备 ID（从互联服务的 /status 取，缓存）——用来判断请求是发给本机还是对方
let selfId = null;
async function getSelfId() {
  if (selfId) return selfId;
  const r = await linkApi('GET', '/status');
  if (r.fail || r.code !== 200) throw new OpError(503, '本机互联服务没在运行');
  selfId = JSON.parse(r.body).self.device_id;
  return selfId;
}

// 发一次文件操作。返回 { result, data }；data 是读文件时的二进制内容
function linkFile(target, op, args, payload) {
  return new Promise((resolve, reject) => {
    const body = payload || Buffer.alloc(0);
    const headers = { 'X-Op': op, 'X-Args': asciiJson(args), 'X-Target': target, 'X-Source': SOURCE, 'X-Result-Body': '1',
      'Content-Type': 'application/octet-stream', 'Content-Length': body.length };
    const r = http.request({ host: '127.0.0.1', port: LINK_API, path: '/file', method: 'POST', headers, timeout: 60000, maxHeaderSize: 8 * 1024 * 1024 }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        if (res.statusCode !== 200) {
          let e = buf.toString('utf8'); try { e = JSON.parse(e).error; } catch {}
          return reject(new OpError(res.statusCode, explain(res.statusCode, e)));
        }
        try {
          if (res.headers['x-result-in-body'] === '1') resolve({ result: JSON.parse(buf.toString('utf8')), data: Buffer.alloc(0) });
          else resolve({ result: JSON.parse(res.headers['x-result'] || 'null'), data: buf });
        } catch (e) { reject(new OpError(502, '互联服务返回的数据有问题：' + e.message)); }
      });
    });
    r.on('error', (e) => reject(new OpError(503, e.code === 'ECONNREFUSED' ? '本机互联服务没在运行' : '连不上本机互联服务：' + e.message)));
    r.on('timeout', () => r.destroy(Object.assign(new Error('互联服务响应超时'), { code: 'ETIMEDOUT' })));
    r.end(body);
  });
}
const targetOf = async (dev) => (dev === await getSelfId() ? 'self' : 'peer');

async function listAll(target, p) {   // 大目录分页读，最多 LIST_CAP 项
  let all = null, offset = 0;
  for (;;) {
    const { result: page } = await linkFile(target, 'list', { path: p, offset, limit: PAGE });
    if (!page || !Array.isArray(page.entries)) throw new OpError(502, '互联服务返回的目录格式不对');
    if (!all) all = { ...page, entries: [] };
    all.entries.push(...page.entries);
    all.total = page.total != null ? page.total : all.entries.length;
    if (page.next_offset == null || page.total == null) break;
    if (all.entries.length >= LIST_CAP) { all.truncated = true; break; }
    offset = page.next_offset;
  }
  delete all.offset; delete all.next_offset;
  return all;
}

const OPS = new Set(['roots', 'list', 'stat', 'mkdir', 'move', 'copy', 'delete', 'watch']);
async function fileOp({ dev, op, args }) {
  if (!OPS.has(op)) throw new OpError(400, '不支持的操作：' + op);
  const target = await targetOf(dev);
  if (op === 'list') return listAll(target, (args || {}).path);
  return (await linkFile(target, op, args || {})).result;
}

// 跨设备传文件或整个文件夹：从源设备分块读出，分块写到目标设备（只新建，不覆盖）；move=true 时全部传完后把源移进回收站
const TREE_MAX = 5000;
const joinP = (d, n) => (d.endsWith('/') ? d + n : d + '/' + n);
async function copyFile(src, dst, fromPath, toPath, mtime) {
  const uploadId = Math.random().toString(36).slice(2, 14);
  let offset = 0;
  for (;;) {
    const { result: rr, data } = await linkFile(src, 'read', { path: fromPath, offset, length: CHUNK });
    const final = rr.eof || !data.length;
    await linkFile(dst, 'write', { path: toPath, offset, upload_id: uploadId, final, if_version: 'new', mtime }, data);
    offset += data.length;
    if (final) return offset;
  }
}
async function transfer({ from, to, move }) {
  const [src, dst] = [await targetOf(from.dev), await targetOf(to.dev)];
  const { result: info } = await linkFile(src, 'stat', { path: from.path });
  if (!info || !info.exists) throw new OpError(404, '文件不存在：' + from.path);
  let bytes = 0, files = 0, dirs = 0, skipped = 0;
  if (info.type === 'dir') {
    // 先把整棵树列出来（快捷方式/符号链接不跟进），数量超限就不传，免得传一半
    const plan = [], queue = [[from.path, to.path]];
    while (queue.length) {
      const [s, d] = queue.shift();
      plan.push({ dir: true, d });
      const page = await listAll(src, s);
      for (const e of page.entries) {
        if (e.link) { skipped++; continue; }
        if (e.type === 'dir') queue.push([joinP(s, e.name), joinP(d, e.name)]);
        else plan.push({ s: joinP(s, e.name), d: joinP(d, e.name), mtime: e.mtime });
      }
      if (page.truncated || plan.length > TREE_MAX) throw new OpError(400, `文件夹里的东西太多（超过 ${TREE_MAX} 项），请分开传`);
    }
    const { result: there } = await linkFile(dst, 'stat', { path: to.path });
    if (there && there.exists) throw new OpError(409, '目标已存在，不会覆盖：' + to.path);
    for (const it of plan) {
      if (it.dir) { await linkFile(dst, 'mkdir', { path: it.d }); dirs++; }
      else { bytes += await copyFile(src, dst, it.s, it.d, it.mtime); files++; }
    }
  } else {
    bytes = await copyFile(src, dst, from.path, to.path, info.mtime); files = 1;
  }
  let trashed = null;
  if (move) trashed = (await linkFile(src, 'delete', { path: from.path })).result.trashed_to;
  return { bytes, files, dirs, skipped, trashed_to: trashed };
}

// 快速查看：把文件内容原样交给页面（图片、PDF、音视频直接显示，文字只取开头）。
// 用 GET 是为了能直接当 <img>/<iframe> 的地址；带一个每次启动随机生成的口令，别的网页拿不到口令就读不了。
const RAW_TOKEN = require('crypto').randomBytes(16).toString('hex');
const RAW_MIME = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp', svg: 'image/svg+xml',
  ico: 'image/x-icon', heic: 'image/heic', pdf: 'application/pdf', mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm', mp3: 'audio/mpeg',
  wav: 'audio/wav', m4a: 'audio/mp4', flac: 'audio/flac', ogg: 'audio/ogg' };
const RAW_MAX = 200 * 1024 * 1024;
async function raw(res, q) {
  if (q.get('t') !== RAW_TOKEN) return sendJson(res, 403, { error: '口令不对' });
  const dev = q.get('dev') || '', p = q.get('path') || '', max = Math.min(Number(q.get('max')) || RAW_MAX, RAW_MAX);
  try {
    const target = await targetOf(dev);
    const { result: info } = await linkFile(target, 'stat', { path: p });
    if (!info || !info.exists || info.type === 'dir') return sendJson(res, 404, { error: '文件不存在' });
    const e = (p.match(/\.([^./]+)$/) || [])[1] || '';
    const type = RAW_MIME[e.toLowerCase()] || 'text/plain; charset=utf-8';
    const len = Math.min(info.size, max);
    const head = { 'Content-Type': type, 'Content-Length': len, 'Cache-Control': 'no-store', 'X-Total-Size': info.size, 'X-Content-Type-Options': 'nosniff' };
    // SVG 和文字（可能是 HTML）里的脚本不许跑：页面只把它们当图、当文字看
    if (/svg|text/.test(type)) head['Content-Security-Policy'] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox";
    res.writeHead(200, head);
    let offset = 0;
    while (offset < len) {
      const { data } = await linkFile(target, 'read', { path: p, offset, length: Math.min(CHUNK, len - offset) });
      if (!data.length) break;
      if (!res.write(data)) await new Promise((r) => res.once('drain', r));
      offset += data.length;
    }
    res.end();
  } catch (err) {
    if (!res.headersSent) sendJson(res, err.code >= 400 && err.code < 600 ? err.code : 500, { error: err.message || String(err) });
    else res.destroy();
  }
}

// 打开对方电脑上的文件：先把它取一份到本机的临时目录（和对方的版本一致就直接复用），再交给 App 用默认程序打开
const os = require('os');
const crypto = require('crypto');
const FETCH_DIR = path.join(os.tmpdir(), '统一文件页-对方文件副本');
async function fetchCopy({ dev, path: p }) {
  const target = await targetOf(dev);
  if (target === 'self') throw new OpError(400, '这是本机的文件，直接打开就行');
  const { result: info } = await linkFile(target, 'stat', { path: p });
  if (!info || !info.exists) throw new OpError(404, '文件不存在：' + p);
  if (info.type === 'dir') throw new OpError(400, '文件夹不用取到本机');
  const name = p.slice(p.lastIndexOf('/') + 1).replace(/[\\:*?"<>|]/g, '_');
  const dir = path.join(FETCH_DIR, crypto.createHash('sha1').update(dev + '|' + p).digest('hex').slice(0, 12));
  const local = path.join(dir, name);
  try {
    const st = fs.statSync(local);
    const known = FETCHED.get(local);
    // 本机副本有没传回去的改动（或冲突）时不拿对方的覆盖它
    if (known && (known.state !== 'ok' || st.mtimeMs !== known.mtimeMs)) return { local, reused: true, size: st.size, unsynced: true };
    if (st.size === info.size && Math.abs(st.mtimeMs / 1000 - info.mtime) < 2) { if (!known) track(local, dev, p, info.version); return { local, reused: true, size: info.size }; }
  } catch {}
  fs.mkdirSync(dir, { recursive: true });
  const part = local + '.part';
  const fd = fs.openSync(part, 'w');
  try {
    let offset = 0;
    for (;;) {
      const { result: rr, data } = await linkFile(target, 'read', { path: p, offset, length: CHUNK });
      if (data.length) fs.writeSync(fd, data, 0, data.length, offset);
      offset += data.length;
      if (rr.eof || !data.length) break;
    }
  } finally { fs.closeSync(fd); }
  let out = local;
  try { fs.renameSync(part, local); }   // 对方改过的话，新副本直接顶替旧副本
  catch {                               // 旧副本正被程序占用：放进另一个子目录
    const alt = path.join(dir, String(Date.now()));
    fs.mkdirSync(alt, { recursive: true });
    out = path.join(alt, name); fs.renameSync(part, out);
  }
  fs.utimesSync(out, info.mtime, info.mtime);
  track(out, dev, p, info.version);
  return { local: out, reused: false, size: info.size };
}

// 副本改了就传回对方：每 3 秒看一眼取下来的副本，改动停下来（两次看到的大小和时间一样）后，
// 按取下来时的版本号写回去；对方在这期间也改过，就不覆盖，记成冲突，副本留着让人自己处理。
const FETCHED = new Map();   // 本机副本路径 → { dev, path, version, mtimeMs, size, pending, state }
const SYNC_LOG = [];         // 给页面显示的结果
let syncSeq = 0;
function track(local, dev, p, version) {
  const st = fs.statSync(local);
  FETCHED.set(local, { dev, path: p, version, mtimeMs: st.mtimeMs, size: st.size, pending: null, state: 'ok' });
}
function syncNote(e, ok, msg) { SYNC_LOG.push({ seq: ++syncSeq, time: Date.now(), ok, dev: e.dev, path: e.path, msg }); if (SYNC_LOG.length > 50) SYNC_LOG.shift(); }
let syncing = false;
async function syncBack() {
  if (syncing) return; syncing = true;
  try {
    for (const [local, e] of FETCHED) {
      if (e.state !== 'ok') continue;
      let st; try { st = fs.statSync(local); } catch { FETCHED.delete(local); continue; }
      if (st.mtimeMs === e.mtimeMs && st.size === e.size) { e.pending = null; continue; }
      const sig = st.mtimeMs + '|' + st.size;
      if (e.pending !== sig) { e.pending = sig; continue; }   // 还在写，等下一轮
      try {
        const target = await targetOf(e.dev);
        const data = fs.readFileSync(local);
        const uploadId = crypto.randomBytes(6).toString('hex');
        let offset = 0, out = null;
        do {
          const part = data.subarray(offset, offset + CHUNK), final = offset + part.length >= data.length;
          const { result } = await linkFile(target, 'write', { path: e.path, offset, upload_id: uploadId, final, if_version: e.version }, part);
          offset += part.length; if (final) out = result;
        } while (!out);
        Object.assign(e, { version: out.version, mtimeMs: st.mtimeMs, size: st.size, pending: null });
        syncNote(e, true, '已把改动传回去');
      } catch (err) {
        if (/VersionConflict|版本/.test(err.message)) { e.state = 'conflict'; syncNote(e, false, '对方那边也改过这个文件，没有覆盖。你改的副本留在 ' + local); }
        else syncNote(e, false, '传回去失败，稍后再试：' + err.message);   // 对方离线等：下一轮再试
        e.pending = null;
      }
    }
  } finally { syncing = false; }
}
setInterval(syncBack, 3000).unref();

// 操作记录（标出智能体做过的操作）：本机的直接读，对方的经长连接取
async function activity(dev) {
  if ((await targetOf(dev)) === 'self') {
    const r = await linkApi('GET', '/activity?n=300');
    if (r.fail || r.code !== 200) throw new OpError(503, '本机互联服务没在运行');
    return JSON.parse(r.body);
  }
  return (await linkFile('peer', 'activity', { n: 300 })).result;
}

// 对方推来的变化：长轮询本机互联服务的 /events
function events(res, qs) {
  const r = http.request({ host: '127.0.0.1', port: LINK_API, path: '/events?' + qs, method: 'GET', timeout: 70000 }, (lr) => {
    res.writeHead(lr.statusCode, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    lr.pipe(res);
  });
  r.on('error', () => { if (!res.headersSent) sendJson(res, 503, { error: '本机互联服务没在运行' }); });
  r.on('timeout', () => r.destroy());
  r.end();
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []; let size = 0;
    req.on('data', (c) => { size += c.length; if (size > 1e6) { reject(new OpError(413, '请求太大')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')); } catch { reject(new OpError(400, '请求格式不对')); } });
  });
}
const api = (res, fn) => fn().then((v) => sendJson(res, 200, v)).catch((e) => sendJson(res, e.code >= 400 && e.code < 600 ? e.code : 500, { error: e.message || String(e) }));

const guard = (res, p) => p.catch((e) => { if (!res.headersSent) sendJson(res, 500, { error: String(e && e.message || e) }); else res.end(); });
const server = http.createServer((req, res) => {
  let url, urlPath;
  try { url = new URL(req.url, 'http://x'); urlPath = decodeURIComponent(url.pathname); }
  catch { res.writeHead(400).end('Bad request'); return; }

  if (urlPath === '/__devices') return guard(res, devices(res));
  // 写操作只接受本页面发来的 POST（跨站页面发不了带 JSON 类型的请求，浏览器会先拦下预检）
  const isPost = req.method === 'POST' && /^application\/json/.test(req.headers['content-type'] || '');
  if (urlPath === '/__file' && isPost) return api(res, async () => fileOp(await readBody(req)));
  if (urlPath === '/__transfer' && isPost) return api(res, async () => transfer(await readBody(req)));
  if (urlPath === '/__token' && isPost) return sendJson(res, 200, { token: RAW_TOKEN });   // 只有本页面（同源、JSON 类型的 POST）拿得到
  if (urlPath === '/__sync') { const since = Number(url.searchParams.get('since')) || 0; return sendJson(res, 200, { seq: syncSeq, items: SYNC_LOG.filter((x) => x.seq > since) }); }
  if (urlPath === '/__raw')return raw(res, url.searchParams);
  if (urlPath === '/__fetch' && isPost)return api(res, async () => fetchCopy(await readBody(req)));
  if (urlPath === '/__activity')return api(res, () => activity(url.searchParams.get('dev') || ''));
  if (urlPath === '/__events') return events(res, url.searchParams.toString());

  let filePath = path.join(ROOT, urlPath === '/' ? 'index.html' : urlPath);
  const rel = path.relative(ROOT, filePath);
  if (rel.startsWith('..') || path.isAbsolute(rel) || /(^|[\\/])(node_modules|\.edge-profile)([\\/]|$)/.test(rel)) {
    res.writeHead(403).end('Forbidden');
    return;
  }
  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, 'index.html');
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('Not found');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    const headers = { 'Content-Type': MIME[ext] || 'application/octet-stream', 'Cache-Control': 'no-store' };
    res.writeHead(200, headers).end(data);
  });
});

server.listen(PORT, '127.0.0.1', () => console.log(`统一文件页：http://localhost:${PORT}`));
