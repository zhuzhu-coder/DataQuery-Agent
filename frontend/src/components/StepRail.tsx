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
  { step: "意图安全检查", x: 430, y: 20, w: 176 },
  { step: "普通回答", x: 170, y: 112 },
  { step: "抽取关键词", x: 430, y: 112 },
  { step: "召回字段信息", x: 170, y: 204 },
  { step: "召回指标信息", x: 430, y: 204 },
  { step: "召回字段取值", x: 690, y: 204 },
  { step: "合并召回信息", x: 430, y: 306 },
  { step: "过滤指标信息", x: 310, y: 410 },
  { step: "过滤表信息", x: 550, y: 410 },
  { step: "添加额外上下文", x: 430, y: 514, w: 176 },
  { step: "生成SQL", x: 430, y: 618 },
  { step: "安全检查SQL", x: 430, y: 722, w: 176 },
  { step: "查询终止", x: 160, y: 826 },
  { step: "校验SQL", x: 430, y: 826 },
  { step: "校正SQL", x: 700, y: 826 },
  { step: "执行SQL", x: 430, y: 930 },
];

const connectors = [
  "M342 40 L30 40 L30 846 L82 846",
  "M430 60 L430 84 L170 84 L170 106",
  "M430 60 L430 106",
  "M430 152 L430 176 L170 176 L170 198",
  "M430 152 L430 198",
  "M430 152 L430 176 L690 176 L690 198",
  "M170 244 L170 270 L430 270 L430 300",
  "M430 244 L430 300",
  "M690 244 L690 270 L430 270 L430 300",
  "M430 346 L430 374 L310 374 L310 404",
  "M430 346 L430 374 L550 374 L550 404",
  "M310 450 L310 478 L430 478 L430 508",
  "M550 450 L550 478 L430 478 L430 508",
  "M430 554 L430 612",
  "M430 658 L430 716",
  "M336 742 L160 742 L160 820",
  "M430 762 L430 820",
  "M352 846 L244 846",
  "M430 866 L430 924",
  "M508 846 L616 846",
  "M700 826 L700 742 L524 742",
];

const branchLabels: BranchLabel[] = [
  { text: "意图不安全", x: 186, y: 32 },
  { text: "普通问题", x: 300, y: 76 },
  { text: "数据查询", x: 450, y: 96, anchor: "start" },
  { text: "安全未通过", x: 248, y: 734 },
  { text: "安全通过", x: 450, y: 796, anchor: "start" },
  { text: "复检仍失败", x: 298, y: 838 },
  { text: "校验未通过", x: 562, y: 838 },
  { text: "校验通过", x: 450, y: 900, anchor: "start" },
  { text: "修正后复检", x: 612, y: 734 },
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

  return (
    <div
      className="absolute -translate-x-1/2"
      style={{ left: node.x, top: node.y, width }}
    >
      <button
        type="button"
        disabled={!hasTrace}
        onClick={onOpen}
        title={hasTrace ? `查看 ${node.step} 的执行轨迹` : `${node.step} 暂无执行轨迹`}
        className={cn(
          "group relative flex h-10 w-full items-center gap-2 rounded-2xl border px-3 text-left text-sm font-semibold shadow-sm transition-all duration-150 focus:outline-none",
          status === "pending" && "border-slate-200 bg-white text-slate-400",
          status === "stopped" && "border-slate-200 bg-slate-50 text-slate-500",
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
            status === "stopped" && "bg-slate-100 text-slate-500",
            status === "running" && "bg-amber-100 text-amber-700",
            status === "success" && "bg-emerald-100 text-emerald-700",
            status === "error" && "bg-rose-100 text-rose-600",
          )}
        >
          <NodeIcon status={status} />
        </span>
        <span className="min-w-0 flex-1 truncate">{node.step}</span>
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

      <div className="overflow-x-auto">
        <div className="relative mx-auto h-[986px] w-[860px]">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 860 986"
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
