"""
Model Interview System

Infrastructure for Cass to conduct systematic interviews across different AI models
and analyze the results for research into AI cognition and consciousness.

Components:
- protocols: Interview protocol storage and management
- dispatch: Multi-model interview execution
- storage: Response collection with provenance
- analysis: Tools for comparing and analyzing responses
- viewer: Response viewing and annotation (API endpoints)
"""

from .protocols import ProtocolManager, InterviewProtocol
from .dispatch import InterviewDispatcher
from .storage import ResponseStorage
from .analysis import InterviewAnalyzer

__all__ = [
    'ProtocolManager',
    'InterviewProtocol',
    'InterviewDispatcher',
    'ResponseStorage',
    'InterviewAnalyzer'
]
