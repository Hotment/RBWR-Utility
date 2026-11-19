window.RoleCommands = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);
    const GROUPS = [
        { name: "Tickets", badge: "TIX", badgeClass: "text-blue-400 border-blue-500/30 bg-blue-500/10", keys: ["panel", "merge"] },
        { name: "Server", badge: "SRV", badgeClass: "text-purple-400 border-purple-500/30 bg-purple-500/10", keys: ["embed", "autorole"] },
        { name: "Discord Community", badge: "COM", badgeClass: "text-pink-400 border-pink-500/30 bg-pink-500/10", keys: ["starboard", "serverstats"] },
        { name: "Members", badge: "MOD", badgeClass: "text-amber-400 border-amber-500/30 bg-amber-500/10", keys: ["mod", "warn", "warnings", "unwarn", "nick", "note", "modlog", "userinfo"] },
        { name: "Bans", badge: "BAN", badgeClass: "text-rose-400 border-rose-500/30 bg-rose-500/10", keys: ["tempban", "unban"] },
        { name: "Channels", badge: "CHN", badgeClass: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10", keys: ["purge", "slowmode", "lock"] },
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
    const ALL = GROUPS.flatMap((g) => g.keys);
    const PRESETS = {
        all: ALL,
        tickets: ["panel", "merge"],
        mod: ["mod", "warn", "warnings", "unwarn", "nick", "note", "modlog", "userinfo", "purge", "slowmode", "lock"],
        community: ["starboard", "serverstats"],
        clear: [],
    };
    const CHIP_ON = "flex items-center justify-between p-2.5 rounded-lg border border-blue-500/40 bg-blue-500/10 text-white cursor-pointer select-none transition hover:border-blue-400";
    const CHIP_OFF = "flex items-center justify-between p-2.5 rounded-lg border border-white/5 bg-black/20 text-slate-400 hover:text-slate-200 hover:border-white/10 cursor-pointer select-none transition";
    const PILL_ON = "text-[9px] font-mono px-1.5 py-0.5 rounded bg-blue-500/30 text-blue-300 font-bold tracking-wider";
    const PILL_OFF = "text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-slate-500 font-medium tracking-wider";
    let st = null;
    let extra = [];
    let wired = false;

    const countBadge = (n) => {
        const total = ALL.length;
        if (n === total) return ["border-emerald-500/30 bg-emerald-500/10 text-emerald-400", `${n}/${total} ALL ACCESS`];
        if (n === 0) return ["border-rose-500/30 bg-rose-500/10 text-rose-400", `0/${total} NO ACCESS`];
        return ["border-blue-500/30 bg-blue-500/10 text-blue-400", `${n}/${total} GRANTED`];
    };

    function roleCard(role, cmds) {
        const id = esc(role.id);
        const [badgeCls, badgeText] = countBadge(cmds.length);
        return `
            <div class="cyber-panel p-5 rounded-xl border border-white/10 flex flex-col gap-4 text-xs font-mono" data-role-card="${id}">
                <div class="flex justify-between items-start sm:items-center gap-3 flex-wrap">
                    <div class="flex items-center gap-2.5 flex-wrap">
                        <span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${role.color ? esc(role.color) : "#64748b"}"></span>
                        <span class="font-bold text-slate-100 text-sm font-display">@${esc(role.name)}</span>
                        <span class="px-2 py-0.5 rounded bg-[#5865F2]/20 text-[#5865F2] text-[10px] font-mono font-bold border border-[#5865F2]/30 cursor-pointer hover:bg-[#5865F2]/30 transition" title="Click to copy role ID" data-copy-role="${id}">ID: ${id}</span>
                        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${badgeCls}" data-role-count>${badgeText}</span>
                    </div>
                    <button type="button" data-remove-role="${id}" class="px-3 py-1 bg-rose-600/10 hover:bg-rose-600 text-rose-400 hover:text-white rounded-lg uppercase border border-rose-500/20 font-bold transition text-[11px]">Remove Role</button>
                </div>

                <div class="flex items-center justify-between gap-2 flex-wrap border-t border-b border-white/5 py-2.5">
                    <span class="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Quick Presets:</span>
                    <div class="flex items-center gap-1.5 flex-wrap">
                        <button type="button" data-preset="all" class="px-2.5 py-1 rounded bg-white/5 hover:bg-white/10 text-slate-300 hover:text-white text-[10px] font-mono font-semibold border border-white/10 transition">All Access</button>
                        <button type="button" data-preset="tickets" class="px-2.5 py-1 rounded bg-blue-500/10 hover:bg-blue-500/20 text-blue-300 text-[10px] font-mono font-semibold border border-blue-500/20 transition">Tickets</button>
                        <button type="button" data-preset="mod" class="px-2.5 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-[10px] font-mono font-semibold border border-amber-500/20 transition">Community Mod</button>
                        <button type="button" data-preset="community" class="px-2.5 py-1 rounded bg-pink-500/10 hover:bg-pink-500/20 text-pink-300 text-[10px] font-mono font-semibold border border-pink-500/20 transition">Community</button>
                        <button type="button" data-preset="clear" class="px-2 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 text-[10px] font-mono font-semibold border border-rose-500/20 transition">Clear All</button>
                    </div>
                </div>

                <div class="flex flex-col gap-3.5">
                    ${GROUPS.map((g) => `
                    <div class="flex flex-col gap-2">
                        <div class="flex items-center gap-2">
                            <span class="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${g.badgeClass}">${g.badge}</span>
                            <span class="text-[11px] font-bold text-slate-300">${esc(g.name)}</span>
                        </div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                            ${g.keys.map((k) => {
                                const on = cmds.includes(k);
                                return `
                                <div data-chip="${k}" class="${on ? CHIP_ON : CHIP_OFF}">
                                    <div class="flex flex-col">
                                        <span class="font-bold text-xs text-slate-200">${esc(INFO[k][0])}</span>
                                        <span class="text-[10px] text-slate-500 font-mono">${esc(INFO[k][1])}</span>
                                    </div>
                                    <input type="checkbox" data-role-cmd="${k}" ${on ? "checked" : ""} style="display:none">
                                    <span data-pill class="${on ? PILL_ON : PILL_OFF}">${on ? "ENABLED" : "DISABLED"}</span>
                                </div>`;
                            }).join("")}
                        </div>
                    </div>`).join("")}
                </div>

                <div class="flex justify-end pt-2 border-t border-white/5">
                    <button type="button" data-save-role="${id}" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg uppercase font-bold text-xs font-mono tracking-wider transition shadow-lg shadow-blue-600/20">Save Permissions</button>
                </div>
            </div>`;
    }

    function setChip(card, key, on) {
        const chip = card.querySelector(`[data-chip="${key}"]`);
        if (!chip) return;
        chip.querySelector("input").checked = on;
        chip.className = on ? CHIP_ON : CHIP_OFF;
        const pill = chip.querySelector("[data-pill]");
        pill.className = on ? PILL_ON : PILL_OFF;
        pill.textContent = on ? "ENABLED" : "DISABLED";
    }

    function updateCount(card) {
        const n = card.querySelectorAll("input[data-role-cmd]:checked").length;
        const [cls, text] = countBadge(n);
        const badge = card.querySelector("[data-role-count]");
        badge.className = `px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${cls}`;
        badge.textContent = text;
    }

    function render() {
        const body = $("role-cmds-body");
        const known = new Map(st.roles.map((r) => [r.id, r]));
        Object.keys(st.assigned).forEach((id) => { if (!known.has(id)) known.set(id, { id, name: `Deleted role (${id})` }); });
        const shown = [...Object.keys(st.assigned), ...extra.filter((id) => !st.assigned[id])];
        const free = st.roles.filter((r) => !shown.includes(r.id));
        body.innerHTML = `
            ${st.bot_online ? "" : '<p class="text-xs text-rose-400 font-mono mb-3">The Discord bot is offline: only roles that already have commands are listed.</p>'}
            ${free.length ? `
            <div class="flex items-end gap-2 flex-wrap mb-4">
                <div class="flex flex-col gap-1 grow max-w-sm">
                    <label class="text-[10px] uppercase font-bold text-slate-400 tracking-wider font-mono" for="role-cmds-add">Add Discord role</label>
                    <select id="role-cmds-add" class="premium-input text-xs p-2.5 rounded-lg outline-none w-full">
                        ${free.map((r) => `<option value="${esc(r.id)}">@${esc(r.name)}</option>`).join("")}
                    </select>
                </div>
                <button type="button" data-add-role class="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg uppercase font-bold text-xs font-mono tracking-wider transition">Add Role</button>
            </div>` : ""}
            <div class="flex flex-col gap-3">
                ${shown.length ? shown.map((id) => roleCard(known.get(id) || { id, name: id }, st.assigned[id] || [])).join("")
                    : '<p class="text-xs text-slate-500 italic font-mono">No role has commands yet. Add one above.</p>'}
            </div>`;
    }

    async function save(roleId, commands, done) {
        try {
            const res = await api(`/api/admin/role-commands/${encodeURIComponent(roleId)}`, { method: "PUT", body: { commands } });
            st.assigned = res.assigned;
            extra = extra.filter((id) => id !== roleId);
            render();
            toast(done);
        } catch (err) {
            toast(err.message, "error");
        }
    }

    function wire() {
        if (wired) return;
        wired = true;
        const body = $("role-cmds-body");
        body.addEventListener("click", (e) => {
            const card = e.target.closest("[data-role-card]");
            if (e.target.closest("[data-add-role]")) {
                const id = $("role-cmds-add").value;
                if (id && !extra.includes(id)) extra.push(id);
                render();
                return;
            }
            if (!card) return;
            const chip = e.target.closest("[data-chip]");
            if (chip) {
                setChip(card, chip.dataset.chip, !chip.querySelector("input").checked);
                updateCount(card);
                return;
            }
            const preset = e.target.closest("[data-preset]");
            if (preset) {
                ALL.forEach((k) => setChip(card, k, PRESETS[preset.dataset.preset].includes(k)));
                updateCount(card);
                return;
            }
            const copy = e.target.closest("[data-copy-role]");
            if (copy) {
                navigator.clipboard?.writeText(copy.dataset.copyRole);
                toast("Role ID copied.");
                return;
            }
            const id = card.dataset.roleCard;
            if (e.target.closest("[data-save-role]")) {
                save(id, [...card.querySelectorAll("input[data-role-cmd]:checked")].map((c) => c.dataset.roleCmd), "Role permissions saved.");
                return;
            }
            if (e.target.closest("[data-remove-role]") && confirm("Remove all commands from this role?")) {
                if (st.assigned[id]) save(id, [], "Role removed.");
                else { extra = extra.filter((x) => x !== id); render(); }
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
