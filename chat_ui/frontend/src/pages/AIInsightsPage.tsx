import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import type { Skill } from "../types/chat";
import { useChatContext } from "../context/ChatContext";
import { MessageList } from "../components/MessageList";
import { ChatInput } from "../components/ChatInput";
import { SkillBar } from "../components/SkillBar";

export function AIInsightsPage() {
  const { messages, isLoading, error, progress, sendMessage, clearChat } = useChatContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const autoAnalyzed = useRef(false);

  // Auto-analyze if ?event=X is present
  useEffect(() => {
    const eventId = searchParams.get("event");
    if (eventId && !autoAnalyzed.current && messages.length === 0) {
      autoAnalyzed.current = true;
      sendMessage(`Analyze event ${eventId} in detail`);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, messages.length, sendMessage, setSearchParams]);

  const handleSkillClick = (skill: Skill) => {
    sendMessage(`[${skill.label}] ${skill.description}`);
  };

  return (
    <div className="ai-insights-page">
      <div className="page-header">
        <div>
          <h1>AI Insights</h1>
          <p className="page-subtitle">Chat with your K8s cluster assistant</p>
        </div>
        <button className="refresh-btn" onClick={clearChat}>
          Clear Chat
        </button>
      </div>

      <div className="chat-wrapper">
        <SkillBar onSkillClick={handleSkillClick} disabled={isLoading} />
        <MessageList messages={messages} isLoading={isLoading} progress={progress} />
        {error && <div className="error-bar">{error}</div>}
        <ChatInput onSend={sendMessage} disabled={isLoading} />
      </div>
    </div>
  );
}
