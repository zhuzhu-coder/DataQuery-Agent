/**
 * Agent 可解释执行轨迹
 * 展示后端 trace SSE 事件，帮助用户看到每个关键节点的产物摘要
 */
import type { TraceItem, TraceState } from "../types/agent";

const VISIBLE_ITEM_LIMIT = 4;
const ITEM_TOTAL_KEYS = ["keyword_count", "column_count", "metric_count", "value_count"];

function isSqlLike(item: TraceItem) {
  const detail = item.detail?.trim().toLowerCase() ?? "";
  return item.label.toLowerCase() === "sql" || detail.startsWith("select");
}

function trimTrailingPeriod(value: string) {
  return value.replace(/[。.]$/, "");
}

function traceItemTotal(trace: TraceState) {
  const metadata = trace.metadata ?? {};
  for (const key of ITEM_TOTAL_KEYS) {
    const value = metadata[key];
    if (typeof value === "number") return value;
  }
  return trace.items?.length ?? 0;
}

function visibleTraceItems(trace: TraceState) {
  return (trace.items ?? []).slice(0, VISIBLE_ITEM_LIMIT);
}

function hiddenItemCount(trace: TraceState) {
  const total = Math.max(traceItemTotal(trace), trace.items?.length ?? 0);
  return Math.max(total - visibleTraceItems(trace).length, 0);
}

function shouldUseInlineItems(items: TraceItem[]) {
  return items.length > 0 && items.every((item) => !item.detail);
}

function InlineTraceItems({ items, hiddenCount }: { items: TraceItem[]; hiddenCount: number }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {items.map((item, itemIndex) => (
        <span
          key={`${item.label}-${itemIndex}`}
          className="max-w-[220px] truncate rounded-full border border-sky-100 bg-sky-50 px-2.5 py-1 text-sm text-sky-700"
        >
          {item.label}
        </span>
      ))}
      {hiddenCount > 0 && (
        <span className="rounded-full border border-sky-100 bg-sky-50 px-2.5 py-1 text-sm text-sky-500">
          ... 还有 {hiddenCount} 项
        </span>
      )}
    </div>
  );
}

function TraceItemRow({ item }: { item: TraceItem }) {
  if (!item.detail) {
    return (
      <li className="flex min-h-9 items-center px-3 py-2 text-sm text-slate-700">
        <span className="truncate">{item.label}</span>
      </li>
    );
  }

  if (isSqlLike(item)) {
    return (
      <li className="px-3 py-2">
        <div className="text-sm font-medium text-slate-800">{item.label}</div>
        <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-sky-100 bg-sky-50 p-3 text-xs leading-5 text-sky-900">
          {item.detail}
        </pre>
      </li>
    );
  }

  return (
    <li className="grid min-h-9 grid-cols-[minmax(140px,0.38fr)_minmax(0,1fr)] items-center gap-3 px-3 py-2">
      <span className="truncate text-sm font-medium text-slate-800">{item.label}</span>
      <span className="truncate text-sm text-slate-500">{trimTrailingPeriod(item.detail)}</span>
    </li>
  );
}

function EllipsisRow({ count }: { count: number }) {
  return (
    <li className="grid min-h-9 grid-cols-[minmax(140px,0.38fr)_minmax(0,1fr)] items-center gap-3 px-3 py-2 text-sm text-slate-400">
      <span className="font-medium text-sky-500">...</span>
      <span className="truncate text-sky-500">{count > 0 ? `还有 ${count} 项未展示` : "还有更多内容"}</span>
    </li>
  );
}

export function TraceDetailContent({ traces = [] }: { traces?: TraceState[] }) {
  if (traces.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
        该节点暂无执行轨迹
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {traces.map((trace, index) => {
        const items = visibleTraceItems(trace);
        const hiddenCount = hiddenItemCount(trace);
        const useInlineItems = shouldUseInlineItems(items);

        return (
          <section key={`${trace.step}-${trace.updatedAt}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="text-sm font-semibold text-slate-900">{trace.title}</span>
              <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[11px] font-medium text-sky-600">
                {trace.step}
              </span>
            </div>
            {trace.summary && (
              <p className="mt-1 text-sm leading-6 text-slate-500">
                {trimTrailingPeriod(trace.summary)}
              </p>
            )}

            {useInlineItems && <InlineTraceItems items={items} hiddenCount={hiddenCount} />}

            {!useInlineItems && (items.length > 0 || hiddenCount > 0) && (
              <ul className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
                {items.map((item, itemIndex) => (
                  <TraceItemRow key={`${item.label}-${itemIndex}`} item={item} />
                ))}
                {hiddenCount > 0 && <EllipsisRow count={hiddenCount} />}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

export function TraceTimeline({ traces = [] }: { traces?: TraceState[] }) {
  if (traces.length === 0) return null;

  return (
    <section className="mt-4 border-t border-slate-200 pt-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-slate-900">执行轨迹</div>
        <div className="text-xs text-slate-400">{traces.length} 条</div>
      </div>

      <ol className="space-y-3">
        {traces.map((trace, index) => {
          const items = visibleTraceItems(trace);
          const hiddenCount = hiddenItemCount(trace);
          const useInlineItems = shouldUseInlineItems(items);

          return (
            <li key={`${trace.step}-${trace.updatedAt}-${index}`} className="relative pl-5">
        <span className="absolute left-0 top-2 h-2 w-2 rounded-full bg-sky-300" />
              {index < traces.length - 1 && (
              <span className="absolute bottom-[-14px] left-[3px] top-5 w-px bg-sky-100" />
              )}

              <details open={index >= traces.length - 2} className="group">
                <summary className="cursor-pointer list-none">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm font-semibold text-slate-800">{trace.title}</span>
                    <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[11px] font-medium text-sky-600">
                      {trace.step}
                    </span>
                  </div>
                  {trace.summary && (
                    <p className="mt-1 text-sm leading-6 text-slate-500">
                      {trimTrailingPeriod(trace.summary)}
                    </p>
                  )}
                </summary>

                {useInlineItems && <InlineTraceItems items={items} hiddenCount={hiddenCount} />}

                {!useInlineItems && (items.length > 0 || hiddenCount > 0) && (
                  <ul className="mt-2 overflow-hidden rounded-xl border border-slate-200 bg-white divide-y divide-slate-100">
                    {items.map((item, itemIndex) => (
                      <TraceItemRow key={`${item.label}-${itemIndex}`} item={item} />
                    ))}
                    {hiddenCount > 0 && <EllipsisRow count={hiddenCount} />}
                  </ul>
                )}
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
