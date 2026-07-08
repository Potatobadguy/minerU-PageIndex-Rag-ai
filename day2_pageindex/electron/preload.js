const { contextBridge, shell } = require("electron");

console.log("[preload] PageIndex RAG Agent preload loaded");

contextBridge.exposeInMainWorld("electronAPI", {
  /** 标记 preload 已加载（确保渲染进程能检测到 Electron 环境） */
  loaded: true,

  /** 用系统默认程序打开本地文件。返回空字符串 = 成功，否则返回错误描述 */
  openFile: async (filepath) => {
    console.log("[preload] openFile:", filepath);
    const err = await shell.openPath(filepath);
    if (err) console.error("[preload] openFile error:", err);
    else console.log("[preload] openFile success");
    return err || "";
  },
});
