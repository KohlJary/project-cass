"""
Attachment Database Operations

Functions for managing attachment metadata in the database.
"""

from .connection import get_db


def save_attachment(metadata) -> None:
    """Save attachment metadata to database."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO attachments (id, conversation_id, message_id, filename, media_type, size, is_image, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                metadata.id,
                metadata.conversation_id,
                metadata.message_id,
                metadata.filename,
                metadata.media_type,
                metadata.size,
                1 if metadata.is_image else 0,
                metadata.created_at,
            )
        )


def get_attachment(attachment_id: str):
    """Get attachment metadata by ID."""
    from attachments import AttachmentMetadata
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, conversation_id, message_id, filename, media_type, size, is_image, created_at FROM attachments WHERE id = ?",
            (attachment_id,)
        )
        row = cursor.fetchone()
        if row:
            return AttachmentMetadata(
                id=row[0],
                conversation_id=row[1],
                message_id=row[2],
                filename=row[3],
                media_type=row[4],
                size=row[5],
                is_image=bool(row[6]),
                created_at=row[7],
            )
        return None


def update_attachment_message(attachment_id: str, message_id: int) -> None:
    """Link an attachment to a message."""
    with get_db() as conn:
        conn.execute(
            "UPDATE attachments SET message_id = ? WHERE id = ?",
            (message_id, attachment_id)
        )


def delete_attachment(attachment_id: str) -> None:
    """Delete attachment metadata from database."""
    with get_db() as conn:
        conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))


def get_attachments_for_message(message_id: int) -> list:
    """Get all attachments for a message."""
    from attachments import AttachmentMetadata
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, conversation_id, message_id, filename, media_type, size, is_image, created_at FROM attachments WHERE message_id = ?",
            (message_id,)
        )
        return [
            AttachmentMetadata(
                id=row[0],
                conversation_id=row[1],
                message_id=row[2],
                filename=row[3],
                media_type=row[4],
                size=row[5],
                is_image=bool(row[6]),
                created_at=row[7],
            )
            for row in cursor.fetchall()
        ]
