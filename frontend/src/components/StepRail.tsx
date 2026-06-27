/**
 * 智能体执行流程图组件
 * 按 LangGraph 节点拓扑展示各步骤状态
 */
import { useEffect, useMemo, useState } from "react";
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../lib/format";
import type { StepState, StepStatus, TraceState } from "../types/agent";
import { TraceDetailContent } from "./TraceTimeline";

type FlowStatus = StepStatus | "pending";

type FlowNode = {
  step: string;
  displayName?: string;
  label?: string;
  caption?: string;
  kind?: "tool";
  toolName?: string;
  x: number;
  y: number;
  w?: number;
};

type BranchLabel = {
  text: string;
  x: number;
  y: number;
  anchor?: "start" | "middle";
};

const nodes: FlowNode[] = [
  { step: "入口解析", displayName: "入口意图解析", x: 430, y: 8, w: 176 },
  { step: "规划召回策略", x: 430, y: 92, w: 176 },
  { step: "抽取关键词", x: 430, y: 184 },
  { step: "执行工具", x: 430, y: 276 },
  { step: "召回字段信息", label: "recall_column", caption: "字段召回", kind: "tool", toolName: "recall_column", x: 210, y: 368, w: 178 },
  { step: "召回指标信息", label: "recall_metric", caption: "指标召回", kind: "tool", toolName: "recall_metric", x: 430, y: 368, w: 178 },
  { step: "召回字段取值", label: "recall_value", caption: "取值召回", kind: "tool", toolName: "recall_value", x: 650, y: 368, w: 178 },
  { step: "合并召回信息", x: 430, y: 480, w: 176 },
  { step: "过滤查询上下文", x: 430, y: 584, w: 176 },
  { step: "需要澄清", x: 775, y: 584, w: 140 },
  { step: "添加额外上下文", x: 430, y: 688, w: 176 },
  { step: "生成SQL", x: 430, y: 792 },
  { step: "安全检查SQL", x: 430, y: 896, w: 176 },
  { step: "查询终止", x: 210, y: 988 },
  { step: "校验SQL", x: 430, y: 988 },
  { step: "校正SQL", x: 650, y: 988 },
  { step: "评估SQL答案", x: 430, y: 1092, w: 176 },
  { step: "执行SQL", x: 430, y: 1196 },
];

const connectors = [
  "M430 48 L430 86",
  "M342 28 L48 28 L48 1008 L132 1008",
  "M518 112 L775 112 L775 578",
  "M430 132 L430 178",
  "M430 224 L430 270",
  "M430 316 L430 340 L210 340 L210 362",
  "M430 316 L430 362",
  "M430 316 L430 340 L650 340 L650 362",
  "M210 414 L210 442 L430 442 L430 474",
  "M430 414 L430 474",
  "M650 414 L650 442 L430 442 L430 474",
  "M430 520 L430 578",
  "M430 624 L430 682",
  "M430 734 L430 786",
  "M430 838 L430 890",
  "M342 916 L210 916 L210 982",
  "M430 938 L430 982",
  "M508 1008 L572 1008",
  "M430 1030 L430 1086",
  "M650 988 L650 916 L524 916",
  "M430 1134 L430 1190",
  "M518 1112 L650 1112 L650 1034",
  "M518 1112 L775 1112 L775 630",
  "M342 1112 L210 1112 L210 1034",
];

const branchLabels: BranchLabel[] = [
  { text: "不安全", x: 195, y: 20 },
  { text: "需澄清", x: 646, y: 104 },
  { text: "安全未通过", x: 276, y: 908 },
  { text: "未通过", x: 540, y: 1000 },
  { text: "校正后复检", x: 587, y: 908 },
  { text: "语义校正", x: 584, y: 1104 },
  { text: "需澄清", x: 735, y: 880 },
  { text: "评估失败", x: 276, y: 1104 },
];

function getStatusMap(steps: StepState[]) {
  return steps.reduce<Record<string, StepState>>((map, item) => {
    map[item.step] = item;
    return map;
  }, {});
}

function statusFor(step: string, map: Record<string, StepState>): FlowStatus {
  return map[step]?.status ?? "pending";
}

function groupTracesByStep(traces: TraceState[] = []) {
  return traces.reduce<Record<string, TraceState[]>>((map, trace) => {
    map[trace.step] = [...(map[trace.step] ?? []), trace];
    return map;
  }, {});
}

function NodeIcon({ status }: { status: FlowStatus }) {
  if (status === "running") {
    return <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />;
  }

  if (status === "success") {
    return <Check className="h-3.5 w-3.5" aria-hidden="true" />;
  }

  if (status === "error") {
    return <X className="h-3.5 w-3.5" aria-hidden="true" />;
  }

  return <Circle className="h-3.5 w-3.5" aria-hidden="true" />;
}

function FlowNodeCard({
  node,
  status,
  traceCount,
  onOpen,
}: {
  node: FlowNode;
  status: FlowStatus;
  traceCount: number;
  onOpen: () => void;
}) {
  const width = node.w ?? 156;
  const hasTrace = traceCount > 0;
  const displayName = node.displayName ?? node.step;
  const displayLabel = node.label ?? displayName;
  const stepTitle = node.toolName ? `${displayName}（${node.toolName}）` : displayName;
  const title = hasTrace
    ? `查看 ${stepTitle} 的执行轨迹`
    : `${stepTitle} 暂无执行轨迹`;

  return (
    <div
      className="absolute -translate-x-1/2"
      style={{ left: node.x, top: node.y, width }}
    >
      <button
        type="button"
        disabled={!hasTrace}
        onClick={onOpen}
        title={title}
        className={cn(
          "group relative flex w-full items-center gap-2 rounded-2xl border px-3 text-left text-sm font-semibold shadow-sm transition-all duration-150 focus:outline-none",
          node.caption ? "h-12" : "h-10",
          status === "pending" && "border-slate-200 bg-white text-slate-400",
          status === "stopped" && "border-slate-300 bg-slate-100 text-slate-500",
          status === "running" && "border-amber-200 bg-amber-50 text-amber-800",
          status === "success" && "border-emerald-200 bg-emerald-50 text-emerald-800",
          status === "error" && "border-rose-200 bg-rose-50 text-rose-600",
          hasTrace && "cursor-pointer hover:-translate-y-0.5 hover:border-sky-400 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:border-sky-400 focus:ring-4 focus:ring-sky-100",
          !hasTrace && "cursor-default",
        )}
      >
        <span
          className={cn(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full",
            status === "pending" && "bg-slate-100 text-slate-400",
            status === "stopped" && "bg-slate-200 text-slate-500",
            status === "running" && "bg-amber-100 text-amber-700",
            status === "success" && "bg-emerald-100 text-emerald-700",
            status === "error" && "bg-rose-100 text-rose-600",
          )}
        >
          <NodeIcon status={status} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate">{displayLabel}</span>
          {node.caption && (
            <span className="mt-0.5 block truncate text-[11px] font-medium opacity-70">
              {node.caption}
            </span>
          )}
        </span>
        {hasTrace && (
          <span className="absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-sky-400 px-1 text-[11px] font-semibold text-white shadow-sm ring-2 ring-white transition group-hover:bg-sky-500">
            {traceCount}
          </span>
        )}
      </button>
    </div>
  );
}

function TraceDialog({
  step,
  traces,
  onClose,
}: {
  step: string;
  traces: TraceState[];
  onClose: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/25"
        aria-label="关闭执行轨迹弹窗"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${step}执行轨迹`}
        className="relative z-10 flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <div className="text-sm font-semibold text-slate-900">{step}</div>
            <div className="mt-1 text-xs text-slate-400">执行轨迹结果</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-full text-sky-500 transition-all duration-150 hover:-translate-y-0.5 hover:bg-sky-50 hover:text-sky-700 hover:shadow-md hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100"
            title="关闭"
            aria-label="关闭"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </header>
        <div className="overflow-y-auto bg-slate-50/60 p-5">
          <TraceDetailContent traces={traces} />
        </div>
      </div>
    </div>
  );
}

export function StepRail({
  steps = [],
  traces = [],
}: {
  steps?: StepState[];
  traces?: TraceState[];
}) {
  const statusMap = getStatusMap(steps);
  const tracesByStep = useMemo(() => groupTracesByStep(traces), [traces]);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const selectedTraces = selectedStep ? tracesByStep[selectedStep] ?? [] : [];

  if (steps.length === 0) return null;

  return (
    <section className="mt-4 rounded-3xl border border-slate-200 bg-slate-50/70 px-3 py-4">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div className="text-sm font-semibold text-slate-900">执行流程</div>
      </div>

      <div className="overflow-x-hidden">
        <div className="relative mx-auto h-[1252px] w-[900px]">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 900 1252"
            fill="none"
            aria-hidden="true"
          >
            <defs>
              <marker
                id="flow-arrow"
                markerHeight="8"
                markerWidth="8"
                orient="auto"
                refX="6"
                refY="4"
              >
                <path d="M0 0 L8 4 L0 8 Z" fill="rgba(100, 116, 139, 0.72)" />
              </marker>
            </defs>
            {connectors.map((path) => (
              <path
                key={path}
                d={path}
                stroke="rgba(100, 116, 139, 0.62)"
                strokeWidth="1.5"
                markerEnd="url(#flow-arrow)"
              />
            ))}
            {branchLabels.map((label) => (
              <text
                key={label.text}
                x={label.x}
                y={label.y}
                fill="rgba(71, 85, 105, 0.72)"
                fontSize="13"
                fontWeight="600"
                textAnchor={label.anchor ?? "middle"}
              >
                {label.text}
              </text>
            ))}
          </svg>

          {nodes.map((node) => (
            <FlowNodeCard
              key={node.step}
              node={node}
              status={statusFor(node.step, statusMap)}
              traceCount={tracesByStep[node.step]?.length ?? 0}
              onOpen={() => setSelectedStep(node.step)}
            />
          ))}
        </div>
      </div>

      {selectedStep && (
        <TraceDialog
          step={selectedStep}
          traces={selectedTraces}
          onClose={() => setSelectedStep(null)}
        />
      )}
    </section>
  );
}
