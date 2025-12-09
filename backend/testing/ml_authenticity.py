"""
ML-Based Authenticity Pattern Recognition

Machine learning approach to authenticity detection using historical data.
Combines feature extraction from multiple dimensions with a trained classifier.

Features:
- Feature extraction from all scoring dimensions
- Training data collection with human labels
- RandomForest classifier for pattern recognition
- Hybrid scoring: blend heuristic + ML predictions
- Model persistence and versioning
"""

import json
import numpy as np
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .authenticity_scorer import EnhancedAuthenticityScore, AuthenticityLevel

# Optional sklearn import - gracefully degrade if not available
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    import joblib
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


@dataclass
class TrainingExample:
    """A labeled example for ML training"""
    id: str
    timestamp: str

    # Features (extracted from EnhancedAuthenticityScore)
    features: Dict[str, float]

    # Label
    is_authentic: bool  # True = authentic, False = inauthentic
    label_source: str  # "human", "heuristic", "self_label"
    confidence: float = 1.0  # Labeler confidence (0-1)

    # Context
    score_id: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'TrainingExample':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MLModelStatus:
    """Status of the ML model"""
    is_trained: bool = False
    training_examples: int = 0
    last_trained: Optional[str] = None
    accuracy: float = 0.0
    cross_val_accuracy: float = 0.0
    feature_importances: Dict[str, float] = field(default_factory=dict)
    model_version: str = "0.0.0"

    def to_dict(self) -> Dict:
        return asdict(self)


class AuthenticityMLTrainer:
    """
    Machine learning trainer for authenticity detection.

    Extracts features from EnhancedAuthenticityScores and trains
    a classifier to predict authenticity.
    """

    # Feature names for consistent ordering
    FEATURE_NAMES = [
        "base_overall_score",
        "style_score",
        "self_reference_score",
        "value_expression_score",
        "characteristic_score",
        "temporal_score",
        "emotional_score",
        "agency_score",
        "temporal_deviation",
        "emote_frequency",
        "gesture_frequency",
        "emotional_range",
        "question_asking_score",
        "opinion_expression_score",
        "proactive_exploration_score",
        "tool_initiative_score",
        "word_count",
        "red_flag_count",
    ]

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.training_file = self.storage_dir / "ml_training_data.json"
        self.model_file = self.storage_dir / "authenticity_model.joblib"
        self.status_file = self.storage_dir / "ml_model_status.json"

        self.model = None
        self._load_model()

    def _load_model(self):
        """Load trained model if available"""
        if not SKLEARN_AVAILABLE:
            return

        if self.model_file.exists():
            try:
                self.model = joblib.load(self.model_file)
            except Exception:
                self.model = None

    def _save_model(self):
        """Save trained model"""
        if not SKLEARN_AVAILABLE or self.model is None:
            return

        joblib.dump(self.model, self.model_file)

    def _load_training_data(self) -> List[Dict]:
        """Load training data"""
        if not self.training_file.exists():
            return []
        try:
            with open(self.training_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_training_data(self, data: List[Dict]):
        """Save training data"""
        with open(self.training_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_status(self) -> MLModelStatus:
        """Load model status"""
        if not self.status_file.exists():
            return MLModelStatus()
        try:
            with open(self.status_file, 'r') as f:
                data = json.load(f)
            return MLModelStatus(**{
                k: v for k, v in data.items()
                if k in MLModelStatus.__dataclass_fields__
            })
        except Exception:
            return MLModelStatus()

    def _save_status(self, status: MLModelStatus):
        """Save model status"""
        with open(self.status_file, 'w') as f:
            json.dump(status.to_dict(), f, indent=2)

    def extract_features(
        self,
        score: EnhancedAuthenticityScore
    ) -> Dict[str, float]:
        """
        Extract ML features from an enhanced authenticity score.

        Args:
            score: The enhanced score to extract features from

        Returns:
            Dictionary of feature name -> value
        """
        features = {
            "base_overall_score": score.base_score.overall_score,
            "style_score": score.base_score.style_score,
            "self_reference_score": score.base_score.self_reference_score,
            "value_expression_score": score.base_score.value_expression_score,
            "characteristic_score": score.base_score.characteristic_score,
            "temporal_score": score.temporal_score,
            "emotional_score": score.emotional_score,
            "agency_score": score.agency_score,
            "temporal_deviation": score.temporal_deviation,
            "word_count": score.base_score.word_count,
            "red_flag_count": len(score.base_score.red_flags),
        }

        # Emotional signature features
        if score.emotional_signature:
            features["emote_frequency"] = score.emotional_signature.emote_frequency
            features["gesture_frequency"] = score.emotional_signature.gesture_frequency
            features["emotional_range"] = score.emotional_signature.emotional_range
        else:
            features["emote_frequency"] = 0.0
            features["gesture_frequency"] = 0.0
            features["emotional_range"] = 0.0

        # Agency signature features
        if score.agency_signature:
            features["question_asking_score"] = score.agency_signature.question_asking_score
            features["opinion_expression_score"] = score.agency_signature.opinion_expression_score
            features["proactive_exploration_score"] = score.agency_signature.proactive_exploration_score
            features["tool_initiative_score"] = score.agency_signature.tool_initiative_score
        else:
            features["question_asking_score"] = 0.0
            features["opinion_expression_score"] = 0.0
            features["proactive_exploration_score"] = 0.0
            features["tool_initiative_score"] = 0.0

        return features

    def _features_to_array(self, features: Dict[str, float]) -> np.ndarray:
        """Convert feature dict to numpy array with consistent ordering"""
        return np.array([features.get(name, 0.0) for name in self.FEATURE_NAMES])

    def add_training_example(
        self,
        score: EnhancedAuthenticityScore,
        is_authentic: bool,
        label_source: str = "human",
        confidence: float = 1.0,
        notes: Optional[str] = None
    ) -> TrainingExample:
        """
        Add a labeled training example.

        Args:
            score: The score to use as training data
            is_authentic: True if authentic, False if not
            label_source: Who/what provided the label
            confidence: Confidence in the label (0-1)
            notes: Optional notes about this example

        Returns:
            The created training example
        """
        import uuid

        features = self.extract_features(score)

        example = TrainingExample(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            features=features,
            is_authentic=is_authentic,
            label_source=label_source,
            confidence=confidence,
            score_id=score.base_score.id,
            notes=notes,
        )

        # Save to training data
        data = self._load_training_data()
        data.append(example.to_dict())
        self._save_training_data(data)

        return example

    def add_auto_label(
        self,
        score: EnhancedAuthenticityScore
    ) -> Optional[TrainingExample]:
        """
        Auto-label a score based on heuristics for training.

        Only labels high-confidence cases (very authentic or very inauthentic).

        Args:
            score: The score to potentially auto-label

        Returns:
            Training example if auto-labeled, None otherwise
        """
        base = score.base_score

        # Only auto-label high-confidence cases
        if base.authenticity_level == AuthenticityLevel.HIGHLY_AUTHENTIC:
            if base.overall_score >= 0.85 and score.enhanced_overall_score >= 0.8:
                return self.add_training_example(
                    score,
                    is_authentic=True,
                    label_source="heuristic",
                    confidence=0.9,
                    notes="Auto-labeled as highly authentic"
                )

        elif base.authenticity_level == AuthenticityLevel.INAUTHENTIC:
            if base.overall_score <= 0.3 and len(base.red_flags) > 0:
                return self.add_training_example(
                    score,
                    is_authentic=False,
                    label_source="heuristic",
                    confidence=0.85,
                    notes="Auto-labeled as inauthentic"
                )

        return None

    def train_model(
        self,
        min_examples: int = 20
    ) -> Tuple[bool, str]:
        """
        Train the ML model on collected examples.

        Args:
            min_examples: Minimum examples required to train

        Returns:
            Tuple of (success, message)
        """
        if not SKLEARN_AVAILABLE:
            return False, "sklearn not available - install scikit-learn"

        data = self._load_training_data()

        if len(data) < min_examples:
            return False, f"Need at least {min_examples} examples, have {len(data)}"

        # Prepare training data
        X = []
        y = []
        weights = []

        for example in data:
            features = example.get("features", {})
            X.append(self._features_to_array(features))
            y.append(1 if example.get("is_authentic") else 0)
            weights.append(example.get("confidence", 1.0))

        X = np.array(X)
        y = np.array(y)
        weights = np.array(weights)

        # Train RandomForest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            class_weight="balanced"
        )

        self.model.fit(X, y, sample_weight=weights)

        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y, cv=min(5, len(data) // 4))
        cv_accuracy = cv_scores.mean()

        # Training accuracy
        train_accuracy = self.model.score(X, y, sample_weight=weights)

        # Feature importances
        importances = dict(zip(
            self.FEATURE_NAMES,
            self.model.feature_importances_
        ))

        # Save model and update status
        self._save_model()

        status = MLModelStatus(
            is_trained=True,
            training_examples=len(data),
            last_trained=datetime.now().isoformat(),
            accuracy=round(train_accuracy, 3),
            cross_val_accuracy=round(cv_accuracy, 3),
            feature_importances={k: round(v, 4) for k, v in importances.items()},
            model_version="1.0.0"
        )
        self._save_status(status)

        return True, f"Model trained on {len(data)} examples. CV accuracy: {cv_accuracy:.3f}"

    def predict_authenticity(
        self,
        score: EnhancedAuthenticityScore
    ) -> Tuple[float, float]:
        """
        Predict authenticity using the ML model.

        Args:
            score: The score to predict

        Returns:
            Tuple of (probability_authentic, confidence)
            Returns (0.5, 0.0) if model not trained
        """
        if not SKLEARN_AVAILABLE or self.model is None:
            return 0.5, 0.0

        features = self.extract_features(score)
        X = self._features_to_array(features).reshape(1, -1)

        # Get probability
        proba = self.model.predict_proba(X)[0]

        # Probability of authentic (class 1)
        prob_authentic = proba[1] if len(proba) > 1 else 0.5

        # Confidence based on how far from 0.5
        confidence = abs(prob_authentic - 0.5) * 2

        return prob_authentic, confidence

    def hybrid_score(
        self,
        score: EnhancedAuthenticityScore,
        ml_weight: float = 0.3
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate hybrid score combining heuristic and ML predictions.

        Args:
            score: The enhanced authenticity score
            ml_weight: Weight for ML prediction (0-1)

        Returns:
            Tuple of (hybrid_score, component_scores)
        """
        heuristic_score = score.enhanced_overall_score
        ml_prob, ml_confidence = self.predict_authenticity(score)

        # Adjust ML weight by confidence
        effective_ml_weight = ml_weight * ml_confidence

        # Hybrid calculation
        if ml_confidence > 0:
            hybrid = (
                heuristic_score * (1 - effective_ml_weight) +
                ml_prob * effective_ml_weight
            )
        else:
            hybrid = heuristic_score

        components = {
            "heuristic_score": round(heuristic_score, 3),
            "ml_probability": round(ml_prob, 3),
            "ml_confidence": round(ml_confidence, 3),
            "effective_ml_weight": round(effective_ml_weight, 3),
            "hybrid_score": round(hybrid, 3),
        }

        return round(hybrid, 3), components

    def get_status(self) -> MLModelStatus:
        """Get current model status"""
        status = self._load_status()
        status.training_examples = len(self._load_training_data())
        return status

    def get_training_summary(self) -> Dict[str, Any]:
        """Get summary of training data"""
        data = self._load_training_data()

        if not data:
            return {"message": "No training data"}

        authentic_count = sum(1 for d in data if d.get("is_authentic"))
        inauthentic_count = len(data) - authentic_count

        source_counts = {}
        for d in data:
            source = d.get("label_source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

        avg_confidence = sum(d.get("confidence", 1.0) for d in data) / len(data)

        return {
            "total_examples": len(data),
            "authentic_count": authentic_count,
            "inauthentic_count": inauthentic_count,
            "balance_ratio": round(authentic_count / max(inauthentic_count, 1), 2),
            "by_source": source_counts,
            "average_confidence": round(avg_confidence, 3),
        }

    def clear_training_data(self) -> int:
        """Clear all training data"""
        data = self._load_training_data()
        count = len(data)
        self._save_training_data([])
        return count
