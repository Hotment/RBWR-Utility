window.Community = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);
    let st = null;
    let wired = false;

    const channelOptions = (selected) => {
        let html = '<option value="">Pick a channel</option>';
        if (selected && !st.text_channels.some((c) => c.id === selected)) {
            html += `<option value="${esc(selected)}" selected>Saved channel (${esc(selected)})</option>`;
        }
        return html + st.text_channels.map((c) =>
            `<option value="${esc(c.id)}" ${c.id === selected ? "selected" : ""}>#${esc(c.name)}${c.category ? ` · ${esc(c.category)}` : ""}</option>`).join("");
    };
    const state = (on, text) => `<span class="badge ${on ? "s-fixed" : "neutral"}">${esc(text || (on ? "On" : "Off"))}</span>`;
    const offline = () => (st.bot_online ? "" : "disabled");

    async function call(path, options, done) {
        try {
            const res = await api(path, options);
            render(res);
            if (done) toast(typeof done === "function" ? done(res) : done);
        } catch (err) {
            toast(err.message, "error");
        }
    }

    function starCard() {
        const c = st.starboard.config;
        const ready = c.enabled && c.channel_id;
        const ignored = new Set((c.ignored_channels || []).map(String));
        return `
        <div class="card" style="margin-bottom:20px">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h2>Starboard</h2>${state(ready)}</div>
            <p class="card-sub">Messages that get enough reactions are reposted to a hall of fame channel, with the author, text, image and a jump link. The count updates live; a post leaves the board when the original is deleted or drops below the threshold. <strong>${st.starboard.posts}</strong> on the board now. Same settings as <code>/starboard</code>.</p>
            ${c.channel_id ? "" : `
            <div class="btn-row" style="align-items:flex-end;margin-bottom:14px">
                <div><label class="adm-label" for="cm-sb-setup-emoji">Reaction</label><input class="adm-input" id="cm-sb-setup-emoji" value="${esc(c.emoji)}" maxlength="64" style="width:80px"></div>
                <div><label class="adm-label" for="cm-sb-setup-threshold">Needed</label><input class="adm-input" id="cm-sb-setup-threshold" type="number" min="1" max="100" value="${c.threshold}" style="width:90px"></div>
                <button type="button" class="btn-gold" data-act="sb-setup" ${offline()}>Quick setup</button>
                <span class="adm-hint">Creates <code>#starboard</code> (members can react but not write) and turns it on.</span>
            </div>`}
            <form id="cm-sb-form">
                <label class="adm-check"><input type="checkbox" id="cm-sb-enabled" ${c.enabled ? "checked" : ""}> Starboard on</label>
                <div class="inline-form" style="margin-top:10px">
                    <div><label class="adm-label" for="cm-sb-channel">Channel</label><select class="adm-select" id="cm-sb-channel">${channelOptions(c.channel_id)}</select></div>
                    <div><label class="adm-label" for="cm-sb-emoji">Reaction</label><input class="adm-input" id="cm-sb-emoji" value="${esc(c.emoji)}" maxlength="64" required></div>
                    <div><label class="adm-label" for="cm-sb-threshold">Needed</label><input class="adm-input" id="cm-sb-threshold" type="number" min="1" max="100" value="${c.threshold}" required></div>
                </div>
                <label class="adm-check"><input type="checkbox" id="cm-sb-self" ${c.self_star ? "checked" : ""}> Count the author's own reaction</label>
                <label class="adm-check"><input type="checkbox" id="cm-sb-bots" ${c.bots ? "checked" : ""}> Allow messages from bots</label>
                <div style="margin-top:12px">
                    <span class="adm-label">Ignored channels <span class="adm-optional">(their messages never go on the board)</span> · <span id="cm-sb-ignored-count">${ignored.size} ignored</span></span>
                    ${st.text_channels.length ? `
                    <input class="adm-input" id="cm-sb-ignored-search" type="search" placeholder="Find a channel" aria-label="Find a channel" style="margin:6px 0">
                    <div id="cm-sb-ignored" class="cm-checklist">
                        ${st.text_channels.map((ch) => `
                        <label class="adm-check" data-name="${esc(ch.name.toLowerCase())}">
                            <input type="checkbox" value="${esc(ch.id)}" ${ignored.has(ch.id) ? "checked" : ""}> #${esc(ch.name)}${ch.category ? ` <span class="adm-hint">${esc(ch.category)}</span>` : ""}
                        </label>`).join("")}
                    </div>` : `<p class="adm-hint">${ignored.size ? `${ignored.size} channel(s) ignored. ` : ""}The channel list needs the bot to be online.</p>`}
                </div>
                <p class="adm-hint">Custom server emoji work too: type it as <code>&lt;:name:id&gt;</code>.</p>
                <div class="btn-row" style="margin-top:12px"><button type="submit" class="btn-gold">Save</button></div>
            </form>
        </div>`;
    }

    function statsCard() {
        const s = st.serverstats;
        const c = s.config;
        const types = st.counter_types;
        const have = new Set(s.counters.map((x) => x.type));
        const free = Object.keys(types).filter((k) => !have.has(k));
        const setUp = Boolean(c.category_id);
        const rows = s.counters.map((x) => `
            <tr>
                <td><b>${esc(x.type)}</b><br><span class="adm-hint">${esc(types[x.type]?.label || "")}</span></td>
                <td><input class="adm-input" data-template="${esc(x.type)}" value="${esc(x.template)}" maxlength="90"></td>
                <td>${x.preview ? esc(x.preview) : '<span class="adm-hint">—</span>'}${x.exists === false ? '<br><span class="adm-hint" style="color:var(--danger)">Channel was deleted</span>' : ""}</td>
                <td><button type="button" class="qbtn c-red" data-act="ss-remove" data-type="${esc(x.type)}" ${offline()}>Remove</button></td>
            </tr>`).join("");
        return `
        <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:10px"><h2>Server stats</h2>${state(setUp && c.enabled, setUp ? (c.enabled ? "On" : "Paused") : "Off")}</div>
            <p class="card-sub">A <code>Server Stats</code> category at the top of the server with locked voice channels whose names show live numbers. Members can see them but not join. Updated every 10 minutes (Discord allows only 2 renames per channel per 10 minutes). Same settings as <code>/serverstats</code>.</p>
            ${setUp ? `
            <form id="cm-ss-form">
                <label class="adm-check"><input type="checkbox" id="cm-ss-enabled" ${c.enabled ? "checked" : ""}> Keep the numbers updated</label>
                <div class="table-wrap" style="margin-top:10px"><table class="admin-table">
                    <thead><tr><th>Counter</th><th>Channel name <span class="adm-optional">({value} = the number)</span></th><th>Now</th><th></th></tr></thead>
                    <tbody>${rows || '<tr><td colspan="4" class="adm-hint">No counters. Add one below.</td></tr>'}</tbody>
                </table></div>
                <div class="btn-row" style="margin-top:12px">
                    <button type="submit" class="btn-gold">Save names</button>
                    <button type="button" class="qbtn c-grey" data-act="ss-refresh" ${offline()}>Update now</button>
                    <button type="button" class="qbtn c-red" data-act="ss-delete" ${offline()}>Delete all stats channels</button>
                </div>
            </form>
            ${free.length ? `
            <div class="inline-form" style="margin-top:16px">
                <div><label class="adm-label" for="cm-ss-add-type">Add a counter</label>
                    <select class="adm-select" id="cm-ss-add-type">${free.map((k) => `<option value="${esc(k)}">${esc(k)} — ${esc(types[k].label)}</option>`).join("")}</select></div>
                <div><label class="adm-label" for="cm-ss-add-name">Name <span class="adm-optional">(optional)</span></label>
                    <input class="adm-input" id="cm-ss-add-name" maxlength="90" placeholder="e.g. Operators: {value}"></div>
                <div><button type="button" class="btn-gold" data-act="ss-add" ${offline()} style="width:100%;padding:10px">Add</button></div>
            </div>` : ""}` : `
            <div class="btn-row" style="align-items:center">
                <button type="button" class="btn-gold" data-act="ss-setup" ${offline()}>Quick setup</button>
                <span class="adm-hint">Creates the category with Members, Humans, Bots and Boosts. Add Open tickets and more afterwards.</span>
            </div>`}
            ${st.members_intent === false ? '<p class="adm-hint">Humans and Bots need the <strong>Server Members Intent</strong> in the Discord Developer Portal.</p>' : ""}
        </div>`;
    }

    function render(next) {
        st = next;
        $("cm-alert").innerHTML = st.bot_online ? "" :
            '<div class="alert error">The Discord bot is offline: you can change saved settings, but setting things up and the channel lists need it running.</div>';
        $("cm-body").innerHTML = starCard() + statsCard();
    }

    function wire() {
        if (wired) return;
        wired = true;
        const body = $("cm-body");
        body.addEventListener("input", (e) => {
            if (e.target.id !== "cm-sb-ignored-search") return;
            const q = e.target.value.trim().toLowerCase();
            body.querySelectorAll("#cm-sb-ignored [data-name]").forEach((row) => { row.hidden = Boolean(q) && !row.dataset.name.includes(q); });
        });
        body.addEventListener("change", (e) => {
            if (e.target.closest("#cm-sb-ignored")) {
                $("cm-sb-ignored-count").textContent = `${body.querySelectorAll("#cm-sb-ignored input:checked").length} ignored`;
            }
        });
        body.addEventListener("submit", (e) => {
            e.preventDefault();
            if (e.target.id === "cm-sb-form") {
                call("/api/admin/community/starboard", { method: "PUT", body: {
                    enabled: $("cm-sb-enabled").checked, channel_id: $("cm-sb-channel").value,
                    emoji: $("cm-sb-emoji").value.trim(), threshold: Number($("cm-sb-threshold").value) || 3,
                    self_star: $("cm-sb-self").checked, bots: $("cm-sb-bots").checked,
                    ignored_channels: $("cm-sb-ignored")
                        ? [...body.querySelectorAll("#cm-sb-ignored input:checked")].map((i) => i.value)
                        : (st.starboard.config.ignored_channels || []),
                } }, "Starboard saved.");
            }
            if (e.target.id === "cm-ss-form") {
                const templates = {};
                body.querySelectorAll("#cm-ss-form [data-template]").forEach((i) => { templates[i.dataset.template] = i.value; });
                call("/api/admin/community/serverstats", { method: "PUT", body: { enabled: $("cm-ss-enabled").checked, templates } },
                    "Saved. Names update within 10 minutes.");
            }
        });
        body.addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-act]");
            if (!btn || btn.disabled) return;
            const act = btn.dataset.act;
            if (act === "sb-setup") {
                call("/api/admin/community/starboard/setup", { method: "POST", body: {
                    emoji: $("cm-sb-setup-emoji").value.trim() || "⭐", threshold: Number($("cm-sb-setup-threshold").value) || 3,
                } }, "Starboard created.");
            }
            if (act === "ss-setup") call("/api/admin/community/serverstats/setup", { method: "POST" }, "Server stats created.");
            if (act === "ss-add") {
                call("/api/admin/community/serverstats/counters", { method: "POST", body: {
                    type: $("cm-ss-add-type").value, template: $("cm-ss-add-name").value,
                } }, "Counter added.");
            }
            if (act === "ss-remove" && confirm(`Remove the ${btn.dataset.type} counter and its channel?`)) {
                call(`/api/admin/community/serverstats/counters/${encodeURIComponent(btn.dataset.type)}`, { method: "DELETE" }, "Counter removed.");
            }
            if (act === "ss-refresh") {
                call("/api/admin/community/serverstats/refresh", { method: "POST" },
                    (r) => r.renamed ? `Updated ${r.renamed} channel${r.renamed === 1 ? "" : "s"}.` : "Everything is already up to date (or Discord's rename limit applies).");
            }
            if (act === "ss-delete" && confirm("Delete the Server Stats category and all its channels?")) {
                call("/api/admin/community/serverstats", { method: "DELETE" }, "Server stats removed.");
            }
        });
    }

    return {
        async open() {
            wire();
            if (!st) $("cm-body").innerHTML = '<p class="adm-hint">Loading…</p>';
            try {
                render(await api("/api/admin/community"));
            } catch (err) {
                $("cm-alert").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
            }
        },
    };
})();
