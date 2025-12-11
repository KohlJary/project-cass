import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { journalsApi, researchApi } from '../../api/client';
import { StandaloneWikiReader } from '../../components/WikiReader';

interface JournalEntry {
  date: string;
  summary: string;
  locked: boolean;
}

interface ResearchCompletion {
  proposal_id: string;
  title: string;
  tasks_completed: number;
  pages_created: number;
  completed_at: string;
}

interface ProposalDetail {
  proposal_id: string;
  title: string;
  theme: string;
  rationale: string;
  status: string;
  tasks_completed: number;
  tasks_failed: number;
  summary: string;
  pages_created: string[];
  pages_updated: string[];
  completed_at: string;
  tasks: Array<{
    task_id: string;
    target: string;
    task_type: string;
    status: string;
  }>;
}

type ViewMode = 'none' | 'journal' | 'research';

export function JournalsTab() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('none');
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [currentMonth, setCurrentMonth] = useState(() => {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() };
  });

  const { data: journalsData, isLoading, error } = useQuery({
    queryKey: ['journals'],
    queryFn: () => journalsApi.getAll({ limit: 100 }).then((r) => r.data),
    retry: false,
  });

  const { data: journalDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['journal', selectedDate],
    queryFn: () =>
      selectedDate ? journalsApi.getByDate(selectedDate).then((r) => r.data) : null,
    enabled: !!selectedDate && viewMode === 'journal',
    retry: false,
  });

  const { data: researchCalendarData } = useQuery({
    queryKey: ['research-calendar'],
    queryFn: () => researchApi.getProposalsCalendar().then((r) => r.data),
    retry: false,
  });

  const { data: proposalDetail, isLoading: proposalLoading } = useQuery({
    queryKey: ['proposal', selectedProposalId],
    queryFn: async (): Promise<ProposalDetail> => {
      const response = await researchApi.getProposal(selectedProposalId!);
      return response.data;
    },
    enabled: !!selectedProposalId && viewMode === 'research',
    retry: false,
  });

  const journalDates = useMemo(() => {
    const dates = new Set<string>();
    journalsData?.journals?.forEach((j: JournalEntry) => dates.add(j.date));
    return dates;
  }, [journalsData]);

  const researchDates = useMemo(() => {
    const dates = new Set<string>();
    researchCalendarData?.dates?.forEach((d: string) => dates.add(d));
    return dates;
  }, [researchCalendarData]);

  const getResearchForDate = (date: string): ResearchCompletion[] => {
    return researchCalendarData?.by_date?.[date] || [];
  };

  const calendarDays = useMemo(() => {
    const { year, month } = currentMonth;
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startPadding = firstDay.getDay();
    const totalDays = lastDay.getDate();

    const days: Array<{ date: string | null; day: number | null; hasJournal: boolean; hasResearch: boolean }> = [];

    for (let i = 0; i < startPadding; i++) {
      days.push({ date: null, day: null, hasJournal: false, hasResearch: false });
    }

    for (let day = 1; day <= totalDays; day++) {
      const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      days.push({
        date,
        day,
        hasJournal: journalDates.has(date),
        hasResearch: researchDates.has(date),
      });
    }

    return days;
  }, [currentMonth, journalDates, researchDates]);

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const goToPrevMonth = () => {
    setCurrentMonth((prev) => {
      if (prev.month === 0) return { year: prev.year - 1, month: 11 };
      return { ...prev, month: prev.month - 1 };
    });
  };

  const goToNextMonth = () => {
    setCurrentMonth((prev) => {
      if (prev.month === 11) return { year: prev.year + 1, month: 0 };
      return { ...prev, month: prev.month + 1 };
    });
  };

  const selectedDateResearch = selectedDate ? getResearchForDate(selectedDate) : [];

  return (
    <div className="journals-tab">
      <div className="journals-layout-horizontal">
        <div className="calendar-column">
          <div className="calendar-panel">
            <div className="calendar-header">
              <button className="nav-btn" onClick={goToPrevMonth}>&lt;</button>
              <span className="month-label">
                {monthNames[currentMonth.month]} {currentMonth.year}
              </span>
              <button className="nav-btn" onClick={goToNextMonth}>&gt;</button>
            </div>

            <div className="calendar-grid">
              <div className="weekday-header">
                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
                  <div key={d} className="weekday">{d}</div>
                ))}
              </div>
              <div className="days-grid">
                {calendarDays.map((d, i) => {
                  const isSelected = d.date === selectedDate;
                  const hasActivity = d.hasJournal || d.hasResearch;

                  return (
                    <div
                      key={i}
                      className={`day-cell ${d.date ? 'valid' : 'empty'} ${d.hasJournal ? 'has-journal' : ''} ${d.hasResearch ? 'has-research' : ''} ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        if (!d.date) return;
                        setSelectedDate(d.date);
                        if (d.hasJournal) {
                          setViewMode('journal');
                          setSelectedProposalId(null);
                        } else if (d.hasResearch) {
                          const completions = getResearchForDate(d.date);
                          if (completions.length > 0) {
                            setViewMode('research');
                            setSelectedProposalId(completions[0].proposal_id);
                          }
                        } else {
                          setViewMode('none');
                          setSelectedProposalId(null);
                        }
                      }}
                    >
                      {d.day && (
                        <>
                          <span className="day-number">{d.day}</span>
                          {hasActivity && (
                            <div className="day-indicators">
                              {d.hasJournal && <span className="journal-dot" title="Journal entry" />}
                              {d.hasResearch && <span className="research-dot" title="Research completed" />}
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="calendar-legend">
              <span className="legend-item"><span className="journal-dot" /> Journal</span>
              <span className="legend-item"><span className="research-dot" /> Research</span>
            </div>
          </div>

          <div className="recent-entries-panel">
            <div className="entries-section">
              <h3>Recent Journals</h3>
              {isLoading ? (
                <div className="loading-state small">Loading...</div>
              ) : error ? (
                <div className="error-state small">Failed to load</div>
              ) : journalsData?.journals?.length > 0 ? (
                <div className="entries">
                  {journalsData.journals.slice(0, 8).map((journal: JournalEntry) => (
                    <div
                      key={journal.date}
                      className={`entry ${selectedDate === journal.date && viewMode === 'journal' ? 'selected' : ''}`}
                      onClick={() => {
                        setSelectedDate(journal.date);
                        setViewMode('journal');
                        setSelectedProposalId(null);
                      }}
                    >
                      <span className="entry-date">{journal.date}</span>
                      {journal.locked && <span className="lock-icon">*</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state small">No journals yet</div>
              )}
            </div>

            <div className="entries-section">
              <h3>Recent Research</h3>
              {researchCalendarData?.total_completed > 0 ? (
                <div className="entries">
                  {Object.entries(researchCalendarData.by_date || {})
                    .flatMap(([date, completions]) =>
                      (completions as ResearchCompletion[]).map((c) => ({ ...c, date }))
                    )
                    .slice(0, 8)
                    .map((completion) => (
                      <div
                        key={completion.proposal_id}
                        className={`entry research ${selectedProposalId === completion.proposal_id ? 'selected' : ''}`}
                        onClick={() => {
                          setSelectedDate(completion.date);
                          setViewMode('research');
                          setSelectedProposalId(completion.proposal_id);
                        }}
                      >
                        <span className="entry-title">{completion.title.substring(0, 30)}...</span>
                        <span className="entry-meta">{completion.pages_created} pages</span>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="empty-state small">No research yet</div>
              )}
            </div>
          </div>
        </div>

        <div className="detail-column">
          {selectedDate && (
            <div className="detail-header">
              <h2>{selectedDate}</h2>
              {journalDates.has(selectedDate) && researchDates.has(selectedDate) && (
                <div className="view-toggle">
                  <button
                    className={`toggle-btn ${viewMode === 'journal' ? 'active' : ''}`}
                    onClick={() => {
                      setViewMode('journal');
                      setSelectedProposalId(null);
                    }}
                  >
                    Journal
                  </button>
                  <button
                    className={`toggle-btn ${viewMode === 'research' ? 'active' : ''}`}
                    onClick={() => {
                      setViewMode('research');
                      const completions = getResearchForDate(selectedDate);
                      if (completions.length > 0) {
                        setSelectedProposalId(completions[0].proposal_id);
                      }
                    }}
                  >
                    Research ({selectedDateResearch.length})
                  </button>
                </div>
              )}
            </div>
          )}

          {viewMode === 'journal' && selectedDate && (
            detailLoading ? (
              <div className="loading-state">Loading journal...</div>
            ) : journalDetail ? (
              <div className="journal-content">
                <div className="journal-header">
                  {journalDetail.metadata?.locked && (
                    <span className="locked-badge">Locked</span>
                  )}
                  {journalDetail.metadata?.summary && (
                    <p className="journal-summary">{journalDetail.metadata.summary}</p>
                  )}
                </div>
                <div className="journal-body">
                  {journalDetail.content}
                </div>
                {journalDetail.metadata && (
                  <details className="journal-metadata">
                    <summary>Metadata</summary>
                    <pre>{JSON.stringify(journalDetail.metadata, null, 2)}</pre>
                  </details>
                )}
              </div>
            ) : (
              <div className="error-state">Failed to load journal</div>
            )
          )}

          {viewMode === 'research' && selectedProposalId && (
            proposalLoading ? (
              <div className="loading-state">Loading research...</div>
            ) : proposalDetail ? (
              <div className="research-content">
                <div className="research-header">
                  <h3 className="research-title">{proposalDetail.title}</h3>
                  <p className="research-theme">{proposalDetail.theme}</p>
                </div>

                <div className="research-stats">
                  <div className="stat">
                    <span className="stat-value">{proposalDetail.tasks_completed || 0}</span>
                    <span className="stat-label">Tasks</span>
                  </div>
                  <div className="stat">
                    <span className="stat-value">{proposalDetail.pages_created?.length || 0}</span>
                    <span className="stat-label">Pages</span>
                  </div>
                  {proposalDetail.tasks_failed > 0 && (
                    <div className="stat failed">
                      <span className="stat-value">{proposalDetail.tasks_failed}</span>
                      <span className="stat-label">Failed</span>
                    </div>
                  )}
                </div>

                {proposalDetail.summary && (
                  <div className="research-summary">
                    <h4>Summary</h4>
                    <div className="summary-text">{proposalDetail.summary}</div>
                  </div>
                )}

                {proposalDetail.pages_created && proposalDetail.pages_created.length > 0 && (
                  <div className="research-pages-section">
                    <h4>Pages Created</h4>
                    <div className="wiki-reader-container">
                      <StandaloneWikiReader
                        pageNames={proposalDetail.pages_created}
                        options={{
                          showSidebar: true,
                          showSearch: true,
                          editable: false,
                          showMaturity: false,
                          showBacklinks: true,
                          showOutgoingLinks: true,
                          compact: true,
                          maxHeight: '400px',
                        }}
                      />
                    </div>
                  </div>
                )}

                {selectedDateResearch.length > 1 && (
                  <div className="other-research">
                    <h4>Other Research on This Day</h4>
                    <div className="research-list">
                      {selectedDateResearch
                        .filter((r) => r.proposal_id !== selectedProposalId)
                        .map((r) => (
                          <div
                            key={r.proposal_id}
                            className="research-item"
                            onClick={() => setSelectedProposalId(r.proposal_id)}
                          >
                            <span className="item-title">{r.title}</span>
                            <span className="item-meta">{r.pages_created} pages</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="error-state">Failed to load research</div>
            )
          )}

          {viewMode === 'none' && (
            <div className="empty-state">
              <div className="empty-icon">#</div>
              <p>Select a date to view journals or research</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
