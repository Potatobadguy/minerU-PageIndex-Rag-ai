import React, { useState } from "react";
import type { KbInfo } from "../api";
import { deleteDocument, viewDocumentUrl } from "../api";

interface KbInfoBarProps {
  info: KbInfo | null;
  loading: boolean;
  onRefresh: () => void;
}

const KbInfoBar: React.FC<KbInfoBarProps> = ({ info, loading, onRefresh }) => {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const handleView = (docName: string) => {
    // 统一走 window.open：Electron 的 setWindowOpenHandler 会拦截 /api/kb/view/ URL
    // 并直接用 shell.openPath 打开本地文件；浏览器端则在新标签页内联显示 PDF
    const viewUrl = viewDocumentUrl(docName);
    window.open(viewUrl, "_blank");
  };

  const handleDelete = async (docName: string) => {
    if (deleting) return;
    setDeleting(docName);
    try {
      await deleteDocument(docName);
      setConfirmDelete(null);
      onRefresh();
    } catch (err) {
      console.error("delete failed:", err);
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="border-b border-slate-200/80 bg-white/70 px-4 py-2">
        <div className="h-4 w-48 animate-pulse rounded bg-slate-100" />
      </div>
    );
  }

  if (!info || info.doc_count === 0) {
    return (
      <div className="border-b border-amber-200 bg-amber-50/80 px-4 py-2.5 text-xs text-amber-700">
        知识库为空，请上传 PDF / DOCX / MD 文档
      </div>
    );
  }

  return (
    <div className="border-b border-slate-200/80 bg-white/70">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-2 text-left transition-colors hover:bg-slate-50"
      >
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-brand-500">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span className="font-medium">
            知识库 · {info.doc_count} 篇文档
          </span>
          {!expanded && (
            <span className="hidden text-slate-400 sm:inline truncate max-w-[400px]">
              {info.documents.map((d) => d.doc_name).join(" · ")}
            </span>
          )}
        </div>
        <span className="text-xs text-slate-400">
          {expanded ? "收起 ▲" : "详情 ▼"}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3 animate-fade-in">
          {/* 确认删除弹窗 */}
          {confirmDelete && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 backdrop-blur-sm animate-fade-in">
              <div className="mx-4 w-full max-w-sm rounded-2xl bg-white p-5 shadow-float animate-scale-in">
                <h3 className="text-sm font-semibold text-slate-800">确认删除</h3>
                <p className="mt-2 text-xs text-slate-500">
                  将删除 <strong className="text-slate-700">{confirmDelete}</strong> 的全部知识库数据：<br />
                  · 原始文档<br />· 检索索引<br />· 增强索引<br />· 解析输出
                  <br /><br />
                  <span className="text-red-500">此操作不可恢复</span>
                </p>
                <div className="mt-4 flex gap-2">
                  <button
                    onClick={() => setConfirmDelete(null)}
                    className="flex-1 rounded-lg border border-slate-200 bg-white py-2 text-xs text-slate-600 shadow-sm hover:bg-slate-50 transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => handleDelete(confirmDelete)}
                    disabled={deleting !== null}
                    className="flex-1 rounded-lg bg-red-500 py-2 text-xs font-medium text-white shadow-sm hover:bg-red-600 transition-colors disabled:opacity-50"
                  >
                    {deleting === confirmDelete ? "删除中…" : "确认删除"}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {info.documents.map((d) => (
              <div
                key={d.doc_name}
                className="group flex items-start gap-2 rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm transition-shadow hover:shadow-card"
              >
                {/* 文档信息 —— 点击可查看 */}
                <div
                  onClick={() => handleView(d.doc_name)}
                  className="flex-1 min-w-0 cursor-pointer"
                  title="点击查看原文"
                >
                  <div className="flex items-center gap-1.5 text-xs font-medium text-slate-700">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-brand-500 flex-none">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <span className="truncate">{d.doc_name}</span>
                  </div>
                  <div className="mt-1 text-[10px] text-slate-400">
                    {d.line_count} 行
                  </div>
                  {d.doc_description && (
                    <p className="mt-1 text-[11px] leading-snug text-slate-500 line-clamp-2">
                      {d.doc_description}
                    </p>
                  )}
                </div>

                {/* 操作按钮 —— hover 时显示 */}
                <div className="flex flex-none gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  {/* 查看文档 */}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleView(d.doc_name); }}
                    className="rounded-md p-1 text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-600"
                    title="查看原文"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                      <circle cx="12" cy="12" r="3"/>
                    </svg>
                  </button>
                  {/* 删除文档 */}
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmDelete(d.doc_name); }}
                    className="rounded-md p-1 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-500"
                    title="删除文档"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default KbInfoBar;
