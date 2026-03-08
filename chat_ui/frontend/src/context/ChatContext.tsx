import { createContext, useContext, useState, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import type { ChatMessage } from "../types/chat";
import { sendChatStream } from "../api/chatApi";
import type { StreamEvent } from "../api/chatApi";

export interface ProgressInfo {
  message: string;
  level: string;
  tool?: string;
  current?: number;
  total?: number;
}

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  progress: ProgressInfo | null;
  sendMessage: (content: string) => void;
  clearChat: () => void;
}

const ChatContext = createContext<ChatState | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressInfo | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  const sendMessage = useCallback((content: string) => {
    const userMessage: ChatMessage = { role: "user", content };
    const updatedMessages = [...messagesRef.current, userMessage];
    setMessages(updatedMessages);
    setIsLoading(true);
    setError(null);
    setProgress(null);

    let isStreaming = false;

    sendChatStream(updatedMessages, (event: StreamEvent) => {
      switch (event.type) {
        case "progress":
          setProgress((prev) => {
            if (event.level === "progress") {
              return {
                message: prev?.message || "",
                level: prev?.level || "info",
                tool: prev?.tool,
                current: event.current,
                total: event.total,
              };
            }
            return {
              message: event.message || "",
              level: event.level || "info",
              tool: prev?.tool,
              current: prev?.current,
              total: prev?.total,
            };
          });
          break;
        case "tool_start":
          setProgress({
            message: `Running ${event.tool}...`,
            level: "info",
            tool: event.tool,
            current: 0,
            total: 0,
          });
          break;
        case "token":
          // Set flag synchronously so subsequent tokens don't create duplicates
          isStreaming = true;
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && !last.tool_calls) {
              // Append to existing streaming message
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...last,
                content: last.content + (event.content || ""),
              };
              return updated;
            }
            // First token — create new assistant message
            return [...prev, { role: "assistant", content: event.content || "" }];
          });
          setProgress(null);
          break;
        case "message":
          if (event.data) {
            if (event.data.role === "assistant" && isStreaming) {
              // Replace streaming message with final complete message
              isStreaming = false;
              setMessages((prev) => {
                const updated = [...prev];
                for (let i = updated.length - 1; i >= 0; i--) {
                  if (updated[i].role === "assistant" && !updated[i].tool_calls) {
                    updated[i] = event.data!;
                    return updated;
                  }
                }
                return [...prev, event.data!];
              });
            } else {
              isStreaming = false;
              setMessages((prev) => [...prev, event.data!]);
            }
          }
          if (event.data?.role === "tool") {
            setProgress((prev) => prev ? { ...prev, current: undefined, total: undefined } : null);
          }
          break;
        case "done":
          break;
      }
    })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unknown error");
      })
      .finally(() => {
        setIsLoading(false);
        setProgress(null);
      });
  }, []);

  const clearChat = useCallback(() => {
    setMessages([]);
    setError(null);
    setProgress(null);
  }, []);

  return (
    <ChatContext.Provider
      value={{ messages, isLoading, error, progress, sendMessage, clearChat }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChatContext must be used inside ChatProvider");
  return ctx;
}
