import React from "react";
import type { ModelsInfo } from "../api";
import UploadButton from "./UploadButton";

interface HeaderProps {
  models: ModelsInfo | null;
  onModelChange: (model: string) => void;
  connected: boolean;
  onUploadSuccess: () => void;
}

const Header: React.FC<HeaderProps> = ({ models, onModelChange, connected, onUploadSuccess }) => {
  return (
    <header className="flex items-center justify-between border-b border-slate-200/80 bg-white/85 px-4 py-3 backdrop-blur-sm">
      <div className="flex items-center gap-3 min-w-0">
        {/* Logo */}
        <div className="flex h-10 w-10 flex-none items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-button">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <circle cx="9" cy="9" r="1" fill="currentColor" stroke="none"/>
          </svg>
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-[17px] font-bold text-gradient">
            PageIndex RAG Agent
          </h1>
          <p className="hidden text-[10px] text-slate-500 sm:block">
            多文档检索增强 · 支持表格与公式
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-none">
        {/* 连接状态 */}
        <div className="hidden items-center gap-1.5 sm:flex" title={connected ? "已连接" : "未连接"}>
          <span
            className={`h-2 w-2 rounded-full ${
              connected
                ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,.5)] animate-pulse-soft"
                : "bg-red-400"
            }`}
          />
          <span className="text-[10px] text-slate-400">
            {connected ? "在线" : "离线"}
          </span>
        </div>

        {/* 上传按钮 */}
        <div className="hidden sm:block">
          <UploadButton onUploadSuccess={onUploadSuccess} />
        </div>

        {/* 模型选择 */}
        <div className="flex items-center gap-1.5">
          <span className="hidden text-[10px] text-slate-400 md:inline">模型</span>
          <select
            value={models?.current || ""}
            onChange={(e) => onModelChange(e.target.value)}
            disabled={!models}
            className="max-w-[160px] sm:max-w-[220px] rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:opacity-50"
            aria-label="选择模型"
          >
            {models?.models.map((m) => (
              <option key={m} value={m}>
                {m.replace(/^(openai|anthropic)\//, "")}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
};

export default Header;
