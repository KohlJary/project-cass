import { useState, useRef } from 'react';
import { exportApi } from '../../api/client';

type ImportType = 'wiki' | 'research' | 'self-model';

interface ImportPreview {
  type: string;
  stats: Record<string, number>;
  sample: unknown[];
  warnings: string[];
}

export function DataImportTab() {
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

    try {
      const text = await file.text();
      const data = JSON.parse(text);

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
    <div className="import-tab">
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
              <span className="upload-icon">[^]</span>
              <span>Click to select a file or drag and drop</span>
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
                  <span className="warning-icon">[!]</span>
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
        <strong>[!] Warning:</strong> Import operations may overwrite existing data.
        Consider creating a backup before importing.
      </div>
    </div>
  );
}
