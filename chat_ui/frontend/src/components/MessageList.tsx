import { useEffect, useRef, useMemo } from "react";
import type { ChatMessage } from "../types/chat";
import type { ProgressInfo } from "../context/ChatContext";
import { MessageBubble } from "./MessageBubble";
import { LoadingIndicator } from "./LoadingIndicator";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  progress?: ProgressInfo | null;
}

export function MessageList({ messages, isLoading, progress }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, progress]);

  // Build a map of tool_call_id -> result content for inline display
  const toolResults = useMemo(() => {
    const map = new Map<string, string>();
    for (const msg of messages) {
      if (msg.role === "tool" && msg.tool_call_id) {
        map.set(msg.tool_call_id, msg.content);
      }
    }
    return map;
  }, [messages]);

  return (
    <div className="message-list">
      {messages.length === 0 && !isLoading && (
        <div className="empty-state">
          <h2>K8s Event Analyzer</h2>
          <p>Ask me anything about your Kubernetes cluster.</p>
          <p className="empty-hint">Use the skill buttons above or type a question below.</p>
        </div>
      )}

      {messages.map((msg, idx) => (
        <MessageBubble key={idx} message={msg} toolResults={toolResults} />
      ))}

      {isLoading && <LoadingIndicator progress={progress} />}
      <div ref={bottomRef} />
    </div>
  );
}
