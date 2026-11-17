// 只给页面开一个口子：请主进程用默认程序打开本机文件。页面拿不到 Node 和 Electron 的其他能力。
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('unified', {
  openPath: (p) => ipcRenderer.invoke('open-path', String(p)),
});
