import { useState } from 'react';
import { exportApi } from '../../api/client';

type ExportType = 'wiki' | 'research' | 'self-model' | 'conversations' | 'dataset';

interface ExportStats {
  wiki?: { total_pages: number; total_links: number };
  research?: { completed_tasks: number; queued_tasks: number; curiosity_chains: number };
  selfModel?: { growth_edges: number; open_questions: number; opinions: number; journals: number };
}

export function DataExportTab() {
  const [stats, setStats] = useState<ExportStats>({});
  const [loadingStats, setLoadingStats] = useState<Record<string, boolean>>({});

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadJson = (data: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    downloadBlob(blob, filename);
  };

  const loadStats = async (type: ExportType) => {
    setLoadingStats(prev => ({ ...prev, [type]: true }));
    try {
      if (type === 'wiki') {
        const { data } = await exportApi.getWikiJson();
        setStats(prev => ({ ...prev, wiki: data.stats }));
      } else if (type === 'research') {
        const { data } = await exportApi.getResearchJson();
        setStats(prev => ({ ...prev, research: data.stats }));
      } else if (type === 'self-model') {
        const { data } = await exportApi.getSelfModelJson();
        setStats(prev => ({ ...prev, selfModel: data.stats }));
      }
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setLoadingStats(prev => ({ ...prev, [type]: false }));
    }
  };

  const exportTypes: { type: ExportType; label: string; description: string; icon: string }[] = [
    {
      type: 'dataset',
      label: 'Complete Dataset',
      description: 'Full research-ready package with wiki, research history, self-model, and README',
      icon: '[+]',
    },
    {
      type: 'wiki',
      label: 'Wiki Graph',
      description: 'All wiki pages with content, links, and metadata',
      icon: 'W',
    },
    {
      type: 'research',
      label: 'Research History',
      description: 'Completed tasks, queued items, and curiosity chains',
      icon: 'R',
    },
    {
      type: 'self-model',
      label: 'Self-Model',
      description: 'Identity, growth edges, opinions, and journals',
      icon: '%',
    },
    {
      type: 'conversations',
      label: 'Conversations',
      description: 'Conversation history (anonymized by default)',
      icon: '>',
    },
  ];

  const handleExport = async (type: ExportType) => {
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '');

    try {
      if (type === 'dataset') {
        const { data } = await exportApi.getDataset();
        downloadBlob(data, `cass_research_dataset_${timestamp}.zip`);
      } else if (type === 'wiki') {
        const { data } = await exportApi.getWikiJson();
        downloadJson(data, `cass_wiki_${timestamp}.json`);
      } else if (type === 'research') {
        const { data } = await exportApi.getResearchJson();
        downloadJson(data, `cass_research_${timestamp}.json`);
      } else if (type === 'self-model') {
        const { data } = await exportApi.getSelfModelJson();
        downloadJson(data, `cass_self_model_${timestamp}.json`);
      } else if (type === 'conversations') {
        const { data } = await exportApi.getConversationsJson(true);
        downloadJson(data, `cass_conversations_${timestamp}.json`);
      }
    } catch (e) {
      console.error('Export failed:', e);
      alert('Export failed. Check console for details.');
    }
  };

  return (
    <div className="export-tab">
      <p className="panel-intro">
        Export Cass's cognitive data for research collaboration, analysis, or backup purposes.
      </p>

      <div className="export-grid">
        {exportTypes.map(({ type, label, description, icon }) => (
          <div key={type} className={`export-card ${type === 'dataset' ? 'featured' : ''}`}>
            <div className="export-card-header">
              <span className="export-icon">{icon}</span>
              <h3>{label}</h3>
            </div>
            <p className="export-description">{description}</p>

            {/* Stats display */}
            {type === 'wiki' && stats.wiki && (
              <div className="export-stats">
                <span>{stats.wiki.total_pages} pages</span>
                <span>{stats.wiki.total_links} links</span>
              </div>
            )}
            {type === 'research' && stats.research && (
              <div className="export-stats">
                <span>{stats.research.completed_tasks} completed</span>
                <span>{stats.research.queued_tasks} queued</span>
                <span>{stats.research.curiosity_chains} chains</span>
              </div>
            )}
            {type === 'self-model' && stats.selfModel && (
              <div className="export-stats">
                <span>{stats.selfModel.growth_edges} edges</span>
                <span>{stats.selfModel.journals} journals</span>
              </div>
            )}

            <div className="export-card-actions">
              {['wiki', 'research', 'self-model'].includes(type) && !stats[type as keyof ExportStats] && (
                <button
                  className="btn-secondary"
                  onClick={() => loadStats(type)}
                  disabled={loadingStats[type]}
                >
                  {loadingStats[type] ? 'Loading...' : 'Preview Stats'}
                </button>
              )}
              <button
                className="btn-primary"
                onClick={() => handleExport(type)}
              >
                Download {type === 'dataset' ? 'ZIP' : 'JSON'}
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="export-note">
        <strong>Note:</strong> Conversation exports are anonymized by default to protect user privacy.
        The complete dataset includes all data types in a single ZIP with documentation.
      </div>
    </div>
  );
}
