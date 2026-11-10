"""Optional block renderers: publications, licences, clinical, trades, languages, etc."""

from __future__ import annotations


def render_publications(p: dict, lines: list[str]) -> None:
    pubs = p.get("publications") or []
    if not pubs:
        return
    lines.append("PUBLICATIONS")
    for pub in pubs:
        line = pub.get("title", "")
        if pub.get("journal_or_venue"):
            line += f" — {pub['journal_or_venue']}"
        if pub.get("year"):
            line += f" ({pub['year']})"
        if pub.get("authors"):
            lines.append(f"Authors: {pub['authors']}")
        lines.append(line)
        if pub.get("doi_or_url"):
            lines.append(f"DOI/URL: {pub['doi_or_url']}")
        lines.append("")


def render_licenses(p: dict, lines: list[str]) -> None:
    licenses = p.get("licenses") or []
    if not licenses:
        return
    lines.append("LICENSES & REGISTRATIONS")
    for lic in licenses:
        line = lic.get("name", "")
        if lic.get("issuing_body"):
            line += f" — {lic['issuing_body']}"
        if lic.get("license_number"):
            line += f" [#{lic['license_number']}]"
        if lic.get("valid_until"):
            line += f" (Valid until: {lic['valid_until']})"
        lines.append(line)
    lines.append("")


def render_clinical_practice(p: dict, lines: list[str]) -> None:
    clinical = p.get("clinical_practice") or []
    if not clinical:
        return
    lines.append("CLINICAL PRACTICE")
    for entry in clinical:
        setting = entry.get("setting", "")
        role = entry.get("role", "")
        institution = entry.get("institution", "")
        if role and institution:
            lines.append(f"{role} — {institution} ({setting})")
        elif setting:
            lines.append(setting)

        start = entry.get("start_date", "")
        end = entry.get("end_date") or "Present"
        if start:
            lines.append(f"{start} - {end}")
        for r in entry.get("responsibilities") or []:
            lines.append(f"- {r}")
        lines.append("")


def render_trade_qualifications(p: dict, lines: list[str]) -> None:
    quals = p.get("trade_qualifications") or []
    if not quals:
        return
    lines.append("TRADE QUALIFICATIONS")
    for q in quals:
        line = q.get("qualification", "")
        if q.get("certifying_body"):
            line += f" — {q['certifying_body']}"
        if q.get("year"):
            line += f" ({q['year']})"
        lines.append(line)
    lines.append("")


def render_languages(p: dict, lines: list[str]) -> None:
    langs = p.get("languages") or []
    if not langs:
        return
    lines.append("LANGUAGES")
    for lang in langs:
        line = lang.get("language", "")
        if lang.get("proficiency"):
            line += f" ({lang['proficiency']})"
        lines.append(line)
    lines.append("")


def render_volunteering(p: dict, lines: list[str]) -> None:
    vols = p.get("volunteering") or []
    if not vols:
        return
    lines.append("VOLUNTEERING")
    for v in vols:
        org = v.get("organization", "")
        role = v.get("role", "")
        if role and org:
            lines.append(f"{role} at {org}")
        elif org:
            lines.append(org)
        if v.get("description"):
            lines.append(v["description"])
        lines.append("")


def render_awards(p: dict, lines: list[str]) -> None:
    awards = p.get("awards") or []
    if not awards:
        return
    lines.append("AWARDS & HONOURS")
    for award in awards:
        line = award.get("title", "")
        if award.get("issuer"):
            line += f" — {award['issuer']}"
        if award.get("year"):
            line += f" ({award['year']})"
        lines.append(line)
        if award.get("description"):
            lines.append(award["description"])
    lines.append("")
