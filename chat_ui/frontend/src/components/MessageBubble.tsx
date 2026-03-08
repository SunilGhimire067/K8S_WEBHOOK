import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../types/chat";
import { ToolCallDisplay } from "./ToolCallDisplay";

interface Props {
  message: ChatMessage;
  toolResults: Map<string, string>;
}

export function MessageBubble({ message, toolResults }: Props) {
  if (message.role === "tool") {
    return null; // tool results are shown inline in ToolCallDisplay
  }

  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="message-role">
        {message.role === "user" ? "You" : "Assistant"}
      </div>

      {message.content && (
        <div className="message-content">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                const codeString = String(children).replace(/\n$/, "");
                if (match) {
                  return (
                    <pre className="code-block">
                      <code className={className}>{codeString}</code>
                    </pre>
                  );
                }
                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {message.tool_calls?.map((tc) => (
        <ToolCallDisplay
          key={tc.id}
          toolCall={tc}
          result={toolResults.get(tc.id)}
        />
      ))}
    </div>
  );
}
