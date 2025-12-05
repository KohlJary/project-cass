/**
 * Growth screen - journal calendar and viewer
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Markdown from 'react-native-markdown-display';
import { colors } from '../theme/colors';
import { apiClient } from '../api/client';
import { JournalListItem, JournalEntry } from '../api/types';

// Calendar helper functions
const getDaysInMonth = (year: number, month: number): number => {
  return new Date(year, month + 1, 0).getDate();
};

const getFirstDayOfMonth = (year: number, month: number): number => {
  return new Date(year, month, 1).getDay();
};

const formatDate = (year: number, month: number, day: number): string => {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
};

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

interface Props {
  userId: string;
}

export function GrowthScreen({ userId }: Props) {
  const today = new Date();
  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth());
  const [journalDates, setJournalDates] = useState<Set<string>>(new Set());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [journalEntry, setJournalEntry] = useState<JournalEntry | null>(null);
  const [isLoadingDates, setIsLoadingDates] = useState(true);
  const [isLoadingEntry, setIsLoadingEntry] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJournalDates = useCallback(async () => {
    try {
      setError(null);
      const { journals } = await apiClient.listJournals(100);
      const dates = new Set(journals.map((j: JournalListItem) => j.date));
      setJournalDates(dates);
    } catch (err: any) {
      console.error('Failed to load journal dates:', err);
      setError('Failed to load journals');
    } finally {
      setIsLoadingDates(false);
      setRefreshing(false);
    }
  }, []);

  const loadJournalEntry = useCallback(async (date: string) => {
    setIsLoadingEntry(true);
    setError(null);
    try {
      const entry = await apiClient.getJournal(date);
      setJournalEntry(entry);
    } catch (err: any) {
      console.error('Failed to load journal entry:', err);
      setError('Failed to load journal entry');
      setJournalEntry(null);
    } finally {
      setIsLoadingEntry(false);
    }
  }, []);

  useEffect(() => {
    loadJournalDates();
  }, [loadJournalDates]);

  useEffect(() => {
    if (selectedDate) {
      loadJournalEntry(selectedDate);
    }
  }, [selectedDate, loadJournalEntry]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadJournalDates();
    if (selectedDate) {
      loadJournalEntry(selectedDate);
    }
  }, [loadJournalDates, loadJournalEntry, selectedDate]);

  const goToPreviousMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear(currentYear - 1);
    } else {
      setCurrentMonth(currentMonth - 1);
    }
  };

  const goToNextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear(currentYear + 1);
    } else {
      setCurrentMonth(currentMonth + 1);
    }
  };

  const handleDateSelect = (date: string) => {
    if (journalDates.has(date)) {
      setSelectedDate(date);
    }
  };

  const renderCalendar = () => {
    const daysInMonth = getDaysInMonth(currentYear, currentMonth);
    const firstDay = getFirstDayOfMonth(currentYear, currentMonth);
    const days: React.ReactNode[] = [];

    // Empty cells for days before the first of the month
    for (let i = 0; i < firstDay; i++) {
      days.push(<View key={`empty-${i}`} style={styles.dayCell} />);
    }

    // Day cells
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = formatDate(currentYear, currentMonth, day);
      const hasJournal = journalDates.has(dateStr);
      const isSelected = selectedDate === dateStr;
      const isToday = dateStr === formatDate(today.getFullYear(), today.getMonth(), today.getDate());

      days.push(
        <TouchableOpacity
          key={day}
          style={[
            styles.dayCell,
            hasJournal && styles.dayCellWithJournal,
            isSelected && styles.dayCellSelected,
            isToday && styles.dayCellToday,
          ]}
          onPress={() => handleDateSelect(dateStr)}
          disabled={!hasJournal}
        >
          <Text
            style={[
              styles.dayText,
              hasJournal && styles.dayTextWithJournal,
              isSelected && styles.dayTextSelected,
              !hasJournal && styles.dayTextDisabled,
            ]}
          >
            {day}
          </Text>
          {hasJournal && <View style={styles.journalIndicator} />}
        </TouchableOpacity>
      );
    }

    return days;
  };

  const markdownStyles = {
    body: {
      color: colors.textPrimary,
      fontSize: 15,
      lineHeight: 22,
    },
    heading1: {
      color: colors.textPrimary,
      fontSize: 22,
      fontWeight: '700' as const,
      marginTop: 16,
      marginBottom: 8,
    },
    heading2: {
      color: colors.textPrimary,
      fontSize: 18,
      fontWeight: '600' as const,
      marginTop: 14,
      marginBottom: 6,
    },
    heading3: {
      color: colors.textPrimary,
      fontSize: 16,
      fontWeight: '600' as const,
      marginTop: 12,
      marginBottom: 4,
    },
    paragraph: {
      color: colors.textMuted,
      marginBottom: 10,
    },
    strong: {
      color: colors.textPrimary,
      fontWeight: '600' as const,
    },
    em: {
      fontStyle: 'italic' as const,
    },
    blockquote: {
      backgroundColor: colors.surface,
      borderLeftWidth: 4,
      borderLeftColor: colors.accent,
      paddingLeft: 12,
      paddingVertical: 8,
      marginVertical: 8,
    },
    code_inline: {
      backgroundColor: colors.surface,
      color: colors.accent,
      paddingHorizontal: 4,
      borderRadius: 4,
      fontFamily: 'monospace',
    },
    fence: {
      backgroundColor: colors.surface,
      padding: 12,
      borderRadius: 8,
      fontFamily: 'monospace',
    },
    list_item: {
      color: colors.textMuted,
      marginBottom: 4,
    },
  };

  if (isLoadingDates) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.accent} />
          <Text style={styles.loadingText}>Loading journals...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Growth</Text>
          <Text style={styles.subtitle}>Cass's daily reflections</Text>
        </View>

        {/* Calendar */}
        <View style={styles.calendarContainer}>
          <View style={styles.calendarHeader}>
            <TouchableOpacity onPress={goToPreviousMonth} style={styles.navButton}>
              <Text style={styles.navButtonText}>◀</Text>
            </TouchableOpacity>
            <Text style={styles.monthTitle}>
              {MONTH_NAMES[currentMonth]} {currentYear}
            </Text>
            <TouchableOpacity onPress={goToNextMonth} style={styles.navButton}>
              <Text style={styles.navButtonText}>▶</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.dayNamesRow}>
            {DAY_NAMES.map(day => (
              <Text key={day} style={styles.dayName}>{day}</Text>
            ))}
          </View>

          <View style={styles.calendarGrid}>
            {renderCalendar()}
          </View>
        </View>

        {/* Journal Entry Viewer */}
        {selectedDate && (
          <View style={styles.journalContainer}>
            <View style={styles.journalHeader}>
              <Text style={styles.journalDateTitle}>
                {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </Text>
              <TouchableOpacity
                onPress={() => setSelectedDate(null)}
                style={styles.closeButton}
              >
                <Text style={styles.closeButtonText}>✕</Text>
              </TouchableOpacity>
            </View>

            {isLoadingEntry ? (
              <View style={styles.entryLoading}>
                <ActivityIndicator size="small" color={colors.accent} />
                <Text style={styles.loadingText}>Loading entry...</Text>
              </View>
            ) : error ? (
              <Text style={styles.errorText}>{error}</Text>
            ) : journalEntry ? (
              <View style={styles.journalContent}>
                <Markdown style={markdownStyles}>
                  {journalEntry.content}
                </Markdown>
                {journalEntry.metadata && (
                  <View style={styles.journalMeta}>
                    {journalEntry.metadata.summary_count !== undefined && (
                      <Text style={styles.metaText}>
                        Based on {journalEntry.metadata.summary_count} summaries
                      </Text>
                    )}
                    {journalEntry.metadata.conversation_count !== undefined && (
                      <Text style={styles.metaText}>
                        From {journalEntry.metadata.conversation_count} conversations
                      </Text>
                    )}
                  </View>
                )}
              </View>
            ) : (
              <Text style={styles.noEntryText}>No journal entry for this date</Text>
            )}
          </View>
        )}

        {/* Empty state when no date selected */}
        {!selectedDate && journalDates.size > 0 && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>
              Tap a highlighted date to view Cass's journal entry
            </Text>
          </View>
        )}

        {/* Empty state when no journals at all */}
        {!selectedDate && journalDates.size === 0 && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateTitle}>No journal entries yet</Text>
            <Text style={styles.emptyStateText}>
              Cass writes daily reflections about conversations and growth.
              Check back after you've had some conversations!
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    color: colors.textMuted,
    fontSize: 14,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: colors.textMuted,
  },
  calendarContainer: {
    marginHorizontal: 16,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  calendarHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  navButton: {
    padding: 8,
  },
  navButtonText: {
    fontSize: 16,
    color: colors.accent,
  },
  monthTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  dayNamesRow: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  dayName: {
    flex: 1,
    textAlign: 'center',
    fontSize: 12,
    fontWeight: '600',
    color: colors.textMuted,
  },
  calendarGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  dayCell: {
    width: '14.28%',
    aspectRatio: 1,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  dayCellWithJournal: {
    backgroundColor: colors.accent + '20',
    borderRadius: 8,
  },
  dayCellSelected: {
    backgroundColor: colors.accent,
    borderRadius: 8,
  },
  dayCellToday: {
    borderWidth: 2,
    borderColor: colors.accent,
    borderRadius: 8,
  },
  dayText: {
    fontSize: 14,
    color: colors.textPrimary,
  },
  dayTextWithJournal: {
    fontWeight: '600',
  },
  dayTextSelected: {
    color: colors.textPrimary,
    fontWeight: '700',
  },
  dayTextDisabled: {
    color: colors.textMuted,
  },
  journalIndicator: {
    position: 'absolute',
    bottom: 4,
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.accent,
  },
  journalContainer: {
    marginHorizontal: 16,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
  },
  journalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  journalDateTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    flex: 1,
  },
  closeButton: {
    padding: 8,
  },
  closeButtonText: {
    fontSize: 16,
    color: colors.textMuted,
  },
  entryLoading: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  journalContent: {
    // Markdown content container
  },
  journalMeta: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.background,
  },
  metaText: {
    fontSize: 12,
    color: colors.textMuted,
    marginBottom: 4,
  },
  errorText: {
    color: colors.error,
    textAlign: 'center',
    padding: 20,
  },
  noEntryText: {
    color: colors.textMuted,
    textAlign: 'center',
    padding: 20,
    fontStyle: 'italic',
  },
  emptyState: {
    marginHorizontal: 16,
    padding: 24,
    alignItems: 'center',
  },
  emptyStateTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  emptyStateText: {
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
    lineHeight: 20,
  },
});
