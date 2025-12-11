import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { WikiTab } from './tabs/WikiTab';
import { ResearchTab } from './tabs/ResearchTab';
import { GoalsTab } from './tabs/GoalsTab';
import './Knowledge.css';

type TabId = 'wiki' | 'research' | 'goals';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'wiki', label: 'Wiki', icon: 'W' },
  { id: 'research', label: 'Research', icon: 'R' },
  { id: 'goals', label: 'Goals', icon: '◎' },
];

export function Knowledge() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'wiki'
  );

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <div className="knowledge-page">
      <header className="page-header">
        <h1>Knowledge</h1>
        <p className="subtitle">Wiki, research, and goals</p>
      </header>

      <nav className="knowledge-tabs" role="tablist" aria-label="Knowledge sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`${tab.id}-panel`}
            className={`knowledge-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <div className="knowledge-content">
        {activeTab === 'wiki' && <WikiTab />}
        {activeTab === 'research' && <ResearchTab />}
        {activeTab === 'goals' && <GoalsTab />}
      </div>
    </div>
  );
}
