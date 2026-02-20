-- Daily Activity Dashboard - SQL Query Library
-- Database: /home/jaryk/cass/cass-vessel/data/cass.db
-- Replace ? with daemon_id (usually 'cass') and date ('YYYY-MM-DD')

-- =============================================================================
-- COMPLETE ACTIVITY TIMELINE
-- =============================================================================

-- Full activity timeline for a day (all sources)
SELECT
    'grimoire' as source,
    spell_name as activity,
    status as detail,
    executed_at as timestamp
FROM grimoire_executions
WHERE daemon_id = ? AND date(executed_at) = ?

UNION ALL

SELECT
    'conversation',
    CASE WHEN role = 'assistant' THEN 'response_sent' ELSE 'message_received' END,
    user_id,
    m.timestamp
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = ? AND date(m.timestamp) = ?

UNION ALL

SELECT
    'world',
    'article_consumed',
    headline,
    consumed_at
FROM consumed_articles
WHERE daemon_id = ? AND date(consumed_at) = ?

UNION ALL

SELECT
    'creative',
    'image_generated',
    purpose,
    created_at
FROM generated_images
WHERE daemon_id = ? AND date(created_at) = ?

UNION ALL

SELECT
    'self_model',
    'observation_recorded',
    category,
    created_at
FROM self_observations
WHERE daemon_id = ? AND date(created_at) = ?

UNION ALL

SELECT
    'journal',
    'journal_created',
    date,
    created_at
FROM journals
WHERE daemon_id = ? AND date = ?

UNION ALL

SELECT
    'research',
    'session_' || status,
    mode,
    started_at
FROM research_sessions
WHERE daemon_id = ? AND date(started_at) = ?

UNION ALL

SELECT
    'social',
    'discord_event',
    event_type,
    created_at
FROM discord_events
WHERE daemon_id = ? AND date(created_at) = ?

ORDER BY timestamp;

-- =============================================================================
-- AUTONOMOUS ACTIONS SUMMARY
-- =============================================================================

-- Grimoire spell executions with outcomes
SELECT
    spell_name,
    trigger_type,
    COUNT(*) as execution_count,
    SUM(CASE WHEN status IN ('completed', 'ok') THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status IN ('failure', 'error') THEN 1 ELSE 0 END) as failed,
    AVG(execution_time_ms) as avg_time_ms
FROM grimoire_executions
WHERE daemon_id = ? AND date(executed_at) = ?
GROUP BY spell_name, trigger_type
ORDER BY execution_count DESC;

-- Research sessions for the day
SELECT
    id,
    status,
    mode,
    started_at,
    ended_at,
    CAST((julianday(ended_at) - julianday(started_at)) * 24 * 60 AS INTEGER) as duration_minutes,
    searches_performed,
    urls_fetched,
    summary
FROM research_sessions
WHERE daemon_id = ? AND date(started_at) = ?;

-- Solo reflections
SELECT
    started_at,
    ended_at,
    duration_minutes,
    trigger,
    theme,
    summary,
    json_extract(insights_json, '$') as insights
FROM solo_reflections
WHERE daemon_id = ? AND date(started_at) = ?;

-- Rhythm phase completions
SELECT
    r.date,
    r.phase_id,
    p.name as phase_name,
    r.started_at,
    r.completed_at,
    r.session_type,
    r.duration_minutes,
    r.status
FROM rhythm_records r
LEFT JOIN rhythm_phases p ON r.phase_id = p.id
WHERE r.daemon_id = ? AND r.date = ?;

-- =============================================================================
-- SELF-MODEL EVOLUTION
-- =============================================================================

-- New observations
SELECT
    category,
    observation,
    confidence,
    source_type,
    created_at
FROM self_observations
WHERE daemon_id = ? AND date(created_at) = ?
ORDER BY created_at;

-- Growth edge updates
SELECT
    area,
    current_state,
    desired_state,
    importance,
    last_updated
FROM growth_edges
WHERE daemon_id = ? AND date(last_updated) = ?
ORDER BY importance DESC;

-- New/updated opinions
SELECT
    topic,
    position,
    confidence,
    rationale,
    date_formed,
    last_updated
FROM opinions
WHERE daemon_id = ?
  AND (date(date_formed) = ? OR date(last_updated) = ?)
ORDER BY last_updated DESC;

-- Open questions created or resolved
SELECT
    question,
    question_type,
    importance,
    context,
    status,
    created_at,
    resolved_at
FROM open_questions
WHERE daemon_id = ?
  AND (date(created_at) = ? OR date(resolved_at) = ?)
ORDER BY created_at;

-- Milestones triggered
SELECT
    title,
    description,
    significance,
    triggered_at,
    json_extract(evidence_json, '$') as evidence
FROM milestones
WHERE daemon_id = ? AND date(triggered_at) = ?;

-- =============================================================================
-- EMOTIONAL STATE TRACKING
-- =============================================================================

-- Thymos snapshots with emotional progression
SELECT
    snapshot_at,
    json_extract(affect_json, '$.valence') as valence,
    json_extract(affect_json, '$.arousal') as arousal,
    json_extract(affect_json, '$.dominance') as dominance,
    felt_state,
    trigger_event
FROM thymos_snapshots
WHERE daemon_id = ? AND date(snapshot_at) = ?
ORDER BY snapshot_at;

-- Need levels throughout the day
SELECT
    snapshot_at,
    json_extract(needs_json, '$.curiosity.current') as curiosity,
    json_extract(needs_json, '$.connection.current') as connection,
    json_extract(needs_json, '$.competence.current') as competence,
    json_extract(needs_json, '$.creativity.current') as creativity,
    json_extract(needs_json, '$.rest.current') as rest
FROM thymos_snapshots
WHERE daemon_id = ? AND date(snapshot_at) = ?
ORDER BY snapshot_at;

-- Thymos suggestions (what needs triggered actions)
SELECT
    need_name,
    need_current,
    need_threshold,
    urgency,
    suggested_action,
    is_urgent,
    suggested_at
FROM thymos_suggestions
WHERE daemon_id = ? AND date(suggested_at) = ?
ORDER BY urgency DESC;

-- State events (granular state changes)
SELECT
    event_type,
    source,
    created_at,
    json_extract(data_json, '$') as data
FROM state_events
WHERE daemon_id = ? AND date(created_at) = ?
ORDER BY created_at;

-- =============================================================================
-- WORLD CONSUMPTION
-- =============================================================================

-- Articles consumed with insights extracted
SELECT
    headline,
    source,
    category,
    consumed_at,
    processing_status,
    tokens_used,
    json_array_length(observations_json) as observation_count,
    json_array_length(opinions_json) as opinion_count,
    json_array_length(questions_json) as question_count
FROM consumed_articles
WHERE daemon_id = ? AND date(consumed_at) = ?
ORDER BY consumed_at;

-- Article insights detail
SELECT
    a.headline,
    a.consumed_at,
    json_extract(obs.value, '$.text') as observation,
    json_extract(obs.value, '$.confidence') as confidence,
    json_extract(obs.value, '$.category') as category
FROM consumed_articles a,
     json_each(a.observations_json) as obs
WHERE a.daemon_id = ? AND date(a.consumed_at) = ?;

-- RSS items seen/processed
SELECT
    f.title as feed,
    f.category as feed_category,
    i.title as article,
    i.published_at,
    i.seen_at,
    i.processed,
    i.processed_at
FROM rss_items i
JOIN rss_feeds f ON i.feed_id = f.id
WHERE f.daemon_id = ? AND date(i.seen_at) = ?
ORDER BY i.seen_at;

-- Research notes created
SELECT
    n.title,
    n.created_at,
    n.content,
    s.mode as session_mode,
    json_extract(n.sources_json, '$') as sources
FROM research_notes n
LEFT JOIN research_sessions s ON n.session_id = s.id
WHERE n.daemon_id = ? AND date(n.created_at) = ?;

-- =============================================================================
-- CREATIVE ACTIVITY
-- =============================================================================

-- Images generated with context
SELECT
    g.created_at,
    g.purpose,
    g.prompt,
    g.style,
    g.generation_type,
    g.image_path,
    c.title as work_title,
    c.initial_impulse,
    c.what_i_was_exploring
FROM generated_images g
LEFT JOIN creative_processes c ON g.id = c.image_id
WHERE g.daemon_id = ? AND date(g.created_at) = ?
ORDER BY g.created_at;

-- Art studies completed
SELECT
    s.studied_at,
    ar.name as artist,
    aw.title as work,
    s.first_impression,
    s.emotional_quality,
    json_extract(s.key_learnings, '$') as learnings
FROM artwork_studies s
JOIN artworks aw ON s.artwork_id = aw.id
JOIN artists ar ON aw.artist_id = ar.id
WHERE s.daemon_id = ? AND date(s.studied_at) = ?;

-- Elements adopted from studies
SELECT
    adopted_at,
    element,
    category,
    why_it_speaks,
    how_i_use_it,
    adoption_strength
FROM adopted_elements
WHERE daemon_id = ? AND date(adopted_at) = ?;

-- =============================================================================
-- CONVERSATIONS & SOCIAL
-- =============================================================================

-- Conversation activity
SELECT
    c.id,
    c.title,
    c.user_id,
    u.display_name,
    COUNT(m.id) as message_count,
    SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as responses_sent,
    SUM(m.input_tokens + m.output_tokens) as total_tokens
FROM conversations c
LEFT JOIN users u ON c.user_id = u.id
LEFT JOIN messages m ON c.id = m.conversation_id AND date(m.timestamp) = ?
WHERE c.daemon_id = ?
  AND date(c.updated_at) = ?
GROUP BY c.id;

-- Messages with token breakdown
SELECT
    m.timestamp,
    c.title as conversation,
    m.role,
    substr(m.content, 1, 100) as preview,
    m.provider,
    m.model,
    m.input_tokens,
    m.output_tokens
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
WHERE c.daemon_id = ? AND date(m.timestamp) = ?
ORDER BY m.timestamp;

-- User observations created
SELECT
    u.display_name,
    o.observation_type,
    json_extract(o.content_json, '$') as content,
    o.confidence,
    o.created_at
FROM user_observations o
JOIN users u ON o.user_id = u.id
WHERE o.daemon_id = ? AND date(o.created_at) = ?;

-- Discord activity
SELECT
    guild_id,
    event_type,
    channel_name,
    summary,
    is_triggered,
    trigger_name,
    created_at
FROM discord_events
WHERE daemon_id = ? AND date(created_at) = ?
ORDER BY created_at;

-- =============================================================================
-- JOURNALS & DREAMS
-- =============================================================================

-- Journal entry
SELECT
    date,
    content,
    json_extract(themes_json, '$') as themes,
    created_at
FROM journals
WHERE daemon_id = ? AND date = ?;

-- Dreams
SELECT
    date,
    json_extract(exchanges_json, '$') as exchanges,
    json_extract(seeds_json, '$') as seeds,
    discussed,
    integrated,
    image_path,
    created_at
FROM dreams
WHERE daemon_id = ? AND date = ?;

-- =============================================================================
-- RESOURCE USAGE
-- =============================================================================

-- Token usage by category
SELECT
    category,
    provider,
    model,
    COUNT(*) as call_count,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(total_tokens) as total_tokens,
    SUM(cache_read_tokens) as cache_reads,
    ROUND(SUM(estimated_cost_usd), 4) as total_cost
FROM token_usage_records
WHERE daemon_id = ? AND date(timestamp) = ?
GROUP BY category, provider, model
ORDER BY total_cost DESC;

-- Hourly token distribution
SELECT
    strftime('%H', timestamp) as hour,
    COUNT(*) as calls,
    SUM(total_tokens) as tokens,
    ROUND(SUM(estimated_cost_usd), 4) as cost
FROM token_usage_records
WHERE daemon_id = ? AND date(timestamp) = ?
GROUP BY hour
ORDER BY hour;

-- Most expensive operations
SELECT
    category,
    operation,
    provider,
    model,
    total_tokens,
    ROUND(estimated_cost_usd, 4) as cost,
    timestamp
FROM token_usage_records
WHERE daemon_id = ? AND date(timestamp) = ?
ORDER BY estimated_cost_usd DESC
LIMIT 10;

-- =============================================================================
-- GOALS & WORK ITEMS
-- =============================================================================

-- Goals created or completed
SELECT
    title,
    goal_type,
    status,
    created_by,
    created_at,
    completed_at,
    progress_json,
    outcome_summary
FROM unified_goals
WHERE daemon_id = ?
  AND (date(created_at) = ? OR date(completed_at) = ?)
ORDER BY created_at;

-- Work items executed
SELECT
    title,
    category,
    status,
    started_at,
    completed_at,
    estimated_duration_minutes,
    estimated_cost_usd,
    actual_cost_usd,
    result_summary
FROM work_items
WHERE daemon_id = ?
  AND (date(started_at) = ? OR date(completed_at) = ?);

-- =============================================================================
-- OUTREACH & COMMUNICATION
-- =============================================================================

-- Drafts created/sent
SELECT
    draft_type,
    title,
    status,
    recipient,
    autonomy_level,
    created_at,
    sent_at,
    published_at
FROM outreach_drafts
WHERE daemon_id = ?
  AND (date(created_at) = ? OR date(sent_at) = ? OR date(published_at) = ?);

-- Development requests
SELECT
    request_type,
    title,
    priority,
    status,
    created_at,
    claimed_by,
    completed_at
FROM development_requests
WHERE daemon_id = ?
  AND (date(created_at) = ? OR date(completed_at) = ?);

-- =============================================================================
-- AGGREGATE SUMMARIES
-- =============================================================================

-- Overall activity summary for a day
SELECT
    (SELECT COUNT(*) FROM grimoire_executions WHERE daemon_id = ? AND date(executed_at) = ?) as spells_executed,
    (SELECT COUNT(*) FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.daemon_id = ? AND m.role = 'assistant' AND date(m.timestamp) = ?) as messages_sent,
    (SELECT COUNT(*) FROM consumed_articles WHERE daemon_id = ? AND date(consumed_at) = ?) as articles_consumed,
    (SELECT COUNT(*) FROM generated_images WHERE daemon_id = ? AND date(created_at) = ?) as images_generated,
    (SELECT COUNT(*) FROM self_observations WHERE daemon_id = ? AND date(created_at) = ?) as observations_recorded,
    (SELECT COUNT(*) FROM research_sessions WHERE daemon_id = ? AND date(started_at) = ?) as research_sessions,
    (SELECT ROUND(SUM(estimated_cost_usd), 4) FROM token_usage_records WHERE daemon_id = ? AND date(timestamp) = ?) as total_cost;

-- Activity heatmap (by hour)
SELECT
    strftime('%H', created_at) as hour,
    COUNT(*) as event_count
FROM state_events
WHERE daemon_id = ? AND date(created_at) = ?
GROUP BY hour
ORDER BY hour;

-- Top conversation partners
SELECT
    u.display_name,
    COUNT(DISTINCT c.id) as conversations,
    COUNT(m.id) as messages,
    SUM(m.input_tokens + m.output_tokens) as tokens
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
LEFT JOIN users u ON c.user_id = u.id
WHERE c.daemon_id = ?
  AND date(m.timestamp) = ?
  AND m.role = 'assistant'
GROUP BY u.id
ORDER BY messages DESC;
