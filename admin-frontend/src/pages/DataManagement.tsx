import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { exportApi } from '../api/client';
import './DataManagement.css';

type ExportType = 'wiki' | 'research' | 'self-model' | 'conversations' | 'dataset' | 'backup';
type ImportType = 'wiki' | 'research' | 'self-model';

interface BackupInfo {
  name: string;
  filename: string;
  size_mb: number;
  created_at: string;
}

interface ExportStats {
  wiki?: { total_pages: number; total_links: number };
  research?: { completed_tasks: number; queued_tasks: number; curiosity_chains: number };
  selfModel?: { growth_edges: number; open_questions: number; opinions: number; journals: number };
}

interface ImportPreview {
  type: string;
  stats: Record<string, number>;
  sample: unknown[];
  warnings: string[];
}

export function DataManagement() {
  const [activeTab, setActiveTab] = useState<'export' | 'import' | 'backups'>('export');

  return (
    <div className="data-management-page">
      <header className="page-header">
        <h1>Data Management</h1>
        <p className="subtitle">Export research data, create backups, and import datasets</p>
      </header>

      <div className="dm-tabs">
        <button
          className={`tab ${activeTab === 'export' ? 'active' : ''}`}
          onClick={() => setActiveTab('export')}
        >
          📤 Export
        </button>
        <button
          className={`tab ${activeTab === 'import' ? 'active' : ''}`}
          onClick={() => setActiveTab('import')}
        >
          📥 Import
        </button>
        <button
          className={`tab ${activeTab === 'backups' ? 'active' : ''}`}
          onClick={() => setActiveTab('backups')}
        >
          💾 Backups
        </button>
      </div>

      <div className="dm-content">
        {activeTab === 'export' && <ExportPanel />}
        {activeTab === 'import' && <ImportPanel />}
        {activeTab === 'backups' && <BackupsPanel />}
      </div>
    </div>
  );
}

function ExportPanel() {
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
      icon: '📦',
    },
    {
      type: 'wiki',
      label: 'Wiki Graph',
      description: 'All wiki pages with content, links, and metadata',
      icon: '🕸️',
    },
    {
      type: 'research',
      label: 'Research History',
      description: 'Completed tasks, queued items, and curiosity chains',
      icon: '🔬',
    },
    {
      type: 'self-model',
      label: 'Self-Model',
      description: 'Identity, growth edges, opinions, and journals',
      icon: '🪞',
    },
    {
      type: 'conversations',
      label: 'Conversations',
      description: 'Conversation history (anonymized by default)',
      icon: '💬',
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
    <div className="export-panel">
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

function ImportPanel() {
  const [selectedType, setSelectedType] = useState<ImportType>('wiki');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [importing, setImporting] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importTypes: { type: ImportType; label: string; description: string; accepts: string }[] = [
    {
      type: 'wiki',
      label: 'Wiki Pages',
      description: 'Import wiki pages from a JSON export',
      accepts: '.json',
    },
    {
      type: 'research',
      label: 'Research Queue',
      description: 'Import research tasks and history',
      accepts: '.json',
    },
    {
      type: 'self-model',
      label: 'Self-Model',
      description: 'Import self-model data (growth edges, opinions)',
      accepts: '.json',
    },
  ];

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    setPreview(null);
    setPreviewError(null);

    // Try to parse and preview the file locally first
    try {
      const text = await file.text();
      const data = JSON.parse(text);

      // Generate local preview based on type
      const localPreview: ImportPreview = {
        type: selectedType,
        stats: {},
        sample: [],
        warnings: [],
      };

      if (selectedType === 'wiki' && data.pages) {
        localPreview.stats = {
          pages: data.pages.length,
          links: data.links?.length || 0,
        };
        localPreview.sample = data.pages.slice(0, 3).map((p: { name: string; page_type: string }) => ({
          name: p.name,
          type: p.page_type,
        }));
      } else if (selectedType === 'research') {
        localPreview.stats = {
          completed_tasks: data.completed_tasks?.length || 0,
          queued_tasks: data.queued_tasks?.length || 0,
        };
      } else if (selectedType === 'self-model') {
        localPreview.stats = {
          growth_edges: data.growth_edges?.length || 0,
          opinions: data.opinions?.length || 0,
          journals: data.journals?.length || 0,
        };
      }

      // Add warnings
      if (!data.export_type) {
        localPreview.warnings.push('File does not have export_type field - may not be a valid Cass export');
      }
      if (data.export_type && data.export_type !== selectedType && data.export_type !== 'self_model') {
        localPreview.warnings.push(`Export type mismatch: file is "${data.export_type}", importing as "${selectedType}"`);
      }

      setPreview(localPreview);
    } catch (e) {
      setPreviewError('Failed to parse file. Make sure it is valid JSON.');
      console.error('Parse error:', e);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;

    setImporting(true);
    try {
      await exportApi.applyImport(selectedFile, selectedType);
      alert('Import completed successfully!');
      setSelectedFile(null);
      setPreview(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (e) {
      console.error('Import failed:', e);
      alert('Import failed. Check console for details.');
    } finally {
      setImporting(false);
    }
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setPreview(null);
    setPreviewError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="import-panel">
      <p className="panel-intro">
        Import data from a previous export. Preview changes before applying.
      </p>

      <div className="import-type-selector">
        <label>Import Type:</label>
        <div className="type-buttons">
          {importTypes.map(({ type, label }) => (
            <button
              key={type}
              className={`type-btn ${selectedType === type ? 'active' : ''}`}
              onClick={() => {
                setSelectedType(type);
                clearSelection();
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="import-description">
        {importTypes.find(t => t.type === selectedType)?.description}
      </div>

      <div className="file-upload-area">
        <input
          ref={fileInputRef}
          type="file"
          accept={importTypes.find(t => t.type === selectedType)?.accepts}
          onChange={handleFileSelect}
          id="import-file"
        />
        <label htmlFor="import-file" className="file-upload-label">
          {selectedFile ? (
            <>
              <span className="file-name">{selectedFile.name}</span>
              <span className="file-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
            </>
          ) : (
            <>
              <span className="upload-icon">📁</span>
              <span>Click to select a file or drag and drop</span>
            </>
          )}
        </label>
        {selectedFile && (
          <button className="clear-file-btn" onClick={clearSelection}>
            ✕
          </button>
        )}
      </div>

      {previewError && (
        <div className="import-error">
          <span className="error-icon">⚠️</span>
          {previewError}
        </div>
      )}

      {preview && (
        <div className="import-preview">
          <h3>Import Preview</h3>

          <div className="preview-stats">
            {Object.entries(preview.stats).map(([key, value]) => (
              <div key={key} className="preview-stat">
                <span className="stat-value">{value}</span>
                <span className="stat-label">{key.replace(/_/g, ' ')}</span>
              </div>
            ))}
          </div>

          {preview.warnings.length > 0 && (
            <div className="preview-warnings">
              {preview.warnings.map((warning, i) => (
                <div key={i} className="warning-item">
                  <span className="warning-icon">⚠️</span>
                  {warning}
                </div>
              ))}
            </div>
          )}

          {preview.sample.length > 0 && (
            <div className="preview-sample">
              <h4>Sample Items</h4>
              <ul>
                {preview.sample.map((item, i) => (
                  <li key={i}>
                    <code>{JSON.stringify(item)}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="import-actions">
            <button
              className="btn-primary"
              onClick={handleImport}
              disabled={importing || preview.warnings.length > 1}
            >
              {importing ? 'Importing...' : 'Apply Import'}
            </button>
            <button className="btn-secondary" onClick={clearSelection}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="import-note">
        <strong>⚠️ Warning:</strong> Import operations may overwrite existing data.
        Consider creating a backup before importing.
      </div>
    </div>
  );
}

function BackupsPanel() {
  const queryClient = useQueryClient();

  const { data: backupsData, isLoading } = useQuery({
    queryKey: ['backups'],
    queryFn: () => exportApi.listBackups().then(r => r.data),
  });

  const createBackupMutation = useMutation({
    mutationFn: () => exportApi.createBackup(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backups'] });
    },
  });

  const backups: BackupInfo[] = backupsData?.backups || [];

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString();
  };

  return (
    <div className="backups-panel">
      <p className="panel-intro">
        Create and manage data backups. Backups include wiki, conversations, users, and system data.
      </p>

      <div className="backup-actions">
        <button
          className="btn-primary create-backup-btn"
          onClick={() => createBackupMutation.mutate()}
          disabled={createBackupMutation.isPending}
        >
          {createBackupMutation.isPending ? 'Creating...' : '💾 Create New Backup'}
        </button>

        {createBackupMutation.isSuccess && (
          <span className="success-message">✓ Backup created successfully</span>
        )}
      </div>

      <div className="backups-list">
        <h3>Available Backups ({backups.length})</h3>

        {isLoading ? (
          <div className="loading">Loading backups...</div>
        ) : backups.length === 0 ? (
          <div className="no-backups">
            No backups found. Create your first backup above.
          </div>
        ) : (
          <div className="backup-items">
            {backups.map((backup) => (
              <div key={backup.name} className="backup-item">
                <div className="backup-info">
                  <span className="backup-name">{backup.filename}</span>
                  <span className="backup-meta">
                    {backup.size_mb.toFixed(2)} MB • {formatDate(backup.created_at)}
                  </span>
                </div>
                <div className="backup-actions-inline">
                  <button className="btn-small" title="Download backup">
                    ⬇️
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="backup-schedule">
        <h3>Automatic Backups</h3>
        <p>
          Automatic daily backups run at 3:00 AM and are retained for 30 days.
          To enable automatic backups, install the systemd timer:
        </p>
        <pre className="code-block">
{`sudo cp backend/scripts/cass-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cass-backup.timer`}
        </pre>
      </div>
    </div>
  );
}
