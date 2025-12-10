"""Extracted from main_sdk.py"""


from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY, DATA_DIR
from datetime import datetime, timedelta

async def generate_and_store_summary(conversation_id: str, force: bool = False, websocket=None):
    """
    Generate a summary chunk for unsummarized messages.

    Uses local LLM to evaluate whether now is a good breakpoint for summarization,
    giving Cass agency over her own memory consolidation.

    Args:
        conversation_id: ID of conversation to summarize
        force: If True, skip evaluation and summarize immediately (for manual /summarize)
        websocket: Optional WebSocket to send status updates to TUI
    """
    async def notify(message: str, status: str = "info"):
        """Send notification to websocket if available"""
        if websocket:
            try:
                await websocket.send_json({
                    "type": "system",
                    "message": message,
                    "status": status,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception:
                pass  # Don't fail summarization if notification fails

    # Prevent duplicate summarization
    if conversation_id in _summarization_in_progress:
        print(f"Summary already in progress for conversation {conversation_id}, skipping")
        return

    _summarization_in_progress.add(conversation_id)

    try:
        # Get unsummarized messages
        messages = conversation_manager.get_unsummarized_messages(
            conversation_id,
            max_messages=SUMMARY_CONTEXT_MESSAGES
        )

        if not messages:
            print(f"No messages to summarize for conversation {conversation_id}")
            return

        # Evaluate whether now is a good time to summarize (unless forced)
        if not force:
            print(f"🔍 Evaluating summarization readiness for {len(messages)} messages...")
            await notify(f"🔍 Evaluating memory consolidation ({len(messages)} messages)...", "evaluating")
            evaluation = await memory.evaluate_summarization_readiness(messages)

            should_summarize = evaluation.get("should_summarize", False)
            confidence = evaluation.get("confidence", 0.0)
            reason = evaluation.get("reason", "No reason")

            print(f"   Evaluation: should_summarize={should_summarize}, confidence={confidence:.2f}")
            print(f"   Reason: {reason}")

            # Only proceed if evaluation says yes with sufficient confidence
            if not should_summarize or confidence < SUMMARIZATION_CONFIDENCE_THRESHOLD:
                print(f"   ⏸ Deferring summarization (confidence {confidence:.2f} < {SUMMARIZATION_CONFIDENCE_THRESHOLD})")
                await notify(f"⏸ Deferring memory consolidation: {reason}", "deferred")
                return

            print(f"   ✓ Proceeding with summarization")

        print(f"Generating summary for {len(messages)} messages in conversation {conversation_id}")
        await notify(f"📝 Consolidating {len(messages)} messages into memory...", "summarizing")

        # Generate summary
        summary_text = await memory.generate_summary_chunk(
            conversation_id=conversation_id,
            messages=messages,
            anthropic_api_key=ANTHROPIC_API_KEY,
            token_tracker=token_tracker
        )

        if not summary_text:
            print("Failed to generate summary")
            await notify("❌ Memory consolidation failed", "error")
            return

        # Get timeframe
        timeframe_start = messages[0]["timestamp"]
        timeframe_end = messages[-1]["timestamp"]

        # Store summary in memory
        memory.store_summary(
            conversation_id=conversation_id,
            summary_text=summary_text,
            timeframe_start=timeframe_start,
            timeframe_end=timeframe_end,
            message_count=len(messages)
        )

        # Mark messages as summarized
        conversation_manager.mark_messages_summarized(
            conversation_id=conversation_id,
            last_message_timestamp=timeframe_end,
            messages_summarized=len(messages)
        )

        print(f"✓ Summary generated and stored for conversation {conversation_id}")
        await notify(f"✓ Memory consolidated ({len(messages)} messages summarized)", "complete")

        # Update working summary (incremental if possible, full rebuild if not)
        await notify("🔄 Updating working summary...", "working_summary")
        conversation = conversation_manager.load_conversation(conversation_id)
        if conversation:
            existing_summary = conversation.working_summary
            working_summary = await memory.generate_working_summary(
                conversation_id=conversation_id,
                conversation_title=conversation.title,
                new_chunk=summary_text,  # The chunk we just created
                existing_summary=existing_summary,  # Existing working summary to integrate into
                anthropic_api_key=ANTHROPIC_API_KEY,
                token_tracker=token_tracker
            )
            if working_summary:
                conversation_manager.update_working_summary(conversation_id, working_summary)
                mode = "incremental" if existing_summary else "initial"
                print(f"✓ Working summary updated ({mode}, {len(working_summary)} chars)")
                await notify("✓ Working summary updated", "complete")

    except Exception as e:
        print(f"Error generating summary: {e}")
    finally:
        # Always remove from in-progress set
        _summarization_in_progress.discard(conversation_id)

async def generate_conversation_title(conversation_id: str, user_message: str, assistant_response: str, websocket=None):
    """
    Generate a title for a conversation based on the first exchange.
    Uses a fast, cheap API call to create a concise title.
    Optionally notifies the client via WebSocket when done.
    """
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": f"Generate a short, descriptive title (3-6 words) for a conversation that started with:\n\nUser: {user_message[:500]}\n\nAssistant: {assistant_response[:500]}\n\nRespond with ONLY the title, no quotes or punctuation."
            }]
        )

        # Track token usage for title generation
        if token_tracker and response.usage:
            token_tracker.record(
                category="internal",
                operation="title_generation",
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                conversation_id=conversation_id
            )

        title = response.content[0].text.strip().strip('"').strip("'")

        # Ensure reasonable length
        if len(title) > 60:
            title = title[:57] + "..."

        # Update the conversation title
        conversation_manager.update_title(conversation_id, title)
        print(f"Auto-generated title for {conversation_id}: {title}")

        # Notify client via WebSocket if available
        if websocket:
            try:
                await websocket.send_json({
                    "type": "title_updated",
                    "conversation_id": conversation_id,
                    "title": title,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as ws_err:
                print(f"Failed to send title update via WebSocket: {ws_err}")

        return title
    except Exception as e:
        print(f"Failed to generate title for {conversation_id}: {e}")
        return None
