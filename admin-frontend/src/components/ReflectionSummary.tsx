import './ReflectionSummary.css';

interface ThoughtEntry {
  timestamp: string;
  content: string;
  thought_type: string;
  confidence: string | number;
  related_concepts: string[];
}

interface ReflectionSummaryProps {
  summary?: string;
  insights?: string[];
  questionsRaised?: string[];
  thoughtStream?: ThoughtEntry[];
  compact?: boolean;
  showThoughtStream?: boolean;
  className?: string;
}

const getThoughtTypeColor = (type: string) => {
  switch (type) {
    case 'observation': return '#89ddff';
    case 'question': return '#82aaff';
    case 'connection': return '#c792ea';
    case 'uncertainty': return '#ffcb6b';
    case 'realization': return '#c3e88d';
    default: return '#888';
  }
};

const formatTimestamp = (ts: string) => {
  const date = new Date(ts);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

export function ReflectionSummary({
  summary,
  insights,
  questionsRaised,
  thoughtStream,
  compact = false,
  showThoughtStream = true,
  className = '',
}: ReflectionSummaryProps) {
  const hasContent = summary || insights?.length || questionsRaised?.length || thoughtStream?.length;

  if (!hasContent) {
    return (
      <div className={`reflection-summary empty ${className}`}>
        <p className="no-summary">No reflection data available yet</p>
      </div>
    );
  }

  return (
    <div className={`reflection-summary ${compact ? 'compact' : ''} ${className}`}>
      {summary && (
        <div className="summary-block">
          <h4>Summary</h4>
          <p>{summary}</p>
        </div>
      )}

      {insights && insights.length > 0 && (
        <div className="insights-block">
          <h4>Key Insights</h4>
          <ul>
            {insights.map((insight, i) => (
              <li key={i}>{insight}</li>
            ))}
          </ul>
        </div>
      )}

      {questionsRaised && questionsRaised.length > 0 && (
        <div className="questions-block">
          <h4>Questions Raised</h4>
          <ul>
            {questionsRaised.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}

      {showThoughtStream && thoughtStream && thoughtStream.length > 0 && (
        <div className="thought-stream-block">
          <h4>Thought Stream ({thoughtStream.length})</h4>
          <div className="thought-stream">
            {thoughtStream.map((thought, i) => (
              <div key={i} className="thought-entry">
                <div className="thought-header">
                  <span
                    className="thought-type"
                    style={{ color: getThoughtTypeColor(thought.thought_type) }}
                  >
                    {thought.thought_type}
                  </span>
                  <span className="thought-time">{formatTimestamp(thought.timestamp)}</span>
                  <span className="thought-confidence">
                    {Math.round(parseFloat(String(thought.confidence)) * 100)}%
                  </span>
                </div>
                <p className="thought-content">{thought.content}</p>
                {thought.related_concepts && thought.related_concepts.length > 0 && (
                  <div className="thought-concepts">
                    {thought.related_concepts.map((c, j) => (
                      <span key={j} className="concept-tag">{c}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
