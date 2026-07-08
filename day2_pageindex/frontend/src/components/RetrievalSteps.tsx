import React from "react";
import type { StepEvent } from "../api";

interface RetrievalStepsProps {
  steps: StepEvent[];
  active: boolean;
}

const STAGE_META: Record<StepEvent["stage"], { label: string }> = {
  collect: { label: "扫描知识库" },
  collect_done: { label: "扫描完成" },
  locate: { label: "定位相关章节" },
  locate_done: { label: "定位完成" },
  extract: { label: "提取章节详情" },
  extract_done: { label: "提取完成" },
  generate: { label: "生成回答" },
  generate_done: { label: "生成完成" },
  fallback: { label: "降级重试" },
};

const ORDER: StepEvent["stage"][] = ["collect", "locate", "extract", "generate"];

const RetrievalSteps: React.FC<RetrievalStepsProps> = ({ steps, active }) => {
  if (steps.length === 0) return null;

  const stageMap = new Map<StepEvent["stage"], StepEvent>();
  for (const s of steps) stageMap.set(s.stage, s);

  return (
    <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50/70 p-3 text-xs animate-fade-in">
      <div className="mb-2 flex items-center gap-2 text-slate-500">
        <span className="dot-flash text-brand-500">
          <span /><span /><span />
        </span>
        <span className="font-medium">检索过程</span>
      </div>
      <div className="space-y-1.5">
        {ORDER.map((stage, idx) => {
          const inProgress = stageMap.has(stage) && !stageMap.has(`${stage}_done` as any);
          const done = stageMap.has(`${stage}_done` as any);
          const meta = STAGE_META[stage];
          const doneStep = stageMap.get(`${stage}_done` as any);
          const inStep = stageMap.get(stage);

          return (
            <div key={stage} className="flex items-start gap-2">
              <div
                className={`mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full text-[10px] ${
                  done
                    ? "bg-emerald-100 text-emerald-600"
                    : inProgress
                    ? "bg-brand-100 text-brand-600"
                    : "bg-slate-100 text-slate-400"
                }`}
              >
                {done ? "✓" : idx + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className={`font-medium ${
                    done
                      ? "text-emerald-600"
                      : inProgress
                      ? "text-brand-600"
                      : "text-slate-400"
                  }`}
                >
                  {meta.label}
                  {inProgress && (
                    <span className="ml-1.5 inline-flex">
                      <span className="dot-flash text-current">
                        <span /><span /><span />
                      </span>
                    </span>
                  )}
                </div>
                {(inStep || doneStep) && (
                  <div className="text-[11px] text-slate-500 mt-0.5 truncate">
                    {(doneStep ?? inStep)!.message}
                    {doneStep?.duration_ms != null && (
                      <span className="ml-1.5 text-slate-400">
                        · {doneStep.duration_ms}ms
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {stageMap.get("locate_done")?.hit_docs &&
        stageMap.get("locate_done")!.hit_docs!.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {stageMap.get("locate_done")!.hit_docs!.map((doc) => (
              <span
                key={doc}
                className="rounded-full bg-brand-50 px-2 py-0.5 text-[10px] text-brand-700 border border-brand-200"
              >
                {doc}
              </span>
            ))}
          </div>
        )}
    </div>
  );
};

export default RetrievalSteps;
