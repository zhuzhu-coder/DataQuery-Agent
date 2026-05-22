/**
 * 聊天输入区组件
 * 处理问题输入、发送和停止当前流式请求
 */
import { ArrowUp, Square } from "lucide-react";
import { FormEvent, KeyboardEvent, useRef } from "react";
import { cn } from "../lib/format";

type ComposerProps = {
    value: string;
    disabled: boolean;
    isStreaming: boolean;
    variant?: "dock" | "inline";
    onChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
};

export function Composer({
    value,
    disabled,
    isStreaming,
    variant = "dock",
    onChange,
    onSubmit,
    onStop,
}: ComposerProps) {
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!disabled) onSubmit();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) onSubmit();
        }
    };

    return (
        <form
            onSubmit={submit}
            className={cn(
                variant === "dock" && "border-t border-sky-50 bg-white px-4 py-4",
                variant === "inline" && "w-full bg-transparent px-0 py-0",
            )}
        >
            <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-[28px] border border-slate-200 bg-white p-2 shadow-chat">
                <textarea
                    ref={textareaRef}
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={onKeyDown}
                    rows={1}
                    placeholder="问一个电商数据问题..."
                    className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-4 py-3 text-[15px] leading-6 text-slate-900 outline-none placeholder:text-slate-400"
                />
                <button
                    type={isStreaming ? "button" : "submit"}
                    onClick={isStreaming ? onStop : undefined}
                    disabled={!isStreaming && disabled}
                    className={cn(
                        "grid h-11 w-11 shrink-0 place-items-center rounded-full text-white transition-all duration-150 hover:-translate-y-0.5 hover:shadow-lg focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 focus:ring-offset-2 disabled:hover:translate-y-0 disabled:hover:shadow-none",
                        isStreaming
                            ? "bg-rose-500 hover:bg-rose-600 hover:shadow-rose-100 focus:ring-rose-100"
                            : "bg-sky-400 hover:bg-sky-500 hover:shadow-sky-100 disabled:cursor-not-allowed disabled:bg-sky-100",
                    )}
                    title={isStreaming ? "停止" : "发送"}
                    aria-label={isStreaming ? "停止" : "发送"}
                >
                    {isStreaming ? (
                        <Square
                            className="h-4 w-4 fill-current"
                            aria-hidden="true"
                        />
                    ) : (
                        <ArrowUp className="h-5 w-5" aria-hidden="true" />
                    )}
                </button>
            </div>
        </form>
    );
}
