"""Deterministic per-entity seeding — architecture.md §4: each entity
generator derives its own child seed from the base seed, so adding/removing
an unrelated entity generator later cannot shift the random stream of
entities generated before it.

**Implementation note (a necessary precision, not a deviation):**
architecture.md §4 writes this as `hash((base_seed, entity_name)) mod
2**32`. Taken literally with Python's builtin `hash()`, that would *not* be
deterministic across process runs — `hash()` on a tuple containing a string
is salted per-process by `PYTHONHASHSEED` unless that env var is fixed,
which this project does not do. Using it would silently break the exact
reproducibility guarantee this whole generator exists to provide. This
module instead derives the child seed via SHA-256 (always deterministic,
independent of process/interpreter state), which is what "a deterministic
hash of (base_seed, entity_name)" actually requires to work as intended.
"""

import hashlib
import random

from faker import Faker


def child_seed(base_seed: int, entity_name: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{entity_name}".encode("utf-8")).hexdigest()
    return int(digest, 16) % (2**32)


def make_rng(base_seed: int, entity_name: str) -> random.Random:
    return random.Random(child_seed(base_seed, entity_name))


def make_faker(base_seed: int, entity_name: str) -> Faker:
    fake = Faker()
    Faker.seed(child_seed(base_seed, entity_name))
    return fake
