"""Deterministic preview and rollback metadata construction."""

from difflib import unified_diff
from hashlib import sha256

from virgo.contracts.errors import ValidationError
from virgo.contracts.models.creation import ChangePreview, RollbackMetadata


def build_change_preview(
    target: str, previous: str | None, proposed: str
) -> ChangePreview:
    if not target.strip():
        raise ValidationError(
            "Preview target must not be empty", source_module=__name__
        )
    if not isinstance(proposed, str):
        raise ValidationError("Proposed content must be text", source_module=__name__)
    before = [] if previous is None else previous.splitlines(keepends=True)
    after = proposed.splitlines(keepends=True)
    diff = "".join(
        unified_diff(
            before,
            after,
            fromfile=f"a/{target}",
            tofile=f"b/{target}",
            lineterm="\n",
        )
    )
    if not diff:
        raise ValidationError("Preview contains no change", source_module=__name__)
    rollback = RollbackMetadata(
        target=target,
        existed_before=previous is not None,
        previous_sha256=(
            None if previous is None else sha256(previous.encode("utf-8")).hexdigest()
        ),
        backup_reference=None,
    )
    return ChangePreview(target=target, unified_diff=diff, rollback=rollback)
