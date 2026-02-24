import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailApi, type Email as EmailType } from '../api/domains';
import './Email.css';

type TabId = 'inbox' | 'sent';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'inbox', label: 'Inbox', icon: '@' },
  { id: 'sent', label: 'Sent', icon: '^' },
];

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  if (isToday) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function getStatusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case 'received':
      return { label: 'New', className: 'status-new' };
    case 'processing':
      return { label: 'Processing', className: 'status-processing' };
    case 'processed':
      return { label: 'Done', className: 'status-done' };
    case 'queued':
      return { label: 'Queued', className: 'status-queued' };
    case 'sent':
      return { label: 'Sent', className: 'status-sent' };
    case 'failed':
      return { label: 'Failed', className: 'status-failed' };
    default:
      return { label: status, className: '' };
  }
}

export function Email() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'inbox'
  );
  const [selectedEmail, setSelectedEmail] = useState<string | null>(null);
  const [showProcessed, setShowProcessed] = useState(false);
  const queryClient = useQueryClient();

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
    setSelectedEmail(null);
  };

  // Queries
  const { data: stats } = useQuery({
    queryKey: ['email-stats'],
    queryFn: () => emailApi.getStats().then(r => r.data),
    refetchInterval: 30000,
  });

  const { data: inboxData, isLoading: inboxLoading } = useQuery({
    queryKey: ['email-inbox', showProcessed],
    queryFn: () => emailApi.getInbox({ limit: 100, include_processed: showProcessed }).then(r => r.data),
    enabled: activeTab === 'inbox',
    refetchInterval: 15000,
  });

  const { data: sentData, isLoading: sentLoading } = useQuery({
    queryKey: ['email-sent'],
    queryFn: () => emailApi.getSent({ limit: 100 }).then(r => r.data),
    enabled: activeTab === 'sent',
    refetchInterval: 30000,
  });

  const { data: emailDetail } = useQuery({
    queryKey: ['email-detail', selectedEmail],
    queryFn: () => selectedEmail ? emailApi.getById(selectedEmail).then(r => r.data) : null,
    enabled: !!selectedEmail,
  });

  // Mutations
  const checkInboxMutation = useMutation({
    mutationFn: () => emailApi.checkInbox(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-inbox'] });
      queryClient.invalidateQueries({ queryKey: ['email-stats'] });
    },
  });

  const respondMutation = useMutation({
    mutationFn: (emailId: string) => emailApi.respondToEmail(emailId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-inbox'] });
      queryClient.invalidateQueries({ queryKey: ['email-sent'] });
      queryClient.invalidateQueries({ queryKey: ['email-stats'] });
    },
  });

  const markProcessedMutation = useMutation({
    mutationFn: (emailId: string) => emailApi.markProcessed(emailId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-inbox'] });
      queryClient.invalidateQueries({ queryKey: ['email-stats'] });
    },
  });

  const inbox = inboxData?.emails || [];
  const sent = sentData?.emails || [];

  return (
    <div className="email-page">
      <header className="page-header">
        <h1>Email</h1>
        <p className="subtitle">Manage Cass's email inbox and outbound messages</p>
      </header>

      {/* Stats banner */}
      {stats && (
        <div className="email-stats-banner">
          <div className="stat-item">
            <span className="stat-value">{stats.inbound.unprocessed}</span>
            <span className="stat-label">Unread</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.inbound.total}</span>
            <span className="stat-label">Inbox Total</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.outbound.sent}</span>
            <span className="stat-label">Sent</span>
          </div>
          {stats.outbound.failed > 0 && (
            <div className="stat-item stat-warning">
              <span className="stat-value">{stats.outbound.failed}</span>
              <span className="stat-label">Failed</span>
            </div>
          )}
        </div>
      )}

      {/* Actions bar */}
      <div className="email-actions-bar">
        <button
          className="btn-primary"
          onClick={() => checkInboxMutation.mutate()}
          disabled={checkInboxMutation.isPending}
        >
          {checkInboxMutation.isPending ? 'Checking...' : 'Check Inbox'}
        </button>
        {activeTab === 'inbox' && (
          <label className="show-processed-toggle">
            <input
              type="checkbox"
              checked={showProcessed}
              onChange={(e) => setShowProcessed(e.target.checked)}
            />
            Show processed
          </label>
        )}
        {checkInboxMutation.isSuccess && (
          <span className="success-message">Inbox checked</span>
        )}
        {checkInboxMutation.isError && (
          <span className="error-message">Check failed</span>
        )}
      </div>

      <nav className="email-tabs" role="tablist" aria-label="Email sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`email-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.id === 'inbox' && stats && stats.inbound.unprocessed > 0 && (
              <span className="tab-badge">{stats.inbound.unprocessed}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="email-content">
        <div className="email-layout">
          {/* Email list */}
          <div className="email-list-panel">
            {activeTab === 'inbox' && (
              <>
                {inboxLoading && <div className="loading-state">Loading inbox...</div>}
                {!inboxLoading && inbox.length === 0 && (
                  <div className="empty-state">No emails in inbox</div>
                )}
                {inbox.map((email) => (
                  <EmailListItem
                    key={email.id}
                    email={email}
                    isSelected={selectedEmail === email.id}
                    onClick={() => setSelectedEmail(email.id)}
                  />
                ))}
              </>
            )}
            {activeTab === 'sent' && (
              <>
                {sentLoading && <div className="loading-state">Loading sent...</div>}
                {!sentLoading && sent.length === 0 && (
                  <div className="empty-state">No sent emails</div>
                )}
                {sent.map((email) => (
                  <EmailListItem
                    key={email.id}
                    email={email}
                    isSelected={selectedEmail === email.id}
                    onClick={() => setSelectedEmail(email.id)}
                  />
                ))}
              </>
            )}
          </div>

          {/* Email detail */}
          <div className="email-detail-panel">
            {!selectedEmail && (
              <div className="empty-state">Select an email to view details</div>
            )}
            {selectedEmail && emailDetail && (
              <EmailDetail
                email={emailDetail}
                onRespond={() => respondMutation.mutate(selectedEmail)}
                onMarkProcessed={() => markProcessedMutation.mutate(selectedEmail)}
                isResponding={respondMutation.isPending}
                isMarkingProcessed={markProcessedMutation.isPending}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface EmailListItemProps {
  email: EmailType;
  isSelected: boolean;
  onClick: () => void;
}

function EmailListItem({ email, isSelected, onClick }: EmailListItemProps) {
  const status = getStatusBadge(email.status);
  const isInbound = email.direction === 'inbound';
  const contact = isInbound ? email.from_address : email.to_address;

  // Extract just the email address or name
  const contactDisplay = contact.includes('<')
    ? contact.split('<')[0].trim() || contact.match(/<([^>]+)>/)?.[1] || contact
    : contact;

  return (
    <div
      className={`email-list-item ${isSelected ? 'selected' : ''} ${email.status === 'received' ? 'unread' : ''}`}
      onClick={onClick}
    >
      <div className="email-list-header">
        <span className="email-contact">{contactDisplay}</span>
        <span className="email-date">{formatDate(email.created_at)}</span>
      </div>
      <div className="email-list-subject">
        {email.subject || '(no subject)'}
      </div>
      <div className="email-list-meta">
        <span className={`email-status-badge ${status.className}`}>{status.label}</span>
        {email.body_plain && (
          <span className="email-preview">
            {email.body_plain.slice(0, 60)}...
          </span>
        )}
      </div>
    </div>
  );
}

interface EmailDetailProps {
  email: EmailType;
  onRespond: () => void;
  onMarkProcessed: () => void;
  isResponding: boolean;
  isMarkingProcessed: boolean;
}

function EmailDetail({ email, onRespond, onMarkProcessed, isResponding, isMarkingProcessed }: EmailDetailProps) {
  const status = getStatusBadge(email.status);
  const isInbound = email.direction === 'inbound';
  const canRespond = isInbound && email.status !== 'processed';

  return (
    <div className="email-detail">
      <div className="email-detail-header">
        <h2>{email.subject || '(no subject)'}</h2>
        <span className={`email-status-badge large ${status.className}`}>{status.label}</span>
      </div>

      <div className="email-meta-grid">
        <div className="meta-row">
          <span className="meta-label">From:</span>
          <span className="meta-value">{email.from_address}</span>
        </div>
        <div className="meta-row">
          <span className="meta-label">To:</span>
          <span className="meta-value">{email.to_address}</span>
        </div>
        <div className="meta-row">
          <span className="meta-label">Date:</span>
          <span className="meta-value">{new Date(email.created_at).toLocaleString()}</span>
        </div>
        {email.thread_id && (
          <div className="meta-row">
            <span className="meta-label">Thread:</span>
            <span className="meta-value mono">{email.thread_id.slice(0, 8)}...</span>
          </div>
        )}
      </div>

      {canRespond && (
        <div className="email-actions">
          <button
            className="btn-primary"
            onClick={onRespond}
            disabled={isResponding}
          >
            {isResponding ? 'Generating response...' : 'Have Cass Respond'}
          </button>
          <button
            className="btn-secondary"
            onClick={onMarkProcessed}
            disabled={isMarkingProcessed}
          >
            {isMarkingProcessed ? 'Marking...' : 'Mark as Processed'}
          </button>
        </div>
      )}

      <div className="email-body">
        {email.body_plain ? (
          <pre>{email.body_plain}</pre>
        ) : email.body_html ? (
          <div
            className="email-html-body"
            dangerouslySetInnerHTML={{ __html: email.body_html }}
          />
        ) : (
          <div className="empty-body">(No body content)</div>
        )}
      </div>

      {email.goal_id && (
        <div className="email-link-info">
          <span className="link-label">Linked Goal:</span>
          <span className="link-value mono">{email.goal_id.slice(0, 8)}...</span>
        </div>
      )}
      {email.stakeholder_id && (
        <div className="email-link-info">
          <span className="link-label">Stakeholder:</span>
          <span className="link-value mono">{email.stakeholder_id.slice(0, 8)}...</span>
        </div>
      )}
    </div>
  );
}
