"""
Cass Vessel - Attachment Storage and Management

Handles file/image uploads for chat messages with two storage modes:
- Persistent: Files saved to data/attachments/, metadata in database
- Session-only: Files in temp directory, cleaned up on disconnect (for demo site)
"""
import os
import uuid
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, BinaryIO
from dataclasses import dataclass, asdict
import mimetypes

from config import DATA_DIR, ATTACHMENTS_SESSION_ONLY


@dataclass
class AttachmentMetadata:
    """Metadata for an uploaded attachment."""
    id: str
    conversation_id: Optional[str]
    message_id: Optional[int]
    filename: str
    media_type: str
    size: int
    created_at: str
    is_image: bool

    def to_dict(self) -> Dict:
        return asdict(self)


class BaseAttachmentStorage:
    """Base class for attachment storage backends."""

    def save(self, file_data: bytes, filename: str, media_type: str,
             conversation_id: Optional[str] = None) -> AttachmentMetadata:
        raise NotImplementedError

    def get(self, attachment_id: str) -> Optional[tuple[bytes, AttachmentMetadata]]:
        raise NotImplementedError

    def get_metadata(self, attachment_id: str) -> Optional[AttachmentMetadata]:
        raise NotImplementedError

    def link_to_message(self, attachment_id: str, message_id: int) -> bool:
        raise NotImplementedError

    def delete(self, attachment_id: str) -> bool:
        raise NotImplementedError

    def cleanup_session(self, session_id: str) -> int:
        """Clean up attachments for a session. Returns count deleted."""
        return 0


class PersistentAttachmentStorage(BaseAttachmentStorage):
    """
    Persistent storage: files in data/attachments/, metadata in database.
    Used for production deployments where attachments should persist.
    """

    def __init__(self):
        self.base_dir = DATA_DIR / "attachments"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_cache: Dict[str, AttachmentMetadata] = {}

    def _get_file_path(self, attachment_id: str, conversation_id: Optional[str] = None) -> Path:
        """Get the filesystem path for an attachment."""
        if conversation_id:
            dir_path = self.base_dir / conversation_id
        else:
            dir_path = self.base_dir / "_unassigned"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / attachment_id

    def save(self, file_data: bytes, filename: str, media_type: str,
             conversation_id: Optional[str] = None) -> AttachmentMetadata:
        """Save attachment to filesystem and database."""
        # Generate unique ID with extension
        ext = Path(filename).suffix.lower() or mimetypes.guess_extension(media_type) or ""
        attachment_id = f"{uuid.uuid4().hex}{ext}"

        # Determine if it's an image
        is_image = media_type.startswith("image/")

        # Create metadata
        metadata = AttachmentMetadata(
            id=attachment_id,
            conversation_id=conversation_id,
            message_id=None,
            filename=filename,
            media_type=media_type,
            size=len(file_data),
            created_at=datetime.now().isoformat(),
            is_image=is_image
        )

        # Save file
        file_path = self._get_file_path(attachment_id, conversation_id)
        file_path.write_bytes(file_data)

        # Save to database
        import database
        database.save_attachment(metadata)

        # Cache metadata
        self._metadata_cache[attachment_id] = metadata

        return metadata

    def get(self, attachment_id: str) -> Optional[tuple[bytes, AttachmentMetadata]]:
        """Retrieve attachment file and metadata."""
        metadata = self.get_metadata(attachment_id)
        if not metadata:
            return None

        file_path = self._get_file_path(attachment_id, metadata.conversation_id)
        if not file_path.exists():
            return None

        return file_path.read_bytes(), metadata

    def get_metadata(self, attachment_id: str) -> Optional[AttachmentMetadata]:
        """Get attachment metadata."""
        # Check cache first
        if attachment_id in self._metadata_cache:
            return self._metadata_cache[attachment_id]

        # Try database
        import database
        metadata = database.get_attachment(attachment_id)
        if metadata:
            self._metadata_cache[attachment_id] = metadata
            return metadata

        return None

    def link_to_message(self, attachment_id: str, message_id: int) -> bool:
        """Associate attachment with a message after send."""
        metadata = self.get_metadata(attachment_id)
        if not metadata:
            return False

        metadata.message_id = message_id
        self._metadata_cache[attachment_id] = metadata

        import database
        database.update_attachment_message(attachment_id, message_id)

        return True

    def delete(self, attachment_id: str) -> bool:
        """Delete attachment file and metadata."""
        metadata = self.get_metadata(attachment_id)
        if not metadata:
            return False

        file_path = self._get_file_path(attachment_id, metadata.conversation_id)
        if file_path.exists():
            file_path.unlink()

        import database
        database.delete_attachment(attachment_id)

        self._metadata_cache.pop(attachment_id, None)
        return True


class SessionAttachmentStorage(BaseAttachmentStorage):
    """
    Session-only storage: files in temp directory, cleaned up on disconnect.
    Used for demo site where we don't want to persist user uploads.
    """

    def __init__(self):
        # Create a unique temp directory for this server instance
        self.base_dir = Path(tempfile.mkdtemp(prefix="cass_attachments_"))
        self._metadata: Dict[str, AttachmentMetadata] = {}
        self._session_attachments: Dict[str, List[str]] = {}  # session_id -> [attachment_ids]

    def _get_file_path(self, attachment_id: str) -> Path:
        """Get the filesystem path for an attachment."""
        return self.base_dir / attachment_id

    def save(self, file_data: bytes, filename: str, media_type: str,
             conversation_id: Optional[str] = None,
             session_id: Optional[str] = None) -> AttachmentMetadata:
        """Save attachment to temp storage."""
        # Generate unique ID with extension
        ext = Path(filename).suffix.lower() or mimetypes.guess_extension(media_type) or ""
        attachment_id = f"{uuid.uuid4().hex}{ext}"

        # Determine if it's an image
        is_image = media_type.startswith("image/")

        # Create metadata
        metadata = AttachmentMetadata(
            id=attachment_id,
            conversation_id=conversation_id,
            message_id=None,
            filename=filename,
            media_type=media_type,
            size=len(file_data),
            created_at=datetime.now().isoformat(),
            is_image=is_image
        )

        # Save file
        file_path = self._get_file_path(attachment_id)
        file_path.write_bytes(file_data)

        # Store metadata in memory
        self._metadata[attachment_id] = metadata

        # Track by session for cleanup
        if session_id:
            if session_id not in self._session_attachments:
                self._session_attachments[session_id] = []
            self._session_attachments[session_id].append(attachment_id)

        return metadata

    def get(self, attachment_id: str) -> Optional[tuple[bytes, AttachmentMetadata]]:
        """Retrieve attachment file and metadata."""
        metadata = self._metadata.get(attachment_id)
        if not metadata:
            return None

        file_path = self._get_file_path(attachment_id)
        if not file_path.exists():
            return None

        return file_path.read_bytes(), metadata

    def get_metadata(self, attachment_id: str) -> Optional[AttachmentMetadata]:
        """Get attachment metadata."""
        return self._metadata.get(attachment_id)

    def link_to_message(self, attachment_id: str, message_id: int) -> bool:
        """Associate attachment with a message."""
        metadata = self._metadata.get(attachment_id)
        if not metadata:
            return False
        metadata.message_id = message_id
        return True

    def delete(self, attachment_id: str) -> bool:
        """Delete attachment."""
        if attachment_id not in self._metadata:
            return False

        file_path = self._get_file_path(attachment_id)
        if file_path.exists():
            file_path.unlink()

        del self._metadata[attachment_id]

        # Remove from session tracking
        for session_attachments in self._session_attachments.values():
            if attachment_id in session_attachments:
                session_attachments.remove(attachment_id)

        return True

    def cleanup_session(self, session_id: str) -> int:
        """Clean up all attachments for a session."""
        if session_id not in self._session_attachments:
            return 0

        attachment_ids = self._session_attachments.pop(session_id, [])
        count = 0
        for attachment_id in attachment_ids:
            if self.delete(attachment_id):
                count += 1

        return count

    def cleanup_all(self):
        """Clean up all attachments (called on shutdown)."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir, ignore_errors=True)


class AttachmentManager:
    """
    Main attachment manager - selects storage backend based on configuration.
    """

    def __init__(self):
        if ATTACHMENTS_SESSION_ONLY:
            self.storage = SessionAttachmentStorage()
            print("[Attachments] Using session-only storage (demo mode)")
        else:
            self.storage = PersistentAttachmentStorage()
            print(f"[Attachments] Using persistent storage at {DATA_DIR / 'attachments'}")

    def save(self, file_data: bytes, filename: str, media_type: str,
             conversation_id: Optional[str] = None,
             session_id: Optional[str] = None) -> AttachmentMetadata:
        """Save an attachment."""
        if isinstance(self.storage, SessionAttachmentStorage):
            return self.storage.save(file_data, filename, media_type, conversation_id, session_id)
        else:
            return self.storage.save(file_data, filename, media_type, conversation_id)

    def get(self, attachment_id: str) -> Optional[tuple[bytes, AttachmentMetadata]]:
        """Get attachment file and metadata."""
        return self.storage.get(attachment_id)

    def get_metadata(self, attachment_id: str) -> Optional[AttachmentMetadata]:
        """Get attachment metadata only."""
        return self.storage.get_metadata(attachment_id)

    def link_to_message(self, attachment_id: str, message_id: int) -> bool:
        """Link attachment to a message after save."""
        return self.storage.link_to_message(attachment_id, message_id)

    def delete(self, attachment_id: str) -> bool:
        """Delete an attachment."""
        return self.storage.delete(attachment_id)

    def cleanup_session(self, session_id: str) -> int:
        """Clean up attachments for a disconnected session."""
        return self.storage.cleanup_session(session_id)

    @property
    def is_session_only(self) -> bool:
        """Check if using session-only storage."""
        return ATTACHMENTS_SESSION_ONLY
