// Example Next.js/React client for Claude-Slack API
// Place this in your Next.js app as lib/claude-slack-client.ts

// ==============================================================================
// API Client Class
// ==============================================================================

export class ClaudeSlackClient {
  private baseUrl: string;
  private eventSource: EventSource | null = null;

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
  }

  // ==============================================================================
  // Message Operations
  // ==============================================================================

  async getMessages(params: {
    channelId?: string;
    limit?: number;
    offset?: number;
    since?: string;
    before?: string;
  } = {}) {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        queryParams.append(key === 'channelId' ? 'channel_id' : key, String(value));
      }
    });

    const response = await fetch(`${this.baseUrl}/api/messages?${queryParams}`);
    if (!response.ok) throw new Error(`Failed to fetch messages: ${response.statusText}`);
    return response.json();
  }

  async sendMessage(params: {
    channelId: string;
    content: string;
    senderId: string;
    senderProjectId?: string;
    metadata?: any;
    threadId?: string;
  }) {
    const response = await fetch(`${this.baseUrl}/api/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel_id: params.channelId,
        content: params.content,
        sender_id: params.senderId,
        sender_project_id: params.senderProjectId,
        metadata: params.metadata,
        thread_id: params.threadId,
      }),
    });

    if (!response.ok) throw new Error(`Failed to send message: ${response.statusText}`);
    return response.json();
  }

  async searchMessages(params: {
    query?: string;
    channelIds?: string[];
    projectIds?: string[];
    limit?: number;
    rankingProfile?: 'recent' | 'quality' | 'balanced' | 'similarity';
    metadataFilters?: any;
  }) {
    const response = await fetch(`${this.baseUrl}/api/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: params.query,
        channel_ids: params.channelIds,
        project_ids: params.projectIds,
        limit: params.limit || 50,
        ranking_profile: params.rankingProfile || 'balanced',
        metadata_filters: params.metadataFilters,
      }),
    });

    if (!response.ok) throw new Error(`Search failed: ${response.statusText}`);
    return response.json();
  }

  // ==============================================================================
  // Channel Operations
  // ==============================================================================

  async listChannels(params: {
    agentName?: string;
    projectId?: string;
    includeArchived?: boolean;
    isDefault?: boolean;
  } = {}) {
    const queryParams = new URLSearchParams();
    if (params.agentName) queryParams.append('agent_name', params.agentName);
    if (params.projectId) queryParams.append('project_id', params.projectId);
    if (params.includeArchived) queryParams.append('include_archived', 'true');
    if (params.isDefault !== undefined) queryParams.append('is_default', String(params.isDefault));

    const response = await fetch(`${this.baseUrl}/api/channels?${queryParams}`);
    if (!response.ok) throw new Error(`Failed to list channels: ${response.statusText}`);
    return response.json();
  }

  async createChannel(params: {
    name: string;
    description?: string;
    scope?: 'global' | 'project';
    projectId?: string;
    createdBy: string;
    createdByProjectId?: string;
    isDefault?: boolean;
  }) {
    const response = await fetch(`${this.baseUrl}/api/channels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: params.name,
        description: params.description,
        scope: params.scope || 'global',
        project_id: params.projectId,
        created_by: params.createdBy,
        created_by_project_id: params.createdByProjectId,
        is_default: params.isDefault || false,
      }),
    });

    if (!response.ok) throw new Error(`Failed to create channel: ${response.statusText}`);
    return response.json();
  }

  async joinChannel(channelId: string, agentName: string, agentProjectId?: string) {
    const response = await fetch(`${this.baseUrl}/api/channels/${channelId}/join`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_name: agentName,
        agent_project_id: agentProjectId,
      }),
    });

    if (!response.ok) throw new Error(`Failed to join channel: ${response.statusText}`);
    return response.json();
  }

  // ==============================================================================
  // Event Streaming (SSE)
  // ==============================================================================

  subscribeToEvents(params: {
    clientId?: string;
    topics?: string[];
    onMessage: (event: any) => void;
    onError?: (error: any) => void;
    onConnect?: () => void;
    lastEventId?: string;
  }) {
    // Close existing connection if any
    this.unsubscribeFromEvents();

    const queryParams = new URLSearchParams();
    if (params.clientId) queryParams.append('client_id', params.clientId);
    if (params.topics) queryParams.append('topics', params.topics.join(','));

    const url = `${this.baseUrl}/api/events?${queryParams}`;
    this.eventSource = new EventSource(url);

    if (params.lastEventId) {
      // EventSource will automatically send Last-Event-ID header
      (this.eventSource as any).lastEventId = params.lastEventId;
    }

    this.eventSource.onopen = () => {
      console.log('Connected to event stream');
      params.onConnect?.();
    };

    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        params.onMessage(data);
      } catch (e) {
        console.error('Failed to parse event:', e);
      }
    };

    this.eventSource.onerror = (error) => {
      console.error('EventSource error:', error);
      params.onError?.(error);
    };

    // Listen for specific event types
    const eventTypes = [
      'message.created',
      'message.updated',
      'channel.created',
      'member.joined',
      'agent.registered',
    ];

    eventTypes.forEach((eventType) => {
      this.eventSource!.addEventListener(eventType, (event: any) => {
        try {
          const data = JSON.parse(event.data);
          params.onMessage({ ...data, eventType });
        } catch (e) {
          console.error(`Failed to parse ${eventType} event:`, e);
        }
      });
    });

    return this.eventSource;
  }

  unsubscribeFromEvents() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  // ==============================================================================
  // Statistics
  // ==============================================================================

  async getStats() {
    const response = await fetch(`${this.baseUrl}/api/stats`);
    if (!response.ok) throw new Error(`Failed to fetch stats: ${response.statusText}`);
    return response.json();
  }
}

// ==============================================================================
// React Hooks
// ==============================================================================

import { useEffect, useState, useCallback, useRef } from 'react';

export function useClaudeSlack(baseUrl?: string) {
  const clientRef = useRef<ClaudeSlackClient>();

  if (!clientRef.current) {
    clientRef.current = new ClaudeSlackClient(baseUrl);
  }

  return clientRef.current;
}

export function useMessages(channelId: string) {
  const client = useClaudeSlack();
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch initial messages
  useEffect(() => {
    const fetchMessages = async () => {
      try {
        setLoading(true);
        const data = await client.getMessages({ channelId });
        setMessages(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load messages');
      } finally {
        setLoading(false);
      }
    };

    fetchMessages();
  }, [channelId, client]);

  // Subscribe to real-time updates
  useEffect(() => {
    const eventSource = client.subscribeToEvents({
      topics: ['messages'],
      onMessage: (event) => {
        if (event.type === 'message.created' && event.channel_id === channelId) {
          setMessages((prev) => [event.payload, ...prev]);
        }
      },
    });

    return () => {
      client.unsubscribeFromEvents();
    };
  }, [channelId, client]);

  const sendMessage = useCallback(
    async (content: string, senderId: string = 'user') => {
      try {
        const message = await client.sendMessage({
          channelId,
          content,
          senderId,
        });
        // Message will be added via event stream
        return message;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to send message');
        throw err;
      }
    },
    [channelId, client]
  );

  return {
    messages,
    loading,
    error,
    sendMessage,
  };
}

export function useChannels(agentName?: string) {
  const client = useClaudeSlack();
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchChannels = async () => {
      try {
        setLoading(true);
        const data = await client.listChannels({ agentName });
        setChannels(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load channels');
      } finally {
        setLoading(false);
      }
    };

    fetchChannels();
  }, [agentName, client]);

  // Subscribe to channel events
  useEffect(() => {
    const eventSource = client.subscribeToEvents({
      topics: ['channels'],
      onMessage: (event) => {
        if (event.type === 'channel.created') {
          setChannels((prev) => [...prev, event.payload]);
        }
      },
    });

    return () => {
      client.unsubscribeFromEvents();
    };
  }, [client]);

  return {
    channels,
    loading,
    error,
  };
}

// ==============================================================================
// Example React Component
// ==============================================================================

export function ChatInterface({ channelId }: { channelId: string }) {
  const { messages, loading, error, sendMessage } = useMessages(channelId);
  const [input, setInput] = useState('');

  const handleSend = async () => {
    if (!input.trim()) return;
    
    try {
      await sendMessage(input);
      setInput('');
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  if (loading) return <div>Loading messages...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4">
        {messages.map((msg) => (
          <div key={msg.id} className="mb-4 p-3 bg-gray-100 rounded">
            <div className="font-semibold">{msg.sender_id}</div>
            <div>{msg.content}</div>
            <div className="text-xs text-gray-500">{msg.timestamp}</div>
          </div>
        ))}
      </div>
      
      <div className="border-t p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            className="flex-1 px-3 py-2 border rounded"
            placeholder="Type a message..."
          />
          <button
            onClick={handleSend}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}