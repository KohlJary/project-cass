import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SystemHealthTab } from './tabs/SystemHealthTab';
import { DataExportTab } from './tabs/DataExportTab';
import { DataImportTab } from './tabs/DataImportTab';
import { DataBackupsTab } from './tabs/DataBackupsTab';
import './Settings.css';

type TabId = 'health' | 'export' | 'import' | 'backups';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'health', label: 'System Health', icon: '!' },
  { id: 'export', label: 'Export', icon: '^' },
  { id: 'import', label: 'Import', icon: 'v' },
  { id: 'backups', label: 'Backups', icon: 'B' },
];

export function Settings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'health'
  );

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>Settings</h1>
        <p className="subtitle">System health, data export, import, and backups</p>
      </header>

      <nav className="settings-tabs" role="tablist" aria-label="Settings sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`${tab.id}-panel`}
            className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <div className="settings-content">
        {activeTab === 'health' && <SystemHealthTab />}
        {activeTab === 'export' && <DataExportTab />}
        {activeTab === 'import' && <DataImportTab />}
        {activeTab === 'backups' && <DataBackupsTab />}
      </div>
    </div>
  );
}
