TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "List recent Kubernetes events stored by the webhook receiver.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["new", "analyzed", "resolved", "all"],
                        "description": "Filter by status (default: 'all')",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical", "all"],
                        "description": "Filter by severity (default: 'all')",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Filter by K8s namespace, or 'all' (default: 'all')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default: 20)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event",
            "description": "Get the full details of a specific Kubernetes event including the raw payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The short event ID returned by list_events",
                    }
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_event",
            "description": "Analyze a Kubernetes event and return diagnostics + suggested fixes. Updates the event status to 'analyzed'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The short event ID to analyze",
                    }
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster_info",
            "description": "Run a READ-ONLY kubectl command to inspect the cluster. Only 'get', 'describe', 'logs', 'top', 'version', and 'events' subcommands are allowed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The kubectl command (e.g. 'kubectl get pods -n default')",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_fix",
            "description": "Apply a kubectl fix command. Runs in --dry-run=client mode by default. Set dry_run=False to apply for real.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The kubectl command to run",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true (default), appends --dry-run=client. Set false to apply.",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_resolved",
            "description": "Mark an event as resolved after a fix has been applied.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "The event ID to mark resolved",
                    },
                    "resolution_note": {
                        "type": "string",
                        "description": "Optional note describing what was done",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_summary",
            "description": "Get a summary dashboard of all events grouped by severity and status. Useful for a quick overview of cluster health.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_resource_usage",
            "description": "Analyze why a specific pod has high CPU or memory usage. Gathers pod description, events, logs, and current metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pod": {"type": "string", "description": "The pod name"},
                    "namespace": {"type": "string", "description": "The namespace (default: 'default')"},
                },
                "required": ["pod"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jvm_details",
            "description": "Get JVM configuration details for Java pods in a namespace. Shows expected JVM flags from environment variables vs actual runtime JVM flags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace to scan (default: 'default')"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_network_status",
            "description": "Get service-to-service network status including endpoints, network policies, and network issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace to check, or 'all' (default: 'all')"},
                    "test_latency": {"type": "boolean", "description": "If true, actively measure latency (slower)"},
                },
                "required": [],
            },
        },
    },
]
