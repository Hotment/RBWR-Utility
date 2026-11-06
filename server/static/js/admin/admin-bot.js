/* Admin panel: Discord bot sections — direct messages, moderation & warnings, autorole and the error monitor.
   The embed builder, automod and welcome/FAQ/custom commands live in embeds.js, automod.js and botconfig.js.
   admin_panel.html calls AdminBot.show(view) whenever a section is opened. */
window.AdminBot = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);
    const PERMS = window.ADMIN_PERMISSIONS || {};
    const can = (section) => !!PERMS[section];

    const state = {
        view: null,
        errors: [],
        errorFilter: "open",
        dms: [],
        dmSearch: [],
        dmOpen: null,
        dmPending: [],
        modSearch: [],
        modMember: null,
    };

    const setCount = (id, value, alert = false) => {
        const el = $(id);
        if (!el) return;
        el.textContent = value;
        el.classList.toggle("alert-count", alert);
    };

    // ------------------------------------------------------------ errors

    async function loadErrors() {
        if (!can("errors")) return;
        try {
            const data = await api("/api/admin/errors");
            state.errors = data.errors;
            const open = data.errors.filter((e) => !e.resolved).length;
            setCount("nav-count-errors", open, open > 0);
            const ov = $("ov-errors");
            if (ov) ov.textContent = open;
            $("errors-alert").innerHTML = data.alerts_configured
                ? ""
                : '<div class="alert info">Discord alerts are off — set <code>DISCORD_BOT_TOKEN</code> and <code>DISCORD_ERROR_ALERT_CHANNEL_ID</code> in <code>.env</code>. Errors are still recorded here.</div>';
            if (state.view === "errors") renderErrors();
        } catch (err) {
            if (state.view === "errors") toast(err.message, "error");
        }
    }

    function renderErrors() {
        const openDetails = new Set([...document.querySelectorAll("#errors-list details[open]")].map((d) => d.dataset.id));
        const list = state.errors.filter((e) =>
            state.errorFilter === "all" || (state.errorFilter === "open" ? !e.resolved : e.resolved));
        $("errors-list").innerHTML = list.length
            ? list.map((e) => {
                const ctx = Object.entries(e.context || {}).map(([k, v]) => `<span>${esc(k)}: ${esc(v)}</span>`).join("");
                return `
                <div class="error-item${e.resolved ? " resolved" : ""}">
                    <div class="row">
                        <div class="title">
                            <span class="tid">#${e.id}</span>
                            <strong>${esc(e.type)}</strong>
                            <span class="badge neutral">${esc(e.origin)}</span>
                            ${e.count > 1 ? `<span class="badge s-investigating">×${e.count}</span>` : ""}
                            ${e.resolved ? `<span class="badge s-fixed">Resolved${e.resolved_by ? ` by ${esc(e.resolved_by)}` : ""}</span>` : ""}
                        </div>
                        <div class="btn-row">
                            <button type="button" class="qbtn ${e.resolved ? "c-gold" : "c-green"}" data-err-resolve="${e.id}" data-resolved="${e.resolved ? 0 : 1}">${e.resolved ? "Reopen" : "Mark resolved"}</button>
                            <button type="button" class="qbtn c-red" data-err-delete="${e.id}">Delete</button>
                        </div>
                    </div>
                    <div class="err-msg">${esc(e.message)}</div>
                    <div class="err-meta">
                        <span title="${esc(AdminUtils.fmtDate(e.last_seen))}">Last: ${esc(AdminUtils.timeAgo(e.last_seen))}</span>
                        ${e.count > 1 ? `<span title="${esc(AdminUtils.fmtDate(e.first_seen))}">First: ${esc(AdminUtils.timeAgo(e.first_seen))}</span>` : ""}
                        ${ctx}
                    </div>
                    ${e.traceback ? `<details data-id="${e.id}" ${openDetails.has(String(e.id)) ? "open" : ""}><summary>Traceback</summary><pre>${esc(e.traceback)}</pre></details>` : ""}
                </div>`;
            }).join("")
            : `<div class="empty">${state.errorFilter === "open" ? "No unresolved errors." : "Nothing here."}</div>`;
    }

    async function sendTestAlert() {
        try {
            const res = await api("/api/admin/errors/test", { method: "POST", body: {} });
            toast(res.sent ? "Test alert recorded and sent to Discord." : "Test alert recorded (it couldn't be sent to Discord — check the bot token and alert channel).");
            await loadErrors();
        } catch (err) { toast(err.message, "error"); }
    }

    // ------------------------------------------------------------ direct messages

    async function loadDms() {
        if (!can("dms")) return;
        try {
            const { conversations } = await api("/api/admin/dms");
            state.dms = conversations;
            const unread = conversations.filter((c) => c.unread).length;
            setCount("nav-count-dms", unread, unread > 0);
            if (state.view === "dms") {
                renderDmList();
                if (state.dmOpen) loadConversation();
            }
        } catch (err) {
            if (state.view === "dms") toast(err.message, "error");
        }
    }

    const dmItem = (p, extra = "") => `
        <button type="button" class="eb-item${state.dmOpen?.user_id === p.user_id ? " active" : ""}" data-dm-user="${esc(p.user_id)}">
            <div class="auth-user">${AdminUtils.avatar(p.avatar, p.name, "sm")}
                <div class="eb-item-main"><strong>${esc(p.name || p.username || p.user_id)}</strong><span class="tk-sub">${extra}</span></div>
            </div>
        </button>`;

    function renderDmList() {
        $("dm-results").innerHTML = state.dmSearch.map((m) => dmItem(m, `@${esc(m.username)}`)).join("");
        $("dm-list").innerHTML = state.dms.length
            ? state.dms.map((c) => dmItem(c,
                `${c.unread ? `<span class="badge type-suggestion">${c.unread} new</span> ` : ""}${c.last.direction === "out" ? "You: " : ""}${esc(c.last.text)} · ${esc(AdminUtils.timeAgo(c.updated_at))}`)).join("")
            : '<div class="adm-hint">No conversations yet.</div>';
    }

    let dmSearchTimer = null;
    function searchMembers(q) {
        clearTimeout(dmSearchTimer);
        if (q.trim().length < 2) { state.dmSearch = []; renderDmList(); return; }
        dmSearchTimer = setTimeout(async () => {
            try {
                const { members } = await api(`/api/admin/discord/members?q=${encodeURIComponent(q.trim())}`);
                state.dmSearch = members.map((m) => ({ ...m, user_id: m.id }));
                if (!members.length) $("dm-results").innerHTML = '<div class="adm-hint">No members found.</div>';
                else renderDmList();
            } catch (err) { $("dm-results").innerHTML = `<div class="alert error">${esc(err.message)}</div>`; }
        }, 300);
    }

    let dmPollTimer = null;
    let dmListPollCounter = 0;

    function startDmPoller() {
        stopDmPoller();
        dmPollTimer = setInterval(async () => {
            if (state.view === "dms" && can("dms")) {
                if (state.dmOpen) {
                    await loadConversation(true);
                }
                dmListPollCounter++;
                if (dmListPollCounter >= 3) {
                    dmListPollCounter = 0;
                    await loadDms();
                }
            }
        }, 2000);
    }

    function stopDmPoller() {
        if (dmPollTimer) {
            clearInterval(dmPollTimer);
            dmPollTimer = null;
        }
    }

    function openConversation(profile) {
        state.dmOpen = profile;
        $("dm-chat").innerHTML = `
            <div class="dm-head">${AdminUtils.avatar(profile.avatar, profile.name)}
                <div><strong>${esc(profile.name || profile.user_id)}</strong><div class="tk-sub">${profile.username ? `@${esc(profile.username)} · ` : ""}<code>${esc(profile.user_id)}</code></div></div>
            </div>
            <div class="tk-msgs" id="dm-msgs"><div class="tk-empty">Loading…</div></div>
            <div class="tk-reply">
                <label class="hidden" for="dm-text">Message</label>
                <div class="dm-pending" id="dm-pending"></div>
                <textarea id="dm-text" class="adm-textarea" maxlength="2000" placeholder="Write a message as the RBWR bot… Paste a Tenor, Giphy or Klipy link to send a GIF, or attach / paste an image. (Enter to send, Shift+Enter for new line)"></textarea>
                <div class="tk-reply-row">
                    <input type="file" id="dm-file" accept="image/png,image/jpeg,image/gif,image/webp" multiple hidden>
                    <button type="button" class="mono-btn" id="dm-attach" title="Attach a GIF or image (max 4, 8 MB each)">GIF / image</button>
                    <button type="button" class="btn-gold" id="dm-send">Send DM</button>
                </div>
            </div>`;
        state.dmPending = [];
        renderDmList();
        loadConversation(false);
        startDmPoller();
        $("dm-text").focus();
    }

    async function loadConversation(isPoll = false) {
        const open = state.dmOpen;
        if (!open) return;
        try {
            const { conversation } = await api(`/api/admin/dms/${encodeURIComponent(open.user_id)}`);
            if (state.dmOpen !== open || !$("dm-msgs")) return;
            const box = $("dm-msgs");
            const messages = conversation?.messages || [];
            const lastAt = messages.length ? messages[messages.length - 1].at : "";
            const count = messages.length;

            if (isPoll && box.dataset.loaded === open.user_id && box.dataset.lastCount === String(count) && box.dataset.lastAt === lastAt) {
                return;
            }

            const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
            box.innerHTML = messages.length ? messages.map((m) => `
                <div class="msg ${m.direction === "out" ? "admin mine" : "author"}">
                    ${m.direction === "out" ? AdminUtils.avatar("/static/favicon.png", "RBWR", "sm") : AdminUtils.avatar(open.avatar, open.name, "sm")}
                    <div class="bubble">
                        <div class="who"><strong>${esc(m.direction === "out" ? m.sent_by || "Admin" : open.name)}</strong>
                            ${m.direction === "out" ? '<span class="role">via bot</span>' : ""}
                            <span title="${esc(AdminUtils.fmtDate(m.at))}">${esc(AdminUtils.timeAgo(m.at))}</span></div>
                        ${dmBody(m)}
                    </div>
                </div>`).join("") : '<div class="tk-empty">No messages yet — say hi.</div>';

            if (atBottom || box.dataset.loaded !== open.user_id) box.scrollTop = box.scrollHeight;
            box.dataset.loaded = open.user_id;
            box.dataset.lastCount = String(count);
            box.dataset.lastAt = lastAt;

            if (conversation?.unread) loadDms();
            else if (isPoll && count !== Number(box.dataset.prevRenderedCount || 0)) {
                renderDmList();
            }
            box.dataset.prevRenderedCount = String(count);
        } catch (err) {
            if (!isPoll) toast(err.message, "error");
        }
    }

    const MEDIA_HOSTS = ["discordapp.com", "discordapp.net", "tenor.com", "giphy.com", "klipy.com"];
    const mediaHostOk = (url) => {
        try {
            const u = new URL(url);
            return u.protocol === "https:" && MEDIA_HOSTS.some((d) => u.hostname === d || u.hostname.endsWith(`.${d}`));
        } catch (_) { return false; }
    };
    const IMAGE_URL = /^https:\/\/\S+\.(?:gif|png|jpe?g|webp)(?:\?\S*)?$/i;
    const imageUrl = (name) => `/api/admin/uploads/${encodeURIComponent(name)}`;

    function dmBody(m) {
        const items = [];
        for (const x of m.media || []) {
            if (x.local) items.push(`<img src="${esc(imageUrl(x.local))}" alt="Image" loading="lazy">`);
            else if (x.type === "video" && mediaHostOk(x.url)) {
                items.push(`<video src="${esc(x.url)}"${x.poster && mediaHostOk(x.poster) ? ` poster="${esc(x.poster)}"` : ""} autoplay loop muted playsinline></video>`);
            } else if (mediaHostOk(x.url)) items.push(`<img src="${esc(x.url)}" alt="GIF" loading="lazy" referrerpolicy="no-referrer">`);
        }
        for (const name of m.images || []) items.push(`<img src="${esc(imageUrl(name))}" alt="Image" loading="lazy">`);
        const shown = [];
        for (const line of String(m.text || "").split("\n")) {
            const t = line.trim();
            if (IMAGE_URL.test(t) && mediaHostOk(t)) items.push(`<img src="${esc(t)}" alt="Image" loading="lazy" referrerpolicy="no-referrer">`);
            else if (!((m.media || []).length && /^https:\/\/\S+$/.test(t) && mediaHostOk(t))) shown.push(line);
        }
        const text = shown.join("\n").trim();
        return `${text ? `<div class="text">${esc(text)}</div>` : ""}${items.length ? `<div class="dm-media">${items.join("")}</div>` : ""}`;
    }

    function renderDmPending() {
        const box = $("dm-pending");
        if (!box) return;
        box.innerHTML = state.dmPending.map((name) => `
            <span class="dm-pending-item"><img src="${esc(imageUrl(name))}" alt="">
            <button type="button" data-dm-unattach="${esc(name)}" title="Remove">×</button></span>`).join("");
    }

    async function uploadImage(file) {
        if (file.size > 8 * 1024 * 1024) throw new Error(`${file.name || "Image"} is larger than 8 MB.`);
        const res = await fetch("/api/admin/uploads", {
            method: "POST", credentials: "same-origin", headers: { "Content-Type": file.type || "application/octet-stream" }, body: file,
        });
        let data = null;
        try { data = await res.json(); } catch (_) { data = null; }
        if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : `Upload failed (${res.status}).`);
        return data.name;
    }

    async function attachDmFiles(files) {
        for (const file of files) {
            if (state.dmPending.length >= 4) return toast("At most 4 images per message.", "error");
            try {
                state.dmPending.push(await uploadImage(file));
                renderDmPending();
            } catch (err) { toast(err.message, "error"); }
        }
    }

    async function sendDm() {
        const input = $("dm-text");
        const text = input.value.trim();
        if ((!text && !state.dmPending.length) || !state.dmOpen) return;
        input.disabled = $("dm-send").disabled = true;
        try {
            await api(`/api/admin/dms/${encodeURIComponent(state.dmOpen.user_id)}`, { method: "POST", body: { message: text, images: state.dmPending } });
            state.dmPending = [];
            renderDmPending();
            input.value = "";
            await loadConversation();
            loadDms();
        } catch (err) {
            toast(err.message, "error");
        } finally {
            input.disabled = $("dm-send").disabled = false;
            input.focus();
        }
    }

    // ------------------------------------------------------------ moderation

    const MOD_DURATIONS = [["60s", "60 seconds"], ["5m", "5 minutes"], ["10m", "10 minutes"], ["1h", "1 hour"],
    ["1d", "1 day"], ["1w", "1 week"], ["28d", "28 days"]];

    function renderModResults() {
        $("mod-results").innerHTML = state.modSearch.map((m) => `
            <button type="button" class="eb-item${state.modMember?.id === m.id ? " active" : ""}" data-mod-user="${esc(m.id)}">
                <div class="auth-user">${AdminUtils.avatar(m.avatar, m.name, "sm")}
                    <div class="eb-item-main"><strong>${esc(m.name)}</strong><span class="tk-sub">@${esc(m.username)}</span></div>
                </div>
            </button>`).join("");
    }

    let modSearchTimer = null;
    function searchModMembers(q) {
        clearTimeout(modSearchTimer);
        if (q.trim().length < 2) { state.modSearch = []; renderModResults(); return; }
        modSearchTimer = setTimeout(async () => {
            try {
                const { members } = await api(`/api/admin/discord/members?q=${encodeURIComponent(q.trim())}`);
                state.modSearch = members;
                if (!members.length) $("mod-results").innerHTML = '<div class="adm-hint">No members found.</div>';
                else renderModResults();
            } catch (err) { $("mod-results").innerHTML = `<div class="alert error">${esc(err.message)}</div>`; }
        }, 300);
    }

    async function openModMember(id) {
        $("mod-member").innerHTML = '<div class="empty">Loading…</div>';
        try {
            const { member } = await api(`/api/admin/moderation/members/${encodeURIComponent(id)}`);
            state.modMember = member;
            renderModMember();
            renderModResults();
        } catch (err) {
            $("mod-member").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
        }
    }

    function renderModMember() {
        const m = state.modMember;
        const timedOut = m.timeout_until && new Date(m.timeout_until) > new Date();
        const off = m.problem ? "disabled" : "";
        const when = (iso) => iso ? `<span title="${esc(AdminUtils.fmtDate(iso))}">${esc(AdminUtils.timeAgo(iso))}</span>` : "—";
        $("mod-member").innerHTML = `
            <div class="dm-head">${AdminUtils.avatar(m.avatar, m.name)}
                <div><strong>${esc(m.name)}</strong><div class="tk-sub">@${esc(m.username)} · <code>${esc(m.id)}</code>${m.bot ? " · bot" : ""}</div></div>
            </div>
            ${m.problem ? `<div class="alert error">${esc(m.problem)}</div>` : ""}
            <div class="mod-info">
                <div><span class="adm-label">Nickname</span>${esc(m.nick || "—")}</div>
                <div><span class="adm-label">Account created</span>${when(m.created_at)}</div>
                <div><span class="adm-label">Joined server</span>${when(m.joined_at)}</div>
                <div><span class="adm-label">Timeout</span>${timedOut ? `until ${esc(AdminUtils.fmtDate(m.timeout_until))}` : "None"}</div>
            </div>
            <div class="adm-label">Roles</div>
            <div class="mod-roles">${m.roles.length
                ? m.roles.map((r) => `<span class="badge neutral"${r.color ? ` style="color:${esc(r.color)}"` : ""}>${esc(r.name)}</span>`).join("")
                : '<span class="adm-hint">No roles</span>'}</div>
            <div class="adm-label">Active warnings (${m.warnings.length})</div>
            <div class="mod-warnings">${m.warnings.length
                ? m.warnings.slice().reverse().map((w) => `
                    <div class="mod-warning">
                        <div><span class="tid">#${w.id}</span> ${esc(w.reason)}
                            <div class="adm-hint">${esc(w.moderator || "?")} · <span title="${esc(AdminUtils.fmtDate(w.at))}">${esc(AdminUtils.timeAgo(w.at))}</span></div></div>
                        <button type="button" class="qbtn c-grey" data-warn-remove="${w.id}">Remove</button>
                    </div>`).join("")
                : '<span class="adm-hint">No warnings</span>'}</div>
            <div class="adm-field">
                <label class="adm-label" for="mod-reason">Reason <span class="adm-optional">(audit log, mod log and DM to the member)</span></label>
                <input id="mod-reason" class="adm-input" maxlength="400">
            </div>
            <div class="mod-actions">
                <div>
                    <span class="adm-label">Warning</span>
                    <div class="btn-row">
                        <button type="button" class="qbtn c-gold" data-mod-action="warn" ${off}>Warn with the reason above</button>
                    </div>
                </div>
                <div>
                    <label class="adm-label" for="mod-duration">Timeout</label>
                    <div class="btn-row">
                        <select id="mod-duration" class="adm-select">${MOD_DURATIONS.map(([v, l]) => `<option value="${v}"${v === "10m" ? " selected" : ""}>${l}</option>`).join("")}</select>
                        <button type="button" class="qbtn c-blue" data-mod-action="timeout" ${off}>Timeout</button>
                        ${timedOut ? `<button type="button" class="qbtn c-green" data-mod-action="untimeout" ${off}>Remove timeout</button>` : ""}
                    </div>
                </div>
                <div>
                    <label class="adm-label" for="mod-nick">Nickname</label>
                    <div class="btn-row">
                        <input id="mod-nick" class="adm-input" maxlength="32" value="${esc(m.nick || "")}" placeholder="Empty resets it">
                        <button type="button" class="qbtn c-teal" data-mod-action="nick" ${off}>Save</button>
                    </div>
                </div>
                <div>
                    <label class="adm-label" for="mod-delete">Kick / Ban</label>
                    <div class="btn-row">
                        <select id="mod-delete" class="adm-select">
                            <option value="0">Keep their messages</option>
                            ${[1, 2, 3, 7].map((d) => `<option value="${d}">Delete last ${d} day${d > 1 ? "s" : ""} (ban)</option>`).join("")}
                        </select>
                        <button type="button" class="qbtn c-gold" data-mod-action="kick" ${off}>Kick</button>
                        <button type="button" class="qbtn c-red" data-mod-action="ban" ${off}>Ban</button>
                    </div>
                </div>
            </div>`;
    }

    async function modAction(action) {
        const m = state.modMember;
        if (!m) return;
        if (action === "warn" && !$("mod-reason").value.trim()) {
            $("mod-reason").focus();
            return toast("Write the reason for the warning first.", "error");
        }
        if (action === "kick" && !confirm(`Kick ${m.name} from the Discord server?`)) return;
        if (action === "ban" && !confirm(`Ban ${m.name} from the Discord server?`)) return;
        const body = {
            action,
            reason: $("mod-reason").value.trim(),
            duration: $("mod-duration").value,
            nick: $("mod-nick").value.trim(),
            delete_days: Number($("mod-delete").value),
        };
        document.querySelectorAll("#mod-member [data-mod-action]").forEach((b) => { b.disabled = true; });
        try {
            const res = await api(`/api/admin/moderation/members/${encodeURIComponent(m.id)}`, { method: "POST", body });
            toast(`${m.name} — ${res.result}.`);
            if (res.member) {
                state.modMember = res.member;
                renderModMember();
            } else {
                state.modMember = null;
                $("mod-member").innerHTML = `<div class="empty">${esc(m.name)} — ${esc(res.result)}.</div>`;
                renderModResults();
                loadModBans();
            }
        } catch (err) {
            toast(err.message, "error");
            if (state.modMember === m) renderModMember();
        }
    }

    async function loadModBans() {
        try {
            const { bans } = await api("/api/admin/moderation/bans");
            $("mod-bans-body").innerHTML = bans.length
                ? bans.map((b) => `
                    <tr>
                        <td><div class="auth-user">${AdminUtils.avatar(b.avatar, b.name, "sm")}
                            <div class="eb-item-main"><strong>${esc(b.name)}</strong><span class="tk-sub">@${esc(b.username)} · <code>${esc(b.id)}</code></span></div></div></td>
                        <td>${esc(b.reason || "—")}</td>
                        <td style="text-align:right"><button type="button" class="qbtn c-green" data-mod-unban="${esc(b.id)}" data-name="${esc(b.name)}">Unban</button></td>
                    </tr>`).join("")
                : '<tr><td colspan="3" class="adm-hint">Nobody is banned.</td></tr>';
        } catch (err) {
            $("mod-bans-body").innerHTML = `<tr><td colspan="3"><div class="alert error">${esc(err.message)}</div></td></tr>`;
        }
    }

    async function removeWarning(id) {
        if (!confirm(`Remove warning #${id}?`)) return;
        try {
            await api(`/api/admin/moderation/warnings/${id}`, { method: "DELETE" });
            toast(`Warning #${id} removed.`);
            if (state.modMember) openModMember(state.modMember.id);
        } catch (err) { toast(err.message, "error"); }
    }

    // escalation rules: [{count, action, duration}]
    const WARN_ACTIONS = { timeout: "Timeout", kick: "Kick", ban: "Ban" };
    let warnRules = [];

    async function loadWarnConfig() {
        try {
            renderWarnConfig(await api("/api/admin/moderation/warn-config"));
        } catch (err) {
            $("warn-rules").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
        }
    }

    function renderWarnConfig(config) {
        warnRules = config.rules.map((r) => ({ ...r }));
        $("warn-expire").value = String(config.expire_days || 0);
        renderWarnRules();
    }

    function renderWarnRules() {
        $("warn-rules").innerHTML = warnRules.length ? warnRules.map((r, i) => `
            <div class="warn-rule" data-rule="${i}">
                <span>At</span>
                <label class="hidden" for="wr-count-${i}">Warnings</label>
                <input id="wr-count-${i}" class="adm-input" type="number" min="1" max="50" value="${r.count}" data-field="count">
                <span>active warnings:</span>
                <label class="hidden" for="wr-action-${i}">Action</label>
                <select id="wr-action-${i}" class="adm-select" data-field="action">
                    ${Object.entries(WARN_ACTIONS).map(([v, l]) => `<option value="${v}"${r.action === v ? " selected" : ""}>${l}</option>`).join("")}
                </select>
                <label class="hidden" for="wr-duration-${i}">Timeout duration</label>
                <select id="wr-duration-${i}" class="adm-select${r.action === "timeout" ? "" : " hidden"}" data-field="duration">
                    ${MOD_DURATIONS.map(([v, l]) => `<option value="${v}"${r.duration === v ? " selected" : ""}>${l}</option>`).join("")}
                    ${r.duration && !MOD_DURATIONS.some(([v]) => v === r.duration) ? `<option value="${esc(r.duration)}" selected>${esc(r.duration)}</option>` : ""}
                </select>
                <button type="button" class="qbtn c-red" data-rule-remove="${i}">Remove</button>
            </div>`).join("")
            : '<div class="adm-hint">No rules — warnings never trigger an automatic action.</div>';
    }

    // ------------------------------------------------------------ autorole

    let autorolePoll = null;

    async function loadAutorole(withForm = false) {
        clearTimeout(autorolePoll);
        try {
            renderAutorole(await api("/api/admin/autorole"), withForm);
        } catch (err) {
            $("ar-alert").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
            $("ar-role").innerHTML = '<option value="">Discord bot unavailable</option>';
            $("ar-meta").textContent = $("ar-sync").textContent = "";
        }
    }

    function renderAutorole(d, withForm) {
        const problems = [];
        if (d.role?.problem) problems.push(d.role.problem);
        if (!d.members_intent) problems.push("The Server Members Intent is disabled in the Discord Developer Portal, so the bot doesn't see members joining.");
        let alert;
        if (!d.role) alert = '<div class="alert info">No autorole is set — new members don\'t get any role. Pick a role below.</div>';
        else if (problems.length) alert = `<div class="alert error"><strong>Autorole can't work right now:</strong><br>${problems.map(esc).join("<br>")}</div>`;
        else if (!d.enabled) alert = `<div class="alert info">Autorole is disabled — <strong>@${esc(d.role.name)}</strong> is set but not given to new members.</div>`;
        else alert = `<div class="alert success">Autorole is working — new members get <strong>@${esc(d.role.name)}</strong>.</div>`;
        $("ar-alert").innerHTML = alert;
        $("ar-guild").textContent = d.guild;

        if (withForm) {
            $("ar-role").innerHTML = '<option value="">— No role —</option>' + d.roles.map((r) =>
                `<option value="${esc(r.id)}">@${esc(r.name)}${r.problem ? " (bot can't assign it)" : ""}</option>`).join("");
            $("ar-role").value = d.configured_role_id || "";
            $("ar-enabled").checked = d.enabled;
            $("ar-bots").checked = d.include_bots;
        }
        const meta = [];
        if (d.role && d.source) meta.push(`Current role: @${d.role.name} (${d.source})`);
        if (d.updated_at) meta.push(`Last changed ${AdminUtils.timeAgo(d.updated_at)}${d.updated_by ? ` by ${d.updated_by}` : ""}`);
        $("ar-meta").textContent = meta.join(" · ");

        const s = d.last_sync;
        $("ar-sync").textContent = d.syncing
            ? "Sync in progress…"
            : s ? `Last sync ${AdminUtils.timeAgo(s.finished_at)} by ${s.started_by}: ${s.assigned} members got @${s.role_name}${s.failed ? `, ${s.failed} failed` : ""}.` : "";
        $("ar-sync-btn").disabled = d.syncing || !d.role;
        if (d.syncing && state.view === "autorole") autorolePoll = setTimeout(() => loadAutorole(), 3000);
    }

    // ------------------------------------------------------------ wiring

    function segment(id, onChange) {
        const root = $(id);
        if (!root) return;
        root.addEventListener("click", (e) => {
            const b = e.target.closest("button[data-value]");
            if (!b) return;
            root.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
            onChange(b.dataset.value);
        });
    }

    function bindErrors() {
        segment("errors-filter", (v) => { state.errorFilter = v; renderErrors(); });
        $("errors-list").addEventListener("click", async (e) => {
            const resolveBtn = e.target.closest("button[data-err-resolve]");
            const deleteBtn = e.target.closest("button[data-err-delete]");
            try {
                if (resolveBtn) {
                    await api(`/api/admin/errors/${resolveBtn.dataset.errResolve}/status`, {
                        method: "POST", body: { resolved: resolveBtn.dataset.resolved === "1" },
                    });
                } else if (deleteBtn) {
                    if (!confirm("Delete this error entry?")) return;
                    await api(`/api/admin/errors/${deleteBtn.dataset.errDelete}`, { method: "DELETE" });
                } else {
                    return;
                }
                await loadErrors();
            } catch (err) { toast(err.message, "error"); }
        });
        $("errors-test").addEventListener("click", () => sendTestAlert());
        $("errors-clear").addEventListener("click", async () => {
            if (!confirm("Delete all resolved errors?")) return;
            try {
                await api("/api/admin/errors/clear-resolved", { method: "POST" });
                await loadErrors();
            } catch (err) { toast(err.message, "error"); }
        });
    }

    function bindModeration() {
        $("mod-search").addEventListener("input", (e) => searchModMembers(e.target.value));
        $("mod-results").addEventListener("click", (e) => {
            const b = e.target.closest("button[data-mod-user]");
            if (b) openModMember(b.dataset.modUser);
        });
        $("mod-member").addEventListener("click", (e) => {
            const b = e.target.closest("button[data-mod-action]");
            if (b) modAction(b.dataset.modAction);
            const w = e.target.closest("button[data-warn-remove]");
            if (w) removeWarning(Number(w.dataset.warnRemove));
        });
        $("warn-rules").addEventListener("change", (e) => {
            const row = e.target.closest("[data-rule]");
            if (!row || !e.target.dataset.field) return;
            const rule = warnRules[Number(row.dataset.rule)];
            rule[e.target.dataset.field] = e.target.dataset.field === "count" ? Number(e.target.value) : e.target.value;
            if (e.target.dataset.field === "action") {
                if (rule.action === "timeout" && !rule.duration) rule.duration = "1h";
                renderWarnRules();
            }
        });
        $("warn-rules").addEventListener("click", (e) => {
            const b = e.target.closest("button[data-rule-remove]");
            if (!b) return;
            warnRules.splice(Number(b.dataset.ruleRemove), 1);
            renderWarnRules();
        });
        $("warn-add-rule").addEventListener("click", () => {
            const next = Math.max(0, ...warnRules.map((r) => r.count)) + 2;
            warnRules.push({ count: Math.min(next, 50), action: "timeout", duration: "1h" });
            renderWarnRules();
        });
        $("warn-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                renderWarnConfig(await api("/api/admin/moderation/warn-config", {
                    method: "PUT",
                    body: { expire_days: Number($("warn-expire").value), rules: warnRules },
                }));
                toast("Warning rules saved.");
            } catch (err) { toast(err.message, "error"); }
        });
        $("mod-bans-body").addEventListener("click", async (e) => {
            const b = e.target.closest("button[data-mod-unban]");
            if (!b || !confirm(`Unban ${b.dataset.name}?`)) return;
            b.disabled = true;
            try {
                await api(`/api/admin/moderation/bans/${encodeURIComponent(b.dataset.modUnban)}/unban`, { method: "POST", body: {} });
                toast(`${b.dataset.name} unbanned.`);
                loadModBans();
            } catch (err) { toast(err.message, "error"); b.disabled = false; }
        });
    }

    function bindDms() {
        $("dm-search").addEventListener("input", (e) => searchMembers(e.target.value));
        const pickDm = (e) => {
            const b = e.target.closest("button[data-dm-user]");
            if (!b) return;
            const id = b.dataset.dmUser;
            const profile = state.dmSearch.find((m) => m.user_id === id) || state.dms.find((c) => c.user_id === id);
            if (profile) openConversation(profile);
        };
        $("dm-results").addEventListener("click", pickDm);
        $("dm-list").addEventListener("click", pickDm);
        $("dm-chat").addEventListener("click", (e) => {
            if (e.target.id === "dm-send") sendDm();
            if (e.target.id === "dm-attach") $("dm-file").click();
            const un = e.target.closest("button[data-dm-unattach]");
            if (un) { state.dmPending = state.dmPending.filter((n) => n !== un.dataset.dmUnattach); renderDmPending(); }
        });
        $("dm-chat").addEventListener("change", (e) => {
            if (e.target.id !== "dm-file") return;
            attachDmFiles([...e.target.files]);
            e.target.value = "";
        });
        $("dm-chat").addEventListener("paste", (e) => {
            const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
            if (!files.length) return;
            e.preventDefault();
            attachDmFiles(files);
        });
        $("dm-chat").addEventListener("error", (e) => {
            if (e.target.matches?.(".dm-media img, .dm-media video")) e.target.classList.add("hidden");
        }, true);
        $("dm-chat").addEventListener("keydown", (e) => {
            if (e.target.id === "dm-text" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendDm(); }
        });
    }

    function bindAutorole() {
        $("ar-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                const data = await api("/api/admin/autorole", {
                    method: "POST",
                    body: { role_id: $("ar-role").value, enabled: $("ar-enabled").checked, include_bots: $("ar-bots").checked },
                });
                renderAutorole(data, true);
                toast("Autorole saved.");
            } catch (err) { toast(err.message, "error"); }
        });
        $("ar-sync-btn").addEventListener("click", async () => {
            if (!confirm("Give the autorole to every existing member who doesn't have it?")) return;
            try {
                renderAutorole(await api("/api/admin/autorole/sync", { method: "POST", body: { include_bots: $("ar-sync-bots").checked } }), false);
                toast("Sync started.");
            } catch (err) { toast(err.message, "error"); }
        });
    }

    async function loadBotStatus() {
        const el = $("bot-status");
        if (!el) return;
        try {
            const { online } = await api("/api/admin/bot-status");
            el.classList.toggle("online", online);
            el.classList.toggle("offline", !online);
            el.title = online ? "The Discord bot is connected." : "The Discord bot is offline.";
        } catch (_) { /* keep the last state */ }
    }

    function init() {
        if (can("errors") && $("errors-list")) bindErrors();
        if (can("moderation") && $("mod-search")) bindModeration();
        if (can("dms") && $("dm-search")) bindDms();
        if (can("autorole") && $("ar-form")) bindAutorole();
        loadBotStatus();
        loadErrors();
        loadDms();
        if (can("automod")) window.Automod?.poll(state.view);
        setInterval(() => {
            if (document.hidden) return;
            loadBotStatus();
            loadErrors();
            loadDms();
            if (can("automod")) window.Automod?.poll(state.view);
        }, 8000);
    }

    /** Called by the panel whenever a section is opened. */
    function show(view) {
        state.view = view;
        if (view !== "dms") stopDmPoller();
        if (view === "dms" && can("dms")) { renderDmList(); loadDms(); if (state.dmOpen) startDmPoller(); }
        if (view === "moderation" && can("moderation")) { loadModBans(); loadWarnConfig(); }
        if (view === "automod" && can("automod")) window.Automod?.open();
        if (view === "embeds" && can("embeds")) window.EmbedBuilder?.open();
        if (view === "autorole" && can("autorole")) loadAutorole(true);
        if (["welcome", "faq", "commands"].includes(view) && can(view)) window.BotConfig?.open(view);
        if (view === "errors" && can("errors")) { renderErrors(); loadErrors(); }
    }

    document.addEventListener("DOMContentLoaded", init);
    return { show };
})();