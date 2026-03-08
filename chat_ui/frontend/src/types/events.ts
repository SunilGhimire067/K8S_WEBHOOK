export interface K8sEvent {
  id: number;
  event_id: string;
  event_type: string;
  kind: string;
  name: string;
  namespace: string;
  reason: string;
  message: string;
  severity: string;
  status: string;
  created_at: string;
  raw_payload?: Record<string, unknown>;
  analysis?: string;
}

export interface EventStats {
  total: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
}
