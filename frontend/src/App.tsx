/**
 * 前端应用主组件
 * 负责聊天会话状态、SSE 事件消费和整体页面布局
 */
import {
  Activity,
  Eraser,
  History,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Server,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { MessageBubble } from "./components/MessageBubble";
import { streamQuery } from "./lib/agentApi";
import { cn, summarizeResult } from "./lib/format";
import type { AgentEvent, ChatMessage, StepState, TraceState } from "./types/agent";

const examples = [
  "统计 2026 年第一季度各大区的 GMV，并按 GMV 从高到低排序",
  "统计 2026 年 3 月各商品品类的销量和销售额",
  "查询华东地区 2026 年第一季度销售额最高的前 5 个商品",
  "按会员等级统计 2026 年第一季度的订单数和销售额",
];

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "Vite /api proxy";

function makeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
  const next = steps.filter((item) => item.step !== event.step);
  next.push({
    step: event.step,
    status: event.status,
    updatedAt: Date.now(),
  });
  return next;
}

function stopRunningSteps(steps: StepState[] = []) {
  return steps.map((step) =>
    step.status === "running" ? { ...step, status: "stopped" as const, updatedAt: Date.now() } : step,
  );
}

function upsertStoppedStep(steps: StepState[] = [], step: string) {
  const next = steps.filter((item) => item.step !== step);
  next.push({
    step,
    status: "stopped",
    updatedAt: Date.now(),
  });
  return next;
}

function markQueryStopped(steps: StepState[] = []) {
  return upsertStoppedStep(stopRunningSteps(steps), "查询终止");
}

function markQueryFailed(steps: StepState[] = []) {
  return upsertStep(stopRunningSteps(steps), {
    type: "progress",
    step: "查询终止",
    status: "error",
  });
}

function appendTrace(traces: TraceState[] = [], event: Extract<AgentEvent, { type: "trace" }>) {
  return [...traces, { ...event, updatedAt: Date.now() }];
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [activeController, setActiveController] = useState<AbortController | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const isStreaming = Boolean(activeController);
  const canSubmit = draft.trim().length > 0 && !isStreaming;

  const completedCount = useMemo(
    () => messages.filter((message) => message.role === "assistant" && message.status === "done").length,
    [messages],
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const startQuery = async (rawQuery = draft) => {
    const query = rawQuery.trim();
    if (!query || isStreaming) return;

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      content: query,
      createdAt: Date.now(),
    };

    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      kind: "process",
      content: "正在连接智能问数助手...",
      createdAt: Date.now(),
      status: "streaming",
      steps: [],
      traces: [],
    };

    const controller = new AbortController();
    setActiveController(controller);
    setDraft("");
    setMessages((current) => [...current, userMessage, assistantMessage]);

    const onEvent = (event: AgentEvent) => {
      setMessages((current) => {
        if (event.type === "result") {
          const answerMessage: ChatMessage = {
            id: makeId(),
            role: "assistant",
            kind: "answer",
            content: summarizeResult(event.data),
            createdAt: Date.now(),
            status: "done",
          };
          return [
            ...current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    status: "done" as const,
                    content: "",
                    result: event.data,
                  }
                : message,
            ),
            answerMessage,
          ];
        }

        if (event.type === "answer") {
          const answerMessage: ChatMessage = {
            id: makeId(),
            role: "assistant",
            kind: "answer",
            content: event.content,
            createdAt: Date.now(),
            status: "done",
          };
          return [
            ...current.map((message) =>
              message.id === assistantId
                ? {
                    ...message,
                    status: "done" as const,
                    content: "",
                  }
                : message,
            ),
            answerMessage,
          ];
        }

        return current.map((message) => {
          if (message.id !== assistantId) return message;

          if (event.type === "progress") {
            return {
              ...message,
              content: event.status === "running" ? `正在执行：${event.step}` : message.content,
              steps: upsertStep(message.steps, event),
            };
          }

          if (event.type === "trace") {
            return {
              ...message,
              traces: appendTrace(message.traces, event),
            };
          }

          return {
            ...message,
            status: "error",
            content: "这次查询没有成功。",
            error: event.message,
            steps: markQueryFailed(message.steps),
          };
        });
      });
    };

    try {
      await streamQuery(query, { signal: controller.signal, onEvent });
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId && message.status === "streaming"
            ? { ...message, status: "done", content: "流程已结束，后端未返回查询结果。" }
            : message,
        ),
      );
    } catch (error) {
      const isAbort = error instanceof DOMException && error.name === "AbortError";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                status: isAbort ? "done" : "error",
                content: isAbort ? "已停止本次查询。" : "无法连接问数接口。",
                error: isAbort ? undefined : error instanceof Error ? error.message : String(error),
                steps: isAbort ? markQueryStopped(message.steps) : message.steps,
              }
            : message,
        ),
      );
    } finally {
      setActiveController(null);
    }
  };

  const stopQuery = () => {
    activeController?.abort();
  };

  const clearConversation = () => {
    if (isStreaming) return;
    setMessages([]);
    setDraft("");
  };

  return (
    <div className="h-dvh overflow-hidden bg-white text-slate-900">
      <div
        className={cn(
          "grid h-full min-h-0 overflow-hidden transition-[grid-template-columns] duration-200",
          isSidebarOpen ? "lg:grid-cols-[292px_minmax(0,1fr)]" : "lg:grid-cols-[72px_minmax(0,1fr)]",
        )}
      >
        <aside className="hidden min-h-0 border-r border-slate-200 bg-slate-50/95 lg:flex lg:flex-col">
          <div className={cn("h-16 border-b border-slate-200", isSidebarOpen ? "px-5" : "px-3")}>
            <div className={cn("flex h-full items-center", isSidebarOpen ? "justify-between gap-3" : "justify-center")}>
              {isSidebarOpen && (
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold text-sky-600">Data Query Agent</div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setIsSidebarOpen((value) => !value)}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl text-sky-600 transition-all duration-150 hover:-translate-y-0.5 hover:bg-sky-50 hover:text-sky-700 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100"
                title={isSidebarOpen ? "收起边栏" : "展开边栏"}
                aria-label={isSidebarOpen ? "收起边栏" : "展开边栏"}
              >
                {isSidebarOpen ? (
                  <PanelLeftClose className="h-5 w-5" aria-hidden="true" />
                ) : (
                  <PanelLeftOpen className="h-5 w-5" aria-hidden="true" />
                )}
              </button>
            </div>
          </div>

          {!isSidebarOpen ? (
            <div className="flex min-h-0 flex-1 flex-col items-center gap-3 px-3 py-4">
              <button
                type="button"
                onClick={clearConversation}
                disabled={isStreaming}
                className="grid h-11 w-11 place-items-center rounded-2xl border border-sky-200 bg-sky-50 text-sky-600 transition-all duration-150 hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-100 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:translate-y-0 disabled:hover:shadow-none"
                title="新会话"
                aria-label="新会话"
              >
                <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          ) : (
            <>
              <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
                <button
                  type="button"
                  onClick={clearConversation}
                  disabled={isStreaming}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-2xl border border-sky-200 bg-sky-50 text-sm font-semibold text-sky-600 transition-all duration-150 hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-100 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400 disabled:hover:translate-y-0 disabled:hover:shadow-none"
                >
                  <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
                  新会话
                </button>

                <section>
                  <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-[0.14em] text-sky-600">
                    <History className="h-3.5 w-3.5" aria-hidden="true" />
                    样例
                  </div>
                  <div className="space-y-2">
                    {examples.map((example) => (
                      <button
                        key={example}
                        type="button"
                        disabled={isStreaming}
                        onClick={() => startQuery(example)}
                        className="w-full rounded-2xl border border-slate-200 bg-white px-3.5 py-3 text-left text-sm leading-5 text-slate-700 transition-all duration-150 hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-50 hover:text-sky-800 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:translate-y-0 disabled:hover:shadow-none"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </section>
              </div>

              <div className="border-t border-slate-200 p-4">
                <div className="grid gap-2 text-xs text-slate-500">
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex items-center gap-2">
                      <Server className="h-3.5 w-3.5 text-sky-600" aria-hidden="true" />
                      API
                    </span>
                    <span className="truncate font-mono">{API_BASE_URL}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="inline-flex items-center gap-2">
                      <Activity className="h-3.5 w-3.5 text-sky-600" aria-hidden="true" />
                      完成
                    </span>
                    <span>{completedCount}</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </aside>

        <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <header className="flex h-16 shrink-0 items-center justify-end border-b border-slate-200 bg-white/95 px-4 backdrop-blur lg:px-6">
            <button
              type="button"
              onClick={clearConversation}
              disabled={isStreaming}
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-full border border-sky-100 bg-sky-50 px-4 text-sm font-medium text-sky-600 shadow-sm transition-all duration-150 hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-100 hover:text-sky-700 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:translate-y-0 disabled:hover:shadow-none",
              )}
              title="清空"
              aria-label="清空"
            >
              <Eraser className="h-4 w-4" aria-hidden="true" />
              清空
            </button>
          </header>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            {messages.length === 0 ? (
              <EmptyState examples={examples} onUseExample={(example) => setDraft(example)}>
                <Composer
                  value={draft}
                  disabled={!canSubmit}
                  isStreaming={isStreaming}
                  variant="inline"
                  onChange={setDraft}
                  onSubmit={() => startQuery()}
                  onStop={stopQuery}
                />
              </EmptyState>
            ) : (
              <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8 pb-12 sm:px-6 lg:px-8">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
              </div>
            )}
          </div>

          {messages.length > 0 && (
            <Composer
              value={draft}
              disabled={!canSubmit}
              isStreaming={isStreaming}
              variant="dock"
              onChange={setDraft}
              onSubmit={() => startQuery()}
              onStop={stopQuery}
            />
          )}
        </main>
      </div>
    </div>
  );
}
