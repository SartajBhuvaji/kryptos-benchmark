"""Publish the Kryptos dataset directory to the HuggingFace Hub.

``src/kryptos/dataset/`` is authored as a Hub repository already -- a card plus one
directory per config -- so publishing is a folder upload with no restructuring step.

Every push runs preflight checks first. Uploading a stale artifact or a card whose
declared config paths do not resolve produces a dataset that fails to load for everyone
who tries it, and the Hub caches aggressively, so it is worth refusing early:

* nothing unexpected is sitting in the folder waiting to be published
* the committed JSONL still matches what the builder produces
* the card carries YAML frontmatter declaring the config and split
* every path the card points at exists
* ``load_dataset`` succeeds against the declared features

Usage::

    python -m kryptos.huggingface.push --dry-run
    python -m kryptos.huggingface.push
    python -m kryptos.huggingface.push --public       # deliberate, never the default
"""

from __future__ import annotations

import argparse
import fnmatch
import pathlib
import re
import sys

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.algorithms.baseline import build
from kryptos.algorithms.baseline.schema import CONFIG, SPLIT, hf_features
from kryptos.algorithms.isomorph import build as isomorph_build
from kryptos.algorithms.isomorph import schema as isomorph_schema

#: Every config the builders produce, baseline first. The card must declare all of them
#: and each must load; a config that exists on disk but not in the card uploads as files
#: the Hub will never surface.
ALL_CONFIGS: tuple[str, ...] = (CONFIG, *(c.name for c in isomorph_schema.CONFIGS))

DEFAULT_REPO_ID = "sartajbhuvaji/kryptos-bench"

DATASET_DIR = build.DATASET_DIR
CARD = DATASET_DIR / "README.md"

#: Never uploaded. The folder is published wholesale, so anything sitting in it ships --
#: including build residue git never sees, because ``upload_folder`` walks the filesystem
#: rather than the index. ``example.py`` is imported by the test suite, which is enough to
#: drop a ``__pycache__`` directory here.
IGNORE_DIRS = {"__pycache__", ".ipynb_checkpoints"}
IGNORE_FILES = ("*.py[cod]", ".DS_Store", "Thumbs.db")

#: The same exclusions in the glob form ``upload_folder`` expects.
IGNORE_PATTERNS = [f"{d}/*" for d in sorted(IGNORE_DIRS)] + list(IGNORE_FILES)

#: What a dataset repository may contain: the card, config data, and the worked example.
#: Anything else is unreviewed content heading for a public URL, so preflight stops.
PUBLISHABLE_SUFFIXES = {".md", ".jsonl", ".py"}


class PreflightError(RuntimeError):
    """Raised when the dataset directory is not fit to publish."""


def _frontmatter(card_text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---\n", card_text, re.S)
    if not match:
        raise PreflightError(f"{CARD} has no YAML frontmatter; the Hub needs it to "
                             "resolve configs and render the card")
    return match.group(1)


def publishable_files() -> list[str]:
    """Relative paths that would actually be uploaded, ignore patterns applied.

    Mirrors what ``upload_folder`` will do, so the dry run cannot claim one file set and
    the real push send another.
    """
    kept = []
    for path in DATASET_DIR.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(DATASET_DIR)
        if set(relative.parts[:-1]) & IGNORE_DIRS:
            continue
        if any(fnmatch.fnmatch(relative.name, pattern) for pattern in IGNORE_FILES):
            continue
        kept.append(relative.as_posix())
    return sorted(kept)


def _expected_artifacts() -> list[tuple[str, pathlib.Path, str]]:
    """Every committed data file with what its builder currently produces.

    One list so the freshness check cannot silently cover the baseline and skip the
    isomorph configs -- the failure mode of adding configs to a check written for one.
    """
    artifacts = [(CONFIG, build.OUTPUT, build.serialize(build.build()))]
    artifacts += [
        (
            config.name,
            isomorph_build.output_for(config),
            isomorph_build.serialize(isomorph_build.build_config(config)),
        )
        for config in isomorph_schema.CONFIGS
    ]
    return artifacts


def _features_for(name: str):
    return hf_features() if name == CONFIG else isomorph_schema.hf_features(name)


def preflight() -> list[str]:
    """Verify the dataset directory is publishable. Returns a list of check descriptions."""
    checks: list[str] = []

    if not DATASET_DIR.is_dir():
        raise PreflightError(f"missing dataset directory {DATASET_DIR}")

    unexpected = [
        f for f in publishable_files() if pathlib.Path(f).suffix not in PUBLISHABLE_SUFFIXES
    ]
    if unexpected:
        raise PreflightError(
            "unexpected file(s) in the dataset directory, which is uploaded wholesale:\n  "
            + "\n  ".join(unexpected)
            + "\nRemove them, or add them to IGNORE_PATTERNS if they are build residue."
        )
    checks.append(f"{len(publishable_files())} file(s) to upload, all recognised types")

    for name, target, payload in _expected_artifacts():
        if not target.exists():
            raise PreflightError(f"missing artifact {target}; run the builder first")
        if target.read_text(encoding="utf-8") != payload:
            raise PreflightError(
                f"{target} is stale -- it does not match what the builder produces. "
                "Re-run the builder and commit the result before publishing."
            )
        checks.append(f"artifact matches builder output ({name})")

    if not CARD.exists():
        raise PreflightError(f"missing dataset card {CARD}")
    front = _frontmatter(CARD.read_text(encoding="utf-8"))
    for name in ALL_CONFIGS:
        if f"config_name: {name}" not in front:
            raise PreflightError(
                f"card frontmatter does not declare config {name!r}. Every config the "
                "builders produce must be declared, or it uploads as files the Hub will "
                "not surface."
            )
    if f"split: {SPLIT}" not in front:
        raise PreflightError(f"card frontmatter does not declare split {SPLIT!r}")
    checks.append(f"card declares all {len(ALL_CONFIGS)} config(s) and split {SPLIT!r}")

    # The reverse direction: a config declared in the card but never built would resolve
    # its path only because a stale file happened to survive on disk.
    declared_configs = set(re.findall(r"^\s*-?\s*config_name:\s*(\S+)\s*$", front, re.M))
    unknown = declared_configs - set(ALL_CONFIGS)
    if unknown:
        raise PreflightError(
            f"card declares config(s) no builder produces: {sorted(unknown)}"
        )

    for declared in re.findall(r"^\s*path:\s*(\S+)\s*$", front, re.M):
        if not (DATASET_DIR / declared).exists():
            raise PreflightError(f"card points at {declared!r}, which does not exist")
        checks.append(f"declared path resolves: {declared}")

    # The Hub only warns about invalid card metadata during upload, which is easy to miss
    # in a wall of progress bars -- and an unrecognised task_category silently drops the
    # dataset out of Hub search. Promote it to a hard failure here instead.
    try:
        from huggingface_hub import DatasetCard
    except ImportError:
        checks.append("SKIPPED metadata validation (huggingface_hub not installed)")
    else:
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            DatasetCard.load(str(CARD)).validate()
        if caught:
            raise PreflightError(
                "card metadata is invalid:\n  "
                + "\n  ".join(str(w.message) for w in caught)
            )
        checks.append("card metadata validates against Hub rules")

    try:
        from datasets import load_dataset
    except ImportError:
        checks.append("SKIPPED load check (datasets not installed)")
    else:
        for name, target, _ in _expected_artifacts():
            ds = load_dataset(
                "json", data_files={SPLIT: str(target)}, features=_features_for(name)
            )
            checks.append(
                f"{name} loads as {ds[SPLIT].num_rows} rows against declared features"
            )

    return checks


def push(repo_id: str, *, private: bool, dry_run: bool) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    who = api.whoami()
    url = f"https://huggingface.co/datasets/{repo_id}"

    files = publishable_files()

    if dry_run:
        print(f"\nDRY RUN -- nothing uploaded. Authenticated as {who['name']}.")
        print(f"Would create {'private' if private else 'PUBLIC'} dataset {repo_id}")
        print(f"Would upload {len(files)} file(s) from {DATASET_DIR}:")
        for f in files:
            print(f"    {f}")
        return url

    api.create_repo(repo_id=repo_id, repo_type="dataset", private=private, exist_ok=True)
    api.upload_folder(
        repo_id=repo_id,
        repo_type="dataset",
        folder_path=str(DATASET_DIR),
        ignore_patterns=IGNORE_PATTERNS,
        commit_message="Update Kryptos baseline config",
    )
    return url


def actual_visibility(repo_id: str) -> str:
    """Report the repo's real visibility rather than what was requested.

    ``create_repo(exist_ok=True)`` does not change the visibility of a repo that already
    exists, so a push that passes ``private=True`` at an already-public repo leaves it
    public. Reporting the requested flag would be actively misleading.
    """
    from huggingface_hub import HfApi

    return "private" if HfApi().dataset_info(repo_id).private else "PUBLIC"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-id", default=DEFAULT_REPO_ID)
    ap.add_argument(
        "--public",
        action="store_true",
        help="publish world-visible; private by default because this cannot be undone "
             "for anything that has already crawled or mirrored it",
    )
    ap.add_argument("--dry-run", action="store_true", help="run checks, upload nothing")
    args = ap.parse_args()

    try:
        for check in preflight():
            print(f"  ok  {check}")
    except PreflightError as exc:
        print(f"preflight failed: {exc}", file=sys.stderr)
        return 1

    url = push(args.repo_id, private=not args.public, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"\npublished {actual_visibility(args.repo_id)} dataset: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
