/**
 * 后端 API 配置与类型定义
 */
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ||
  "http://127.0.0.1:8765";

/** 知识库文档元信息 */
export interface KbDocument {
  doc_name: string;
  doc_description: string;
  line_count: number;
}

/** 知识库整体信息 */
export interface KbInfo {
  resource_dir: string;
  doc_count: number;
  documents: KbDocument[];
}

/** 模型列表 */
export interface ModelsInfo {
  models: string[];
  current: string;
}

/** 引用来源 */
export interface SourceImage {
  url: string;
  caption: string;
}

export interface SourceTable {
  caption: string;
  html: string;
}

export interface Source {
  doc_name: string;
  section: string;
  summary: string;
  /** 增强版索引附带的图片（相对路径，需拼 API_BASE） */
  images?: SourceImage[];
  /** 增强版索引附带的表格 */
  tables?: SourceTable[];
}

/** 检索过程步骤 */
export type StepStage =
  | "collect"
  | "collect_done"
  | "locate"
  | "locate_done"
  | "extract"
  | "extract_done"
  | "generate"
  | "generate_done"
  | "fallback";

export interface StepEvent {
  stage: StepStage;
  message: string;
  duration_ms?: number;
  hit_docs?: string[];
  source_count?: number;
}

/** 聊天消息（前端状态） */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  /** 检索过程（仅 assistant 消息） */
  steps?: StepEvent[];
  /** 引用来源（仅 assistant 消息） */
  sources?: Source[];
  /** 是否正在生成 */
  streaming?: boolean;
  /** 是否出错 */
  error?: boolean;
  /** 时间戳 */
  ts: number;
}

/** ===== API 调用 ===== */

export async function fetchKbInfo(): Promise<KbInfo> {
  const r = await fetch(`${API_BASE}/api/kb-info`);
  if (!r.ok) throw new Error(`kb-info: ${r.status}`);
  return r.json();
}

export async function fetchModels(): Promise<ModelsInfo> {
  const r = await fetch(`${API_BASE}/api/models`);
  if (!r.ok) throw new Error(`models: ${r.status}`);
  return r.json();
}

export async function switchModel(model: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/model/switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!r.ok) throw new Error(`switch model: ${r.status}`);
}

export function viewDocumentUrl(docName: string): string {
  return `${API_BASE}/api/kb/view/${encodeURIComponent(docName)}`;
}

export async function deleteDocument(docName: string): Promise<{ ok: boolean; deleted: string[] }> {
  const r = await fetch(`${API_BASE}/api/kb/document/${encodeURIComponent(docName)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`delete: ${r.status}`);
  return r.json();
}

/**
 * SSE 流式聊天。
 * 通过 fetch + ReadableStream 手动解析 SSE（避免 EventSource 不支持 POST 的限制）。
 */
export interface StreamHandlers {
  onStep: (step: StepEvent) => void;
  onToken: (delta: string) => void;
  onSources: (sources: Source[]) => void;
  onError: (message: string) => void;
  onDone: (answer: string) => void;
}

export async function streamChat(
  query: string,
  model: string | undefined,
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ query, model }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    throw new Error(`chat stream: ${resp.status} ${resp.statusText}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      // 流结束前，处理 buffer 中剩余的事件（最后一个可能没有 \r\n\r\n 结尾）
      if (buffer.trim()) {
        const events = buffer.split(/\r?\n\r?\n/);
        for (const raw of events) {
          if (!raw.trim()) continue;
          const lines = raw.split(/\r?\n/);
          let event = "message";
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("event:")) {
              event = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataStr += line.slice(5).trim();
            }
          }
          if (!dataStr) continue;
          let data: any;
          try {
            data = JSON.parse(dataStr);
          } catch {
            continue;
          }
          switch (event) {
            case "step":
              handlers.onStep(data as StepEvent);
              break;
            case "token":
              handlers.onToken(data.delta || "");
              break;
            case "sources":
              handlers.onSources(data.sources || []);
              break;
            case "error":
              handlers.onError(data.message || "未知错误");
              break;
            case "done":
              handlers.onDone(data.answer || "");
              return;
          }
        }
      }
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    // SSE 以双换行分隔事件（支持 \r\n\r\n 和 \n\n）
    const events = buffer.split(/\r?\n\r?\n/);
    buffer = events.pop() || "";

    for (const raw of events) {
      const lines = raw.split(/\r?\n/);
      let event = "message";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event:")) {
          event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataStr += line.slice(5).trim();
        }
      }
      if (!dataStr) continue;
      let data: any;
      try {
        data = JSON.parse(dataStr);
      } catch {
        continue;
      }
      switch (event) {
        case "step":
          handlers.onStep(data as StepEvent);
          break;
        case "token":
          handlers.onToken(data.delta || "");
          break;
        case "sources":
          handlers.onSources(data.sources || []);
          break;
        case "error":
          handlers.onError(data.message || "未知错误");
          break;
        case "done":
          handlers.onDone(data.answer || "");
          return;
      }
    }
  }
}
