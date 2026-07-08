/**
 * Electron 主进程
 * - 启动 Python 后端子进程
 * - 加载前端 dev server 或 build 产物（dist/index.html）
 * - 应用退出时清理后端进程
 *
 * 运行模式：
 *   1. 开发模式（默认未打包）：加载 http://127.0.0.1:5173，需先跑 vite dev
 *   2. 桌面模式（ELECTRON_PROD=1 或 --prod）：加载 frontend/dist/index.html，
 *      无需 vite，启动快，适合"一键打开"
 *   3. 打包后（app.isPackaged）：加载 resources 内的 dist
 */
const { app, BrowserWindow, shell, dialog } = require("electron");
const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

const BACKEND_PORT = 8765;
const FRONTEND_DEV_URL = "http://127.0.0.1:5173";

// 运行模式判定
const forceProd =
  process.env.ELECTRON_PROD === "1" || process.argv.includes("--prod");
const isPackaged = app.isPackaged;
const isDev = !isPackaged && !forceProd;

// 项目根目录（未打包：electron/ 的上一级；打包后：resourcesPath）
const projectRoot = isPackaged
  ? process.resourcesPath
  : path.join(__dirname, "..");

// PDF 文档存档目录（day1_PDF2MD/resource，与 day2_pageindex 平级）
const DOC_RESOURCE_DIR = path.resolve(projectRoot, "..", "day1_PDF2MD", "resource");

let mainWindow = null;
let backendProcess = null;

/** 探测后端是否就绪 */
function waitForBackend(maxRetries = 40) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const check = () => {
      const req = http.get(
        `http://127.0.0.1:${BACKEND_PORT}/api/health`,
        (res) => {
          if (res.statusCode === 200) resolve();
          else retry();
          res.resume();
        }
      );
      req.on("error", retry);
      req.setTimeout(1500, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      retries += 1;
      if (retries >= maxRetries) reject(new Error("Backend not ready"));
      else setTimeout(check, 700);
    };
    check();
  });
}

/** 探测可用的 Python 命令（优先 py launcher） */
function resolvePythonCmd() {
  if (process.env.PYTHON_CMD) {
    return { cmd: process.env.PYTHON_CMD, args: [] };
  }
  // Windows：优先 py launcher（可指定版本）
  if (process.platform === "win32") {
    try {
      execSync("py -3.12 --version", { stdio: "ignore", windowsHide: true });
      return { cmd: "py", args: ["-3.12"] };
    } catch {
      try {
        execSync("py --version", { stdio: "ignore", windowsHide: true });
        return { cmd: "py", args: [] };
      } catch {
        /* fall through */
      }
    }
  }
  return { cmd: "python", args: [] };
}

/** 启动 Python 后端 */
function startBackend() {
  // Windows: 先检查 8765 端口是否被占用，如果占用则杀掉旧进程
  if (process.platform === "win32") {
    try {
      const netstat = execSync(
        `netstat -ano | findstr "${BACKEND_PORT}"`,
        { encoding: "utf-8", windowsHide: true }
      );
      const lines = netstat.split("\n").filter((l) => l.includes(":" + BACKEND_PORT));
      for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid && !isNaN(Number(pid))) {
          console.log(`[electron] killing old process on port ${BACKEND_PORT}: PID ${pid}`);
          try { execSync(`taskkill /PID ${pid} /F /T`, { windowsHide: true, stdio: "ignore" }); } catch {}
        }
      }
      // 给操作系统 500ms 释放端口
      execSync("ping -n 1 -w 500 127.0.0.1 > nul", { windowsHide: true, stdio: "ignore" });
    } catch {
      // 端口未被占用，正常继续
    }
  }

  const backendDir = path.join(projectRoot, "backend");
  if (!fs.existsSync(path.join(backendDir, "server.py"))) {
    console.error(`[electron] backend/server.py not found at ${backendDir}`);
    return;
  }

  const { cmd, args } = resolvePythonCmd();
  const fullArgs = [...args, "server.py"];
  console.log(`[electron] starting backend: ${cmd} ${fullArgs.join(" ")} (cwd: ${backendDir})`);

  backendProcess = spawn(cmd, fullArgs, {
    cwd: backendDir,
    windowsHide: true,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });

  backendProcess.stdout.on("data", (data) =>
    process.stdout.write(`[backend] ${data}`)
  );
  backendProcess.stderr.on("data", (data) =>
    process.stderr.write(`[backend] ${data}`)
  );
  backendProcess.on("exit", (code) =>
    console.log(`[backend] exited with code ${code}`)
  );
}

/** 创建主窗口 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 720,
    minHeight: 540,
    backgroundColor: "#020617",
    title: "PageIndex RAG Agent",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  // 拦截新窗口打开，将 PDF 查看请求转为直接打开本地文件
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    console.log("[electron] setWindowOpenHandler:", url);

    // 拦截 /api/kb/view/{docName} → 直接打开本地 PDF
    const viewMatch = url.match(/\/api\/kb\/view\/(.+?)(?:\?|$)/);
    if (viewMatch) {
      try {
        const docName = decodeURIComponent(viewMatch[1]);
        console.log("[electron] 查找本地 PDF:", docName);
        console.log("[electron] 搜索目录:", DOC_RESOURCE_DIR);

        if (fs.existsSync(DOC_RESOURCE_DIR)) {
          const files = fs.readdirSync(DOC_RESOURCE_DIR);
          console.log("[electron] 目录文件数:", files.length);
          for (const f of files) {
            const stem = path.parse(f).name;
            if (stem === docName || docName.includes(stem) || stem.includes(docName)) {
              const filepath = path.join(DOC_RESOURCE_DIR, f);
              console.log("[electron] 匹配成功 → 打开:", filepath);
              shell.openPath(filepath).then((err) => {
                if (err) console.error("[electron] openPath 失败:", err);
              });
              return { action: "deny" };
            }
          }
          console.log("[electron] 未找到匹配文件, 回退到浏览器打开");
        } else {
          console.log("[electron] 目录不存在:", DOC_RESOURCE_DIR);
        }
      } catch (e) {
        console.error("[electron] 查找本地文件失败:", e);
      }
      // 本地未找到 → 回退到浏览器显示（后端 /api/kb/view 会返回 PDF）
      shell.openExternal(url);
      return { action: "deny" };
    }

    // 非 PDF 查看链接 → 系统浏览器打开
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev) {
    mainWindow.loadURL(FRONTEND_DEV_URL);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    // 加载 build 产物：项目根/frontend/dist/index.html
    const distFile = path.join(projectRoot, "frontend", "dist", "index.html");
    if (!fs.existsSync(distFile)) {
      dialog.showErrorBox(
        "前端未构建",
        `找不到 ${distFile}\n\n请先在 frontend/ 目录运行：\n  npm install\n  npm run build`
      );
      app.quit();
      return;
    }
    mainWindow.loadFile(distFile);
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  startBackend();

  try {
    await waitForBackend();
    console.log("[electron] backend ready");
  } catch (e) {
    console.error("[electron] backend failed to start:", e.message);
    if (!isDev) {
      dialog.showErrorBox(
        "后端启动失败",
        "Python 后端未能正常启动。请检查 Python 环境与 PageIndex/.env 配置。"
      );
    }
  }

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (backendProcess) {
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", backendProcess.pid, "/f", "/t"]);
      } else {
        backendProcess.kill("SIGTERM");
      }
    } catch (e) {
      console.error("[electron] kill backend failed:", e);
    }
    backendProcess = null;
  }
});
