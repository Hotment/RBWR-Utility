/* Owner admin panel: automod settings, message test and incident log. */
window.Automod = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);

    const ACTIONS = { log: "Log only", delete: "Delete", warn: "Delete + warn", timeout: "Delete + timeout" };
    const JOIN_ACTIONS = { alert: "Log only", timeout: "Timeout", kick: "Kick" };
    const DURATIONS = [["60s", "60 seconds"], ["5m", "5 minutes"], ["10m", "10 minutes"], ["1h", "1 hour"],
        ["1d", "1 day"], ["1w", "1 week"], ["28d", "28 days"]];

    // field types: check, number, list (one entry per line)
    const FILTERS = [
        { key: "words", desc: "Messages with a blocked word. Matching ignores case, accents and look-alikes (h3ll0 = hello).",
            fields: [{ name: "words", type: "list", label: "Blocked words — one per line, * matches any letters (spam*)" }] },
        { key: "invites", desc: "Discord invite links (discord.gg/…) to other servers.",
            fields: [{ name: "allow_own", type: "check", label: "Allow invites to this server" }] },
        { key: "links", desc: "Links to any site that isn't on the list below. Subdomains are allowed too.",
            fields: [{ name: "allowed", type: "list", label: "Allowed domains — one per line" }] },
        { key: "mentions", desc: "Messages that mention many members or roles, or try to ping @everyone / @here without permission.",
            fields: [{ name: "max", type: "number", label: "Max mentions per message", min: 1, max: 100 }] },
        { key: "caps", desc: "Messages written mostly in capital letters.",
            fields: [{ name: "percent", type: "number", label: "Capital letters (%)", min: 50, max: 100 },
                { name: "min_length", type: "number", label: "Only from this many letters", min: 5, max: 500 }] },
        { key: "emoji", desc: "Messages with lots of emoji (custom server emoji count too).",
            fields: [{ name: "max", type: "number", label: "Max emoji per message", min: 1, max: 100 }] },
        { key: "lines", desc: "Very long messages that flood the channel with lines.",
            fields: [{ name: "max", type: "number", label: "Max lines per message", min: 3, max: 100 }] },
        { key: "spam", desc: "Many messages in a short time. The whole burst is deleted.",
            fields: [{ name: "messages", type: "number", label: "Messages", min: 2, max: 50 },
                { name: "seconds", type: "number", label: "Within seconds", min: 2, max: 120 }] },
        { key: "duplicates", desc: "The same message sent again and again (in any channel).",
            fields: [{ name: "count", type: "number", label: "Same message", min: 2, max: 20 },
                { name: "seconds", type: "number", label: "Within seconds", min: 5, max: 3600 }] },
    ];
    const JOIN = [
        { key: "raid", title: "Raid protection", actions: JOIN_ACTIONS,
            desc: "When many members join at once, raid mode starts and an alert is logged. Members who join during raid mode get the action below.",
            fields: [{ name: "joins", type: "number", label: "Joins", min: 3, max: 100 },
                { name: "seconds", type: "number", label: "Within seconds", min: 5, max: 600 },
                { name: "lockdown_minutes", type: "number", label: "Raid mode lasts (minutes)", min: 1, max: 1440 }] },
        { key: "account_age", title: "New accounts", actions: JOIN_ACTIONS, duration: true,
            desc: "Discord accounts younger than this get the action below when they join (kicked members are told why).",
            fields: [{ name: "days", type: "number", label: "Minimum account age (days)", min: 1, max: 365 }] },
    ];

    let initialized = false;
    const am = { data: null, channels: [], roles: [], exemptRoles: [], exemptChannels: [], listsLoaded: false };

    // ------------------------------------------------------------ loading

    async function load() {
        try {
            if (!am.listsLoaded) {
                const [channels, roles] = await Promise.all([api("/api/admin/discord/channels"), api("/api/admin/discord/roles")])
                    .catch(() => [{ channels: [] }, { roles: [] }]);
                am.channels = channels.channels;
                am.roles = roles.roles;
                am.listsLoaded = am.channels.length > 0;
            }
            render(await api("/api/admin/automod"), true);
        } catch (err) {
            $("am-alert").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
        }
    }

    // ------------------------------------------------------------ rendering

    function render(d, withForm) {
        am.data = d;
        renderAlerts(d);
        renderStats(d);
        renderIncidents(d);
        if (withForm) renderForm(d.config);
    }

    function renderAlerts(d) {
        const c = d.config;
        const alerts = [];
        if (!d.bot_online) alerts.push('<div class="alert error">The Discord bot is offline — automod isn\'t running.</div>');
        if (d.bot_online && !d.message_content_intent) {
            alerts.push('<div class="alert error">The <strong>Message Content Intent</strong> is disabled in the Discord Developer Portal, so the bot can\'t read messages and the message filters don\'t work.</div>');
        }
        if (d.bot_online && !d.members_intent && (c.raid.enabled || c.account_age.enabled)) {
            alerts.push('<div class="alert error">The <strong>Server Members Intent</strong> is disabled, so the bot doesn\'t see members joining and join protection doesn\'t work.</div>');
        }
        if (d.raid_until) {
            alerts.push(`<div class="alert error am-raid"><span><strong>Raid mode is on</strong> until ${esc(AdminUtils.fmtDate(d.raid_until))}. New members get: ${esc(JOIN_ACTIONS[c.raid.action])}.</span>
                <button type="button" class="qbtn c-red" id="am-end-raid">End raid mode</button></div>`);
        }
        if (!c.enabled) alerts.push('<div class="alert info">Automod is <strong>off</strong>. Turn it on below and save.</div>');
        $("am-alert").innerHTML = alerts.join("");
        updateCount(d);
    }

    function updateCount(d) {
        const el = $("nav-count-automod");
        if (!el) return;
        const day = recent(d.incidents, 1).length;
        el.textContent = d.config.enabled ? (d.raid_until ? "RAID" : String(day)) : "off";
        el.classList.toggle("alert-count", !!d.raid_until);
    }

    const recent = (incidents, days) => incidents.filter((i) => Date.now() - Date.parse(i.at) < days * 86400000);

    function renderStats(d) {
        const week = recent(d.incidents, 7);
        $("am-stat-day").textContent = recent(d.incidents, 1).length;
        $("am-stat-week").textContent = week.length;
        const counts = {};
        week.forEach((i) => { counts[i.filter] = (counts[i.filter] || 0) + 1; });
        const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
        $("am-stat-top").textContent = top ? d.labels[top[0]] || top[0] : "—";
        $("am-stat-raid").textContent = d.raid_until ? "On" : "Off";
    }

    function renderIncidents(d) {
        $("am-body").innerHTML = d.incidents.length ? d.incidents.map((i) => `
            <tr>
                <td style="white-space:nowrap" title="${esc(AdminUtils.fmtDate(i.at))}">${esc(AdminUtils.timeAgo(i.at))}</td>
                <td><div class="auth-user">${AdminUtils.avatar(i.user_avatar, i.user_name, "sm")}
                    <div class="eb-item-main"><strong>${esc(i.user_name)}</strong><span class="tk-sub"><code>${esc(i.user_id)}</code></span></div></div></td>
                <td>${esc(d.labels[i.filter] || i.filter)}${i.channel_name ? `<div class="adm-hint">#${esc(i.channel_name)}</div>` : ""}</td>
                <td>${esc(i.detail)}${i.content ? `<div class="am-content">${esc(i.content)}</div>` : ""}</td>
                <td><span class="pill">${esc(i.result || i.action)}</span></td>
            </tr>`).join("")
            : '<tr><td colspan="5" class="adm-hint">Nothing yet — incidents show up here as soon as automod acts.</td></tr>';
    }

    function actionControls(key, rule, actions, withDuration) {
        return `
            <div class="am-action-row">
                <div>
                    <label class="adm-label" for="am-${key}-action">Action</label>
                    <select id="am-${key}-action" class="adm-select" data-f="action">
                        ${Object.entries(actions).map(([v, l]) => `<option value="${v}"${rule.action === v ? " selected" : ""}>${l}</option>`).join("")}
                    </select>
                </div>
                ${withDuration ? `<div class="${rule.action === "timeout" ? "" : "hidden"}" data-duration-box>
                    <label class="adm-label" for="am-${key}-duration">Timeout</label>
                    <select id="am-${key}-duration" class="adm-select" data-f="duration">
                        ${DURATIONS.map(([v, l]) => `<option value="${v}"${rule.duration === v ? " selected" : ""}>${l}</option>`).join("")}
                        ${rule.duration && !DURATIONS.some(([v]) => v === rule.duration) ? `<option value="${esc(rule.duration)}" selected>${esc(rule.duration)}</option>` : ""}
                    </select>
                </div>` : ""}
            </div>`;
    }

    function fieldHtml(key, f, rule) {
        const id = `am-${key}-${f.name}`;
        if (f.type === "check") {
            return `<label class="adm-check"><input type="checkbox" id="${id}" data-f="${f.name}"${rule[f.name] ? " checked" : ""}> ${esc(f.label)}</label>`;
        }
        if (f.type === "list") {
            return `<div><label class="adm-label" for="${id}">${esc(f.label)}</label>
                <textarea id="${id}" class="adm-textarea am-list" rows="4" data-f="${f.name}" data-type="list">${esc((rule[f.name] || []).join("\n"))}</textarea></div>`;
        }
        return `<div><label class="adm-label" for="${id}">${esc(f.label)}</label>
            <input id="${id}" class="adm-input" type="number" min="${f.min}" max="${f.max}" required value="${esc(rule[f.name])}" data-f="${f.name}" data-type="number"></div>`;
    }

    function cardHtml(spec, rule, title, actions, withDuration) {
        return `
            <div class="card am-filter${rule.enabled ? "" : " off"}" data-am="${spec.key}">
                <label class="adm-check am-filter-head"><input type="checkbox" data-f="enabled"${rule.enabled ? " checked" : ""}>
                    <strong>${esc(title)}</strong></label>
                <p class="adm-hint am-desc">${esc(spec.desc)}</p>
                <div class="am-fields">${spec.fields.map((f) => fieldHtml(spec.key, f, rule)).join("")}</div>
                ${actionControls(spec.key, rule, actions, withDuration)}
            </div>`;
    }

    function renderForm(c) {
        $("am-enabled").checked = c.enabled;
        $("am-notify").checked = c.notify;
        $("am-staff").checked = c.exempt_staff;
        $("am-log").innerHTML = '<option value="">Moderation log channel (from .env)</option>' + am.channels.map((ch) =>
            `<option value="${esc(ch.id)}">#${esc(ch.name)}${ch.category ? ` (${esc(ch.category)})` : ""}</option>`).join("");
        if (c.log_channel_id && !am.channels.some((ch) => ch.id === c.log_channel_id)) {
            $("am-log").insertAdjacentHTML("beforeend", `<option value="${esc(c.log_channel_id)}">Channel ${esc(c.log_channel_id)}</option>`);
        }
        $("am-log").value = c.log_channel_id || "";
        am.exemptRoles = [...c.exempt_roles];
        am.exemptChannels = [...c.exempt_channels];
        renderExempt();
        $("am-filters").innerHTML = FILTERS.map((s) => cardHtml(s, c.filters[s.key], am.data.labels[s.key], ACTIONS, true)).join("");
        $("am-join").innerHTML = JOIN.map((s) => cardHtml(s, c[s.key], s.title, s.actions, !!s.duration)).join("");
        $("am-dirty").textContent = "";
    }

    function renderExempt() {
        const roleName = (id) => am.roles.find((r) => r.id === id)?.name || id;
        const channelName = (id) => am.channels.find((ch) => ch.id === id)?.name || id;
        const chips = (ids, name, prefix, kind) => ids.length
            ? ids.map((id) => `<span class="am-chip">${prefix}${esc(name(id))}<button type="button" data-unexempt="${kind}" data-id="${esc(id)}" aria-label="Remove">&times;</button></span>`).join("")
            : '<span class="adm-hint">None</span>';
        $("am-ex-roles").innerHTML = chips(am.exemptRoles, roleName, "@", "role");
        $("am-ex-channels").innerHTML = chips(am.exemptChannels, channelName, "#", "channel");
        $("am-ex-role").innerHTML = '<option value="">+ Add a role…</option>' + am.roles
            .filter((r) => !am.exemptRoles.includes(r.id)).map((r) => `<option value="${esc(r.id)}">@${esc(r.name)}</option>`).join("");
        $("am-ex-channel").innerHTML = '<option value="">+ Add a channel…</option>' + am.channels
            .filter((ch) => !am.exemptChannels.includes(ch.id)).map((ch) => `<option value="${esc(ch.id)}">#${esc(ch.name)}</option>`).join("");
    }

    // ------------------------------------------------------------ saving

    function readCard(card) {
        const out = {};
        card.querySelectorAll("[data-f]").forEach((el) => {
            if (el.type === "checkbox") out[el.dataset.f] = el.checked;
            else if (el.dataset.type === "number") out[el.dataset.f] = Number(el.value);
            else if (el.dataset.type === "list") out[el.dataset.f] = el.value.split("\n").map((x) => x.trim()).filter(Boolean);
            else out[el.dataset.f] = el.value;
        });
        return out;
    }

    function collect() {
        const card = (key) => readCard(document.querySelector(`[data-am="${key}"]`));
        const filters = {};
        FILTERS.forEach((s) => { filters[s.key] = card(s.key); });
        return {
            enabled: $("am-enabled").checked,
            log_channel_id: $("am-log").value,
            notify: $("am-notify").checked,
            exempt_staff: $("am-staff").checked,
            exempt_roles: am.exemptRoles,
            exempt_channels: am.exemptChannels,
            filters,
            raid: { ...am.data.config.raid, ...card("raid") },
            account_age: { ...am.data.config.account_age, ...card("account_age") },
        };
    }

    const markDirty = () => { $("am-dirty").textContent = "Unsaved changes"; };

    // ------------------------------------------------------------ wiring

    function bind() {
        $("am-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            const btn = e.submitter;
            if (btn) btn.disabled = true;
            try {
                render(await api("/api/admin/automod", { method: "PUT", body: collect() }), true);
                toast("Automod settings saved.");
            } catch (err) { toast(err.message, "error"); }
            if (btn) btn.disabled = false;
        });
        $("am-form").addEventListener("input", markDirty);
        $("am-form").addEventListener("change", (e) => {
            markDirty();
            const card = e.target.closest(".am-filter");
            if (!card) return;
            if (e.target.dataset.f === "enabled") card.classList.toggle("off", !e.target.checked);
            if (e.target.dataset.f === "action") card.querySelector("[data-duration-box]")?.classList.toggle("hidden", e.target.value !== "timeout");
        });
        $("am-ex-role").addEventListener("change", (e) => {
            if (e.target.value) { am.exemptRoles.push(e.target.value); renderExempt(); }
        });
        $("am-ex-channel").addEventListener("change", (e) => {
            if (e.target.value) { am.exemptChannels.push(e.target.value); renderExempt(); }
        });
        $("am-form").addEventListener("click", (e) => {
            const b = e.target.closest("button[data-unexempt]");
            if (!b) return;
            const list = b.dataset.unexempt === "role" ? am.exemptRoles : am.exemptChannels;
            list.splice(list.indexOf(b.dataset.id), 1);
            renderExempt();
            markDirty();
        });
        $("am-alert").addEventListener("click", async (e) => {
            if (e.target.id !== "am-end-raid") return;
            try {
                render(await api("/api/admin/automod/raid/end", { method: "POST" }), false);
                toast("Raid mode ended.");
            } catch (err) { toast(err.message, "error"); }
        });
        $("am-test-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const { hit } = await api("/api/admin/automod/test", { method: "POST", body: { text: $("am-test").value } });
                $("am-test-result").innerHTML = hit
                    ? `<span class="pill am-hit">${esc(am.data.labels[hit.filter])}: ${esc(hit.detail)} → ${esc(ACTIONS[hit.action])}</span>`
                    : '<span class="pill am-ok">No filter matches — the message would stay.</span>';
            } catch (err) { toast(err.message, "error"); }
        });
        $("am-clear").addEventListener("click", async () => {
            if (!confirm("Clear the automod incident log?")) return;
            try {
                render(await api("/api/admin/automod/incidents", { method: "DELETE" }), false);
                toast("Incident log cleared.");
            } catch (err) { toast(err.message, "error"); }
        });
    }

    return {
        open() {
            if (!initialized) { bind(); initialized = true; }
            load();
        },
        /** Refresh timer: keeps the nav badge (and the incident log of an open view) current. */
        async poll(view) {
            try {
                const d = await api("/api/admin/automod");
                if (view === "automod" && am.data) render(d, false);
                else updateCount(d);
            } catch (_) { /* shown when the view is opened */ }
        },
    };
})();
