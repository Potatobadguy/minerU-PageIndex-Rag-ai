import React, { memo, useState } from "react";
import type { ChatMessage } from "../api";
import MarkdownView from "./MarkdownView";
import RetrievalSteps from "./RetrievalSteps";
import SourcesPanel from "./SourcesPanel";
import { ImageModal, resolveImageUrl } from "./SourcesPanel";

interface MessageBubbleProps {
  message: ChatMessage;
}

/** 从文本中提取候选关键词（中文+数字，2-4 字） */
function extractKeywords(text: string): string[] {
  const pure = text.replace(/[^\u4e00-\u9fff0-9]/g, "");
  const keywords = new Set<string>();
  const maxN = Math.min(4, pure.length);
  for (let n = 2; n <= maxN; n++) {
    for (let i = 0; i <= pure.length - n; i++) {
      keywords.add(pure.slice(i, i + n));
    }
  }
  return Array.from(keywords);
}

/** 判断图片是否与回答内容相关 */
function isImageRelevant(caption: string, section: string, answer: string): boolean {
  const answerLower = answer.toLowerCase();
  const text = (caption + " " + section).toLowerCase();
  if (!text.trim()) return true;
  const keywords = extractKeywords(text);
  if (keywords.length === 0) return true;
  return keywords.some((k) => answerLower.includes(k));
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isSystem = message.role === "system";
  const [modalSrc, setModalSrc] = useState<string | null>(null);
  const [modalCaption, setModalCaption] = useState("");

  // 收集消息中所有引用图片（含 caption / section）
  const rawImages: { url: string; caption: string; section: string }[] = [];
  const seen = new Set<string>();
  message.sources?.forEach((src) => {
    src.images?.forEach((img) => {
      if (!seen.has(img.url)) {
        seen.add(img.url);
        rawImages.push({
          url: img.url,
          caption: img.caption || "",
          section: src.section || "",
        });
      }
    });
  });

  // 过滤：只保留与回答内容相关的图片
  const answerText = message.content || "";
  const isNoAnswer = /无法回答|信息不足|没有相关|未找到|无法确定|没有提供/i.test(answerText);
  const inlineImages = isNoAnswer
    ? []
    : rawImages.filter((img) => isImageRelevant(img.caption, img.section, answerText));

  if (isSystem) {
    return (
      <div className="flex justify-center animate-fade-in">
        <div className="rounded-full bg-white/70 backdrop-blur px-4 py-1.5 text-xs text-slate-400 shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex gap-3 animate-slide-up ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
    >
      {/* 头像 */}
      <div
        className={`flex h-10 w-10 flex-none items-center justify-center rounded-full text-sm shadow-sm ${
          isUser
            ? "bg-gradient-to-br from-brand-500 to-brand-700 text-white"
            : "bg-gradient-to-br from-emerald-500 to-teal-600 text-white"
        }`}
        aria-hidden="true"
      >
        {isUser ? "我" : "AI"}
      </div>

      {/* 消息主体 */}
      <div
        className={`flex min-w-0 max-w-[calc(100%-3rem)] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        {/* 角色标签 */}
        <div className="px-1 text-[11px] font-medium text-slate-400">
          {isUser ? "你" : "PageIndex Agent"}
          <span className="ml-2 text-slate-350">
            {new Date(message.ts).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </div>

        {/* 气泡 */}
        <div
          className={`w-full rounded-2xl px-4 py-3 shadow-sm ${
            isUser
              ? "bg-brand-600 text-white rounded-tr-sm"
              : message.error
              ? "bg-red-50 border border-red-200 text-red-700 rounded-tl-sm"
              : "bg-white border border-slate-200 text-slate-700 rounded-tl-sm shadow-card"
          }`}
        >
          {/* 检索过程 */}
          {isAssistant && message.streaming && message.steps && (
            <RetrievalSteps steps={message.steps} active={message.streaming} />
          )}

          {/* 内容 */}
          {isUser ? (
            <p className="whitespace-pre-wrap break-words leading-relaxed">
              {message.content}
            </p>
          ) : message.content ? (
            <MarkdownView content={message.content} />
          ) : message.streaming ? (
            <div className="flex items-center gap-2 py-1 text-slate-400">
              <span className="dot-flash text-brand-500">
                <span /><span /><span />
              </span>
              <span className="text-sm">正在思考…</span>
            </div>
          ) : null}

          {message.error && (
            <div className="mt-1 text-xs text-red-500">
              请检查后端服务是否正常，或更换模型重试。
            </div>
          )}

          {/* 内联图片画廊 — 回答中直接显示图片 */}
          {isAssistant && inlineImages.length > 0 && (
            <div className="mt-3 -mx-1 flex gap-2 overflow-x-auto pb-1">
              {inlineImages.map((img, idx) => (
                <button
                  key={img.url}
                  onClick={() => {
                    setModalSrc(resolveImageUrl(img.url));
                    setModalCaption(img.caption || `图片 ${idx + 1}`);
                  }}
                  className="relative flex-none rounded-lg border border-slate-200 bg-white p-1 shadow-sm transition hover:shadow-md hover:scale-[1.02] active:scale-[0.98]"
                  title={img.caption || `图片 ${idx + 1}`}
                >
                  <img
                    src={resolveImageUrl(img.url)}
                    alt={img.caption || `图片 ${idx + 1}`}
                    className="h-24 w-auto max-w-[180px] rounded object-cover"
                    loading="lazy"
                  />
                  {img.caption && (
                    <div className="mt-1 max-w-[180px] truncate px-1 text-[10px] text-slate-500">
                      {img.caption}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 引用来源 */}
        {isAssistant && message.sources && message.sources.length > 0 && (
          <SourcesPanel sources={message.sources} />
        )}

        {/* 图片放大弹窗 */}
        {modalSrc && (
          <ImageModal
            src={modalSrc}
            caption={modalCaption}
            onClose={() => setModalSrc(null)}
          />
        )}
      </div>
    </div>
  );
};

export default memo(MessageBubble);
