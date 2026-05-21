/**
 * 智能体执行流程图组件
 * 按 LangGraph 节点拓扑展示各步骤状态
 */
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { cn } from "../lib/format";
import type { StepState, StepStatus } from "../types/agent";

type FlowStatus = StepStatus | "pending";

type FlowNode = {
  step: string;
  x: number;
  y: number;
  w?: number;
};

const nodes: FlowNode[] = [
  { step: "抽取关键词", x: 430, y: 20 },
  { step: "召回字段信息", x: 170, y: 112 },
  { step: "召回指标信息", x: 430, y: 112 },
  { step: "召回字段取值", x: 690, y: 112 },
  { step: "合并召回信息", x: 430, y: 214 },
  { step: "过滤指标信息", x: 310, y: 318 },
  { step: "过滤表信息", x: 550, y: 318 },
  { step: "添加额外上下文", x: 430, y: 422, w: 176 },
  { step: "生成SQL", x: 430, y: 526 },
  { step: "安全检查SQL", x: 430, y: 630, w: 176 },
  { step: "查询终止", x: 130, y: 734 },
  { step: "校验SQL", x: 430, y: 734 },
  { step: "校正SQL", x: 700, y: 734 },
  { step: "执行SQL", x: 430, y: 838 },
];

const connectors = [
  "M430 60 L430 84 L170 84 L170 106",
  "M430 60 L430 106",
  "M430 60 L430 84 L690 84 L690 106",
  "M170 152 L170 178 L430 178 L430 208",
  "M430 152 L430 208",
  "M690 152 L690 178 L430 178 L430 208",
  "M430 254 L430 282 L310 282 L310 312",
  "M430 254 L430 282 L550 282 L550 312",
  "M310 358 L310 386 L430 386 L430 416",
  "M550 358 L550 386 L430 386 L430 416",
  "M430 462 L430 520",
  "M430 566 L430 624",
  "M342 650 L130 650 L130 728",
  "M430 670 L430 728",
  "M352 754 L214 754",
  "M430 774 L430 832",
  "M508 754 L616 754",
  "M700 734 L700 650 L524 650",
];

const branchLabels = [
  { text: "安全未通过", x: 203, y: 642 },
  { text: "安全通过", x: 450, y: 704 },
  { text: "复检仍失败", x: 250, y: 746 },
  { text: "校验未通过", x: 529, y: 746 },
  { text: "校验通过", x: 450, y: 808 },
  { text: "修正后复检", x: 580, y: 642 },
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

function FlowNodeCard({ node, status }: { node: FlowNode; status: FlowStatus }) {
  const width = node.w ?? 156;

  return (
    <div
      className="absolute -translate-x-1/2"
      style={{ left: node.x, top: node.y, width }}
    >
      <div
        className={cn(
          "flex h-10 items-center gap-2 rounded-2xl border px-3 text-sm font-semibold shadow-sm transition",
          status === "pending" && "border-slate-200 bg-white text-slate-400",
          status === "stopped" && "border-slate-200 bg-slate-50 text-slate-500",
          status === "running" && "border-amber-200 bg-amber-50 text-amber-800",
          status === "success" && "border-emerald-200 bg-emerald-50 text-emerald-800",
          status === "error" && "border-rose-200 bg-rose-50 text-rose-600",
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
      </div>
    </div>
  );
}

export function StepRail({ steps = [] }: { steps?: StepState[] }) {
  if (steps.length === 0) return null;

  const statusMap = getStatusMap(steps);

  return (
    <section className="mt-4 rounded-3xl border border-slate-200 bg-slate-50/70 px-3 py-4">
      <div className="mb-3 flex items-center justify-between gap-3 px-1">
        <div className="text-sm font-semibold text-slate-900">执行流程</div>
        <div className="text-xs text-slate-400">LangGraph</div>
      </div>

      <div className="overflow-x-auto">
        <div className="relative mx-auto h-[894px] w-[860px]">
          <svg
            className="pointer-events-none absolute inset-0 h-full w-full"
            viewBox="0 0 860 894"
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
            />
          ))}
        </div>
      </div>
    </section>
  );
}
