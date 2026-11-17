"""Skill aliases: short or vendor forms mapped to one canonical, normalised name."""

from app.domain.trust.normalise import normalise_text

# Keys are casefolded raw forms or normalise_text forms; values are normalise_text forms.
SKILL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "es6": "javascript",
    "ts": "typescript",
    "py": "python",
    "python3": "python",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "postgres": "postgresql",
    "psql": "postgresql",
    "pg": "postgresql",
    "mongo": "mongodb",
    "ms sql": "sql server",
    "mssql": "sql server",
    "microsoft sql server": "sql server",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "ms word": "word",
    "microsoft word": "word",
    "ms office": "microsoft office",
    "ms powerpoint": "powerpoint",
    "microsoft powerpoint": "powerpoint",
    "amazon web services": "aws",
    "google cloud platform": "gcp",
    "google cloud": "gcp",
    "microsoft azure": "azure",
    "node.js": "nodejs",
    "node js": "nodejs",
    "node": "nodejs",
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    "vue.js": "vue",
    "vuejs": "vue",
    "vue js": "vue",
    "next.js": "nextjs",
    "next js": "nextjs",
    "c++": "cpp",
    "c#": "csharp",
    ".net": "dotnet",
    "golang": "go",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "ci/cd": "ci cd",
    "cicd": "ci cd",
    "gh actions": "github actions",
    "tf": "terraform",
    "autocad 2d": "autocad",
    "plc programming": "plc",
    "cpr": "cardiopulmonary resuscitation",
    "bls": "basic life support",
    "acls": "advanced cardiac life support",
}


def canonical_skill(s: str) -> str:
    """One comparable form per skill: alias lookup on the raw form, then on the normalised form."""
    raw = " ".join(s.casefold().split())
    if raw in SKILL_ALIASES:
        return SKILL_ALIASES[raw]
    norm = normalise_text(s)
    return SKILL_ALIASES.get(norm, norm)


def skill_forms(canonical: str) -> set[str]:
    """The canonical form and its longer aliases, for searching free text.

    Aliases under three characters ("js", "ml") are left out: as bare words they collide with
    ordinary text ("ml" of medication) and would support a skill the source never names.
    """
    aliases = {normalise_text(k) for k, v in SKILL_ALIASES.items() if v == canonical}
    return {canonical, *(a for a in aliases if len(a) >= 3)}
