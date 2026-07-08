import React, { useEffect, useRef, useState } from "react";

interface InputBarProps {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
}

const InputBar: React.FC<InputBarProps> = ({ onSend, onStop, streaming, disabled }) => {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSend();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-slate-200/80 bg-white/85 px-3 py-3 backdrop-blur-sm sm:px-4">
      <div className="mx-auto max-w-4xl">
        <div className="input-glow flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50/80 p-2 transition-shadow focus-within:border-brand-300">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              streaming
                ? "正在生成回答…"
                : "输入问题，Enter 发送 / Shift+Enter 换行"
            }
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none disabled:opacity-50"
            style={{ maxHeight: "200px" }}
            aria-label="问题输入框"
          />
          {streaming ? (
            <button
              onClick={onStop}
              className="flex h-9 flex-none items-center gap-1.5 rounded-xl bg-red-500 px-4 text-sm font-medium text-white shadow-sm transition-all hover:bg-red-600 active:scale-95"
            >
              <span className="h-3 w-3 rounded-sm bg-white" />
              <span>停止</span>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!text.trim() || disabled}
              className="flex h-9 flex-none items-center gap-1.5 rounded-xl bg-brand-600 px-4 text-sm font-medium text-white shadow-button transition-all hover:bg-brand-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              <span>发送</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          )}
        </div>
        <p className="mt-1.5 hidden text-center text-[10px] text-slate-400 sm:block">
          PageIndex RAG Agent · 回答基于知识库检索，支持 Markdown 表格与 LaTeX 公式
        </p>
      </div>
    </div>
  );
};

export default InputBar;
