"""Classifier package."""

from urluniq.classifiers.classifier import Classification, URLClassifier
from urluniq.classifiers.rules import (
    CATEGORY_LABELS,
    DEFAULT_RULES,
    ClassificationRule,
)

__all__ = [
    "CATEGORY_LABELS",
    "Classification",
    "ClassificationRule",
    "DEFAULT_RULES",
    "URLClassifier",
]
