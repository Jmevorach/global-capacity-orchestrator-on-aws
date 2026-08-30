"""Shared error types for live inference validation helpers."""


class ManagedInferenceValidationError(RuntimeError):
    """Sanitized validation error safe to include in the private report."""


class InferenceCommandFailure(RuntimeError):
    """A subprocess failed; raw output is already in the private checkpoint."""
