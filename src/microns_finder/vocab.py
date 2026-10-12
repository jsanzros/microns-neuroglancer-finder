"""Cell-type vocabulary: map the names people use to MICrONS label values."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

import yaml

# Label systems, in the fallback order used by the default mode.
LABEL_SYSTEMS = ("subclass", "mtype", "meso")
LABEL_COLUMNS = {"subclass": "cell_type", "mtype": "mtype", "meso": "meso_type"}
LABEL_MODES = ("subclass", "mtype", "meso", "consensus")


@dataclass(frozen=True)
class Term:
    key: str
    label: str
    group: str = "any"
    synonyms: tuple[str, ...] = ()
    broad_type: tuple[str, ...] = ()
    definitions: dict[str, tuple[str, ...]] = field(default_factory=dict)  # system -> label values
    layers: tuple[str, ...] = ()  # default soma-layer filter for position-defined terms
    always: tuple[str, ...] = ()  # label systems required in every mode
    notes: str = ""

    def systems_for(self, mode: str) -> list[str]:
        """Label systems whose definitions a cell must satisfy under `mode`."""
        if mode not in LABEL_MODES:
            raise ValueError(f"labels must be one of {LABEL_MODES}, not {mode!r}")
        if not self.definitions:
            return []
        if mode == "consensus":
            return [s for s in LABEL_SYSTEMS if s in self.definitions]
        order = [mode] + [s for s in LABEL_SYSTEMS if s != mode]
        chosen = [next(s for s in order if s in self.definitions)]
        return chosen + [s for s in LABEL_SYSTEMS if s in self.always and s not in chosen]

    def describe(self, mode: str = "subclass") -> str:
        parts = []
        if self.broad_type:
            parts.append(f"broad_type in {list(self.broad_type)}")
        for system in self.systems_for(mode):
            parts.append(f"{LABEL_COLUMNS[system]} in {list(self.definitions[system])}")
        if self.layers:
            parts.append(f"soma in {list(self.layers)} (unless --layer is given)")
        return " AND ".join(parts) if parts else "(no label filter)"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "group": self.group,
            "synonyms": list(self.synonyms),
            "broad_type": list(self.broad_type),
            **{LABEL_COLUMNS[s]: list(v) for s, v in self.definitions.items()},
            **({"layer": list(self.layers)} if self.layers else {}),
            "notes": self.notes,
        }


def normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[\s_]+|(?<=[a-z])-(?=[a-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_TRAILING = re.compile(r"\s+(cells?|neurons?|interneurons?|types?)$")
_LEADING = re.compile(r"^(an?|the|some|one|any)\s+")


def _variants(text: str) -> list[str]:
    """Normalized forms of `text`, from most to least specific."""
    base = normalize(text)
    out = [base]
    stripped = _LEADING.sub("", base)
    out.append(stripped)
    for form in list(out):
        if form.endswith("s") and len(form) > 3 and not form.endswith("ss"):
            out.append(form[:-1])
    for form in list(out):
        out.append(_TRAILING.sub("", form))
    seen, unique = set(), []
    for form in out:
        if form and form not in seen:
            seen.add(form)
            unique.append(form)
    return unique


@lru_cache(maxsize=1)
def load_terms() -> tuple[Term, ...]:
    raw = yaml.safe_load(resources.files("microns_finder").joinpath("vocab.yaml").read_text(encoding="utf-8"))
    terms = []
    for entry in raw:
        definitions = {s: tuple(entry[s]) for s in LABEL_SYSTEMS if entry.get(s)}
        terms.append(
            Term(
                key=entry["key"],
                label=entry["label"],
                group=entry.get("group", "any"),
                synonyms=tuple(str(s) for s in entry.get("synonyms", [])),
                broad_type=tuple(entry.get("broad_type", [])),
                definitions=definitions,
                layers=tuple(entry.get("layer", [])),
                always=tuple(entry.get("always", [])),
                notes=entry.get("notes", "") or "",
            )
        )
    return tuple(terms)


@lru_cache(maxsize=1)
def _index() -> dict[str, Term]:
    index: dict[str, Term] = {}
    for term in load_terms():
        for name in (term.key, term.label, *term.synonyms):
            for form in _variants(name):
                if not _is_layer(form):  # "L1 cell" must not make "L1" a cell type
                    index.setdefault(form, term)
    return index


_LAYER_NAMES = {"L1", "L2", "L3", "L4", "L5", "L6", "WM"}


def _is_layer(text: str) -> bool:
    from .layers import parse_layers

    try:
        return bool(parse_layers(text))
    except ValueError:
        return False


def get_term(key: str) -> Term:
    for term in load_terms():
        if term.key == key:
            return term
    raise KeyError(key)


class UnknownTermError(ValueError):
    def __init__(self, text: str, suggestions: list[str], message: str | None = None):
        self.text = text
        self.suggestions = suggestions
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(message or f"Unknown cell type {text!r}.{hint} Run `microns-finder terms` to list them.")


def resolve(text: str, known_labels: dict[str, set[str]] | None = None) -> Term:
    """Resolve free text ("neurogliaform cells", "OPCs", "L5 PT") to a Term.

    Falls back to raw label values ("L2a", "6P-CT", "AltBasket") when
    `known_labels` ({system: set of values}) is given.
    """
    index = _index()
    forms = _variants(text)
    for form in forms:
        if form in index:
            return index[form]
    if known_labels:
        wanted = {f.replace(" ", "") for f in forms} | {text.strip().lower()}
        for system in LABEL_SYSTEMS:
            for value in sorted(known_labels.get(system, ())):
                if value in _LAYER_NAMES:  # "L1" is a layer here, not the meso_type class
                    continue
                if value.lower() in wanted or normalize(value) in forms:
                    return Term(
                        key=f"{system}:{value}",
                        label=f"{value} ({LABEL_COLUMNS[system]})",
                        definitions={system: (value,)},
                    )
    if _is_layer(normalize(text)):
        raise UnknownTermError(text, [], f"{text!r} is a layer, not a cell type. Ask for a type in it, e.g. 'neuron in {text}'.")
    suggestions = difflib.get_close_matches(normalize(text), list(index), n=5, cutoff=0.6)
    seen = []
    for s in suggestions:
        if index[s].key not in seen:
            seen.append(index[s].key)
    raise UnknownTermError(text, seen)
