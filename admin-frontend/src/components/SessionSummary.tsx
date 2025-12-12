import ReactMarkdown from 'react-markdown';
import './SessionSummary.css';

interface SessionSummaryProps {
  summary?: string;
  findings?: string | string[];
  insights?: string[];
  questionsRaised?: string[];
  nextSteps?: string[];
  className?: string;
  compact?: boolean;
}

export function SessionSummary({
  summary,
  findings,
  insights,
  questionsRaised,
  nextSteps,
  className = '',
  compact = false,
}: SessionSummaryProps) {
  // Convert findings to array if it's a string
  const findingsList = typeof findings === 'string'
    ? findings.split('\n').filter(f => f.trim().startsWith('-')).map(f => f.replace(/^-\s*/, ''))
    : findings;

  const hasContent = summary || findingsList?.length || insights?.length || questionsRaised?.length || nextSteps?.length;

  if (!hasContent) {
    return (
      <div className={`session-summary empty ${className}`}>
        <p className="no-summary">No summary available yet</p>
      </div>
    );
  }

  return (
    <div className={`session-summary ${compact ? 'compact' : ''} ${className}`}>
      {summary && (
        <div className="summary-block">
          {!compact && <h4>Summary</h4>}
          <div className="markdown-content">
            <ReactMarkdown>{summary}</ReactMarkdown>
          </div>
        </div>
      )}

      {findingsList && findingsList.length > 0 && (
        <div className="findings-block">
          <h4>Key Findings</h4>
          <ul>
            {findingsList.map((finding, i) => (
              <li key={i}>{finding}</li>
            ))}
          </ul>
        </div>
      )}

      {insights && insights.length > 0 && (
        <div className="insights-block">
          <h4>Insights</h4>
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

      {nextSteps && nextSteps.length > 0 && (
        <div className="next-steps-block">
          <h4>Next Steps</h4>
          <ul>
            {nextSteps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
