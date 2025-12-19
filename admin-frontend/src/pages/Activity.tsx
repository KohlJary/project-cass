import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ConversationsTab } from './tabs/ConversationsTab';
import { JournalsTab } from './tabs/JournalsTab';
import { ReflectionTab } from './tabs/ReflectionTab';
import { AutonomousResearchTab } from './tabs/AutonomousResearchTab';
import { DailyRhythmTab } from './tabs/DailyRhythmTab';
import { NarrativeTab } from './tabs/NarrativeTab';
import { StateTab } from './tabs/StateTab';
import './Activity.css';

type TabId = 'conversations' | 'journals' | 'reflection' | 'autonomous' | 'rhythm' | 'narrative' | 'state';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'conversations', label: 'Conversations', icon: '>' },
  { id: 'journals', label: 'Journals', icon: '#' },
  { id: 'reflection', label: 'Reflection', icon: '~' },
  { id: 'autonomous', label: 'Autonomous Research', icon: '*' },
  { id: 'rhythm', label: 'Daily Rhythm', icon: '@' },
  { id: 'narrative', label: 'Threads', icon: '&' },
  { id: 'state', label: 'State', icon: '%' },
];

export function Activity() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'conversations'
  );

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <div className="activity-page">
      <header className="page-header">
        <h1>Activity</h1>
        <p className="subtitle">Conversations, journals, and reflection sessions</p>
      </header>

      <nav className="activity-tabs" role="tablist" aria-label="Activity sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`${tab.id}-panel`}
            className={`activity-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <div className="activity-content">
        {activeTab === 'conversations' && <ConversationsTab />}
        {activeTab === 'journals' && <JournalsTab />}
        {activeTab === 'reflection' && <ReflectionTab />}
        {activeTab === 'autonomous' && <AutonomousResearchTab />}
        {activeTab === 'rhythm' && <DailyRhythmTab />}
        {activeTab === 'narrative' && <NarrativeTab />}
        {activeTab === 'state' && <StateTab />}
      </div>
    </div>
  );
}
