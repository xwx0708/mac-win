/* 统一文件页
   把 Windows 资源管理器和 Mac 访达合成一个页面。设备列表来自 Tailscale，不写死任何一台。
   所有设备的文件都经页面服务（server.js）→ 本机互联服务实时读取和操作，对方的再走 Tailscale 长连接；
   对方的变化经长连接推过来，本机正在看的文件夹定时重读。删除只进回收站。智能体做过的操作在名字旁标出。 */

// ───────────────────────────────────────── 图标
const P = {
  back: 'M15 5l-7 7 7 7', fwd: 'M9 5l7 7-7 7', up: 'M12 19V5M5 12l7-7 7 7',
  refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7', search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-3.5-3.5',
  plus: 'M12 5v14M5 12h14', cut: 'M6 6l12 12M6 18L18 6M5 5h2v2H5zM5 17h2v2H5z', copy: 'M9 9h10v11H9zM5 15V4h10',
  paste: 'M8 5h8v3H8zM6 6H5v14h14V6h-1', rename: 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4',
  share: 'M12 15V4M8 8l4-4 4 4M5 12v8h14v-8', trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  sort: 'M7 4v16M4 17l3 3 3-3M17 20V4M14 7l3-3 3 3', group: 'M4 5h16M4 12h10M4 19h6', filter: 'M4 5h16l-6 8v6l-4-2v-4z',
  tag: 'M4 4h8l8 8-8 8-8-8zM8.5 8.5h.01', eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01', home: 'M4 11l8-7 8 7v9h-5v-6H9v6H4z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2', swap: 'M4 8h14l-3-3M20 16H6l3 3',
  desktop: 'M3 5h18v11H3zM9 20h6M12 16v4', download: 'M12 4v11M7 11l5 5 5-5M5 20h14', doc: 'M6 3h8l4 4v14H6zM14 3v4h4',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M9 9h.01', apps: 'M5 5h5v5H5zM14 5h5v5h-5zM5 14h5v5H5zM14 14h5v5h-5z',
  music: 'M9 18V6l10-2v12M9 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM19 16a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z', video: 'M4 6h12v12H4zM16 10l5-3v10l-5-3',
  drive: 'M4 14h16v5H4zM6 14l2-9h8l2 9M16.5 16.5h.01', cloud: 'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9.5 4.3 4.3 0 0 1 17.5 18z',
  network: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
  lock: 'M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3', list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  columns: 'M4 5h5v14H4zM9.5 5h5v14h-5zM15 5h5v14h-5z', gallery: 'M4 4h16v11H4zM4 18h3v2H4zM8.5 18h3v2h-3zM13 18h3v2h-3zM17.5 18H20v2h-2.5z',
  panel: 'M4 5h16v14H4zM15 5v14', star: 'M12 4l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z',
  users: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 19c0-3 3-5 6-5s6 2 6 5M17 11a2.5 2.5 0 1 0 0-5M21 19c0-2.5-1.5-4-4-4.6',
  close: 'M6 6l12 12M18 6L6 18', chev: 'M9 6l6 6-6 6', terminal: 'M4 5h16v14H4zM7 9l3 3-3 3M12 15h5',
  airdrop: 'M12 13h.01M8.5 15.5a5 5 0 1 1 7 0M5.5 18a9 9 0 1 1 13 0', folder: 'M3 7h6l2 2h10v10H3z', send: 'M4 12h14M13 6l6 6-6 6',
  open: 'M5 5h6M5 5v14h14v-6M13 5h6v6M19 5l-8 8', user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20c0-4 4-6 8-6s8 2 8 6',
};
const ic = (n, c = '') => `<svg class="ic ${c}" viewBox="0 0 24 24"><path d="${P[n]}"/></svg>`;

// ───────────────────────────────────────── 设备
// 设备一台也不写死：全部来自 Tailscale 里这个账号下已授权的设备（页面服务 /__devices，每 15 秒刷新一次）。
// 新设备加入 Tailscale 后会自动出现在左侧；装了互联服务并连上的设备，可以浏览它的共享目录。
const DROP = 'M12 3C12 3 6 10 6 14.5a6 6 0 0 0 12 0C18 10 12 3 12 3z';
let DEVS = [];
const D = id => DEVS.find(d => d.id === id) || { id, name: '未知设备', host: '', os: '' };
const SELF = () => DEVS.find(d => d.self) || { id: 'self', name: '本机', host: '', os: /Mac/.test(navigator.platform) ? 'macos' : 'windows', self: true, online: true };
const osCls = id => { const o = D(id).os; return o === 'windows' ? 'win' : o === 'macos' ? 'mac' : 'oth'; };
const OS_SHORT = { windows: 'Windows', macos: 'Mac', ios: 'iPhone', android: 'Android', linux: 'Linux' };
// 设备标记：水滴。Windows 实心尖朝左下，Mac 空心尖朝右上（开屏动画里两颗水滴的来向），其他系统空心尖朝上
const drop = (d, c = '') => `<svg class="drop ${osCls(d)} ${c}" viewBox="0 0 24 24"><path d="${DROP}"/></svg>`;
function devName(id) {   // 同一系统只有一台时叫"Mac""Windows"，有多台时带上设备名
  const d = D(id), short = OS_SHORT[d.os] || d.os || '设备';
  return DEVS.filter(x => x.os === d.os).length > 1 ? `${short} ${d.name}` : short;
}
const devStatus = d => d.self ? '本机'
  : !d.online ? `离线${d.lastSeen && !d.lastSeen.startsWith('0001') ? ' · ' + ago(d.lastSeen) : ''}`
  : d.linked ? `在线${d.rtt != null ? ' · <b class="num">' + Math.round(d.rtt) + '</b> ms' : ''}`
  : '在线 · 未接入互联服务';
// 侧栏空间窄，用短一点的状态；完整状态在悬停提示和主页卡片里
const devStatusShort = d => d.self ? '本机'
  : !d.online ? `离线${d.lastSeen && !d.lastSeen.startsWith('0001') ? ' · ' + ago(d.lastSeen).replace(' ', '') : ''}`
  : d.linked ? `在线${d.rtt != null ? ' · <b class="num">' + Math.round(d.rtt) + '</b> ms' : ''}`
  : '在线 · 未接入';
function ago(iso) {
  const s = (Date.now() - new Date(iso)) / 1000;
  return s < 3600 ? Math.max(1, Math.round(s / 60)) + ' 分钟前' : s < 86400 ? Math.round(s / 3600) + ' 小时前' : Math.round(s / 86400) + ' 天前';
}
const GOO = c => `<svg class="goo ${c}" viewBox="0 0 44 24"><g filter="url(#goo)"><circle class="a" cx="15" cy="12" r="6"/><circle class="b" cx="29" cy="12" r="6"/></g></svg>`;

// ───────────────────────────────────────── 文件树
// 所有设备（包括本机）的文件都经页面服务 → 本机互联服务实时读取，对方的再走 Tailscale 长连接。进入文件夹时才读。
// 节点按"设备 + 路径"唯一：同一个文件夹无论从侧栏、收藏还是面包屑进入，都是同一个节点。
// 路径一律用 / 分隔的绝对路径：Windows 如 E:/工作区，Mac 如 /Users/wx。
let uid = 0;
const ALL = [];
const NODES = new Map();   // 设备|路径（小写）→ 节点
const ROOTS = {};          // 设备 id → 侧栏里列出的顶层：各个盘 + 共享目录
const INFO = {};           // 设备 id → 互联服务给的 roots（盘、常用位置、禁区、可写范围）
const isRoot = p => p === '/' || /^[A-Za-z]:\/$/.test(p);
function parentPath(p) {
  if (isRoot(p)) return null;
  const q = p.slice(0, p.lastIndexOf('/'));
  return q === '' ? '/' : /^[A-Za-z]:$/.test(q) ? q + '/' : q;
}
const joinPath = (d, name) => (d.endsWith('/') ? d + name : d + '/' + name);
const baseName = p => (isRoot(p) ? p : p.slice(p.lastIndexOf('/') + 1));
const nkey = (dev, p) => dev + '|' + p.toLowerCase();   // NTFS 和 APFS 默认都不分大小写
function node(dev, p, init) {
  let n = NODES.get(nkey(dev, p));
  if (!n) {
    const pp = parentPath(p);
    n = { id: ++uid, dev, path: p, name: baseName(p), kind: 'dir', date: '', children: [], unloaded: true, tags: [...((TAGSTORE[nkey(dev, p)] || {}).tags || [])], parent: pp ? node(dev, pp) : null };
    NODES.set(nkey(dev, p), n); ALL.push(n);
  }
  if (init) Object.assign(n, init);
  return n;
}
const byId = id => ALL.find(n => n.id === +id);
const kids = n => (n.children || []).filter(c => !c.gone && (state.showHidden || !c.hidden));
const roots = id => ROOTS[id] || [];
const sharePath = dev => ((INFO[dev] && INFO[dev].places.find(p => p.name === '互传')) || {}).path || '';

// 调页面服务。出错时抛出带中文原因的 Error
async function callJSON(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  let j = {}; try { j = await r.json(); } catch {}
  if (!r.ok) throw new Error(j.error || `出错（${r.status}）`);
  return j;
}
const callFile = (dev, op, args) => callJSON('/__file', { dev, op, args });

const fmtTime = t => { const d = new Date(t * 1000), z = x => String(x).padStart(2, '0'); return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`; };
const busy = () => state.renaming || drag || wheel;
let pendingRender = false;
function softRender() { if (busy()) { pendingRender = true; return; } pendingRender = false; render(); }

// 读一个文件夹。quiet=true 是后台刷新：内容没变就不重绘
async function loadDir(n, quiet) {
  if (n.loadingDir || n.kind !== 'dir') return;
  n.loadingDir = true;
  const seq = n.loadSeq = (n.loadSeq || 0) + 1;
  let changed = !quiet;
  try {
    const j = await callFile(n.dev, 'list', { path: n.path });
    if (seq !== n.loadSeq) return;
    const list = j.entries.map(e => {
      const c = node(n.dev, joinPath(n.path, e.name));
      Object.assign(c, { name: e.name, kind: e.type === 'dir' ? 'dir' : 'file', size: e.type === 'dir' ? undefined : e.size,
        date: e.mtime ? fmtTime(e.mtime) : '', mtime: e.mtime, version: e.version, alloc: e.alloc, hidden: !!e.hidden, gone: false });
      return c;
    });
    const sig = j.entries.map(e => `${e.name}|${e.type}|${e.size}|${e.mtime}`).join('\n');
    for (const old of n.children || []) if (!list.includes(old)) old.gone = true;
    n.children = list; n.unloaded = false; n.writable = j.writable; n.truncated = j.truncated ? j.total : 0;
    if (n.loadError) changed = true;
    n.loadError = null;
    if (sig !== n.sig) changed = true;
    n.sig = sig;
  } catch (e) {
    if (seq === n.loadSeq && !quiet) { n.loadError = String(e.message || e); changed = true; }
  } finally { if (seq === n.loadSeq) n.loadingDir = false; }
  if (changed) softRender();
}
const reload = (...ns) => ns.filter(n => n && n.kind === 'dir').forEach(n => loadDir(n, true));

// 设备的盘和常用位置（互联服务的 roots 操作）
const WORKSPACE_PATH = 'E:/工作区';
let WORKSPACE = null;
async function loadRoots(d) {
  try {
    const info = await callFile(d.id, 'roots', {});
    INFO[d.id] = info;
    const drives = info.drives.map(x => node(d.id, x.path, { name: x.label, drive: { total: x.total, free: x.free, fs: x.fs || '' }, writable: x.writable }));
    // 工作区不是每台电脑都有：只在本机真有这个文件夹时才放进收藏
    if (d.self && info.platform === 'windows') WORKSPACE = await callFile(d.id, 'stat', { path: WORKSPACE_PATH }).then(s => s.exists && s.type === 'dir' ? WORKSPACE_PATH : null).catch(() => null);
    const share = info.places.find(p => p.name === '互传');
    ROOTS[d.id] = share ? [...drives, node(d.id, share.path, { shareRoot: true })] : drives;
  } catch (e) { if (!ROOTS[d.id]) ROOTS[d.id] = []; }
}

// 收藏里的常用文件夹：把各台设备上意义相同的位置合成一个入口（Mac 叫"文稿""影片"，Windows 叫"文档""视频"）
const PLACE_KEYS = { 桌面: 'desktop', 文档: 'docs', 文稿: 'docs', 下载: 'dl', 图片: 'pics', 视频: 'video', 影片: 'video', 音乐: 'music', 互传: 'share' };
const MERGED_DEF = { desktop: ['桌面', 'desktop'], docs: ['文档', 'doc'], dl: ['下载', 'download'], pics: ['图片', 'image'], video: ['视频', 'video'], music: ['音乐', 'music'], share: ['互传', 'swap'] };
let MERGED = {};
function buildMerged() {
  MERGED = {};
  for (const [k, [label, icon]] of Object.entries(MERGED_DEF)) MERGED[k] = { label, icon, nodes: [] };
  for (const d of DEVS) {
    if (!roots(d.id).length || !INFO[d.id]) continue;
    for (const p of INFO[d.id].places) { const k = PLACE_KEYS[p.name]; if (k) MERGED[k].nodes.push(node(d.id, p.path)); }
  }
}
const browsable = () => DEVS.filter(d => roots(d.id).length);

async function refreshDevices() {
  try {
    const r = await fetch('/__devices'); const j = await r.json();
    if (!r.ok) throw new Error(j.error);
    const before = JSON.stringify(DEVS.map(d => [d.id, d.online, d.linked, d.rtt && Math.round(d.rtt / 10)]));
    DEVS = j.devices.sort((a, b) => (b.self - a.self) || (b.linked - a.linked) || (b.online - a.online) || a.name.localeCompare(b.name));
    const usable = DEVS.filter(d => d.self || d.linked);
    await Promise.all(usable.map(loadRoots));
    for (const d of DEVS) if (!d.self && !d.linked) ROOTS[d.id] = [];   // 离线或没接入互联服务：先不显示它的盘
    buildMerged();
    return before !== JSON.stringify(DEVS.map(d => [d.id, d.online, d.linked, d.rtt && Math.round(d.rtt / 10)]));
  } catch (e) {
    if (!DEVS.length) { DEVS = [{ id: 'self', self: true, name: '本机', host: '', os: /Mac/.test(navigator.platform) ? 'macos' : 'windows', online: true, linked: false }]; buildMerged(); }
    return false;
  }
}

// ───────────────────────────────────────── 实时更新
// 对方的文件夹：订阅（互联服务的 watch），对方有变化时经长连接推过来；本机的文件夹：每 3 秒重读一次正在看的文件夹。
const peerDev = () => DEVS.find(d => !d.self && d.linked);
const otherOf = id => (D(id).self ? (peerDev() || {}).id : SELF().id);
function shownDirs() {
  const l = loc();
  if (l.t === 'node') { const n = byId(l.id); return n && n.kind === 'dir' ? [n] : []; }
  if (l.t === 'merged') return MERGED[l.k].nodes;
  if (l.t === 'home') return MERGED.share ? MERGED.share.nodes : [];
  return [];
}
let watchSig = '', watchAt = 0;
async function syncWatch(force) {
  const p = peerDev(); if (!p) return;
  const paths = shownDirs().filter(n => n.dev === p.id && !n.unloaded).map(n => n.path);
  const sig = paths.join('\n');
  if (!force && sig === watchSig && Date.now() - watchAt < 60000) return;
  try { await callFile(p.id, 'watch', { paths, ttl: 150 }); watchSig = sig; watchAt = Date.now(); } catch {}
}
const reloadTimers = new Map();
function onPeerEvent(e) {
  const p = peerDev(); if (!p) return;
  const abs = /^([A-Za-z]:)?\//.test(e.path) ? e.path : joinPath(sharePath(p.id), e.path);
  const parent = NODES.get(nkey(p.id, parentPath(abs) || abs));
  if (!parent || parent.unloaded) return;
  clearTimeout(reloadTimers.get(parent.id));
  reloadTimers.set(parent.id, setTimeout(() => { flash[nkey(p.id, abs)] = Date.now(); loadDir(parent, true); }, 250));
}
const flash = {};   // 刚被对方改过的项目，短暂高亮
async function eventLoop() {
  let seq = -1, ep = '';
  for (;;) {
    try {
      const j = await callJSON(`/__events?since=${seq}&wait=25&epoch=${encodeURIComponent(ep)}`);
      if (seq >= 0) j.events.forEach(onPeerEvent);
      seq = j.seq; ep = j.epoch;
    } catch { await new Promise(r => setTimeout(r, 3000)); }
  }
}
function pollSelf() {
  for (const n of shownDirs()) if (D(n.dev).self && !n.unloaded) loadDir(n, true);
}

// ───────────────────────────────────────── 智能体做过的操作
// 读两台电脑的操作记录，找出智能体（Claude Code / Codex）最近一小时写入、新建、移动、复制过的文件，在列表里标出来。
const AGENT = {};   // 设备|路径 → { agent, action, time }
const AGENT_NAME = { claude: 'Claude', codex: 'Codex' };
async function refreshActivity() {
  for (const d of browsable()) {
    try {
      const j = await callJSON('/__activity?dev=' + encodeURIComponent(d.id));
      for (const it of j.items || []) {
        const s = it.source || {};
        if (s.kind !== 'agent' || !['write', 'mkdir', 'move', 'copy'].includes(it.action) || !it.ok) continue;
        const dev = it.target === 'self' ? d.id : otherOf(d.id);
        const p = it.detail && (it.detail.dst || it.detail.path);
        if (!dev || !p) continue;
        const abs = /^([A-Za-z]:)?\//.test(p) ? p.replace(/\\/g, '/') : joinPath(sharePath(dev), p);
        const k = nkey(dev, abs);
        if (!AGENT[k] || AGENT[k].time < it.time) AGENT[k] = { agent: s.agent, action: it.action, time: it.time };
      }
    } catch {}
  }
}
const ACTION_NAME = { write: '写入', mkdir: '新建', move: '移动', copy: '复制' };
function agentOf(n) {
  const a = AGENT[nkey(n.dev, n.path)];
  return a && Date.now() / 1000 - a.time < 3600 ? a : null;
}
function agentMark(n) {
  const a = agentOf(n); if (!a) return '';
  return `<span class="agentmark" title="${esc(AGENT_NAME[a.agent] || a.agent)} ${ago(new Date(a.time * 1000).toISOString())}${ACTION_NAME[a.action] || ''}了它">${esc(AGENT_NAME[a.agent] || a.agent)}</span>`;
}

// 颜色标签的界面已暂时撤下（待定，见 README"待定事项"）。下面的存储仍保留：已有的标签数据不丢，改名、移动时照样跟着走，改版时直接接上
const TAGS = { red: ['红色', '#e5534b'], orange: ['橙色', '#e0823d'], yellow: ['黄色', '#d4a72c'], green: ['绿色', '#57ab5a'], blue: ['蓝色', '#539bf5'], purple: ['紫色', '#986ee2'], gray: ['灰色', '#8b8b8b'] };
// 标签存在 App 自己的存储里（按 设备|路径），重启后还在；本页面里改名、移动时跟着走
var TAGSTORE; try { TAGSTORE = JSON.parse(localStorage.getItem('unified.tags') || '{}'); } catch { TAGSTORE = {}; }
function saveTags(n) {
  const k = nkey(n.dev, n.path);
  if (n.tags.length) TAGSTORE[k] = { dev: n.dev, path: n.path, kind: n.kind, tags: n.tags }; else delete TAGSTORE[k];
  try { localStorage.setItem('unified.tags', JSON.stringify(TAGSTORE)); } catch {}
}
function moveTags(dev, from, to) {   // 文件夹改名/移动时，它自己和里面的标签都换到新路径
  const pre = nkey(dev, from), hit = Object.keys(TAGSTORE).filter(k => k === pre || k.startsWith(pre + '/'));
  for (const k of hit) {
    const v = TAGSTORE[k]; delete TAGSTORE[k];
    const np = to + v.path.slice(from.length), c = node(dev, np, { kind: v.kind });
    c.tags = [...new Set([...c.tags, ...v.tags])]; saveTags(c);
  }
  if (hit.length) try { localStorage.setItem('unified.tags', JSON.stringify(TAGSTORE)); } catch {}
}
// 文件类型：[显示名, 图标原色]
const EXT = {
  pdf: ['PDF 文档', '#e5484d'], doc: ['Word 文档', '#2b7cd3'], docx: ['Word 文档', '#2b7cd3'], xls: ['Excel 表格', '#1f9d55'], xlsx: ['Excel 表格', '#1f9d55'], csv: ['CSV 表格', '#1f9d55'],
  ppt: ['PowerPoint 演示', '#d9622b'], pptx: ['PowerPoint 演示', '#d9622b'], zip: ['压缩文件', '#c9a227'], rar: ['压缩文件', '#c9a227'], '7z': ['压缩文件', '#c9a227'],
  png: ['图片', '#9b6ee0'], jpg: ['图片', '#9b6ee0'], jpeg: ['图片', '#9b6ee0'], webp: ['图片', '#9b6ee0'], gif: ['图片', '#9b6ee0'], svg: ['矢量图', '#9b6ee0'],
  mp4: ['视频', '#d6457a'], mov: ['视频', '#d6457a'], mkv: ['视频', '#d6457a'], mp3: ['音频', '#e07a3d'], wav: ['音频', '#e07a3d'], m4a: ['音频', '#e07a3d'],
  md: ['Markdown 文稿', '#7d8590'], txt: ['文本文稿', '#7d8590'], log: ['日志', '#7d8590'], html: ['网页', '#e4673a'], css: ['样式表', '#3f8fd9'], js: ['JavaScript', '#d6b21f'],
  json: ['JSON 文件', '#b8962e'], py: ['Python 脚本', '#3776ab'], ps1: ['PowerShell 脚本', '#2f6fc4'], sh: ['Shell 脚本', '#4a9d5b'], csv2: ['', ''],
  exe: ['应用程序', '#5b6470'], msi: ['安装程序', '#5b6470'], dmg: ['磁盘映像', '#5b6470'], app: ['应用程序', '#3d8bf0'], lnk: ['快捷方式', '#4d9be6'], url: ['网址快捷方式', '#4d9be6'],
  f3d: ['Fusion 模型', '#f08a24'], fcstd: ['FreeCAD 模型', '#d94f3d'], stl: ['3D 模型', '#f08a24'], loop: ['Loop 组件', '#7b5cd6'], photoslibrary: ['照片图库', '#e0823d'],
};
const ext = n => (n.name.includes('.') ? n.name.split('.').pop().toLowerCase() : '');
const typeOf = n => n.kind === 'dir' ? (n.drive ? '磁盘' : '文件夹') : ((EXT[ext(n)] || [])[0] || (ext(n) ? esc(ext(n).toUpperCase()) + ' 文件' : '文件'));
const fmtSize = b => b == null ? '—' : b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(1) + ' KB' : b < 1073741824 ? (b / 1048576).toFixed(1) + ' MB' : (b / 1073741824).toFixed(b < 1e12 ? 1 : 0) + ' GB';
const big = b => b >= 1e12 ? (b / 1099511627776).toFixed(2) + ' TB' : Math.round(b / 1073741824) + ' GB';
const pathOf = n => { const p = []; for (let x = n; x; x = x.parent) p.unshift(x); return p; };
const pathText = n => (/^[A-Za-z]:\//.test(n.path) ? n.path.replace(/\//g, '\\') : n.path);   // Windows 用反斜杠显示
const recent = () => ALL.filter(n => n.kind === 'file' && !n.gone && !n.hidden && n.date && !pathOf(n).some(p => p.gone)).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 16);
const sizeLabel = n => n.kind === 'dir' ? (n.unloaded ? '—' : kids(n).length + ' 项') : fmtSize(n.size);

// ───────────────────────────────────────── 状态
const state = {
  tabs: [{ hist: [{ t: 'home' }], i: 0 }], cur: 0, view: 'list', dev: 'all', sel: null, loading: false, renaming: null,
  preview: true, sort: { key: 'name', dir: 1 }, homeTab: 'recent', homeDev: null, q: '', clip: null,
  open: new Set(loadOpen()),   // 侧栏里展开着的设备分组
};
function loadOpen() { try { return JSON.parse(localStorage.getItem('unified.openDevices') || '[]'); } catch { return []; } }
function saveOpen() { try { localStorage.setItem('unified.openDevices', JSON.stringify([...state.open])); } catch {} }
const tab = () => state.tabs[state.cur];
const loc = () => tab().hist[tab().i];
function go(l) { const t = tab(); t.hist = t.hist.slice(0, t.i + 1); t.hist.push(l); t.i++; state.sel = null; state.q = ''; render(); setTimeout(() => syncWatch(true), 600); }

function resolve(l) {
  if (l.t === 'home') return { title: '主页', icon: 'home', crumbs: [], items: [] };
  if (l.t === 'recent') return { title: '最近使用', icon: 'clock', crumbs: [], items: recent(), flat: true };
  if (l.t === 'merged') { const mg = MERGED[l.k]; return { title: mg.label, icon: mg.icon, crumbs: [], items: mg.nodes.flatMap(kids), merged: mg }; }
  if (l.t === 'dev') return { title: devName(l.k), dev: l.k, crumbs: [], items: roots(l.k) };
  if (l.t === 'stub') return { title: l.label, icon: l.icon, crumbs: [], items: [], stub: true };
  const n = byId(l.id);
  return { title: n.name, node: n, dev: n.dev, crumbs: pathOf(n), items: kids(n) };
}
function visibleItems(r) {
  let items = r.items.filter(n => state.dev === 'all' || n.dev === state.dev);
  if (state.q) items = items.filter(n => n.name.toLowerCase().includes(state.q.toLowerCase()));
  const { key, dir } = state.sort;
  const val = n => key === 'name' ? n.name.toLowerCase() : key === 'date' ? n.date : key === 'size' ? (n.size || 0) : key === 'dev' ? n.dev : typeOf(n);
  return [...items].sort((a, b) => (a.kind !== b.kind ? (a.kind === 'dir' ? -1 : 1) : (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * dir));
}

// ───────────────────────────────────────── 小部件
// 图标用各自系统的原色：Windows 文件夹是黄色，Mac 文件夹是蓝色；文件按类型上色（PDF 红、Word 蓝、Excel 绿……）
const FOLDER = 'M2.5 6.5A1.5 1.5 0 0 1 4 5h5l2 2.2h9a1.5 1.5 0 0 1 1.5 1.5v9.8A1.5 1.5 0 0 1 20 20H4a1.5 1.5 0 0 1-1.5-1.5z';
const FOLDER_FRONT = 'M2.5 10.2A1.5 1.5 0 0 1 4 8.7h16a1.5 1.5 0 0 1 1.5 1.5v8.3A1.5 1.5 0 0 1 20 20H4a1.5 1.5 0 0 1-1.5-1.5z';
function fileIcon(n, cls = '') {
  if (n.locked) return `<span class="fi dir locked ${cls}">${ic('lock')}</span>`;
  if (n.drive) return `<span class="fi drv ${cls}">${ic('drive')}</span>`;
  if (n.kind === 'dir') return `<span class="fi dir ${osCls(n.dev)} ${cls}"><svg viewBox="0 0 24 24"><path class="bk" d="${FOLDER}"/><path class="ft" d="${FOLDER_FRONT}"/></svg></span>`;
  const e = ext(n), c = (EXT[e] || [])[1] || '#6b7280';
  return `<span class="fi file ${cls}" style="--c:${c}"><i>${esc(e.slice(0, 4)) || '·'}</i></span>`;
}
const devChip = d => `<span class="chip">${drop(d)}${esc(devName(d))}</span>`;
const WARN_USED = 80;   // 已用超过这个百分比，容量数字和进度条变成琥珀色
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const used = n => Math.round(100 - 100 * n.drive.free / n.drive.total);
const warnCls = n => (used(n) > WARN_USED ? 'warn' : '');
const nm = n => state.renaming === n.id ? `<input class="rename" value="${esc(n.name)}" data-rename="${n.id}">` : `<span class="nm">${esc(n.name)}</span>`;
const rowCls = n => `${state.sel === n.id ? 'sel' : ''} ${state.clip && state.clip.mode === 'cut' && state.clip.id === n.id ? 'cut' : ''} ${Date.now() - (flash[nkey(n.dev, n.path)] || 0) < 2500 ? 'fresh' : ''}`;

// ───────────────────────────────────────── 渲染
function render() {
  const r = resolve(loc());
  renderToolbar(r); renderCmd(r); renderSidebar(); renderContent(r); renderPreview(); renderStatus(r);
  document.getElementById('body').classList.toggle('nopreview', !state.preview || !state.sel);   // 详情面板只在选中文件时弹出
  const cols = document.querySelector('.cols');
  if (cols) cols.scrollLeft = cols.scrollWidth;
  const inp = document.querySelector('input.rename');
  if (inp) { inp.focus(); const dot = inp.value.lastIndexOf('.'); inp.setSelectionRange(0, dot > 0 ? dot : inp.value.length); }
}

function linkBadge() {
  const on = DEVS.filter(d => d.online).length, peer = DEVS.find(d => !d.self && d.linked);
  return `<span class="pulse ${peer ? '' : 'idle'}"></span>${on} 台在线 <em>Tailscale</em>` + (peer ? `互联 <b class="num">${peer.rtt != null ? Math.round(peer.rtt) : '—'}</b> ms` : '互联未连上');
}

function renderToolbar(r) {
  const t = tab();
  const root = `<button class="crumb" data-go='{"t":"home"}'>${ic('home')}</button>`;
  let crumbs = '';
  if (r.node) crumbs = `<button class="crumb" data-go='{"t":"dev","k":"${r.dev}"}'>${drop(r.dev)}${esc(devName(r.dev))}</button>` +
    r.crumbs.map(n => `${ic('chev', 'sep')}<button class="crumb" data-go='{"t":"node","id":${n.id}}'>${esc(n.name)}</button>`).join('');
  else if (r.title !== '主页') crumbs = `${ic('chev', 'sep')}<button class="crumb">${r.dev ? drop(r.dev) : ''}${esc(r.title)}</button>` +
    (r.merged ? `<span class="hint">${r.merged.nodes.map(n => `${drop(n.dev)}${esc(pathText(n))}`).join('<i>＋</i>')}</span>` : '');
  document.getElementById('toolbar').innerHTML = `
    <div class="navs">
      <button data-act="back" ${t.i ? '' : 'disabled'} title="后退">${ic('back')}</button>
      <button data-act="fwd" ${t.i < t.hist.length - 1 ? '' : 'disabled'} title="前进">${ic('fwd')}</button>
      <button data-act="up" ${r.node ? '' : 'disabled'} title="上一级">${ic('up')}</button>
      <button data-act="refresh" title="刷新">${ic('refresh')}</button>
    </div>
    <div class="address">${root}${crumbs}</div>
    <label class="search">${ic('search')}<input id="q" placeholder="在 ${esc(r.title)} 中搜索" value="${esc(state.q)}"><kbd>全部设备</kbd></label>`;
}

function renderCmd(r) {
  const b = (icon, label, extra = '') => `<button ${extra} title="${label}">${ic(icon)}<span>${label}</span></button>`;
  const on = k => state.sel ? `data-do="${k}"` : 'disabled';
  const views = [['icon', 'apps', '图标'], ['list', 'list', '列表'], ['column', 'columns', '分栏'], ['gallery', 'gallery', '画廊']]
    .map(([v, i, l]) => `<button class="${state.view === v ? 'on' : ''}" data-view="${v}" title="${l}">${ic(i)}</button>`).join('');
  const devs = `<button class="${state.dev === 'all' ? 'on' : ''}" data-dev="all">全部</button>` + browsable()
    .map(d => `<button class="${state.dev === d.id ? 'on' : ''}" data-dev="${d.id}">${drop(d.id)}${esc(devName(d.id))}</button>`).join('');
  const snap = thumbSnapshot();
  document.getElementById('cmdbar').innerHTML = `
    <div class="grp">${b('plus', '新建文件夹', r.node && r.node.writable ? 'data-do="newfolder"' : 'disabled')}</div>
    <div class="grp icononly">${b('cut', '剪切', on('cut'))}${b('copy', '复制', on('copy'))}${b('paste', '粘贴', state.clip && r.node ? 'data-do="paste"' : 'disabled')}${b('rename', '重命名', on('rename'))}${b('share', '共享', on('send'))}${b('trash', '删除', on('delete'))}</div>
    <div class="grp">${b('sort', '排序')}${b('group', '分组')}${b('filter', '筛选')}</div>
    <div class="grp">${b('eye', '快速查看', on('look'))}${b('send', '发送到另一台', on('send'))}</div>
    <div class="grow"></div>
    <div class="segctl" data-seg="dev"><i class="seg-thumb"></i>${devs}</div>
    <div class="segctl icons" data-seg="view"><i class="seg-thumb"></i>${views}</div>
    <button class="toggle ${state.preview ? 'on' : ''}" data-act="preview" title="详情面板">${ic('panel')}</button>`;
  placeThumbs(snap);
}
// 分段切换（设备、视图）的白色滑块：工具栏每次重绘都是新元素。重绘前先记下滑块此刻在屏幕上的位置
// （正在滑动时就是滑到一半的位置），新滑块先放在那里，下一帧再移到新选中的按钮上，由 CSS 过渡平滑滑过去
function thumbSnapshot() {
  const snap = {};
  document.querySelectorAll('#cmdbar .segctl').forEach(el => {
    const t = el.querySelector('.seg-thumb'); if (!t || t.style.opacity === '0') return;
    const a = el.getBoundingClientRect(), b = t.getBoundingClientRect();
    snap[el.dataset.seg] = { x: b.left - a.left - el.clientLeft, w: b.width };
  });
  return snap;
}
function placeThumbs(snap = {}) {
  document.querySelectorAll('#cmdbar .segctl').forEach(el => {
    const t = el.querySelector('.seg-thumb'), on = el.querySelector('button.on');
    if (!on) { t.style.opacity = '0'; return; }
    const put = (x, w) => { t.style.transform = `translateX(${x}px)`; t.style.width = w + 'px'; };
    const from = snap[el.dataset.seg], to = { x: on.offsetLeft, w: on.offsetWidth };
    t.classList.add('still');
    if (from && (Math.abs(from.x - to.x) > .5 || Math.abs(from.w - to.w) > .5)) {
      put(from.x, from.w);
      void t.offsetWidth;   // 让旧位置先生效
      t.classList.remove('still');
    }
    put(to.x, to.w);
    if (t.classList.contains('still')) { void t.offsetWidth; t.classList.remove('still'); }
  });
}

function renderSidebar() {
  const l = loc(), same = x => JSON.stringify(x) === JSON.stringify(l);
  const row = (go, icon, label, right = '', dropId = '') =>
    `<button class="srow ${same(go) ? 'on' : ''}" data-go='${JSON.stringify(go)}' ${dropId}>${icon}<span>${label}</span>${right}</button>`;
  const two = mg => `<span class="both">${mg.nodes.map(n => drop(n.dev)).join('')}</span>`;
  const one = d => `<span class="both">${drop(d)}</span>`;
  const drive = n => `<button class="srow drive ${same({ t: 'node', id: n.id }) ? 'on' : ''}" data-go='{"t":"node","id":${n.id}}' data-dropnode="${n.id}">${ic('drive')}<span>${esc(n.name)}</span></button>`;   // 容量只在主页的设备栏里显示，侧栏不重复
  const folder = n => `<button class="srow ${same({ t: 'node', id: n.id }) ? 'on' : ''}" data-go='{"t":"node","id":${n.id}}' data-dropnode="${n.id}">${fileIcon(n)}<span>${esc(n.name)}</span><small>共享目录</small></button>`;
  // 每台设备一个可展开的分组：点标题展开它的磁盘 / 共享目录，再点一下收起
  const devGroup = d => {
    const tip = `${esc(devName(d.id))}（${esc(d.host)}）· ${esc(devStatus(d).replace(/<[^>]+>/g, ''))}`;
    // 离线设备没有可看的东西：不能展开，只显示名字和状态
    if (!d.online) return `<div class="devhead offline" title="${tip}">${ic('chev', 'caret none')}${drop(d.id)}<span>${esc(devName(d.id))}</span><em>${devStatusShort(d)}</em></div>`;
    const open = state.open.has(d.id), rs = roots(d.id);
    const body = rs.map(n => n.drive ? drive(n) : folder(n)).join('')
      + (!rs.length ? `<div class="srow note">没有装互联服务，看不到它的文件</div>` : '');
    return `<button class="devhead ${open ? 'open' : ''}" data-toggledev="${d.id}" title="${tip}">
        ${ic('chev', 'caret')}${drop(d.id)}<span>${esc(devName(d.id))}</span><em>${devStatusShort(d)}</em></button>
      <div class="devbody ${open ? 'open' : ''}"><div>${body}</div></div>`;
  };
  const work = WORKSPACE && INFO[SELF().id] ? node(SELF().id, WORKSPACE) : null;
  const mergedRows = ['desktop', 'docs', 'dl', 'pics', 'video', 'music'].filter(k => MERGED[k].nodes.length)
    .map(k => row({ t: 'merged', k }, ic(MERGED[k].icon), MERGED[k].label, two(MERGED[k]), `data-dropmerged="${k}"`)).join('');
  document.getElementById('sidebar').innerHTML = `
    ${row({ t: 'home' }, ic('home'), '主页')}
    ${row({ t: 'merged', k: 'share' }, ic('swap'), '互传', two(MERGED.share), 'data-dropmerged="share"')}
    <h6>收藏</h6>
    ${mergedRows}
    ${work ? row({ t: 'node', id: work.id }, ic('folder'), '工作区', one(work.dev), `data-dropnode="${work.id}"`) : ''}
    <h6>设备<em class="num">${DEVS.filter(d => d.online).length}/${DEVS.length} 在线</em></h6>
    ${DEVS.map(devGroup).join('')}`;
}

const emptyHTML = (icon, title, sub = '') => `<div class="empty">${ic(icon)}<p>${title}</p>${sub ? `<small>${sub}</small>` : ''}</div>`;
function renderContent(r) {
  const el = document.getElementById('content');
  if (loc().t === 'home') { el.className = 'home'; el.innerHTML = homeHTML(); return; }
  const items = visibleItems(r);
  el.className = 'v-' + state.view;
  if (r.stub) { el.innerHTML = emptyHTML(r.icon, esc(r.title), '初版原型里这一项还没有接入'); return; }
  if (r.node && r.node.kind === 'dir') {
    if (r.node.loadError && !r.node.loadingDir) { el.innerHTML = emptyHTML('network', `读取失败：${esc(r.node.loadError)}`, `<button class="retry" data-retry="${r.node.id}">重试</button>`); return; }
    if (r.node.unloaded) {
      loadDir(r.node);
      el.innerHTML = `<div class="empty">${GOO('big busy')}<p>正在从 ${esc(devName(r.dev))} 读取…</p><small>${D(r.dev).self ? '经本机互联服务' : '经 Tailscale 长连接'}</small></div>`; return;
    }
  }
  if (r.merged) r.merged.nodes.filter(n => n.unloaded && !n.loadingDir && !n.loadError).forEach(n => loadDir(n));
  if (state.view === 'column') { el.innerHTML = columnHTML(r, items); return; }
  if (!items.length) { el.innerHTML = emptyHTML('folder', state.q ? '没有匹配的项目' : '这里是空的'); return; }
  if (state.view === 'list') el.innerHTML = tableHTML(items, r.flat || r.merged);
  else if (state.view === 'icon') el.innerHTML = `<div class="grid">${items.map(n => `<div class="tile ${rowCls(n)}" data-id="${n.id}">${fileIcon(n, 'big')}${nm(n)}<span class="sub">${drop(n.dev)}</span></div>`).join('')}</div>`;
  else el.innerHTML = galleryHTML(items);
}

function tableHTML(items, showWhere) {
  const th = (key, label, cls = '') => `<th class="${cls} ${state.sort.key === key ? 'sorted' : ''}" data-sort="${key}">${label}${state.sort.key === key ? (state.sort.dir > 0 ? ' ↑' : ' ↓') : ''}</th>`;
  return `<table class="tbl"><thead><tr>${th('name', '名称')}${th('dev', '设备', 'c-dev')}${th('date', '修改日期', 'c-date')}${th('type', '类型', 'c-type')}${th('size', '大小', 'c-size')}</tr></thead><tbody>
    ${items.map(n => `<tr class="${rowCls(n)}" data-id="${n.id}">
      <td><div class="namecell">${fileIcon(n)}${nm(n)}${agentMark(n)}${showWhere && n.parent ? `<span class="where">${esc(pathText(n.parent))}</span>` : ''}</div></td>
      <td class="c-dev">${devChip(n.dev)}</td><td class="c-date num">${n.date || '—'}</td><td class="c-type">${typeOf(n)}</td>
      <td class="c-size num">${n.drive ? big(n.drive.total) : sizeLabel(n)}</td></tr>`).join('')}
  </tbody></table>`;
}

function columnHTML(r, items) {
  const col = (list, activeId) => `<div class="col">${list.map(n => `<div class="crow ${n.id === activeId ? 'path' : ''} ${rowCls(n)}" data-id="${n.id}" data-single="1">${fileIcon(n)}${nm(n)}${n.kind === 'dir' ? ic('chev', 'sep') : ''}</div>`).join('') || '<div class="colempty">空</div>'}</div>`;
  let cols = [];
  if (r.node) {
    const chain = pathOf(r.node);
    const devs = `<div class="col devs">${browsable().map(d => `<div class="crow ${d.id === r.dev ? 'path' : ''}" data-go='{"t":"dev","k":"${d.id}"}'>${drop(d.id)}<span class="nm">${esc(devName(d.id))}</span>${ic('chev', 'sep')}</div>`).join('')}</div>`;
    cols = [devs, col(roots(r.dev), chain[0].id), ...chain.map((n, i) => col(i === chain.length - 1 ? items : kids(n), chain[i + 1] && chain[i + 1].id))];
  } else cols = [col(items)];
  return `<div class="cols">${cols.join('')}</div>`;
}

function galleryHTML(items) {
  const s = (state.sel && items.find(n => n.id === state.sel)) || items[0];
  return `<div class="stage">${fileIcon(s, 'giant')}<b>${esc(s.name)}</b><small>${devChip(s.dev)} ${typeOf(s)} · ${sizeLabel(s)}</small></div>
    <div class="strip">${items.map(n => `<div class="thumb ${n.id === s.id ? 'sel' : ''}" data-id="${n.id}" data-single="1">${fileIcon(n, 'big')}<span class="nm">${esc(n.name)}</span></div>`).join('')}</div>`;
}

function homeHTML() {
  // 设备栏：左边列出所有设备（来自 Tailscale），右边是选中设备的分区容量和共享目录，独立滚动
  const hd = DEVS.find(d => d.id === state.homeDev) || SELF();
  const dot = d => `<i class="dot ${d.self ? 'self' : !d.online ? 'off' : d.linked ? 'on' : 'idle'}"></i>`;
  const devRow = d => `<button class="dl-row ${d.id === hd.id ? 'on' : ''} ${d.online ? '' : 'offline'}" data-homedev="${d.id}" title="${esc(devName(d.id))}（${esc(d.host)}）">
      ${drop(d.id, 'lg')}<span class="dl-txt"><b>${esc(devName(d.id))}</b><small>${dot(d)}${devStatusShort(d)}</small></span></button>`;
  const rs = roots(hd.id), drives = rs.filter(n => n.drive), shares = rs.filter(n => !n.drive);
  const part = n => `<button class="part" data-go='{"t":"node","id":${n.id}}' data-dropnode="${n.id}">
      <span class="pt-top"><span class="pt-name">${esc(n.name)}</span><span class="pt-pct ${warnCls(n)}"><b class="num">${used(n)}%</b> 已用</span></span>
      <span class="pt-bar ${warnCls(n)}" style="--p:${used(n)}%"></span>
      <span class="pt-foot num">${big(n.drive.total - n.drive.free)} / ${big(n.drive.total)}<em>可用 ${big(n.drive.free)}${n.drive.fs ? ' · ' + esc(n.drive.fs) : ''}</em></span></button>`;
  const shareRow = n => `<button class="shr" data-go='{"t":"node","id":${n.id}}' data-dropnode="${n.id}">${ic('folder')}<span>${esc(pathText(n))}</span><em class="num">${n.unloaded ? '—' : kids(n).length + ' 项'}</em></button>`;
  const detail = `<div class="dd-head"><div><b>${esc(devName(hd.id))}</b><small>${esc(hd.host)}</small></div><span class="dd-st">${dot(hd)}${devStatus(hd)}</span></div>
    ${rs.length ? `${drives.length ? `<h5>分区 · <span class="num">${drives.length}</span></h5>${drives.map(part).join('')}` : ''}
      ${shares.length ? `<h5>共享目录 · <span class="num">${shares.length}</span></h5>${shares.map(shareRow).join('')}` : ''}`
      : `<p class="dd-note">${hd.online ? '这台设备在 Tailscale 里，但没有装互联服务，暂时看不到它的文件和容量' : '这台设备现在离线，连上后才能看到它的文件和容量'}</p>`}`;
  for (const d of DEVS) for (const n of roots(d.id)) if (n.shareRoot && n.unloaded && !n.loadingDir && !n.loadError) loadDir(n);   // 主页显示共享目录的项目数
  const rc = recent().filter(n => state.dev === 'all' || n.dev === state.dev);
  const rec = rc.slice(0, 4).map(n => `<div class="reccard ${rowCls(n)}" data-id="${n.id}"><span class="why">最近修改<em class="num">${n.date.slice(5)}</em></span>${fileIcon(n, 'big')}<span class="nm">${esc(n.name)}</span><span class="where">${drop(n.dev)}${esc(pathText(n.parent))}</span></div>`).join('');
  const lists = { recent: rc, shared: MERGED.share.nodes.flatMap(kids) };
  const items = lists[state.homeTab].filter(n => state.dev === 'all' || n.dev === state.dev);
  const pills = [['recent', 'clock', '最近使用'], ['shared', 'swap', '互传']]
    .map(([k, i, l]) => `<button class="pill ${state.homeTab === k ? 'on' : ''}" data-hometab="${k}">${ic(i)}${l}</button>`).join('');
  return `<div class="sec"><span>设备</span><i></i><em>来自 Tailscale 已授权的设备 · 新设备加入后会自动出现</em></div>
    <div class="devpanel"><div class="dl">${DEVS.map(devRow).join('')}</div><div class="dd">${detail}</div></div>
    <div class="sec"><span>最近</span><i></i></div><div class="recgrid">${rec}</div>
    <div class="sec"><span class="pills">${pills}</span><i></i><em class="num">${items.length} 项</em></div>
    ${items.length ? tableHTML(items, true) : emptyHTML('folder', '还没有项目')}`;
}

// 右侧详情面板：单击文件后显示属性。跨设备读取有延迟，所以先播放加载动画
let lastPv = null;
function renderPreview() {
  const el = document.getElementById('preview');
  const n = state.sel && byId(state.sel);
  if (!n) { lastPv = null; el.innerHTML = ''; return; }   // 没选中时面板收起，不占地方
  if (state.loading) {
    el.innerHTML = `<div class="pv-load">${GOO('big busy')}<p>正在从 ${esc(devName(n.dev))} 读取属性…</p><div class="sk"></div><div class="sk s2"></div><div class="sk s3"></div><div class="sk"></div><div class="sk s2"></div></div>`;
    return;
  }
  const fresh = n.id !== lastPv; lastPv = n.id;
  const kv = (k, v) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`;
  const sec = t => `<div class="sec small"><span>${t}</span><i></i></div>`;
  
  const general = n.drive
    ? kv('类型', '磁盘') + kv('总容量', big(n.drive.total)) + kv('可用空间', big(n.drive.free)) + kv('已用', used(n) + '%') + kv('文件系统', esc(n.drive.fs || '—'))
    : kv('类型', typeOf(n)) + kv('位置', esc(n.parent ? pathText(n.parent) : pathText(n))) + (n.kind === 'dir' ? kv('包含', sizeLabel(n)) : kv('大小', `<span class="num">${fmtSize(n.size)}</span>`) + (n.alloc != null ? kv('占用空间', `<span class="num">${fmtSize(n.alloc)}</span>`) : ''));
  const ro = n.drive ? !n.writable : !(n.parent && n.parent.writable);
  const ag = agentOf(n);
  const attrs = kv('可以修改', ro ? '否（只读区域）' : '是') + kv('隐藏', n.hidden ? '是' : '否')
    + (n.version ? kv('版本号', `<span class="num">${esc(n.version)}</span>`) : '')
    + (ag ? kv('最近智能体操作', `${esc(AGENT_NAME[ag.agent] || ag.agent)} · ${ago(new Date(ag.time * 1000).toISOString())}${ACTION_NAME[ag.action] || ''}`) : '');
  el.innerHTML = `<div class="pv ${fresh ? 'in' : ''}">
    <div class="pv-thumb">${RAWTOKEN && n.kind === 'file' && lookKind(n) === 'image' && n.size < 20 * 1024 * 1024
      ? `<img class="pv-img" src="/__raw?t=${RAWTOKEN}&dev=${encodeURIComponent(n.dev)}&path=${encodeURIComponent(n.path)}" alt="" onerror="this.replaceWith(document.createRange().createContextualFragment(this.dataset.fb))" data-fb="${esc(fileIcon(n, 'giant'))}">`
      : fileIcon(n, 'giant')}</div>
    <h3>${esc(n.name)}</h3>
    <p class="pv-sub">${devChip(n.dev)}<span>${typeOf(n)}</span><span class="num">${n.drive ? big(n.drive.total) : sizeLabel(n)}</span></p>
    ${sec('常规')}${general}
    ${n.drive ? '' : sec('时间') + kv('修改时间', `<span class="num">${n.date || '—'}</span>`)}
    ${sec('属性')}${attrs}
    ${sec('所在设备')}${kv('设备', `${esc(devName(n.dev))} · ${esc(D(n.dev).host)}`)}${kv('来源', D(n.dev).self ? '经本机互联服务实时读取' : '经 Tailscale 长连接实时读取')}${kv('完整路径', esc(pathText(n)))}
  </div>`;
}

function renderStatus(r) {
  const n = state.sel && byId(state.sel);
  const count = loc().t === 'home' ? recent().length : visibleItems(r).length;
  const path = n ? pathOf(n) : (r.node ? r.crumbs : []);
  const d = n ? n.dev : r.dev;
  document.getElementById('statusbar').innerHTML = `
    <span class="num">${count} 个项目${r.node && r.node.truncated ? `（共 ${r.node.truncated} 项，只显示前 ${count} 项）` : ''}${n ? ` · 已选 1 个 · ${sizeLabel(n)}` : ''}</span>
    <span class="pathbar">${d && path.length ? drop(d) + path.map(x => `<span>${esc(x.name)}</span>`).join(ic('chev', 'sep')) : ''}</span>
    <span class="link">${linkBadge()}</span><span class="right">${browsable().map(x => drop(x.id) + esc(devName(x.id))).join(ic('swap', 'sep'))}<em>实时</em></span>`;
}

// ───────────────────────────────────────── 提示条
let toastTimer;
// ───────────────────────────────────────── 快速查看（空格键 / 轮盘里的"快速查看"）
// 图片、PDF、音视频直接显示；文字文件只取开头 256 KB。内容经页面服务实时从文件所在的电脑读取。
let RAWTOKEN = null;
async function rawUrl(n, max) {
  if (!RAWTOKEN) RAWTOKEN = (await callJSON('/__token', {})).token;
  return `/__raw?t=${RAWTOKEN}&dev=${encodeURIComponent(n.dev)}&path=${encodeURIComponent(n.path)}${max ? '&max=' + max : ''}`;
}
const KIND_OF = { image: 'png jpg jpeg gif webp bmp svg ico', pdf: 'pdf', video: 'mp4 mov webm', audio: 'mp3 wav m4a flac ogg' };
const lookKind = n => Object.keys(KIND_OF).find(k => KIND_OF[k].split(' ').includes(ext(n))) || 'text';
const TEXT_MAX = 256 * 1024;
let qlFor = null;
function closeLook() { const el = document.getElementById('ql'); if (el) el.remove(); qlFor = null; }
async function quickLook(n) {
  if (n.kind === 'dir') return toast('文件夹不能快速查看，双击进去看');
  closeLook(); qlFor = n.id;
  const el = document.createElement('div'); el.id = 'ql';
  el.innerHTML = `<div class="ql-box"><div class="ql-head">${fileIcon(n)}<b>${esc(n.name)}</b>${devChip(n.dev)}<span class="num">${fmtSize(n.size)}</span><button data-qlclose="1" title="关闭（Esc）">✕</button></div>
    <div class="ql-body"><div class="pv-load">${GOO('big busy')}<p>正在从 ${esc(devName(n.dev))} 读取…</p></div></div></div>`;
  el.addEventListener('click', e => { if (e.target === el || e.target.dataset.qlclose) closeLook(); });
  document.body.appendChild(el);
  const body = el.querySelector('.ql-body'), kind = lookKind(n);
  try {
    if (kind === 'text') {
      if (n.size > 50 * 1024 * 1024 && !EXT_TEXT.has(ext(n))) throw new Error('这个文件太大，又不是文字，没法预览');
      const r = await fetch(await rawUrl(n, TEXT_MAX));
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `出错（${r.status}）`);
      const buf = new Uint8Array(await r.arrayBuffer());
      if (qlFor !== n.id) return;
      if (buf.slice(0, 8000).includes(0)) throw new Error(`${typeOf(n)} 不是文字文件，这里没法预览，可以双击用默认程序打开`);
      const txt = new TextDecoder('utf-8').decode(buf), more = n.size > TEXT_MAX;
      body.innerHTML = `<pre class="ql-text">${esc(txt)}</pre>${more ? `<p class="ql-note">只显示了开头 ${fmtSize(TEXT_MAX)}，全文 ${fmtSize(n.size)}</p>` : ''}`;
    } else {
      const u = await rawUrl(n);
      if (qlFor !== n.id) return;
      body.innerHTML = kind === 'image' ? `<img class="ql-media" src="${u}" alt="">`
        : kind === 'pdf' ? `<iframe class="ql-pdf" src="${u}"></iframe>`
        : kind === 'video' ? `<video class="ql-media" src="${u}" controls autoplay></video>`
        : `<audio src="${u}" controls autoplay></audio>`;
      const m = body.firstElementChild;
      m.onerror = () => { if (qlFor === n.id) body.innerHTML = `<p class="ql-note">读不出来：可能文件已被移动，或者格式不支持预览</p>`; };
    }
  } catch (e) { if (qlFor === n.id) body.innerHTML = `<p class="ql-note">${esc(e.message || e)}</p>`; }
}
const EXT_TEXT = new Set('txt md markdown json js mjs ts tsx jsx css html htm xml yml yaml toml ini cfg conf log csv tsv py rb go rs java c h cpp hpp cs sh bash zsh ps1 bat cmd sql m tex srt'.split(' '));

function toast(msg, undo) {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
  el.innerHTML = `<span>${msg}</span>${undo ? '<button data-undo="1">撤销</button>' : ''}`;
  el.onclick = e => { if (e.target.dataset.undo) { undo(); el.classList.remove('on'); render(); } };
  el.classList.add('on'); clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('on'), undo ? 5000 : 2400);
}

// ───────────────────────────────────────── 打开（双击 / 回车 / 轮盘里的"打开"）
// 文件夹：进入。Windows 上的文件：交给本地页面服务，用默认程序打开，和资源管理器双击一样。
function launchFx(n) {
  document.querySelectorAll(`[data-id="${n.id}"]`).forEach(el => { el.classList.remove('launch'); void el.offsetWidth; el.classList.add('launch'); });
}
async function openItem(n) {
  if (n.kind === 'dir') return go({ t: 'node', id: n.id });
  launchFx(n);
  if (!window.unified) return toast('只有在桌面 App 里才能打开文件');
  const peer = !D(n.dev).self;
  toast(peer ? `正在从 ${esc(devName(n.dev))} 取 ${esc(n.name)}…` : `正在打开 ${esc(n.name)}…`);
  try {
    let p = pathText(n);
    // 对方电脑上的文件：先取一份到本机临时目录再打开（只读副本，改了不会自动传回去）
    if (peer) p = (await callJSON('/__fetch', { dev: n.dev, path: n.path })).local;
    const r = await window.unified.openPath(p);
    if (peer && r.ok) return toast(`已打开 ${esc(n.name)}（从 ${esc(devName(n.dev))} 取来的副本，保存后会自动传回去）`);
    toast(r.ok ? `已用默认程序打开 ${esc(n.name)}` : `打不开：${esc(r.error)}`);
  } catch (e) { toast('打不开文件：' + esc(e.message || e)); }
}

// ───────────────────────────────────────── 选中与文件操作
// 单击：选中，并向文件所在的设备查一次最新属性（跨设备有延迟，先播放加载动画）
let loadTimer;
async function select(id) {
  if (state.sel === id && !state.loading) return;
  state.sel = id; state.loading = true; render();
  const n = byId(id), t0 = Date.now(), mine = (loadTimer = {});
  try {
    if (!n.drive) {
      const s = await callFile(n.dev, 'stat', { path: n.path });
      if (s.exists) Object.assign(n, { size: s.type === 'dir' ? undefined : s.size, alloc: s.alloc, date: s.mtime ? fmtTime(s.mtime) : n.date, version: s.version, hidden: !!s.hidden });
    }
  } catch {}
  await new Promise(r => setTimeout(r, Math.max(0, 280 - (Date.now() - t0))));   // 太快时也让加载动画播完一小段
  if (loadTimer !== mine || state.sel !== id) return;
  state.loading = false; renderPreview();
}
// "发送到另一台"：本机的文件发到对方的共享目录，对方的文件发回本机的共享目录
const otherDev = n => otherOf(n.dev);
const shareNode = dev => roots(dev).find(x => x.shareRoot);
const canChange = n => !!(n.parent && n.parent.writable && !n.drive && !n.shareRoot);   // 只读区域、磁盘本身、共享目录本身都不能改名删除移动
let opBusy = false;
async function run(label, fn, refresh = []) {
  if (opBusy) return toast('上一个操作还没完成');
  opBusy = true; toast(label + '…');
  try { const msg = await fn(); toast(msg); }
  catch (e) { toast(`${label}失败：${esc(e.message || e)}`); }
  finally { opBusy = false; reload(...refresh); }
}
// 把 n 放进文件夹 dst：同一台设备上是移动或复制；跨设备是传一份（cut/move 时传完后把源文件移进回收站）
function place(n, dst, move) {
  if (n.dev === dst.dev && (dst === n || pathOf(dst).includes(n))) return toast('不能把文件夹放进它自己或它的子文件夹');
  if (n.dev === dst.dev && dst === n.parent && move) return;
  if (!dst.writable) return toast(`${esc(dst.name)} 是只读区域，不能放东西进去`);
  if (move && !canChange(n)) return toast(`${esc(n.name)} 在只读区域，只能复制，不能移走`);
  const to = joinPath(dst.path, n.name);
  if (n.dev === dst.dev) {
    return run(move ? `正在移动 ${esc(n.name)}` : `正在复制 ${esc(n.name)}`,
      async () => { await callFile(n.dev, move ? 'move' : 'copy', { src: n.path, dst: to }); if (move) moveTags(n.dev, n.path, to); return `已${move ? '移动' : '复制'}到 ${esc(dst.name)}`; },
      [n.parent, dst]);
  }
  return run(`正在把 ${esc(n.name)} 传到 ${esc(devName(dst.dev))}`, async () => {
    const r = await callJSON('/__transfer', { from: { dev: n.dev, path: n.path }, to: { dev: dst.dev, path: to }, move });
    const what = n.kind === 'dir' ? `（${r.files} 个文件，${fmtSize(r.bytes)}${r.skipped ? `，跳过 ${r.skipped} 个快捷方式` : ''}）` : `（${fmtSize(r.bytes)}）`;
    return `已${move ? '移动' : '发送'}到 ${esc(devName(dst.dev))} 的 ${esc(dst.name)}${what}${move ? '，原' + (n.kind === 'dir' ? '文件夹' : '文件') + '已移到' + esc(r.trashed_to) : ''}`;
  }, [n.parent, dst]);
}
function act(k, n) {
  if (!n) return;
  if (k === 'open') return openItem(n);
  if (k === 'look') return quickLook(n);
  if (k === 'copy' || k === 'cut') {
    if (k === 'cut' && !canChange(n)) return toast(`${esc(n.name)} 在只读区域，不能剪切`);
    state.clip = { id: n.id, mode: k }; render(); return toast(`${k === 'cut' ? '已剪切' : '已复制'} ${esc(n.name)}，到目标文件夹后点粘贴`);
  }
  if (k === 'paste') {
    const src = byId(state.clip.id), dst = loc().t === 'node' && byId(loc().id);
    if (!src || !dst || dst.kind !== 'dir') return toast('这里不能粘贴，请先进入一个文件夹');
    const move = state.clip.mode === 'cut'; state.clip = null; render();
    return place(src, dst, move);
  }
  if (k === 'rename') { if (!canChange(n)) return toast(`${esc(n.name)} 在只读区域，不能改名`); state.renaming = n.id; return render(); }
  if (k === 'props') { state.preview = true; state.sel = null; return select(n.id); }
  if (k === 'send') {
    const to = otherDev(n), share = to && shareNode(to);
    if (!share) return toast('没有已连上的设备可以发送');
    return place(n, share, false);
  }
  if (k === 'delete') {
    if (!canChange(n)) return toast(`${esc(n.name)} 在只读区域，不能删除`);
    if (state.sel === n.id) state.sel = null;
    return run(`正在删除 ${esc(n.name)}`, async () => {
      const r = await callFile(n.dev, 'delete', { path: n.path });
      return `已把 ${esc(n.name)} 移到${esc(/^\.trash\//.test(r.trashed_to) ? '共享目录的回收区' : r.trashed_to)}，可以从那里恢复`;
    }, [n.parent]);
  }
}
// 新建文件夹：在当前文件夹里建"新建文件夹"，建好后直接进入改名
async function newFolder() {
  const dir = loc().t === 'node' && byId(loc().id);
  if (!dir || dir.kind !== 'dir') return toast('请先进入一个文件夹');
  if (!dir.writable) return toast(`${esc(dir.name)} 是只读区域，不能新建`);
  const base = D(dir.dev).os === 'macos' ? '未命名文件夹' : '新建文件夹';
  const names = new Set((dir.children || []).filter(c => !c.gone).map(c => c.name.toLowerCase()));
  let name = base; for (let i = 2; names.has(name.toLowerCase()); i++) name = `${base} (${i})`;
  try {
    await callFile(dir.dev, 'mkdir', { path: joinPath(dir.path, name) });
    await loadDir(dir, true);
    const c = node(dir.dev, joinPath(dir.path, name));
    state.sel = c.id; state.renaming = c.id; render();
  } catch (e) { toast('新建失败：' + esc(e.message || e)); }
}

// ───────────────────────────────────────── 右键轮盘
// 以鼠标位置为圆心展开。整个圆盘都是激活区：鼠标在圆内移动不会消失，移出圆外才收起；左键点某一项才执行。
const WHEEL = [['open', '打开', 'open'], ['look', '快速查看', 'eye'], ['copy', '复制', 'copy'], ['cut', '剪切', 'cut'], ['rename', '重命名', 'rename'], ['send', '发送', 'send'], ['props', '属性', 'info'], ['delete', '删除', 'trash']];
const R = 124, R0 = 42;
let wheel = null;
function openWheel(x, y, n) {
  closeWheel();
  const cx = Math.max(R + 6, Math.min(innerWidth - R - 6, x)), cy = Math.max(R + 6, Math.min(innerHeight - R - 6, y));
  const N = WHEEL.length, step = 360 / N, gap = 1.6;
  const pt = (r, a) => [R + r * Math.cos(a * Math.PI / 180), R + r * Math.sin(a * Math.PI / 180)];
  const fixed = !canChange(n);   // 磁盘、共享目录本身和只读区域里的东西不能改名、删除、剪切
  let paths = '', labels = '';
  WHEEL.forEach(([k, label, icon], i) => {
    const a0 = -90 - step / 2 + i * step + gap, a1 = a0 + step - gap * 2, mid = (a0 + a1) / 2;
    const [x0, y0] = pt(R - 2, a0), [x1, y1] = pt(R - 2, a1), [x2, y2] = pt(R0, a1), [x3, y3] = pt(R0, a0), [lx, ly] = pt((R + R0) / 2, mid);
    const off = (fixed && ['cut', 'rename', 'delete'].includes(k)) || (k === 'send' && (!otherDev(n) || n.kind === 'dir' || !n.parent));
    const to = otherDev(n), text = k === 'send' ? (to ? `发到 ${devName(to)}` : '发送') : label;
    paths += `<path class="${off ? 'off' : ''} ${k === 'delete' ? 'danger' : ''}" data-wheel="${k}" data-label="${esc(text)}" style="--i:${i}" d="M${x0} ${y0}A${R - 2} ${R - 2} 0 0 1 ${x1} ${y1}L${x2} ${y2}A${R0} ${R0} 0 0 0 ${x3} ${y3}Z"/>`;
    labels += `<div class="wl ${off ? 'off' : ''}" data-for="${k}" style="left:${Math.round(lx - 38)}px;top:${Math.round(ly - 22)}px;--i:${i}">${ic(icon)}<span>${esc(text)}</span></div>`;
  });
  const el = document.createElement('div');
  el.id = 'wheel'; el.style.left = Math.round(cx - R) + "px"; el.style.top = Math.round(cy - R) + "px"; el.style.width = el.style.height = R * 2 + 'px';
  el.innerHTML = `<svg viewBox="0 0 ${R * 2} ${R * 2}">${paths}</svg>${labels}<div class="hub">${fileIcon(n, 'mid')}<span>${esc(n.name)}</span></div>`;
  document.body.appendChild(el);
  wheel = { el, cx, cy, n, inside: Math.hypot(x - cx, y - cy) <= R };
  requestAnimationFrame(() => el.classList.add('on'));
}
function closeWheel() { if (!wheel) return; const el = wheel.el; wheel = null; el.classList.remove('on'); el.classList.add('out'); setTimeout(() => el.remove(), 180); }

document.addEventListener('contextmenu', e => {
  const t = e.target.closest('[data-id]');
  e.preventDefault();   // 任何地方都不弹浏览器自带的右键菜单
  if (drag || press) { cancelDrag(); return; }
  if (!t && !e.target.closest('#wheel')) { closeWheel(); return; }
  if (!t) return;
  const n = byId(t.dataset.id);
  if (state.sel !== n.id) select(n.id);
  openWheel(e.clientX, e.clientY, n);
});
document.addEventListener('mousemove', e => {
  if (wheel) {
    const d = Math.hypot(e.clientX - wheel.cx, e.clientY - wheel.cy);
    if (d <= R) wheel.inside = true; else if (wheel.inside && d > R + 4) return closeWheel();
    const p = e.target.closest('[data-wheel]');
    wheel.el.querySelectorAll('.wl').forEach(l => l.classList.toggle('hot', !!p && l.dataset.for === p.dataset.wheel));
  }
  dragMove(e);
});

// ───────────────────────────────────────── 长按拖动
// 左键按住约 0.3 秒进入拖动；拖到文件夹、侧栏的位置或磁盘上松开即移动，跨设备则是发送一份副本
let press = null, drag = null, suppressClick = false;
document.addEventListener('mousedown', e => {
  if (e.button !== 0 || e.target.closest('#wheel') || e.target.closest('input')) return;
  const t = e.target.closest('[data-id]'); if (!t) return;
  const n = byId(t.dataset.id); if (!n.parent) return;
  press = { n, x: e.clientX, y: e.clientY, timer: setTimeout(() => startDrag(n, press.x, press.y), 300) };
});
function startDrag(n, x, y) {
  const g = document.createElement('div'); g.id = 'ghost'; g.innerHTML = `${fileIcon(n)}<span>${esc(n.name)}</span><em></em>`;
  document.body.appendChild(g); document.body.classList.add('dragging');
  drag = { n, g, target: null }; press = null; placeGhost(x, y);
}
const placeGhost = (x, y) => { drag.g.style.transform = `translate(${x + 14}px, ${y + 12}px)`; };
function dropTarget(el) {
  const t = el && el.closest('[data-dropnode],[data-dropmerged],[data-id]'); if (!t) return null;
  let node = t.dataset.dropnode ? byId(t.dataset.dropnode) : t.dataset.dropmerged ? null : byId(t.dataset.id);
  if (t.dataset.dropmerged) { const mg = MERGED[t.dataset.dropmerged]; node = mg.nodes.find(x => x.dev === drag.n.dev) || mg.nodes[0]; }
  if (!node || node.kind !== 'dir' || !node.writable || node === drag.n || node === drag.n.parent || pathOf(node).includes(drag.n)) return null;
  if (node.dev === drag.n.dev && !canChange(drag.n)) return null;   // 只读区域里的东西不能移走（跨设备发送副本可以）
  return { el: t, node };
}
function dragMove(e) {
  if (press && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 6) { clearTimeout(press.timer); press = null; }   // 还没到长按时间就移动：不算拖动
  if (!drag) return;
  placeGhost(e.clientX, e.clientY);
  drag.g.style.display = 'none'; const tg = dropTarget(document.elementFromPoint(e.clientX, e.clientY)); drag.g.style.display = '';
  document.querySelectorAll('.droptarget').forEach(x => x.classList.remove('droptarget'));
  drag.target = tg;
  if (tg) tg.el.classList.add('droptarget');
  drag.g.querySelector('em').textContent = tg ? (tg.node.dev === drag.n.dev ? `移动到 ${tg.node.name}` : `发送到 ${devName(tg.node.dev)} · ${tg.node.name}`) : '';
}
function cancelDrag() {
  if (press) { clearTimeout(press.timer); press = null; }
  if (!drag) return;
  drag.g.remove(); drag = null; document.body.classList.remove('dragging');
  document.querySelectorAll('.droptarget').forEach(x => x.classList.remove('droptarget'));
}
window.addEventListener('blur', cancelDrag);
document.addEventListener('mouseup', e => {
  if (e.button !== 0) return;
  if (press) { clearTimeout(press.timer); press = null; }
  if (!drag) return;
  const { n, g, target } = drag; drag = null; g.remove(); document.body.classList.remove('dragging'); suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
  if (target) {   // 同一台设备上是移动；跨设备是发送一份副本
    state.sel = null; render();
    place(n, target.node, target.node.dev === n.dev);
  } else if (pendingRender) render();
});

// ───────────────────────────────────────── 点击
document.addEventListener('click', e => {
  if (suppressClick) return;
  const wp = e.target.closest('[data-wheel]');
  if (wp) { const n = wheel.n; closeWheel(); if (!wp.classList.contains('off')) act(wp.dataset.wheel, n); return; }
  if (wheel) { if (!e.target.closest('#wheel')) closeWheel(); return; }
  if (e.target.closest('input.rename')) return;
  const t = e.target.closest('[data-toggledev],[data-retry],[data-go],[data-act],[data-do],[data-view],[data-dev],[data-sort],[data-hometab],[data-homedev],[data-id]');
  if (!t) { if (e.target.closest('#content') && state.sel) { state.sel = null; render(); } return; }
  const d = t.dataset;
  if (d.toggledev) { state.open.has(d.toggledev) ? state.open.delete(d.toggledev) : state.open.add(d.toggledev); saveOpen(); return renderSidebar(); }
  if (d.retry) { const n = byId(d.retry); n.loadError = null; n.unloaded = true; return render(); }
  if (d.do === 'newfolder') return newFolder();
  if (d.do === 'paste') return act('paste', true);
  if (d.do) return act(d.do, byId(state.sel));
  if (d.go) return go(JSON.parse(d.go));
  if (d.view) { state.view = d.view; return render(); }
  if (d.dev) { state.dev = d.dev; return render(); }
  if (d.hometab) { state.homeTab = d.hometab; return render(); }
  if (d.homedev) { state.homeDev = d.homedev; return renderContent(resolve(loc())); }
  if (d.sort) { state.sort = { key: d.sort, dir: state.sort.key === d.sort ? -state.sort.dir : 1 }; return render(); }
  if (d.act) {
    const tb = tab();
    if (d.act === 'back' && tb.i) tb.i--;
    else if (d.act === 'fwd' && tb.i < tb.hist.length - 1) tb.i++;
    else if (d.act === 'up') { const n = byId(loc().id); return go(n.parent ? { t: 'node', id: n.parent.id } : { t: 'dev', k: n.dev }); }
    else if (d.act === 'preview') state.preview = !state.preview;
    else if (d.act === 'refresh') {
      shownDirs().forEach(n => { n.loadError = null; loadDir(n); });
      refreshDevices().then(render);
    }
    if (d.act !== 'preview') state.sel = null;
    return render();
  }
  if (d.id) {
    // 双击打开：单击会重绘列表，第二下点到的已经是新元素，浏览器自带的 dblclick 不可靠，
    // 所以自己判断——同一项在 500 毫秒内被点两次就算双击（和 Windows 默认双击间隔一致）
    const n = byId(d.id), now = performance.now();
    if (lastClick.id === n.id && now - lastClick.t < 500) { lastClick = { id: null, t: 0 }; return openItem(n); }
    lastClick = { id: n.id, t: now };
    if (d.single && n.kind === 'dir' && state.view === 'column') return go({ t: 'node', id: n.id });   // 分栏里单击文件夹直接进入
    select(n.id);   // 单击：选中，并在右侧显示属性
  }
});
let lastClick = { id: null, t: 0 };
function commitRename(inp) {
  const n = byId(inp.dataset.rename), v = inp.value.trim();
  state.renaming = null;
  if (v && v !== n.name) {
    if (/[\\/]/.test(v) || (D(n.dev).os === 'windows' && /[:*?"<>|]/.test(v))) { render(); return toast('名字里不能有 \\ / : * ? " < > | 这些字符'); }
    const dst = joinPath(n.parent.path, v);
    run(`正在重命名 ${esc(n.name)}`, async () => {
      await callFile(n.dev, 'move', { src: n.path, dst });
      moveTags(n.dev, n.path, dst);
      const c = node(n.dev, dst, { kind: n.kind }); state.sel = c.id;
      return `已重命名为 ${esc(v)}`;
    }, [n.parent]);
  }
  render();
}
document.addEventListener('focusout', e => { if (e.target.matches && e.target.matches('input.rename') && state.renaming) commitRename(e.target); });
document.addEventListener('input', e => {
  if (e.target.id !== 'q') return;
  state.q = e.target.value; const r = resolve(loc());
  renderContent(r); renderStatus(r);
});
document.addEventListener('keydown', e => {
  if (e.target.matches('input.rename')) { if (e.key === 'Enter') commitRename(e.target); if (e.key === 'Escape') { state.renaming = null; render(); } return; }
  if (e.target.tagName === 'INPUT') return;
  if (qlFor && (e.key === 'Escape' || e.key === ' ')) { e.preventDefault(); return closeLook(); }
  if (e.key === 'Escape') { if (wheel) return closeWheel(); state.sel = null; render(); }
  const n = state.sel && byId(state.sel);
  if (n && e.key === ' ') { e.preventDefault(); return act('look', n); }
  if (n && e.key === 'F2') act('rename', n);
  if (n && e.key === 'Delete') act('delete', n);
  if (n && e.key === 'Enter') act('open', n);
  if (e.altKey && e.key === 'ArrowLeft') document.querySelector('[data-act=back]').click();
  if (e.altKey && e.key === 'ArrowRight') document.querySelector('[data-act=fwd]').click();
});

// ───────────────────────────────────────── 启动
// 先从 Tailscale 读设备，再渲染；之后每 15 秒刷新一次，新设备、上下线会自动反映到左侧
(async function boot() {
  if (navigator.userAgent.includes('Electron')) document.body.classList.add('app');
  if (/Mac/.test(navigator.platform)) document.body.classList.add('mac');
  await refreshDevices();
  render();
  if (document.fonts) document.fonts.ready.then(() => placeThumbs(thumbSnapshot()));   // 字体加载完按钮宽度会变，滑块重新对齐
  // 先读各台设备的常用文件夹，主页的"最近"才有内容
  for (const k of ['desktop', 'docs', 'dl', 'share']) (MERGED[k] ? MERGED[k].nodes : []).forEach(n => loadDir(n, true));
  refreshActivity().then(softRender);
  callJSON('/__token', {}).then(j => { RAWTOKEN = j.token; }).catch(() => {});   // 快速查看和图片缩略图用
  // 打开过的对方文件副本，保存后由页面服务传回去；这里把结果提示出来
  let syncSeen = null;
  setInterval(async () => {
    try {
      const j = await callJSON('/__sync?since=' + (syncSeen ?? 1e12));
      if (syncSeen !== null) for (const it of j.items) {
        toast(`${esc(baseName(it.path))}：${esc(it.msg)}`);
        const p = NODES.get(nkey(it.dev, parentPath(it.path) || it.path)); if (p) loadDir(p, true);
      }
      syncSeen = j.seq;
    } catch {}
  }, 3000);
  eventLoop();                                                 // 对方推来的变化
  setInterval(pollSelf, 3000);                                  // 本机正在看的文件夹每 3 秒重读
  setInterval(() => syncWatch(), 5000);                         // 对方的文件夹：按正在看的位置订阅
  setInterval(() => refreshActivity().then(softRender), 10000); // 智能体做过的操作
  setInterval(async () => {
    const changed = await refreshDevices();
    if (!changed || busy()) { renderStatus(resolve(loc())); return; }
    renderStatus(resolve(loc())); renderSidebar(); renderCmd(resolve(loc()));
    if (loc().t === 'home') renderContent(resolve(loc()));
  }, 15000);
})();
