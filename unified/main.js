// 统一文件页 · 桌面 App（Electron）
// 窗口没有系统标题栏和菜单栏，也没有浏览器的右键菜单；右上角只留系统自带的最小化 / 最大化 / 关闭按钮。
// 页面服务（server.js）在 App 内部启动；如果已经有一份在跑（比如开着副屏画布），就直接用它。
const { app, BrowserWindow, Menu, screen, shell, ipcMain } = require('electron');
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 5511;
const URL = `http://127.0.0.1:${PORT}/`;
const BAR_HEIGHT = 46;   // 和页面顶部工具栏同高，系统窗口按钮叠在工具栏上
const IS_MAC = process.platform === 'darwin';

// 自检模式（UNIFIED_SELFTEST=结果文件路径）：用独立的配置目录启动，从页面里调用打开文件的通道，把结果写进文件后退出
const SELFTEST = process.env.UNIFIED_SELFTEST;
// 截图模式（UNIFIED_SNAPSHOT=png 路径）：另开一个窗口，页面加载 6 秒后把页面内容存成图片再退出（App 自己截自己，不需要系统的屏幕录制权限）
const SNAPSHOT = process.env.UNIFIED_SNAPSHOT;
if (SELFTEST || SNAPSHOT) app.setPath('userData', path.join(app.getPath('temp'), SNAPSHOT ? 'unified-snapshot' : 'unified-selftest'));
if (process.platform === 'win32') app.setAppUserModelId('MacWin.UnifiedFiles');
if (!app.requestSingleInstanceLock()) app.quit();   // 只开一个窗口；再次双击快捷方式时把已有窗口调到前面

const alive = () => new Promise((resolve) => {
  const req = http.get(URL, { timeout: 800 }, (res) => { res.resume(); resolve(res.statusCode === 200); });
  req.on('error', () => resolve(false)); req.on('timeout', () => { req.destroy(); resolve(false); });
});

// 页面服务和主进程的代码改了，App 自己重启一次（页面文件改了不用，页面会自己刷新）
function restartOnChange() {
  let t = null;
  for (const f of ['server.js', 'main.js', 'preload.js']) {
    try {
      fs.watch(path.join(__dirname, f), () => {
        clearTimeout(t);
        t = setTimeout(() => { app.relaunch(); app.exit(0); }, 1500);   // 等文件写完
      });
    } catch {}
  }
}

let win = null;
async function createWindow() {
  if (!(await alive())) { require('./server.js'); if (!SELFTEST) restartOnChange(); }
  for (let i = 0; i < 20 && !(await alive()); i++) await new Promise((r) => setTimeout(r, 150));

  // 有副屏就开在副屏上，没有就开在主屏
  const displays = screen.getAllDisplays();
  const target = displays.find((d) => d.id !== screen.getPrimaryDisplay().id) || screen.getPrimaryDisplay();
  const { x, y, width, height } = target.workArea;

  win = new BrowserWindow({
    x: x + 40, y: y + 40, width: Math.min(1360, width - 80), height: Math.min(860, height - 80),
    minWidth: 900, minHeight: 560,
    title: '统一文件页', backgroundColor: '#000000', show: false,
    icon: path.join(__dirname, IS_MAC ? 'icon.png' : 'icon.ico'),   // Windows 任务栏 / 窗口图标
    titleBarStyle: 'hidden',
    // Windows：右上角叠系统的最小化/最大化/关闭；Mac：左上角的红黄绿按钮放在工具栏里居中
    ...(IS_MAC ? { trafficLightPosition: { x: 16, y: Math.round((BAR_HEIGHT - 14) / 2) } }
      : { titleBarOverlay: { color: '#000000', symbolColor: '#ffffff', height: BAR_HEIGHT } }),
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false, preload: path.join(__dirname, 'preload.js') },
  });
  // Windows 任务栏按 程序身份 分组、取图标：不设的话显示 electron.exe 的原子图标
  if (!IS_MAC) win.setAppDetails({ appId: 'MacWin.UnifiedFiles', appIconPath: path.join(__dirname, 'icon.ico'), appIconIndex: 0,
    relaunchCommand: `"${process.execPath}" "${__dirname}"`, relaunchDisplayName: '统一文件页' });
  win.once('ready-to-show', () => { win.maximize(); win.show(); });

  // 页面里的链接一律不在 App 里开新窗口；外部网址交给系统浏览器
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url) && !url.startsWith(URL)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => { if (!url.startsWith(URL)) e.preventDefault(); });
  win.loadURL(URL);
  win.on('closed', () => { win = null; });

  if (SNAPSHOT) win.webContents.once('did-finish-load', async () => {
    await new Promise((r) => setTimeout(r, 6000));
    fs.writeFileSync(SNAPSHOT, (await win.webContents.capturePage()).toPNG());
    app.quit();
  });
  if (SELFTEST) win.webContents.once('did-finish-load', async () => {
    const cases = JSON.parse(process.env.UNIFIED_SELFTEST_CASES || '[]');
    const results = {};
    for (const p of cases) results[p] = await win.webContents.executeJavaScript(`window.unified.openPath(${JSON.stringify(p)})`);
    fs.writeFileSync(SELFTEST, JSON.stringify(results, null, 2));
    app.quit();
  });
}

// ── 双击打开本机文件（和资源管理器双击一样，用默认程序打开）
// 只接受本 App 窗口里、来自本页面的请求；只接受普通的本机绝对路径；按真实路径（解开联接点/符号链接）排除隐私区域。
const os = require('os');
const NEVER = IS_MAC ? [path.join(os.homedir(), '.ssh'), path.join(os.homedir(), 'Library', 'Keychains')] : ['E:\\隐私数据'];
const inside = (child, parent) => { const r = path.relative(parent.toLowerCase(), child.toLowerCase()); return r === '' || (!r.startsWith('..') && !path.isAbsolute(r)); };
ipcMain.handle('open-path', async (e, p) => {
  if (!win || e.sender !== win.webContents || !e.senderFrame || !e.senderFrame.url.startsWith(URL)) return { ok: false, error: '请求来源不对' };
  if (typeof p !== 'string' || !(IS_MAC ? p.startsWith('/') : /^[A-Za-z]:\\/.test(p)) || p.includes('\0')) return { ok: false, error: '只能打开本机磁盘上的普通路径' };
  const resolved = path.resolve(p);
  if (NEVER.some((n) => inside(resolved, n))) return { ok: false, error: '隐私数据不通过这个页面打开' };   // 先按路径文字拒绝，连磁盘都不碰
  let real;
  try { real = fs.realpathSync.native(resolved); } catch { return { ok: false, error: '这台电脑上找不到这个文件（可能已被移动或改名）' }; }
  for (const n of NEVER) {
    let nr = n; try { nr = fs.realpathSync.native(n); } catch {}
    if (inside(real, n) || inside(real, nr)) return { ok: false, error: '隐私数据不通过这个页面打开' };
  }
  const err = await shell.openPath(real);
  return err ? { ok: false, error: err } : { ok: true };
});

Menu.setApplicationMenu(null);   // 不要菜单栏，也就没有刷新、开发者工具这些浏览器快捷键
app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
app.whenReady().then(() => {
  // Mac 的程序坞图标（不设就是 Electron 默认的）
  if (IS_MAC && app.dock) try { app.dock.setIcon(path.join(__dirname, 'icon.png')); } catch {}
  return createWindow();
});
app.on('window-all-closed', () => app.quit());
