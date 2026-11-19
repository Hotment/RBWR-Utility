window.RoleCommands = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);
    const GROUPS = [
        ["Tickets", ["panel", "merge"]],
        ["Server", ["embed", "autorole"]],
        ["Community", ["starboard", "serverstats"]],
        ["Members", ["mod", "warn", "warnings", "unwarn", "nick", "note", "modlog", "userinfo"]],
        ["Bans", ["tempban", "unban"]],
        ["Channels", ["purge", "slowmode", "lock"]],
    ];
    const INFO = {
        panel: ["/panel", "Ticket panel and its buttons"], merge: ["/merge", "Merge tickets"],
        embed: ["/embed", "Post embeds as the bot"], autorole: ["/autorole", "Role given to new members"],
        starboard: ["/starboard", "Hall of fame channel"], serverstats: ["/serverstats", "Live counters in channel names"],
        mod: ["/mod", "Timeout, nickname, kick and ban panel"], warn: ["/warn", "Warn members"],
        warnings: ["/warnings", "See a member's warnings"], unwarn: ["/unwarn", "Remove warnings"],
        nick: ["/nick", "Change a member's nickname"], note: ["/note", "Private notes about members"],
        modlog: ["/modlog", "A member's moderation history"], userinfo: ["User info", "Right-click member details"],
        tempban: ["/tempban", "Ban for a limited time"], unban: ["/unban", "Lift bans"],
        purge: ["/purge", "Delete up to 100 messages"], slowmode: ["/slowmode", "Limit how often people post"],
        lock: ["/lock, /unlock", "Stop everyone from writing"],
    };
    const RISKY = new Set(["mod", "tempban", "unban", "purge", "lock", "autorole", "embed", "serverstats"]);
    let st = null;
    let pick = null;
    let wired = false;

    const chip = (key, on) => `
        <label class="flex items-center justify-between gap-2 p-2.5 rounded-lg border cursor-pointer select-none transition ${on ? "border-blue-500/40 bg-blue-500/10 text-white" : "border-white/5 bg-black/20 text-slate-400 hover:border-white/10"}">
            <span class="flex flex-col">
                <span class="font-bold text-xs text-slate-200 font-mono">${esc(INFO[key][0])}${RISKY.has(key) ? ' <span class="text-[9px] text-rose-300 border border-rose-500/30 rounded px-1">HIGH IMPACT</span>' : ""}</span>
                <span class="text-[10px] text-slate-500 font-mono">${esc(INFO[key][1])}</span>
            </span>
            <input type="checkbox" data-role-cmd="${key}" ${on ? "checked" : ""} class="accent-blue-500">
        </label>`;

    function render() {
        const body = $("role-cmds-body");
        const known = new Map(st.roles.map((r) => [r.id, r]));
        Object.keys(st.assigned).forEach((id) => { if (!known.has(id)) known.set(id, { id, name: `Deleted role (${id})` }); });
        if (!known.size) {
            body.innerHTML = `<p class="text-xs text-slate-500 italic font-mono">${st.bot_online ? "There are no roles on the server." : "The role list needs the Discord bot to be online."}</p>`;
            return;
        }
        if (!known.has(pick)) pick = Object.keys(st.assigned)[0] || [...known.keys()][0];
        const cmds = st.assigned[pick] || [];
        const summary = Object.entries(st.assigned).map(([id, list]) => `
            <div class="text-xs font-mono"><span class="font-bold text-slate-200">@${esc(known.get(id)?.name || id)}</span>
                <span class="text-slate-500">${list.map((c) => esc(INFO[c]?.[0] || c)).join(", ")}</span></div>`).join("");
        body.innerHTML = `
            ${st.bot_online ? "" : '<p class="text-xs text-rose-400 font-mono mb-3">The Discord bot is offline: only roles that already have commands are listed.</p>'}
            <div class="flex flex-col gap-1 mb-4">${summary || '<p class="text-xs text-slate-500 italic font-mono">No role has commands yet.</p>'}</div>
            <label class="text-[10px] uppercase font-bold text-slate-400 tracking-wider font-mono" for="role-cmds-pick">Role</label>
            <select id="role-cmds-pick" class="premium-input text-xs p-2.5 rounded-lg outline-none w-full max-w-sm mt-1 mb-4 block">
                ${[...known.values()].map((r) => `<option value="${esc(r.id)}" ${r.id === pick ? "selected" : ""}>@${esc(r.name)}${st.assigned[r.id] ? ` (${st.assigned[r.id].length})` : ""}</option>`).join("")}
            </select>
            <div class="flex flex-col gap-3.5">
                ${GROUPS.map(([title, keys]) => `
                <div class="flex flex-col gap-2">
                    <span class="text-[11px] font-bold text-slate-300">${esc(title)}</span>
                    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">${keys.map((k) => chip(k, cmds.includes(k))).join("")}</div>
                </div>`).join("")}
            </div>
            <div class="flex justify-end pt-3 mt-3 border-t border-white/5">
                <button type="button" data-save-role-cmds class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg uppercase font-bold text-xs font-mono tracking-wider transition">Save role commands</button>
            </div>`;
    }

    function wire() {
        if (wired) return;
        wired = true;
        const body = $("role-cmds-body");
        body.addEventListener("change", (e) => {
            if (e.target.id === "role-cmds-pick") { pick = e.target.value; render(); }
        });
        body.addEventListener("click", async (e) => {
            if (!e.target.closest("button[data-save-role-cmds]")) return;
            const commands = [...body.querySelectorAll("input[data-role-cmd]:checked")].map((c) => c.dataset.roleCmd);
            try {
                const res = await api(`/api/admin/role-commands/${encodeURIComponent(pick)}`, { method: "PUT", body: { commands } });
                st.assigned = res.assigned;
                render();
                toast("Role commands saved.");
            } catch (err) {
                toast(err.message, "error");
            }
        });
    }

    return {
        async open() {
            if (!$("role-cmds-body")) return;
            wire();
            try {
                st = await api("/api/admin/role-commands");
                render();
            } catch (err) {
                $("role-cmds-body").innerHTML = `<p class="text-xs text-rose-400 font-mono">${esc(err.message)}</p>`;
            }
        },
    };
})();
