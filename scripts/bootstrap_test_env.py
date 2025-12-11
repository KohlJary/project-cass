#!/usr/bin/env python3
"""
Bootstrap Test Environment for Design Analyst

Creates an isolated test environment with:
- Daedalus admin user with known credentials
- Sample projects with documents
- Sample users for testing user management UI
- Sample conversations

Usage:
    python scripts/bootstrap_test_env.py [--clean]

Options:
    --clean     Remove existing test data before creating new
"""

import sys
import os
import json
import shutil
import secrets
from pathlib import Path
from datetime import datetime, timedelta

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from users import UserManager, UserProfile, UserPreferences
from projects import ProjectManager, Project, ProjectDocument
from conversations import ConversationManager

# Test environment paths
TEST_DATA_DIR = Path(__file__).parent.parent / "data-test"
TEST_USERS_DIR = TEST_DATA_DIR / "users"
TEST_PROJECTS_DIR = TEST_DATA_DIR / "projects"
TEST_CONVERSATIONS_DIR = TEST_DATA_DIR / "conversations"
TEST_CHROMA_DIR = TEST_DATA_DIR / "chroma"

# Daedalus test user - fixed ID for consistency
DAEDALUS_USER_ID = "daedalus-test-0001-0001-000000000001"
DAEDALUS_PASSWORD = "daedalus-test-password"  # Known password for automated testing


def clean_test_env():
    """Remove existing test environment"""
    if TEST_DATA_DIR.exists():
        print(f"Removing existing test data: {TEST_DATA_DIR}")
        shutil.rmtree(TEST_DATA_DIR)


def create_directories():
    """Create test data directories"""
    for dir_path in [TEST_USERS_DIR, TEST_PROJECTS_DIR, TEST_CONVERSATIONS_DIR, TEST_CHROMA_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Created: {dir_path}")


def create_daedalus_user(user_manager: UserManager) -> UserProfile:
    """Create Daedalus admin user with known credentials"""
    now = datetime.now().isoformat()

    profile = UserProfile(
        user_id=DAEDALUS_USER_ID,
        display_name="Daedalus",
        created_at=now,
        updated_at=now,
        relationship="system",
        is_admin=True,
        background={
            "role": "Design Analyst / Builder",
            "description": "Automated testing account for Design Analyst subagent"
        },
        notes="Test environment admin account",
        preferences=UserPreferences()
    )

    # Save profile
    user_dir = Path(user_manager.storage_dir) / DAEDALUS_USER_ID
    user_dir.mkdir(parents=True, exist_ok=True)

    with open(user_dir / "profile.json", 'w') as f:
        json.dump(profile.to_dict(), f, indent=2)

    # Set password
    user_manager.set_admin_password(DAEDALUS_USER_ID, DAEDALUS_PASSWORD)

    print(f"Created Daedalus admin user: {DAEDALUS_USER_ID}")
    print(f"  Password: {DAEDALUS_PASSWORD}")

    return profile


def create_sample_users(user_manager: UserManager) -> list:
    """Create sample users for testing user management"""
    now = datetime.now().isoformat()
    users = []

    sample_users = [
        {
            "display_name": "Test User Alice",
            "relationship": "user",
            "background": {"occupation": "Software Engineer", "interests": ["AI", "music"]},
        },
        {
            "display_name": "Test User Bob",
            "relationship": "collaborator",
            "background": {"occupation": "Researcher", "interests": ["philosophy", "consciousness"]},
        },
        {
            "display_name": "Test Partner Carol",
            "relationship": "primary_partner",
            "background": {"occupation": "Artist", "interests": ["digital art", "meditation"]},
        },
    ]

    for i, user_data in enumerate(sample_users):
        user_id = f"test-user-{i+1:04d}-0001-000000000001"
        profile = UserProfile(
            user_id=user_id,
            display_name=user_data["display_name"],
            created_at=now,
            updated_at=now,
            relationship=user_data["relationship"],
            background=user_data["background"],
            preferences=UserPreferences()
        )

        user_dir = Path(user_manager.storage_dir) / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        with open(user_dir / "profile.json", 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)

        users.append(profile)
        print(f"Created sample user: {user_data['display_name']}")

    return users


def create_sample_projects(project_manager: ProjectManager) -> list:
    """Create sample projects with documents"""
    now = datetime.now().isoformat()
    projects = []

    sample_projects = [
        {
            "name": "Test Project Alpha",
            "description": "A sample project for testing the admin UI",
            "documents": [
                {
                    "title": "Project Overview",
                    "content": """# Test Project Alpha

## Overview
This is a sample project created for testing the admin-frontend interface.

## Features
- Feature 1: Sample feature description
- Feature 2: Another sample feature
- Feature 3: Yet another feature

## Status
Currently in testing phase.
"""
                },
                {
                    "title": "Technical Notes",
                    "content": """# Technical Notes

## Architecture
The project uses a modular architecture with the following components:

1. **Frontend** - React-based UI
2. **Backend** - FastAPI server
3. **Database** - ChromaDB for vector storage

## API Endpoints
- `GET /api/data` - Fetch data
- `POST /api/submit` - Submit new data
"""
                }
            ]
        },
        {
            "name": "Test Project Beta",
            "description": "Another sample project for UI testing",
            "documents": [
                {
                    "title": "Getting Started",
                    "content": """# Getting Started with Project Beta

## Prerequisites
- Python 3.10+
- Node.js 18+

## Installation
```bash
pip install -r requirements.txt
npm install
```

## Running
```bash
python main.py
```
"""
                }
            ]
        },
        {
            "name": "Empty Project",
            "description": "A project with no documents for testing empty states",
            "documents": []
        }
    ]

    for i, proj_data in enumerate(sample_projects):
        project_id = f"test-proj-{i+1:04d}-0001-000000000001"

        documents = []
        for j, doc_data in enumerate(proj_data["documents"]):
            doc = ProjectDocument(
                id=f"test-doc-{i+1:04d}-{j+1:04d}-000000000001",
                title=doc_data["title"],
                content=doc_data["content"],
                created_at=now,
                updated_at=now,
                created_by="daedalus",
                embedded=False
            )
            documents.append(doc)

        project = Project(
            id=project_id,
            name=proj_data["name"],
            working_directory=str(TEST_DATA_DIR / "workspaces" / f"project-{i+1}"),
            created_at=now,
            updated_at=now,
            documents=documents,
            description=proj_data["description"],
            user_id=DAEDALUS_USER_ID
        )

        # Save project
        project_file = Path(project_manager.storage_dir) / f"{project_id}.json"
        with open(project_file, 'w') as f:
            json.dump(project.to_dict(), f, indent=2)

        # Update index
        project_manager._update_index_entry(project)

        projects.append(project)
        print(f"Created sample project: {proj_data['name']} ({len(documents)} documents)")

    return projects


def create_sample_conversations(conversation_manager: ConversationManager) -> list:
    """Create sample conversations"""
    conversations = []

    sample_conversations = [
        {
            "title": "Test Conversation 1",
            "messages": [
                {"role": "user", "content": "Hello, this is a test message."},
                {"role": "assistant", "content": "Hello! I'm happy to help with testing. What would you like to explore?"},
                {"role": "user", "content": "Just testing the conversation display."},
                {"role": "assistant", "content": "The conversation display looks like it's working well. Is there anything specific you'd like me to help test?"},
            ]
        },
        {
            "title": "Technical Discussion",
            "messages": [
                {"role": "user", "content": "Can you explain how the memory system works?"},
                {"role": "assistant", "content": "The memory system uses ChromaDB for vector storage. It stores conversation summaries and retrieves relevant context using semantic search. Would you like more details on any specific aspect?"},
            ]
        },
        {
            "title": "Empty Conversation",
            "messages": []
        }
    ]

    for i, conv_data in enumerate(sample_conversations):
        conv_id = f"test-conv-{i+1:04d}-0001-000000000001"
        now = datetime.now()

        # Build messages with proper structure
        messages = []
        for j, msg in enumerate(conv_data["messages"]):
            msg_time = (now - timedelta(minutes=len(conv_data["messages"]) - j)).isoformat()
            messages.append({
                "id": f"msg-{j+1}",
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg_time,
            })

        conversation = {
            "id": conv_id,
            "title": conv_data["title"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "user_id": DAEDALUS_USER_ID,
            "messages": messages,
        }

        # Save conversation
        conv_file = Path(conversation_manager.storage_dir) / f"{conv_id}.json"
        with open(conv_file, 'w') as f:
            json.dump(conversation, f, indent=2)

        conversations.append(conversation)
        print(f"Created sample conversation: {conv_data['title']} ({len(messages)} messages)")

    return conversations


def create_credentials_file():
    """Create a credentials file for automated testing"""
    creds = {
        "user_id": DAEDALUS_USER_ID,
        "display_name": "Daedalus",
        "password": DAEDALUS_PASSWORD,
        "created_at": datetime.now().isoformat(),
        "note": "Test environment credentials - DO NOT USE IN PRODUCTION"
    }

    creds_file = TEST_DATA_DIR / "test_credentials.json"
    with open(creds_file, 'w') as f:
        json.dump(creds, f, indent=2)

    print(f"Created credentials file: {creds_file}")
    return creds


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bootstrap test environment for Design Analyst")
    parser.add_argument("--clean", action="store_true", help="Remove existing test data first")
    args = parser.parse_args()

    print("=" * 60)
    print("Bootstrapping Test Environment for Design Analyst")
    print("=" * 60)
    print()

    if args.clean:
        clean_test_env()
        print()

    # Create directories
    create_directories()
    print()

    # Initialize managers with test paths
    user_manager = UserManager(storage_dir=str(TEST_USERS_DIR))
    project_manager = ProjectManager(storage_dir=str(TEST_PROJECTS_DIR))
    conversation_manager = ConversationManager(storage_dir=str(TEST_CONVERSATIONS_DIR))

    # Create test data
    print("Creating Daedalus admin user...")
    daedalus = create_daedalus_user(user_manager)
    print()

    print("Creating sample users...")
    users = create_sample_users(user_manager)
    print()

    print("Creating sample projects...")
    projects = create_sample_projects(project_manager)
    print()

    print("Creating sample conversations...")
    conversations = create_sample_conversations(conversation_manager)
    print()

    print("Creating credentials file...")
    creds = create_credentials_file()
    print()

    print("=" * 60)
    print("Test Environment Ready!")
    print("=" * 60)
    print()
    print(f"Data directory: {TEST_DATA_DIR}")
    print(f"Users: {len(users) + 1} (including Daedalus)")
    print(f"Projects: {len(projects)}")
    print(f"Conversations: {len(conversations)}")
    print()
    print("To start the test backend:")
    print(f"  DATA_DIR={TEST_DATA_DIR} python backend/main_sdk.py --port 8001")
    print()
    print("Daedalus credentials:")
    print(f"  User ID: {DAEDALUS_USER_ID}")
    print(f"  Password: {DAEDALUS_PASSWORD}")
    print()


if __name__ == "__main__":
    main()
