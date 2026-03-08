import { useEffect, useState } from "react";
import { fetchSettings, updateSettings } from "../api/settingsApi";
import type { LlmSettings } from "../api/settingsApi";

export function SettingsPage() {
  const [form, setForm] = useState<LlmSettings>({
    litellm_base_url: "",
    litellm_model: "",
    litellm_api_key: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showKey, setShowKey] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchSettings();
      setForm(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await updateSettings(form);
      setSuccess(`Updated: ${result.updated.join(", ")}`);
      setTimeout(() => setSuccess(""), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="settings-page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      {error && <div className="page-error">{error}</div>}
      {success && <div className="page-success">{success}</div>}

      {loading ? (
        <div className="page-loading">Loading settings...</div>
      ) : (
        <div className="settings-card">
          <h2>LLM Configuration</h2>
          <p className="settings-description">
            Configure the LiteLLM endpoint used for AI Insights and chat analysis.
          </p>

          <div className="settings-form">
            <label className="settings-label">
              <span>Base URL</span>
              <input
                type="text"
                value={form.litellm_base_url}
                onChange={(e) => setForm({ ...form, litellm_base_url: e.target.value })}
                placeholder="https://your-litellm-proxy.com/v1"
              />
            </label>

            <label className="settings-label">
              <span>Model</span>
              <input
                type="text"
                value={form.litellm_model}
                onChange={(e) => setForm({ ...form, litellm_model: e.target.value })}
                placeholder="openai/gpt-4o"
              />
            </label>

            <label className="settings-label">
              <span>API Key</span>
              <div className="input-with-toggle">
                <input
                  type={showKey ? "text" : "password"}
                  value={form.litellm_api_key}
                  onChange={(e) => setForm({ ...form, litellm_api_key: e.target.value })}
                  placeholder="sk-..."
                />
                <button
                  type="button"
                  className="toggle-visibility-btn"
                  onClick={() => setShowKey(!showKey)}
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
            </label>

            <button
              className="save-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
