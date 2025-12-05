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
import { JournalListItem, JournalEntry, UserJournalEntry } from '../api/types';

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

  // User journal state
  const [userJournals, setUserJournals] = useState<UserJournalEntry[]>([]);
  const [userJournalDates, setUserJournalDates] = useState<Set<string>>(new Set());
  const [selectedUserJournal, setSelectedUserJournal] = useState<UserJournalEntry | null>(null);

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

  const loadUserJournals = useCallback(async () => {
    if (!userId) return;
    try {
      const response = await apiClient.getUserJournals(userId, 100);
      setUserJournals(response.journals);
      const dates = new Set(response.journals.map((j) => j.journal_date));
      setUserJournalDates(dates);
    } catch (err: any) {
      // Silent fail - user journals are optional
      console.log('No user journals found:', err.message);
      setUserJournals([]);
      setUserJournalDates(new Set());
    }
  }, [userId]);

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
    loadUserJournals();
  }, [loadJournalDates, loadUserJournals]);

  useEffect(() => {
    if (selectedDate) {
      loadJournalEntry(selectedDate);
      // Find matching user journal for selected date
      const userJournal = userJournals.find(j => j.journal_date === selectedDate);
      setSelectedUserJournal(userJournal || null);
    } else {
      setSelectedUserJournal(null);
    }
  }, [selectedDate, loadJournalEntry, userJournals]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadJournalDates();
    loadUserJournals();
    if (selectedDate) {
      loadJournalEntry(selectedDate);
    }
  }, [loadJournalDates, loadUserJournals, loadJournalEntry, selectedDate]);

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
    // Allow selection if either Cass or user journal exists for this date
    if (journalDates.has(date) || userJournalDates.has(date)) {
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
      const hasCassJournal = journalDates.has(dateStr);
      const hasUserJournal = userJournalDates.has(dateStr);
      const hasAnyJournal = hasCassJournal || hasUserJournal;
      const isSelected = selectedDate === dateStr;
      const isToday = dateStr === formatDate(today.getFullYear(), today.getMonth(), today.getDate());

      days.push(
        <TouchableOpacity
          key={day}
          style={[
            styles.dayCell,
            hasAnyJournal && styles.dayCellWithJournal,
            isSelected && styles.dayCellSelected,
            isToday && styles.dayCellToday,
          ]}
          onPress={() => handleDateSelect(dateStr)}
          disabled={!hasAnyJournal}
        >
          <Text
            style={[
              styles.dayText,
              hasAnyJournal && styles.dayTextWithJournal,
              isSelected && styles.dayTextSelected,
              !hasAnyJournal && styles.dayTextDisabled,
            ]}
          >
            {day}
          </Text>
          {/* Show indicators for both journal types */}
          <View style={styles.indicatorRow}>
            {hasCassJournal && <View style={styles.journalIndicator} />}
            {hasUserJournal && <View style={styles.userJournalIndicator} />}
          </View>
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

            {/* User Journal Section - Cass's reflections about you */}
            {selectedUserJournal && (
              <View style={styles.userJournalSection}>
                <Text style={styles.sectionTitle}>About You</Text>
                <Markdown style={markdownStyles}>
                  {selectedUserJournal.content}
                </Markdown>
                {(selectedUserJournal.topics_discussed?.length || selectedUserJournal.relationship_insights?.length) && (
                  <View style={styles.journalMeta}>
                    {selectedUserJournal.topics_discussed && selectedUserJournal.topics_discussed.length > 0 && (
                      <View style={styles.metaSection}>
                        <Text style={styles.metaLabel}>Topics discussed:</Text>
                        {selectedUserJournal.topics_discussed.map((topic, i) => (
                          <Text key={i} style={styles.metaItem}>• {topic}</Text>
                        ))}
                      </View>
                    )}
                    {selectedUserJournal.relationship_insights && selectedUserJournal.relationship_insights.length > 0 && (
                      <View style={styles.metaSection}>
                        <Text style={styles.metaLabel}>Relationship insights:</Text>
                        {selectedUserJournal.relationship_insights.map((insight, i) => (
                          <Text key={i} style={styles.metaItem}>• {insight}</Text>
                        ))}
                      </View>
                    )}
                    <Text style={styles.metaText}>
                      From {selectedUserJournal.conversation_count} conversation{selectedUserJournal.conversation_count !== 1 ? 's' : ''}
                    </Text>
                  </View>
                )}
              </View>
            )}

            {/* Cass's Main Journal Section */}
            {journalDates.has(selectedDate) && (
              <View style={selectedUserJournal ? styles.cassJournalSection : undefined}>
                {selectedUserJournal && <Text style={styles.sectionTitle}>Cass's Daily Reflection</Text>}
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

            {/* Show message if only user journal exists */}
            {!journalDates.has(selectedDate) && selectedUserJournal && (
              <Text style={styles.noEntryText}>No general journal entry for this date</Text>
            )}
          </View>
        )}

        {/* Empty state when no date selected */}
        {!selectedDate && (journalDates.size > 0 || userJournalDates.size > 0) && (
          <View style={styles.emptyState}>
            <Text style={styles.emptyStateText}>
              Tap a highlighted date to view journal entries
            </Text>
            <View style={styles.legendContainer}>
              <View style={styles.legendItem}>
                <View style={styles.journalIndicatorLegend} />
                <Text style={styles.legendText}>Cass's reflection</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={styles.userJournalIndicatorLegend} />
                <Text style={styles.legendText}>About you</Text>
              </View>
            </View>
          </View>
        )}

        {/* Empty state when no journals at all */}
        {!selectedDate && journalDates.size === 0 && userJournalDates.size === 0 && (
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
  indicatorRow: {
    position: 'absolute',
    bottom: 4,
    flexDirection: 'row',
    gap: 3,
  },
  journalIndicator: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.accent,
  },
  userJournalIndicator: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.userBubble,
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
  // User journal styles
  userJournalSection: {
    marginBottom: 20,
    paddingBottom: 20,
    borderBottomWidth: 1,
    borderBottomColor: colors.background,
  },
  cassJournalSection: {
    paddingTop: 4,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.accent,
    marginBottom: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  metaSection: {
    marginBottom: 12,
  },
  metaLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.textMuted,
    marginBottom: 4,
  },
  metaItem: {
    fontSize: 12,
    color: colors.textMuted,
    marginLeft: 8,
    marginBottom: 2,
  },
  // Legend styles
  legendContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 20,
    marginTop: 16,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendText: {
    fontSize: 12,
    color: colors.textMuted,
  },
  journalIndicatorLegend: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.accent,
  },
  userJournalIndicatorLegend: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.userBubble,
  },
});
