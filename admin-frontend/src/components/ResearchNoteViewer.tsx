import ReactMarkdown from 'react-markdown';
import './ResearchNoteViewer.css';

interface Source {
  url: string;
  title: string;
}

interface ResearchNoteViewerProps {
  title: string;
  content: string;
  sources?: Source[];
  createdAt?: string;
  className?: string;
  onClose?: () => void;
}

export function ResearchNoteViewer({
  title,
  content,
  sources,
  createdAt,
  className = '',
  onClose,
}: ResearchNoteViewerProps) {
  return (
    <div className={`research-note-viewer ${className}`}>
      <div className="note-viewer-header">
        <div className="note-title-area">
          <h4>{title}</h4>
          {createdAt && (
            <span className="note-created">
              {new Date(createdAt).toLocaleString()}
            </span>
          )}
        </div>
        {onClose && (
          <button className="close-btn" onClick={onClose}>
            ×
          </button>
        )}
      </div>

      <div className="note-body markdown-content">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>

      {sources && sources.length > 0 && (
        <div className="note-sources">
          <h5>Sources</h5>
          <ul>
            {sources.map((source, i) => (
              <li key={i}>
                <a href={source.url} target="_blank" rel="noopener noreferrer">
                  {source.title || source.url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
