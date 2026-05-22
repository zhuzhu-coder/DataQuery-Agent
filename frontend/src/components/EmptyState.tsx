/**
 * 首页空状态组件
 * 展示产品入口信息和可点击的示例问数问题
 */
import type { ReactNode } from "react";

type EmptyStateProps = {
  examples: string[];
  children?: ReactNode;
  onUseExample: (example: string) => void;
};

export function EmptyState({ examples, children, onUseExample }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col items-center justify-center px-4 py-12 sm:px-6">
      <h1 className="mb-8 text-center text-2xl font-semibold leading-tight text-slate-900 sm:text-3xl">
        今天想查询什么数据？
      </h1>

      <div className="flex w-full max-w-5xl flex-wrap justify-center gap-3">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onUseExample(example)}
            className="max-w-full rounded-2xl border border-slate-200 bg-white px-5 py-3 text-left text-[15px] leading-6 text-slate-800 shadow-sm transition-all duration-150 hover:-translate-y-0.5 hover:border-sky-300 hover:bg-sky-50 hover:text-sky-800 hover:shadow-lg hover:shadow-sky-100 focus:-translate-y-0.5 focus:outline-none focus:ring-4 focus:ring-sky-100 focus:ring-offset-2 sm:text-base"
          >
            {example}
          </button>
        ))}
      </div>

      {children && <div className="mt-7 w-full max-w-3xl">{children}</div>}
    </div>
  );
}
