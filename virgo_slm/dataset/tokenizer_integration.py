"""Connects Phase 3 dataset pipeline output to Phase 2 tokenizer training.

Deliberately does not modify ``virgo_slm.tokenizer`` at all --
:meth:`VirgoTokenizer.train_from_files` already accepts a list of plain
text file paths, and :func:`run_pipeline` already produces exactly that
(``train.txt``, one file, UTF-8 plain text). This module is a thin,
explicit seam so callers don't have to know the pipeline's internal file
layout, plus a manifest-driven language-balance summary so tokenizer
training runs are reproducible and auditable from a dataset manifest
alone.

Distinguishes three corpora, from smallest/least trustworthy to largest,
so nothing here can be silently mistaken for "the" production corpus:

- ``smoke``: ``virgo_slm/tokenizer/sample_corpus`` -- ~15KB hand-written,
  Phase 2's smoke test only. Never treat as production.
- ``pipeline_output``: whatever a given Phase 3 pipeline run actually
  processed. Only as trustworthy as the sources fed into it -- a pipeline
  run over a second small/hand-written fixture is still not a production
  corpus, even though it went through the full Phase 3 pipeline.
- ``production``: a pipeline run over a real, user-supplied and
  user-approved corpus with real license/provenance metadata. Phase 3
  does not claim this has happened; it only makes it possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from virgo_slm.dataset.manifest import DatasetManifest
from virgo_slm.dataset.pipeline import PipelineResult

CorpusMaturity = Literal["smoke", "pipeline_output", "production"]


@dataclass(frozen=True, slots=True)
class TokenizerTrainingCorpus:
    """What :meth:`VirgoTokenizer.train_from_files` needs, plus provenance."""

    files: tuple[str, ...]
    maturity: CorpusMaturity
    manifest: DatasetManifest | None
    language_distribution: dict[str, int]
    total_characters: int

    def is_production_ready(self) -> bool:
        """True only if every source declared a real license/provenance.

        This is a necessary, not sufficient, check: it verifies the
        pipeline was not left at ``"unspecified"`` defaults, but it cannot
        verify a claimed license/provenance is actually accurate -- that
        verification is a human responsibility, per the Phase 3 policy
        against inventing or silently trusting provenance.
        """
        if self.maturity != "pipeline_output" or self.manifest is None:
            return False
        unspecified_license = self.manifest.license_distribution.get(
            "unspecified", 0
        )
        unspecified_provenance = self.manifest.provenance_distribution.get(
            "unspecified", 0
        )
        return (
            self.manifest.total_accepted > 0
            and unspecified_license == 0
            and unspecified_provenance == 0
        )


def corpus_from_pipeline_result(
    result: PipelineResult, *, split: Literal["train", "validation", "test"] = "train"
) -> TokenizerTrainingCorpus:
    """Build a tokenizer-training corpus descriptor from one pipeline run.

    Uses ``result.split_files[split]`` directly -- the exact file
    :func:`virgo_slm.dataset.pipeline.run_pipeline` already wrote, no
    reformatting or copying.
    """
    file_path = result.split_files[split]
    records_in_split = tuple(
        r for r in result.accepted_records if r.split == split
    )
    language_distribution: dict[str, int] = {}
    for record in records_in_split:
        language_distribution[record.effective_language] = (
            language_distribution.get(record.effective_language, 0) + 1
        )

    return TokenizerTrainingCorpus(
        files=(file_path,),
        maturity="pipeline_output",
        manifest=result.manifest,
        language_distribution=language_distribution,
        total_characters=sum(len(r.text) for r in records_in_split),
    )
