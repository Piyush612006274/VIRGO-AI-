"""Explicit exception types for Phase 4 training failures.

Task 20 requires clear errors, not silent continuation, for a specific
list of failure modes. Each gets its own exception subclass (rather than
one generic ``TrainingError``) so callers/tests can assert on the exact
failure category, and so error messages are written once, correctly,
instead of ad-hoc at each call site.
"""

from __future__ import annotations


class TrainingError(Exception):
    """Base class for every Phase 4 training error."""


class InvalidTrainingConfigError(TrainingError):
    """A ``TrainingConfig`` (or one of its sub-configs) failed validation."""


class MissingDatasetError(TrainingError):
    """A configured dataset path/split does not exist or is empty."""


class InvalidTokenizerError(TrainingError):
    """The tokenizer could not be loaded, or is structurally invalid."""


class VocabularySizeMismatchError(TrainingError):
    """The tokenizer's vocabulary size does not match the model config's."""


class InvalidSequenceLengthError(TrainingError):
    """A requested sequence length is invalid or exceeds model capacity."""


class InvalidCheckpointError(TrainingError):
    """A checkpoint file is missing, corrupted, or structurally invalid."""


class IncompatibleCheckpointError(TrainingError):
    """A checkpoint's config does not match the current run's config."""


class UnavailableDeviceError(TrainingError):
    """A requested device (e.g. ``cuda``) is not available on this machine."""


class UnsupportedPrecisionError(TrainingError):
    """A requested precision is not supported on the resolved device."""


class CorruptedDatasetRecordError(TrainingError):
    """A dataset record could not be tokenized/packed correctly."""
