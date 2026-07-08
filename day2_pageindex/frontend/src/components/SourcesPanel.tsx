import React, { useState } from "react";
import type { Source } from "../api";
import { API_BASE } from "../api";

interface SourcesPanelProps {
  sources: Source[];
}

/** 将相对路径图片 URL 转为绝对路径 */
export function resolveImageUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  return API_BASE + url;
}

/** 图片弹窗 */
export const ImageModal: React.FC<{ src: string; caption: string; onClose: () => void }> = ({
  src,
  caption,
  onClose,
}) => {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="relative max-h-[90vh] max-w-[90vw] rounded-2xl bg-white p-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute -right-3 -top-3 flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-lg hover:bg-slate-100 transition-colors"
          aria-label="关闭"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <img
          src={src}
          alt={caption || "文档图片"}
          className="max-h-[80vh] max-w-[85vw] rounded-xl object-contain"
        />
        {caption && (
          <p className="mt-3 text-center text-sm text-slate-500">{caption}</p>
        )}
      </div>
    </div>
  );
};

const SourcesPanel: React.FC<SourcesPanelProps> = ({ sources }) => {
  const [expanded, setExpanded] = useState(false);
  const [modalSrc, setModalSrc] = useState<string | null>(null);
  const [modalCaption, setModalCaption] = useState("");

  if (!sources || sources.length === 0) return null;

  const display = expanded ? sources : sources.slice(0, 3);

  // 统计图片总数
  const totalImages = sources.reduce((sum, s) => sum + (s.images?.length || 0), 0);

  return (
    <>
      <div className="mt-2 rounded-lg border border-slate-200 bg-white/80 animate-fade-in shadow-sm">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors"
          aria-expanded={expanded}
        >
          <span className="flex items-center gap-1.5">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-brand-500"
            >
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            <span>
              引用来源（{sources.length}）
              {totalImages > 0 && (
                <span className="ml-1 text-brand-500">· {totalImages} 张图片</span>
              )}
            </span>
          </span>
          <span className="text-slate-400">{expanded ? "收起 ▲" : "展开 ▼"}</span>
        </button>
        {expanded && (
          <div className="border-t border-slate-200 px-3 py-2 space-y-2.5 max-h-[60vh] overflow-y-auto">
            {display.map((s, i) => (
              <div
                key={i}
                className="rounded-lg bg-slate-50 p-2.5 border border-slate-200"
              >
                {/* 文档路径 */}
                <div className="flex items-center gap-2 text-xs">
                  <span className="rounded bg-brand-100 px-1.5 py-0.5 text-brand-700 font-medium text-[10px]">
                    {s.doc_name}
                  </span>
                  <span className="text-slate-300">›</span>
                  <span className="text-slate-700 font-medium text-[11px]">
                    {s.section}
                  </span>
                </div>

                {/* 摘要 */}
                {s.summary && (
                  <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 line-clamp-3">
                    {s.summary}
                  </p>
                )}

                {/* 图片缩略图 */}
                {s.images && s.images.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {s.images.map((img, j) => (
                      <button
                        key={j}
                        onClick={() => {
                          setModalSrc(resolveImageUrl(img.url));
                          setModalCaption(img.caption || "");
                        }}
                        className="group relative flex-shrink-0 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm hover:shadow-md hover:border-brand-300 transition-all"
                        title={img.caption || "点击放大查看"}
                      >
                        <img
                          src={resolveImageUrl(img.url)}
                          alt={img.caption || `图片 ${j + 1}`}
                          className="h-20 w-auto max-w-[160px] object-cover"
                          loading="lazy"
                        />
                        {img.caption && (
                          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-2 py-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <span className="text-[10px] text-white line-clamp-1">
                              {img.caption}
                            </span>
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* 表格 */}
                {s.tables && s.tables.length > 0 && (
                  <div className="mt-2 space-y-2">
                    {s.tables.map((tbl, j) => (
                      <div key={j} className="overflow-x-auto">
                        {tbl.caption && (
                          <p className="mb-1 text-[10px] font-medium text-slate-500">
                            {tbl.caption}
                          </p>
                        )}
                        <div
                          className="text-[10px] leading-relaxed [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-slate-300 [&_td]:px-1.5 [&_td]:py-0.5 [&_tr]:even:bg-white"
                          dangerouslySetInnerHTML={{ __html: tbl.html }}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 图片全屏弹窗 */}
      {modalSrc && (
        <ImageModal
          src={modalSrc}
          caption={modalCaption}
          onClose={() => setModalSrc(null)}
        />
      )}
    </>
  );
};

export default SourcesPanel;
