/**
 * 智能体类型定义
 * 定义智能问数助手前端使用的 SSE 事件、流程步骤和聊天消息类型
 */
export type ProgressStatus = "running" | "success" | "error";
export type StepStatus = ProgressStatus | "stopped";

export type ProgressEvent = {
  type: "progress";
  step: string;
  status: ProgressStatus;
};

export type ResultEvent = {
  type: "result";
  data: unknown;
};

export type ErrorEvent = {
  type: "error";
  message: string;
};

export type TraceItem = {
  label: string;
  detail?: string;
};

export type TraceEvent = {
  type: "trace";
  step: string;
  title: string;
  summary?: string;
  items?: TraceItem[];
  metadata?: Record<string, unknown>;
};

export type AgentEvent = ProgressEvent | ResultEvent | ErrorEvent | TraceEvent;

export type StepState = {
  step: string;
  status: StepStatus;
  updatedAt: number;
};

export type TraceState = TraceEvent & {
  updatedAt: number;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: number;
  status?: "streaming" | "done" | "error";
  steps?: StepState[];
  traces?: TraceState[];
  result?: unknown;
  error?: string;
};
