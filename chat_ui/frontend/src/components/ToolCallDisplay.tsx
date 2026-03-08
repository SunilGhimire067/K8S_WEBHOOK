import { useState } from "react";
import type { ToolCall } from "../types/chat";

interface Props {
  toolCall: ToolCall;
  result?: string;
}

export function ToolCallDisplay({ toolCall, result }: Props) {
  const [expanded, setExpanded] = useState(false);

  let parsedArgs: Record<string, unknown> = {};
  try {
    parsedArgs = JSON.parse(toolCall.function.arguments);
  } catch {
    /* ignore */
  }

  return (
    <div className="tool-call-card">
      <div
        className="tool-call-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="tool-icon">&#9881;</span>
        <span className="tool-name">{toolCall.function.name}</span>
        <span className="tool-toggle">{expanded ? "\u25B2" : "\u25BC"}</span>
      </div>

      {expanded && (
        <div className="tool-call-body">
          <div className="tool-args">
            <strong>Arguments:</strong>
            <pre>{JSON.stringify(parsedArgs, null, 2)}</pre>
          </div>
          {result && (
            <div className="tool-result">
              <strong>Result:</strong>
              <pre>{result}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
