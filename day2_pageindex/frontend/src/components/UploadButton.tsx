import React, { useRef, useState } from "react";
import { API_BASE } from "../api";

interface UploadButtonProps {
  onUploadSuccess: () => void;
}

type PipelineStage = "idle" | "uploading" | "parsing" | "indexing" | "enhancing" | "done" | "error";

interface StageInfo {
  stage: PipelineStage;
  message: string;
  filename: string;
}

const STAGE_CONFIG: Record<PipelineStage, { label: string; icon: string; color: string }> = {
  idle:   { label: "准备上传",  icon: "📄", color: "text-slate-400" },
  uploading: { label: "文件上传中", icon: "📤", color: "text-brand-500" },
  parsing: { label: "文档解析中", icon: "🔍", color: "text-amber-500" },
  indexing: { label: "检索树构建中", icon: "🌲", color: "text-indigo-500" },
  enhancing: { label: "图片增强检索中", icon: "🖼️", color: "text-purple-500" },
  done:   { label: "已加入知识库", icon: "✅", color: "text-emerald-500" },
  error:  { label: "处理失败",   icon: "❌", color: "text-red-500" },
};

const STAGE_ORDER: PipelineStage[] = ["uploading", "parsing", "indexing", "enhancing", "done"];

const UploadButton: React.FC<UploadButtonProps> = ({ onUploadSuccess }) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<PipelineStage>("idle");
  const [message, setMessage] = useState("");
  const [filename, setFilename] = useState("");
  const [showProgress, setShowProgress] = useState(false);
  const stageRef = useRef<PipelineStage>("idle");
  stageRef.current = stage;
  const resetState = () => {
    setStage("idle");
    setMessage("");
    setFilename("");
    setShowProgress(false);
  };

  const scheduleClose = () => {
    setTimeout(() => {
      resetState();
      onUploadSuccess();
    }, 1200);
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!ext || !["pdf", "docx", "doc", "md"].includes(ext)) {
      alert("仅支持 PDF、DOCX、MD 文件");
      return;
    }

    setShowProgress(true);
    setStage("uploading");
    setMessage("正在上传文件…");
    setFilename(file.name);

    try {
      const form = new FormData();
      form.append("file", file);

      const resp = await fetch(`${API_BASE}/api/kb/upload`, {
        method: "POST",
        body: form,
      });

      if (!resp.ok || !resp.body) {
        setStage("error");
        setMessage(`上传失败: ${resp.statusText}`);
        return;
      }

      // SSE 流式读取进度
      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split(/\r?\n\r?\n/);
        buffer = events.pop() || "";

        for (const raw of events) {
          const lines = raw.split(/\r?\n/);
          let evtType = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event:")) evtType = line.slice(6).trim();
            else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
          }
          if (!dataStr) continue;
          let data: any;
          try { data = JSON.parse(dataStr); } catch { continue; }

          switch (evtType) {
            case "uploading":
            case "parsing":
            case "indexing":
            case "enhancing":
              setStage(evtType as PipelineStage);
              setMessage(data.message || "");
              break;
            case "done":
              setStage("done");
              setMessage(data.message || "已加入知识库");
              scheduleClose();
              break;
            case "error":
              setStage("error");
              setMessage(data.message || "处理失败");
              break;
            case "reload_done":
              // 知识库已刷新，无需额外操作
              break;
          }
        }
      }

      // 流结束后兜底：若已到 done/error 阶段由 scheduleClose 处理，
      // 若流意外中断且仍在 indexing/enhancing 阶段也尝试关闭
      if (stageRef.current === "indexing" || stageRef.current === "enhancing") {
        scheduleClose();
      }
    } catch (err: any) {
      setStage("error");
      setMessage(err.message || "网络错误");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const currentStageIdx = STAGE_ORDER.indexOf(stage);
  const cfg = STAGE_CONFIG[stage];

  return (
    <>
      {/* 上传按钮 */}
      <button
        onClick={() => fileRef.current?.click()}
        disabled={showProgress}
        className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 shadow-sm transition-all hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 disabled:opacity-50"
        title="上传 PDF/DOCX/MD 到知识库"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>上传文档</span>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.docx,.doc,.md"
        onChange={handleUpload}
        className="hidden"
        aria-label="选择 PDF、DOCX 或 MD 文件上传"
      />

      {/* 进度弹窗 */}
      {showProgress && (
        <div className="fixed inset-0 z-50 flex pt-[15vh] justify-center bg-black/20 backdrop-blur-sm animate-fade-in">
          <div className="mx-4 w-full max-w-sm rounded-2xl bg-white p-6 shadow-float animate-scale-in self-start">
            {/* 文件名 + 关闭按钮 */}
            <div className="mb-4 flex items-start justify-between gap-2">
              <div className="truncate text-sm font-medium text-slate-700" title={filename}>
                {filename}
              </div>
              <button
                onClick={resetState}
                className="flex-none rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
                title="关闭"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* 进度阶段 */}
            <div className="space-y-3">
              {STAGE_ORDER.map((s, idx) => {
                const sCfg = STAGE_CONFIG[s];
                const isActive = idx === currentStageIdx;
                const isDone = idx < currentStageIdx;
                const isPending = idx > currentStageIdx;
                const isError = stage === "error";

                return (
                  <div key={s} className="flex items-center gap-3">
                    {/* 状态图标 */}
                    <div
                      className={`flex h-8 w-8 flex-none items-center justify-center rounded-full text-sm transition-all duration-500 ${
                        isDone
                          ? "bg-emerald-100 text-emerald-600"
                          : isActive && !isError
                          ? "bg-brand-100 text-brand-600 shadow-[0_0_12px_rgba(37,99,235,.25)]"
                          : isPending
                          ? "bg-slate-100 text-slate-300"
                          : "bg-red-50 text-red-400"
                      }`}
                    >
                      {isDone ? (
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      ) : isActive && !isError ? (
                        <span className="dot-flash text-brand-600">
                          <span /><span /><span />
                        </span>
                      ) : (
                        <span className="text-current">{sCfg.icon}</span>
                      )}
                    </div>

                    {/* 阶段标签 */}
                    <div className="flex-1 min-w-0">
                      <div
                        className={`text-xs font-medium transition-colors ${
                          isDone ? "text-emerald-600" : isActive && !isError ? "text-slate-800" : "text-slate-400"
                        }`}
                      >
                        {sCfg.label}
                      </div>
                      {isActive && !isError && (
                        <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full animate-shimmer rounded-full bg-gradient-to-r from-brand-400 via-brand-600 to-brand-400 bg-[length:200%_100%]" />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* 完成/错误消息 */}
            {stage === "done" && (
              <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700 animate-fade-in">
                {message}
              </div>
            )}
            {stage === "error" && (
              <div className="mt-4 space-y-2">
                <div className="rounded-lg bg-red-50 p-3 text-xs text-red-600">
                  {message}
                </div>
                <button
                  onClick={resetState}
                  className="w-full rounded-lg border border-slate-200 bg-white py-2 text-xs text-slate-600 shadow-sm hover:bg-slate-50 transition-colors"
                >
                  关闭
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default UploadButton;
