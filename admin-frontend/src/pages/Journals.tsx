import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { journalsApi } from '../api/client';
import './Journals.css';

interface JournalEntry {
  date: string;
  summary: string;
  locked: boolean;
}

export function Journals() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
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
    enabled: !!selectedDate,
    retry: false,
  });

  // Build a set of dates with journals for quick lookup
  const journalDates = useMemo(() => {
    const dates = new Set<string>();
    journalsData?.journals?.forEach((j: JournalEntry) => dates.add(j.date));
    return dates;
  }, [journalsData]);

  // Generate calendar days
  const calendarDays = useMemo(() => {
    const { year, month } = currentMonth;
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startPadding = firstDay.getDay(); // 0 = Sunday
    const totalDays = lastDay.getDate();

    const days: Array<{ date: string | null; day: number | null; hasJournal: boolean }> = [];

    // Add padding for days before the 1st
    for (let i = 0; i < startPadding; i++) {
      days.push({ date: null, day: null, hasJournal: false });
    }

    // Add actual days
    for (let day = 1; day <= totalDays; day++) {
      const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      days.push({
        date,
        day,
        hasJournal: journalDates.has(date),
      });
    }

    return days;
  }, [currentMonth, journalDates]);

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  const goToPrevMonth = () => {
    setCurrentMonth((prev) => {
      if (prev.month === 0) {
        return { year: prev.year - 1, month: 11 };
      }
      return { ...prev, month: prev.month - 1 };
    });
  };

  const goToNextMonth = () => {
    setCurrentMonth((prev) => {
      if (prev.month === 11) {
        return { year: prev.year + 1, month: 0 };
      }
      return { ...prev, month: prev.month + 1 };
    });
  };

  return (
    <div className="journals-page">
      <header className="page-header">
        <h1>Journals</h1>
        <p className="subtitle">Cass's daily reflections</p>
      </header>

      <div className="journals-layout">
        {/* Calendar panel */}
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
              {calendarDays.map((d, i) => (
                <div
                  key={i}
                  className={`day-cell ${d.date ? 'valid' : 'empty'} ${d.hasJournal ? 'has-journal' : ''} ${d.date === selectedDate ? 'selected' : ''}`}
                  onClick={() => d.date && d.hasJournal && setSelectedDate(d.date)}
                >
                  {d.day && (
                    <>
                      <span className="day-number">{d.day}</span>
                      {d.hasJournal && <span className="journal-dot" />}
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Journal list below calendar */}
          <div className="journal-list">
            <h3>Recent Entries</h3>
            {isLoading ? (
              <div className="loading-state small">Loading...</div>
            ) : error ? (
              <div className="error-state small">Failed to load</div>
            ) : journalsData?.journals?.length > 0 ? (
              <div className="entries">
                {journalsData.journals.slice(0, 10).map((journal: JournalEntry) => (
                  <div
                    key={journal.date}
                    className={`entry ${selectedDate === journal.date ? 'selected' : ''}`}
                    onClick={() => setSelectedDate(journal.date)}
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
        </div>

        {/* Journal reader */}
        <div className="reader-panel">
          {selectedDate ? (
            detailLoading ? (
              <div className="loading-state">Loading journal...</div>
            ) : journalDetail ? (
              <div className="journal-content">
                <div className="journal-header">
                  <div className="date-display">
                    <span className="date-badge">{selectedDate}</span>
                    {journalDetail.metadata?.locked && (
                      <span className="locked-badge">Locked</span>
                    )}
                  </div>
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
          ) : (
            <div className="empty-state">
              <div className="empty-icon">#</div>
              <p>Select a date with a journal entry</p>
              <p className="hint">Dates with journals are marked with a purple dot</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
