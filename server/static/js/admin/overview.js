// Admin panel → Overview: one row of indicators (open bugs, pending suggestions, errors, crashes,
// unread messages, active servers) and the bot status, from /admin/overview-stats.
// Only sections the admin can open are returned. Refreshes every 30 s and when Overview is shown.
window.Overview = (() => {
    const $ = (id) => document.getElementById(id);
    let timer = null;

    const TILES = [
        { key: "bugs", label: "Open bugs", href: "/admin/tickets", tone: "#f87171" },
        { key: "suggestions", label: "Pending suggestions", href: "/admin/tickets", tone: "#fbbf24" },
        { key: "errors", label: "Unresolved errors", href: "/admin/errors", tone: "#fb923c" },
        { key: "crashes", label: "Unresolved crashes", href: "/admin/crashes", tone: "#f472b6" },
        { key: "messages", label: "Unread messages", href: "/admin/contact", tone: "#a78bfa" },
        { key: "servers", label: "Active servers", href: "/admin/servers", tone: "#34d399" },
    ];

    function render(d) {
        const tiles = TILES.filter((t) => typeof d[t.key] === "number");
        const box = $("ov-stats");
        box.innerHTML = tiles.map((t) => `
            <a href="${t.href}" class="cyber-panel ov-stat ${d[t.key] > 0 && t.key !== "servers" ? "has" : ""}" style="--tone:${t.tone}">
                <span class="ov-value">${d[t.key]}</span>
                <span class="ov-label">${t.label}</span>
            </a>`).join("");
        box.hidden = !tiles.length;

        // keep the sidebar counter in step with the indicator
        const navErrors = $("nav-count-errors");
        if (navErrors && typeof d.errors === "number") {
            navErrors.textContent = d.errors;
            navErrors.classList.toggle("alert-count", d.errors > 0);
        }

        if (typeof d.bot_online === "boolean") {
            const pill = $("ov-bot");
            pill.hidden = false;
            pill.classList.toggle("online", d.bot_online);
            pill.classList.toggle("offline", !d.bot_online);
            $("ov-bot-text").textContent = d.bot_online ? "Discord bot online" : "Discord bot offline";
        }
    }

    async function load() {
        const view = $("view-overview");
        if (!view || view.classList.contains("hidden") || document.hidden) return;
        try {
            const res = await fetch("/admin/overview-stats", { credentials: "same-origin", headers: { Accept: "application/json" } });
            if (res.ok) render(await res.json());
        } catch (_) { /* offline: keep the last numbers */ }
    }

    function start() {
        if (!$("ov-stats")) return;
        load();
        // the panel switches views without reloading: refresh as soon as Overview is shown again
        new MutationObserver(load).observe($("view-overview"), { attributes: true, attributeFilter: ["class"] });
        clearInterval(timer);
        timer = setInterval(load, 30000);
        document.addEventListener("visibilitychange", load);
    }

    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
    return { refresh: load };
})();
