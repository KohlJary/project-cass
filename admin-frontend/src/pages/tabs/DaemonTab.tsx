import { useState, useRef, useEffect, useCallback } from 'react';
import { daemonsApi, genesisApi } from '../../api/client';
import { useDaemon } from '../../context/DaemonContext';

interface SeedExport {
  filename: string;
  daemon_name: string;
  daemon_label: string;
  size_mb: string;
  stats?: Record<string, number>;
  error?: string;
}

interface ImportPreview {
  daemon_name: string;
  daemon_label: string;
  exported_at: string;
  stats: Record<string, number>;
}

export function DaemonTab() {
  const { currentDaemon, refreshDaemons } = useDaemon();
  const [seedExports, setSeedExports] = useState<SeedExport[]>([]);
  const [loadingSeeds, setLoadingSeeds] = useState(true);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importingSeed, setImportingSeed] = useState<string | null>(null);
  const [importName, setImportName] = useState('');
  const [skipEmbeddings, setSkipEmbeddings] = useState(false);
  const [replaceCurrent, setReplaceCurrent] = useState(false);
  const [daemonDetails, setDaemonDetails] = useState<{ stats?: Record<string, number> } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchSeeds = useCallback(async () => {
    try {
      const { data } = await daemonsApi.listSeedExports();
      setSeedExports(data.seeds || []);
    } catch (e) {
      console.error('Failed to fetch seeds:', e);
    } finally {
      setLoadingSeeds(false);
    }
  }, []);

  const fetchDaemonDetails = useCallback(async () => {
    if (!currentDaemon?.id) return;
    try {
      const { data } = await daemonsApi.getById(currentDaemon.id);
      setDaemonDetails(data);
    } catch (e) {
      console.error('Failed to fetch daemon details:', e);
    }
  }, [currentDaemon?.id]);

  useEffect(() => {
    fetchSeeds();
  }, [fetchSeeds]);

  useEffect(() => {
    fetchDaemonDetails();
  }, [fetchDaemonDetails]);

  const handleExportCurrent = async () => {
    if (!currentDaemon?.id) return;
    try {
      const response = await daemonsApi.exportDaemon(currentDaemon.id);
      const blob = new Blob([response.data], { type: 'application/zip' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const label = currentDaemon.label || currentDaemon.name || 'daemon';
      const date = new Date().toISOString().split('T')[0].replace(/-/g, '');
      a.download = `${label}_export_${date}.anima`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export failed:', e);
      alert('Export failed. Check console for details.');
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFile(file);
    setPreview(null);
    setPreviewError(null);

    try {
      if (file.name.endsWith('.json')) {
        // Genesis JSON file - parse and preview
        const text = await file.text();
        const jsonData = JSON.parse(text);
        const { data } = await genesisApi.previewImport(jsonData);
        // Map genesis preview to ImportPreview format
        setPreview({
          daemon_name: data.daemon?.name || '',
          daemon_label: data.daemon?.label || '',
          exported_at: '',
          stats: data.would_create || {},
        });
      } else {
        const { data } = await daemonsApi.previewImport(file);
        setPreview(data);
      }
    } catch (e) {
      setPreviewError('Failed to preview file. Make sure it is a valid .anima or .json file.');
      console.error('Preview error:', e);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;

    if (replaceCurrent && currentDaemon?.id) {
      const confirmed = window.confirm(
        `This will overwrite "${currentDaemon.label || currentDaemon.name}" with the imported data. Continue?`
      );
      if (!confirmed) return;
    }

    setImporting(true);
    try {
      if (selectedFile.name.endsWith('.json')) {
        // Genesis JSON import
        const text = await selectedFile.text();
        const jsonData = JSON.parse(text);
        await genesisApi.importJson(jsonData);
      } else {
        // Use merge_existing=true when replacing to overwrite existing daemon
        await daemonsApi.importDaemon(selectedFile, importName || undefined, skipEmbeddings, replaceCurrent);
      }
      alert('Import completed successfully!');
      clearSelection();
      await refreshDaemons();
      fetchSeeds();
    } catch (e) {
      console.error('Import failed:', e);
      alert('Import failed. Check console for details.');
    } finally {
      setImporting(false);
    }
  };

  const handleImportSeed = async (seed: SeedExport, replace: boolean = false) => {
    if (replace) {
      const confirmed = window.confirm(
        `This will overwrite the existing daemon with "${seed.daemon_label}". Continue?`
      );
      if (!confirmed) return;
    }

    setImportingSeed(seed.filename);
    try {
      // Use merge_existing=true when replacing to overwrite existing daemon
      await daemonsApi.importSeed(seed.filename, undefined, false, replace);
      alert(`Imported daemon "${seed.daemon_label}" (entity: ${seed.daemon_name}) successfully!`);
      await refreshDaemons();
    } catch (e) {
      console.error('Seed import failed:', e);
      alert('Import failed. Check console for details.');
    } finally {
      setImportingSeed(null);
    }
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setPreview(null);
    setPreviewError(null);
    setImportName('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatNumber = (num: number) => num.toLocaleString();

  return (
    <div className="daemon-tab">
      <p className="panel-intro">
        Export and import complete daemon instances. Each <code>.anima</code> file contains
        the full cognitive state including conversations, memories, wiki, and identity.
      </p>

      {/* Export Current Daemon */}
      <div className="daemon-section">
        <h3>Export Current Daemon</h3>
        {currentDaemon ? (
          <div className="daemon-export-card">
            <div className="daemon-info">
              <span className="daemon-icon">*</span>
              <div className="daemon-details">
                <span className="daemon-name">
                  {currentDaemon.label || currentDaemon.name}
                  {currentDaemon.name && <span className="entity-name"> ({currentDaemon.name})</span>}
                </span>
                <span className="daemon-stats">
                  {daemonDetails?.stats?.conversations || 0} conversations |{' '}
                  {daemonDetails?.stats?.wiki_pages || 0} wiki pages |{' '}
                  {daemonDetails?.stats?.journals || 0} journals
                </span>
              </div>
            </div>
            <button className="btn-primary" onClick={handleExportCurrent}>
              Export .anima
            </button>
          </div>
        ) : (
          <div className="no-daemon">No daemon selected</div>
        )}
      </div>

      {/* Seed Exports */}
      <div className="daemon-section">
        <h3>Available Seed Exports</h3>
        {loadingSeeds ? (
          <div className="loading">Loading seed exports...</div>
        ) : seedExports.length === 0 ? (
          <div className="no-seeds">
            No seed exports found in the <code>seed/</code> folder.
          </div>
        ) : (
          <div className="seed-exports-list">
            {seedExports.map((seed) => (
              <div key={seed.filename} className="seed-export-item">
                <div className="seed-info">
                  <span className="seed-filename">{seed.filename}</span>
                  {seed.error ? (
                    <span className="seed-error">Error: {seed.error}</span>
                  ) : (
                    <span className="seed-meta">
                      {seed.daemon_label} ({seed.daemon_name}) | {seed.size_mb} MB |{' '}
                      {formatNumber(seed.stats?.total_rows || 0)} rows
                    </span>
                  )}
                </div>
                <div className="seed-actions">
                  <button
                    className="btn-secondary"
                    onClick={() => handleImportSeed(seed, false)}
                    disabled={!!seed.error || importingSeed === seed.filename}
                  >
                    {importingSeed === seed.filename ? 'Importing...' : 'Import'}
                  </button>
                  {currentDaemon && (
                    <button
                      className="btn-danger-small"
                      onClick={() => handleImportSeed(seed, true)}
                      disabled={!!seed.error || importingSeed === seed.filename}
                      title={`Replace "${currentDaemon.label || currentDaemon.name}" with this seed`}
                    >
                      Replace
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Custom Import */}
      <div className="daemon-section">
        <h3>Import from File</h3>

        <div className="file-upload-area">
          <input
            ref={fileInputRef}
            type="file"
            accept=".anima,.json,.zip"
            onChange={handleFileSelect}
            id="daemon-import-file"
          />
          <label htmlFor="daemon-import-file" className="file-upload-label">
            {selectedFile ? (
              <>
                <span className="file-name">{selectedFile.name}</span>
                <span className="file-size">({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)</span>
              </>
            ) : (
              <>
                <span className="upload-icon">[^]</span>
                <span>Click to select .anima or .json file</span>
              </>
            )}
          </label>
          {selectedFile && (
            <button className="clear-file-btn" onClick={clearSelection}>
              x
            </button>
          )}
        </div>

        {previewError && (
          <div className="import-error">
            <span className="error-icon">[!]</span>
            {previewError}
          </div>
        )}

        {preview && (
          <div className="import-preview daemon-import-preview">
            <h4>Import Preview</h4>
            <div className="preview-daemon-info">
              <div className="preview-field">
                <span className="field-label">Label:</span>
                <span className="field-value">{preview.daemon_label}</span>
              </div>
              <div className="preview-field">
                <span className="field-label">Entity Name:</span>
                <span className="field-value">{preview.daemon_name}</span>
              </div>
              <div className="preview-field">
                <span className="field-label">Exported:</span>
                <span className="field-value">{new Date(preview.exported_at).toLocaleString()}</span>
              </div>
              <div className="preview-field">
                <span className="field-label">Total Rows:</span>
                <span className="field-value">{formatNumber(preview.stats?.total_rows || 0)}</span>
              </div>
            </div>

            <div className="preview-stats">
              {Object.entries(preview.stats)
                .filter(([key]) => key !== 'total_rows')
                .slice(0, 6)
                .map(([key, value]) => (
                  <div key={key} className="preview-stat">
                    <span className="stat-value">{formatNumber(value)}</span>
                    <span className="stat-label">{key.replace(/_/g, ' ')}</span>
                  </div>
                ))}
            </div>

            <div className="import-options">
              <div className="import-option">
                <label htmlFor="import-name">Custom Name (optional):</label>
                <input
                  id="import-name"
                  type="text"
                  value={importName}
                  onChange={(e) => setImportName(e.target.value)}
                  placeholder={preview.daemon_label}
                />
              </div>
              <div className="import-option checkbox">
                <input
                  id="skip-embeddings"
                  type="checkbox"
                  checked={skipEmbeddings}
                  onChange={(e) => setSkipEmbeddings(e.target.checked)}
                />
                <label htmlFor="skip-embeddings">Skip embedding rebuild (faster, do later)</label>
              </div>
              {currentDaemon && (
                <div className="import-option checkbox danger">
                  <input
                    id="replace-current"
                    type="checkbox"
                    checked={replaceCurrent}
                    onChange={(e) => setReplaceCurrent(e.target.checked)}
                  />
                  <label htmlFor="replace-current">
                    Replace current daemon ({currentDaemon.label || currentDaemon.name})
                  </label>
                </div>
              )}
            </div>

            <div className="import-actions">
              <button
                className={`btn-primary ${replaceCurrent ? 'btn-danger' : ''}`}
                onClick={handleImport}
                disabled={importing}
              >
                {importing ? 'Importing...' : replaceCurrent ? 'Replace & Import' : 'Import Daemon'}
              </button>
              <button className="btn-secondary" onClick={clearSelection}>
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="import-note">
        <strong>[!] Note:</strong> {replaceCurrent
          ? 'Replace mode will permanently delete the current daemon before importing.'
          : 'Importing creates a new daemon instance. Use "Replace" to delete the current one first.'}
      </div>
    </div>
  );
}
