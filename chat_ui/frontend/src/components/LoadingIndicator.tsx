import type { ProgressInfo } from "../context/ChatContext";

interface Props {
  progress?: ProgressInfo | null;
}

export function LoadingIndicator({ progress }: Props) {
  const displayMessage = progress?.message || "Thinking...";
  const levelClass = progress?.level === "warning" ? "progress-warning"
    : progress?.level === "error" ? "progress-error"
    : "";

  const hasBar = progress?.total != null && progress.total > 0;
  const percent = hasBar ? Math.round(((progress!.current || 0) / progress!.total!) * 100) : 0;

  return (
    <div className="loading-indicator">
      <div className="loading-dots">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </div>
      <div className="loading-detail">
        <span className={`loading-text ${levelClass}`}>{displayMessage}</span>
        {progress?.tool && (
          <span className="loading-tool">{progress.tool}</span>
        )}
        {hasBar && (
          <div className="progress-bar-wrapper">
            <div className="progress-bar-container">
              <div
                className="progress-bar-fill"
                style={{ width: `${percent}%` }}
              />
            </div>
            <span className="progress-bar-label">{progress!.current}/{progress!.total}</span>
          </div>
        )}
      </div>
    </div>
  );
}
