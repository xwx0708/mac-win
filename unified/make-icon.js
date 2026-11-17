// 从 icon.svg 生成 icon.png（1024）和 icon.ico（Windows 用，内含 16–256 各尺寸）。
// 用法：在 unified 里运行  node_modules\electron\dist\electron.exe make-icon.js
// 用 Electron 自己的 Chromium 渲染 SVG，不需要别的工具。
const { app, BrowserWindow, nativeImage } = require('electron');
const fs = require('fs');
const path = require('path');

app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const svg = fs.readFileSync(path.join(__dirname, 'icon.svg'), 'utf8');
  const win = new BrowserWindow({ width: 1024, height: 1024, show: false, frame: false, transparent: true, useContentSize: true,
    backgroundColor: '#00000000', webPreferences: { offscreen: true, javascript: false } });
  await win.loadURL('data:text/html,' + encodeURIComponent(
    `<html style="background:transparent;overflow:hidden"><body style="margin:0;background:transparent;overflow:hidden">` +
    svg.replace('<svg ', '<svg style="display:block" ') + `</body></html>`));
  await new Promise((r) => setTimeout(r, 500));
  const img = await win.webContents.capturePage({ x: 0, y: 0, width: 1024, height: 1024 });
  const png = img.resize({ width: 1024, height: 1024, quality: 'best' });
  fs.writeFileSync(path.join(__dirname, 'icon.png'), png.toPNG());

  // ICO：每个尺寸存一张 PNG（Windows Vista 以后都认）
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const pngs = sizes.map((s) => png.resize({ width: s, height: s, quality: 'best' }).toPNG());
  const head = Buffer.alloc(6 + 16 * sizes.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(sizes.length, 4);
  let offset = head.length;
  sizes.forEach((s, i) => {
    const o = 6 + 16 * i;
    head.writeUInt8(s >= 256 ? 0 : s, o); head.writeUInt8(s >= 256 ? 0 : s, o + 1);
    head.writeUInt16LE(1, o + 4); head.writeUInt16LE(32, o + 6);
    head.writeUInt32LE(pngs[i].length, o + 8); head.writeUInt32LE(offset, o + 12);
    offset += pngs[i].length;
  });
  fs.writeFileSync(path.join(__dirname, 'icon.ico'), Buffer.concat([head, ...pngs]));
  console.log('icon.png / icon.ico 已生成');
  app.quit();
});
