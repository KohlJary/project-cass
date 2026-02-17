/**
 * Agency - Cass's autonomous goal formation and outreach capabilities
 *
 * Promoted to its own page as the most important admin function
 * (approving autonomous actions).
 */
import { AgencyTab } from './tabs/AgencyTab';
import './Agency.css';

export function Agency() {
  return (
    <div className="agency-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Agency</h1>
          <p className="subtitle">
            Autonomous goal formation, outreach, and autonomy progression
          </p>
        </div>
      </header>

      <div className="agency-content">
        <AgencyTab />
      </div>
    </div>
  );
}
