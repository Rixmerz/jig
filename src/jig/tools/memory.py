"""MCP tools: memory_get, memory_set, memory_delete."""
from __future__ import annotations


def register_memory_tools(mcp) -> None:

    @mcp.tool()
    def memory_get(
        tags: list[str] | None = None,
        top_n: int = 5,
        expand_links: bool = True,
    ) -> dict:
        # readOnlyHint: True
        """Retrieve relevant memories from the jig user-level memory store.

        Returns context-ready text for the top matching memory nodes,
        filtered by tags, with high-priority nodes always included and
        linked nodes expanded one level.

        Args:
            tags: Keywords to match against memory tags (e.g. ["boot", "plymouth"]).
                  If empty, returns only high-priority nodes.
            top_n: Max nodes to return (default 5). High-priority nodes are
                   always included on top of this limit.
            expand_links: Follow `links` fields one level to include related
                          nodes (default True).

        Returns:
            context: formatted text ready to prepend to a prompt
            nodes: list of matched node summaries (id, name, priority, tags)
            stats: token estimate for the returned context
        """
        from jig.engines.memory_store import query, CHARS_PER_TOKEN

        nodes = query(tags or [], top_n=top_n, expand_links=expand_links)
        if not nodes:
            return {"context": "", "nodes": [], "stats": {"tokens": 0}}

        context = "\n\n---\n\n".join(n.to_context() for n in nodes)
        return {
            "context": context,
            "nodes": [
                {"id": n.id, "name": n.name, "priority": n.priority, "tags": n.tags}
                for n in nodes
            ],
            "stats": {"tokens": len(context) // CHARS_PER_TOKEN},
        }

    @mcp.tool()
    def memory_set(
        id: str,
        name: str,
        description: str,
        type: str,
        body: str,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        priority: str = "normal",
        ttl: str = "",
    ) -> dict:
        """Create or update a memory node in the jig user-level memory store.

        Memories persist across projects and sessions at ~/.jig/memory/.
        Use this to record lessons learned, project context, user preferences,
        or cross-project references that should survive beyond a single session.

        Args:
            id: Unique slug (e.g. "feedback_amdgpu_boot"). Overwrites if exists.
            name: Human-readable title.
            description: One-line summary used for indexing.
            type: One of: feedback | project | user | reference
            body: Full markdown content of the memory.
            tags: Keywords for retrieval (e.g. ["boot", "plymouth", "amdgpu"]).
            links: IDs of related memories to expand when this node is activated.
            priority: "high" (always included), "normal" (default), "low" (only if relevant).
            ttl: Optional expiry: "90d", "4w", "48h". Omit for permanent.

        Returns:
            id: The saved node ID
            path: Absolute path to the memory file
        """
        from jig.engines.memory_store import MemoryNode, save, MEMORY_DIR

        node = MemoryNode(
            id=id,
            name=name,
            description=description,
            type=type,
            tags=tags or [],
            links=links or [],
            priority=priority,
            ttl=ttl,
            body=body,
        )
        save(node)
        return {"id": id, "path": str(MEMORY_DIR / f"{id}.md")}

    @mcp.tool()
    def memory_delete(id: str) -> dict:
        """Delete a memory node from the jig store by ID.

        Args:
            id: The node ID (slug) to delete.

        Returns:
            deleted: True if the file existed and was removed, False if not found.
        """
        from jig.engines.memory_store import MEMORY_DIR, _ensure_dir

        _ensure_dir()
        f = MEMORY_DIR / f"{id}.md"
        if f.exists():
            f.unlink()
            return {"deleted": True, "id": id}
        return {"deleted": False, "id": id}
