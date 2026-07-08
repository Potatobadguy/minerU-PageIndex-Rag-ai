import React, { useCallback, useEffect, useRef, useState } from "react";
import Header from "./components/Header";
import KbInfoBar from "./components/KbInfoBar";
import MessageBubble from "./components/MessageBubble";
import InputBar from "./components/InputBar";
import UploadButton from "./components/UploadButton";
import {
  ChatMessage,
  KbInfo,
  ModelsInfo,
  Source,
  StepEvent,
  fetchKbInfo,
  fetchModels,
  streamChat,
  switchModel,
} from "./api";

const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

const SAMPLE_QUESTIONS = [
  "导线荷载需要考虑哪些因素？",
  "重覆冰线路的设计冰厚如何取值？",
  "不同冰区的荷载组合对比",
];

const App: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [kbInfo, setKbInfo] = useState<KbInfo | null>(null);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [connected, setConnected] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [loadingMeta, setLoadingMeta] = useState(true);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadMeta = useCallback(async () => {
    setLoadingMeta(true);
    try {
      const [kb, m] = await Promise.all([fetchKbInfo(), fetchModels()]);
      setKbInfo(kb);
      setModels(m);
      setConnected(true);
    } catch (e) {
      setConnected(false);
      console.error("load meta failed:", e);
    } finally {
      setLoadingMeta(false);
    }
  }, []);

  useEffect(() => {
    loadMeta();
    setMessages([
      {
        id: uid(),
        role: "system",
        content: "欢迎使用，输入问题即可基于知识库检索回答，支持表格与公式渲染。",
        ts: Date.now(),
      },
    ]);
  }, [loadMeta]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const handleSend = useCallback(
    async (text: string) => {
      if (streaming) return;

      const userMsg: ChatMessage = {
        id: uid(), role: "user", content: text, ts: Date.now(),
      };
      const assistantId = uid();
      const assistantMsg: ChatMessage = {
        id: assistantId, role: "assistant", content: "",
        steps: [], sources: [], streaming: true, ts: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      const updateAssistant = (updater: (m: ChatMessage) => ChatMessage) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? updater(m) : m))
        );
      };

      try {
        await streamChat(text, models?.current, {
          onStep: (step: StepEvent) =>
            updateAssistant((m) => ({ ...m, steps: [...(m.steps || []), step] })),
          onToken: (delta: string) =>
            updateAssistant((m) => ({ ...m, content: m.content + delta })),
          onSources: (sources: Source[]) =>
            updateAssistant((m) => ({ ...m, sources })),
          onError: (msg: string) =>
            updateAssistant((m) => ({
              ...m, streaming: false, error: true,
              content: m.content || msg,
            })),
          onDone: (answer: string) =>
            updateAssistant((m) => ({
              ...m, content: answer || m.content, streaming: false,
            })),
        }, controller.signal);
      } catch (e: any) {
        if (e.name === "AbortError") {
          updateAssistant((m) => ({
            ...m, streaming: false,
            content: m.content + "\n\n_（已中断）_",
          }));
        } else {
          updateAssistant((m) => ({
            ...m, streaming: false, error: true,
            content: `请求失败：${e.message || e}`,
          }));
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [streaming, models?.current]
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleModelChange = useCallback(async (model: string) => {
    try {
      await switchModel(model);
      setModels((prev) => (prev ? { ...prev, current: model } : prev));
    } catch (e) {
      console.error("switch model failed:", e);
    }
  }, []);

  const handleClear = useCallback(() => {
    if (streaming) return;
    setMessages([{
      id: uid(), role: "system", content: "对话已清空。", ts: Date.now(),
    }]);
  }, [streaming]);

  return (
    <div className="flex h-screen flex-col" style={{ background: "#faf9f6" }}>
      {/* 顶部装饰条 */}
      <div className="h-1 bg-gradient-to-r from-brand-500 via-indigo-500 to-teal-500" />

      <Header
        models={models}
        onModelChange={handleModelChange}
        connected={connected}
        onUploadSuccess={() => loadMeta()}
      />
      <KbInfoBar info={kbInfo} loading={loadingMeta} onRefresh={loadMeta} />

      {/* 消息列表 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto overflow-x-hidden"
        style={{ background: "linear-gradient(180deg, #faf9f6 0%, #f3f1ec 100%)" }}
        role="log"
        aria-live="polite"
        aria-label="对话消息列表"
      >
        <div className="mx-auto max-w-4xl space-y-5 px-3 py-5 sm:px-4">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}

          {/* 空状态 */}
          {messages.length <= 1 && !streaming && (
            <div className="mt-10 animate-fade-in">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-100 to-blue-50 shadow-card">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-brand-600">
                  <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                  <path d="M8 11h6M11 8v6" strokeWidth="1"/>
                </svg>
              </div>
              <h2 className="mb-2 text-center text-lg font-semibold text-slate-700">
                开始提问
              </h2>
              <p className="mb-4 text-center text-sm text-slate-500">
                试试这些问题：
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {SAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSend(q)}
                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm transition-all hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 hover:shadow-card"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* 底部操作栏 */}
      <div className="border-t border-slate-200/80 bg-white/80 px-4 py-1.5 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <button
            onClick={handleClear}
            disabled={streaming || messages.length <= 1}
            className="text-xs text-slate-400 transition-colors hover:text-slate-600 disabled:opacity-30"
          >
            清空对话
          </button>
          <span className="text-[10px] text-slate-400">
            {messages.filter((m) => m.role !== "system").length} 条消息
          </span>
        </div>
      </div>

      <InputBar
        onSend={handleSend}
        onStop={handleStop}
        streaming={streaming}
        disabled={!connected}
      />
    </div>
  );
};

export default App;
