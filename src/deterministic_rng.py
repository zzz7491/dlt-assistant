"""P4-1 deterministic RNG seed derivation (production hardening).

Derives a stable, platform-independent integer RNG seed from a *publication
identity*. This is used ONLY to make the production recommendation path
reproducible: the same publication identity always yields the same seed, hence
the same A/B/C/D candidate bundle.

It does NOT pick a "best-performing" seed. The seed carries no performance
signal — it is purely a namespace key so that a given publication is reproducible.

Excluded from the digest (contract, see docs/architecture/DETERMINISTIC-RNG-CONTRACT.md):
  - draw results / future results / hit counts / backtest performance
  - current time / process id / machine id / system entropy
  - Python's process-salted hash()

Stdlib only (hashlib). No new dependencies.
"""
from __future__ import annotations

import hashlib

# -----------------------------------------------------------------
# Stable, human-auditable identity constants for the production publication.
#
# GAME_ID               : which lottery game (大乐透 = DLT).
# STRATEGY_BUNDLE       : namespace for the A/B/C/D recommendation bundle.
# ALGORITHM_VERSION     : the frozen recommendation algorithm version. When the
#                        algorithm is formally upgraded, bump this version; the
#                        new version deterministically yields a new seed sequence
#                        while every *published* (version, issue) pair can still
#                        be reproduced exactly.
# -----------------------------------------------------------------
GAME_ID = "DLT"
STRATEGY_BUNDLE = "BUNDLE"
ALGORITHM_VERSION = "dlt-recommender-v1"

# Full SHA-256 digest (32 bytes) -> 256-bit seed integer. The large namespace
# keeps seed collisions across distinct publications astronomically unlikely
# while remaining a plain deterministic int accepted by random.Random().
_SEED_BYTES = 32


class SeedDerivationError(RuntimeError):
    """A required publication-identity component is missing/empty.

    Fail-closed: P4-1 forbids silently falling back to seed=None.
    """


def derive_deterministic_seed(game_id: str, target_issue, strategy_id: str,
                             algorithm_version: str,
                             *, strict: bool = True) -> int:
    """Return a deterministic, platform-independent RNG seed.

    Same identity -> same seed. Different target_issue or algorithm_version ->
    (almost certainly) a different seed. Built on hashlib.sha256, never on
    Python's process-salted hash(), so results are identical across processes,
    machines, and interpreter runs.

    strict=True (default): raise SeedDerivationError if any component is missing
    or empty, instead of silently deriving a degenerate / None seed.
    """
    components = {
        "game_id": game_id,
        "target_issue": target_issue,
        "strategy_id": strategy_id,
        "algorithm_version": algorithm_version,
    }
    if strict:
        for name in ("game_id", "target_issue", "strategy_id", "algorithm_version"):
            val = components[name]
            if val is None or str(val).strip() == "":
                raise SeedDerivationError(
                    f"deterministic seed derivation missing required component {name!r}; "
                    "falling back to seed=None is forbidden (P4-1 STEP 14 fail-closed)."
                )
    normalized = "|".join(str(components[k]) for k in
                          ("game_id", "target_issue", "strategy_id", "algorithm_version"))
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:_SEED_BYTES], "big")


def publication_seed(target_issue, *, game_id: str = GAME_ID,
                     strategy_id: str = STRATEGY_BUNDLE,
                     algorithm_version: str = ALGORITHM_VERSION) -> int:
    """Convenience wrapper for the production call path: seed bound to a
    target_issue within the current game/strategy/algorithm namespace."""
    return derive_deterministic_seed(game_id, target_issue, strategy_id,
                                     algorithm_version)
