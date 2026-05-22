/**
 * 聊天消息气泡组件
 * 组合展示用户问题、智能体回复、执行流程和结果表格
 */
import { Copy } from "lucide-react";
import { ResultTable } from "./ResultTable";
import { StepRail } from "./StepRail";
import { cn, formatTime, toClipboardText } from "../lib/format";
import type { ChatMessage } from "../types/agent";

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isProcessMessage = message.kind === "process";
  const shouldShowContent = isUser || !isProcessMessage || (!message.steps?.length && message.result === undefined);

  const copy = async () => {
    const text = message.result ? toClipboardText(message.result) : message.content;
    await navigator.clipboard.writeText(text);
  };

  return (
    <article className={cn("group flex gap-3", isUser && "justify-end")}>
      <div className={cn("max-w-[920px] flex-1", isUser && "flex max-w-[640px] justify-end")}>
        <div
          className={cn(
            "relative px-5 py-4",
            isUser
              ? "rounded-[26px] bg-slate-100 text-slate-900 shadow-sm ring-1 ring-slate-200"
              : "rounded-[26px] border border-slate-200 bg-white text-slate-900 shadow-sm",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            {shouldShowContent && (
              <p className="whitespace-pre-wrap text-[15px] leading-7">{message.content}</p>
            )}
            {!isUser && message.status !== "streaming" && (
              <button
                type="button"
                onClick={copy}
                className="ml-auto shrink-0 rounded-full p-1.5 text-sky-500 opacity-0 outline-none transition-all duration-150 hover:-translate-y-0.5 hover:bg-sky-50 hover:text-sky-700 hover:shadow-md hover:shadow-sky-100 focus:-translate-y-0.5 focus:opacity-100 focus:ring-4 focus:ring-sky-100 group-hover:opacity-100"
                title="复制"
                aria-label="复制"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>

          {message.error && (
            <div className="mt-3 rounded-2xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600">
              {message.error}
            </div>
          )}

          {!isUser && <StepRail steps={message.steps} traces={message.traces} />}
          {!isUser && message.result !== undefined && <ResultTable data={message.result} />}

          <div
            className={cn(
              "mt-3 text-xs",
              isUser ? "text-slate-500" : "text-slate-400",
            )}
          >
            {formatTime(message.createdAt)}
          </div>
        </div>
      </div>
    </article>
  );
}
