from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class MergeError(ValueError):
    pass


def closed_status(ticket: dict[str, Any]) -> str:
    return "invalid" if ticket.get("type") == "bug_report" else "declined"


def _find(data: dict[str, Any], ticket_id: int) -> dict[str, Any] | None:
    return next((s for s in data.get("suggestions", []) if s.get("id") == ticket_id), None)


def merge(data: dict[str, Any], source_id: int, target_id: int, by: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    source = _find(data, source_id)
    target = _find(data, target_id)
    if source is None:
        raise MergeError(f"Ticket #{source_id} not found.")
    if target is None:
        raise MergeError(f"Ticket #{target_id} not found.")
    seen = {source_id}
    while target.get("merged_into"):
        if target["id"] in seen:
            raise MergeError("Those tickets are already merged into each other.")
        seen.add(target["id"])
        following = _find(data, target["merged_into"])
        if following is None:
            raise MergeError(f"Ticket #{target['id']} was already merged into #{target['merged_into']}, which no longer exists.")
        target = following
    if target["id"] == source_id:
        raise MergeError("A ticket can't be merged into itself.")
    if source.get("merged_into"):
        raise MergeError(f"Ticket #{source_id} is already merged into #{source['merged_into']}.")
    if (source.get("type") or "suggestion") != (target.get("type") or "suggestion"):
        raise MergeError("Only tickets of the same type can be merged (a bug into a bug, a suggestion into a suggestion).")

    is_bug = source.get("type") == "bug_report"
    previous = str(source.get("status") or ("open" if is_bug else "pending"))
    source["merged_into"] = target["id"]
    source["merged_at"] = datetime.now(timezone.utc).isoformat()
    source["merged_by"] = by
    source["status"] = closed_status(source)

    followers = target.setdefault("followers", [])
    newcomers = [{"discord_id": source.get("discord_id"), "name": source.get("discord_username") or source.get("name"),
                  "from_ticket": source_id}] + list(source.get("followers", []))
    for f in newcomers:
        did = str(f.get("discord_id") or "")
        if not did or did == str(target.get("discord_id") or ""):
            continue
        if any(str(x.get("discord_id") or "") == did for x in followers):
            continue
        followers.append(f)
    merged_from = target.setdefault("merged_from", [])
    if source_id not in merged_from:
        merged_from.append(source_id)
    return source, target, previous


def merge_notice(source: dict[str, Any], target: dict[str, Any]) -> str:
    title = target.get("title") or (target.get("suggestion") or target.get("description") or "")[:60]
    return (f"This ticket is about the same thing as #{target['id']}" + (f" \"{title}\"" if title else "")
            + ", so an administrator merged it there. Further updates happen in that ticket.")
