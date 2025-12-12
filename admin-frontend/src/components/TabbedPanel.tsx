import { useState, type ReactNode } from 'react';
import './TabbedPanel.css';

export interface Tab {
  id: string;
  label: string;
  icon?: string;
  content: ReactNode;
}

interface TabbedPanelProps {
  tabs: Tab[];
  defaultTab?: string;
  className?: string;
}

export function TabbedPanel({ tabs, defaultTab, className = '' }: TabbedPanelProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0]?.id);

  const activeContent = tabs.find(t => t.id === activeTab)?.content;

  return (
    <div className={`tabbed-panel ${className}`}>
      <div className="tabbed-panel-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tabbed-panel-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon && <span className="tab-icon">{tab.icon}</span>}
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tabbed-panel-content">
        {activeContent}
      </div>
    </div>
  );
}
