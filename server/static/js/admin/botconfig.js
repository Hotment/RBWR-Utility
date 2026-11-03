/* Admin panel: welcome & goodbye messages, FAQ and custom commands. */
window.BotConfig = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);

    let initialized = false;
    const discord = { channels: [], roles: [], canPingAll: false, loaded: false };

    // ------------------------------------------------------------ discord channels & roles

    async function loadDiscordLists() {
        if (discord.loaded) return;
        const [channels, roles] = await Promise.all([api("/api/admin/discord/channels"), api("/api/admin/discord/roles")]);
        discord.channels = channels.channels;
        discord.roles = roles.roles;
        discord.canPingAll = roles.can_ping_all;
        discord.loaded = true;
    }

    const channelOptions = (empty) => `<option value="">${esc(empty)}</option>` + discord.channels.map((c) =>
        `<option value="${esc(c.id)}">#${esc(c.name)}${c.category ? ` (${esc(c.category)})` : ""}</option>`).join("");
    const roleOptions = () => '<option value="">— No ping —</option>' + discord.roles.map((r) =>
        `<option value="${esc(r.id)}">@${esc(r.name)}${!r.mentionable && !discord.canPingAll ? " (not pingable)" : ""}</option>`).join("");
    const channelName = (id) => discord.channels.find((c) => c.id === id)?.name;
    const roleName = (id) => discord.roles.find((r) => r.id === id)?.name;

    function fillSelect(id, html, value) {
        const el = $(id);
        const keep = value ?? el.value;
        el.innerHTML = html;
        el.value = keep;
    }

    function fmtDuration(ms) {
        const m = Math.round(ms / 60000);
        if (m < 1) return "<1m";
        if (m < 60) return `${m}m`;
        const h = Math.floor(m / 60);
        return h < 24 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}d ${h % 24}h`;
    }

    const interval = (s) => s % 60 ? `${s} seconds` : `${s / 60} minute${s === 60 ? "" : "s"}`;

    // ------------------------------------------------------------ welcome & goodbye

    const GREETINGS = {
        welcome: ["Welcome message", "Posted when someone joins the server."],
        goodbye: ["Goodbye message", "Posted when someone leaves the server (or is kicked or banned)."],
    };

    async function loadWelcome() {
        try {
            await loadDiscordLists();
            renderWelcome(await api("/api/admin/welcome"));
        } catch (err) {
            $("wl-alert").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
        }
    }

    function renderWelcome(d) {
        $("wl-alert").innerHTML = d.bot_online ? "" : '<div class="alert error">The Discord bot is offline — nobody is greeted right now.</div>';
        $("wl-forms").innerHTML = Object.entries(GREETINGS).map(([kind, [title, sub]]) => {
            const c = d[kind] || {};
            return `
                <form class="card" data-greeting="${kind}">
                    <div class="filters" style="justify-content:space-between;margin:0">
                        <h2 style="margin:0">${title}</h2>
                        <label class="adm-check"><input type="checkbox" id="wl-${kind}-enabled" ${c.enabled ? "checked" : ""}> Enabled</label>
                    </div>
                    <p class="card-sub">${sub}</p>
                    <div class="adm-field">
                        <label class="adm-label" for="wl-${kind}-channel">Channel</label>
                        <select id="wl-${kind}-channel" class="adm-select">${channelOptions("Pick a channel…")}</select>
                    </div>
                    <div class="adm-field">
                        <label class="adm-label" for="wl-${kind}-message">Message text</label>
                        <textarea id="wl-${kind}-message" class="adm-textarea" maxlength="2000" rows="3" style="min-height:70px" placeholder="${esc(d.defaults[kind])}">${esc(c.message || "")}</textarea>
                        <div class="adm-hint">Empty = the default text above, or no text when an embed is chosen.</div>
                    </div>
                    <div class="adm-field">
                        <label class="adm-label" for="wl-${kind}-template">Embed <span class="adm-optional">(template from the Embed Builder)</span></label>
                        <select id="wl-${kind}-template" class="adm-select">
                            <option value="">— Text only —</option>
                            ${d.templates.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}
                        </select>
                    </div>
                    <label class="adm-check" style="margin-bottom:12px"><input type="checkbox" id="wl-${kind}-avatar" ${c.avatar_thumbnail ? "checked" : ""}> Show the member's avatar as the embed thumbnail</label>
                    <div class="btn-row">
                        <button type="submit" class="btn-gold" style="padding:10px 20px">Save</button>
                        <button type="button" class="mono-btn" data-greeting-test="${kind}" title="Post it now with you as the member">Send test</button>
                    </div>
                    ${c.updated_at ? `<div class="adm-hint" style="margin-top:10px">Last changed ${esc(AdminUtils.timeAgo(c.updated_at))} by ${esc(c.updated_by || "?")}</div>` : ""}
                </form>`;
        }).join("");
        for (const kind of Object.keys(GREETINGS)) {
            const c = d[kind] || {};
            $(`wl-${kind}-channel`).value = c.channel_id || "";
            $(`wl-${kind}-template`).value = c.template || "";
        }
    }

    // ------------------------------------------------------------ faq

    const faq = { entries: [], editing: null };

    async function loadFaq() {
        try {
            renderFaq(await api("/api/admin/faq"));
        } catch (err) { toast(err.message, "error"); }
    }

    function renderFaq(d) {
        faq.entries = d.entries;
        $("faq-body").innerHTML = faq.entries.length ? faq.entries.map((e) => `
            <tr>
                <td><code>${esc(e.name)}</code></td>
                <td><strong>${esc(e.title)}</strong><div class="adm-hint faq-answer">${esc(e.answer)}</div></td>
                <td>${e.uses || 0}×</td>
                <td style="text-align:right;white-space:nowrap">
                    <button type="button" class="qbtn c-grey" data-faq-edit="${esc(e.name)}">Edit</button>
                    <button type="button" class="qbtn c-red" data-faq-delete="${esc(e.name)}">Delete</button>
                </td>
            </tr>`).join("") : '<tr><td colspan="4" class="adm-hint">No FAQ entries yet. Add one above.</td></tr>';
    }

    function editFaq(entry) {
        faq.editing = entry ? entry.name : null;
        $("faq-name").value = entry?.name || "";
        $("faq-title").value = entry?.title || "";
        $("faq-answer").value = entry?.answer || "";
        $("faq-form-title").textContent = entry ? `Edit /faq ${entry.name}` : "Add a FAQ entry";
        $("faq-submit").textContent = entry ? "Save changes" : "Add entry";
        $("faq-cancel").classList.toggle("hidden", !entry);
        if (entry) $("faq-form").scrollIntoView({ behavior: "smooth" });
    }

    // ------------------------------------------------------------ custom commands

    const cc ={ data: null, editing: null };
    const COOLDOWNS = ["0", "5", "10", "30", "60", "300"];

    async function loadCommands() {
        try {
            await loadDiscordLists().catch(() => {});
            renderCommands(await api("/api/admin/commands"), true);
        } catch (err) { toast(err.message, "error"); }
    }

    function renderCommands(d, withForm = false) {
        cc.data = d;
        const p = esc(d.prefix);
        document.querySelectorAll(".cc-prefix").forEach((el) => { el.textContent = d.prefix; });
        $("cc-alert").innerHTML = d.message_content_intent ? "" :
            `<div class="alert error">The <strong>Message Content Intent</strong> is disabled in the Discord Developer Portal (or the bot is offline), so the bot can't read commands like <code>${p}bug</code>.</div>`;
        if (withForm) {
            $("cc-prefix").value = d.prefix;
            fillSelect("cc-template", '<option value="">Build it here</option>' +
                (d.templates.length ? `<optgroup label="Embed Builder templates">${d.templates.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}</optgroup>` : ""));
            fillSelect("cc-role", '<option value="">Everyone</option>' + discord.roles.map((r) => `<option value="${esc(r.id)}">Only @${esc(r.name)}</option>`).join(""));
        }
        $("cc-body").innerHTML = d.commands.length ? d.commands.map((c) => `
            <tr>
                <td><code>${p}${esc(c.name)}</code>${c.aliases?.length ? `<div class="adm-hint">${c.aliases.map((a) => p + esc(a)).join(", ")}</div>` : ""}
                    ${c.role_id ? `<div class="adm-hint">Only @${esc(roleName(c.role_id) || c.role_id)}</div>` : ""}</td>
                <td><div class="faq-answer">${esc(c.response) || '<span class="adm-hint">(embed only)</span>'}</div>
                    ${c.template ? `<div class="adm-hint">Embed: ${esc(c.template)}</div>` : c.embed ? `<div class="adm-hint">Embed: ${esc(c.embed.title || "own embed")}</div>` : ""}</td>
                <td>${c.uses || 0}×</td>
                <td><button type="button" class="qbtn ${c.enabled ? "c-green" : "c-grey"}" data-cc-toggle="${esc(c.name)}">${c.enabled ? "On" : "Off"}</button></td>
                <td style="text-align:right;white-space:nowrap">
                    <button type="button" class="qbtn c-grey" data-cc-edit="${esc(c.name)}">Edit</button>
                    <button type="button" class="qbtn c-red" data-cc-delete="${esc(c.name)}">Delete</button>
                </td>
            </tr>`).join("") : '<tr><td colspan="5" class="adm-hint">No commands yet. Add one above.</td></tr>';
    }

    function editCommand(c) {
        cc.editing = c ? c.name : null;
        $("cc-name").value = c?.name || "";
        $("cc-aliases").value = (c?.aliases || []).join(", ");
        $("cc-response").value = c?.response || "";
        $("cc-use-embed").checked = !!(c?.template || c?.embed);
        $("cc-template").value = c?.template || "";
        fillCommandEmbed(c?.embed);
        $("cc-role").value = c?.role_id || "";
        $("cc-cooldown").value = COOLDOWNS.includes(String(c?.cooldown)) ? String(c.cooldown) : "10";
        $("cc-reply").checked = c ? c.reply : true;
        $("cc-delete").checked = c ? c.delete_trigger : false;
        $("cc-enabled").checked = c ? c.enabled : true;
        $("cc-form-title").textContent = c ? `Edit ${cc.data.prefix}${c.name}` : "Add a command";
        $("cc-submit").textContent = c ? "Save changes" : "Add command";
        $("cc-cancel").classList.toggle("hidden", !c);
        if (c) $("cc-form").scrollIntoView({ behavior: "smooth" });
    }

    // ---- the command's own embed (stored as Discord embed JSON, edited as Embed Builder data)

    const DEFAULT_EMBED_COLOR = 0x00d1ff;
    const hexColor = (n) => `#${n.toString(16).padStart(6, "0").toUpperCase()}`;

    function setCommandColor(n) {
        $("cc-e-color").value = hexColor(n).toLowerCase();
        $("cc-e-color-hex").value = hexColor(n);
    }

    function readCommandEmbed() {
        const hex = $("cc-e-color-hex").value.trim().replace(/^#/, "");
        return {
            title: $("cc-e-title").value,
            url: $("cc-e-url").value.trim(),
            description: $("cc-e-description").value,
            color: /^[0-9a-f]{6}$/i.test(hex) ? parseInt(hex, 16) : DEFAULT_EMBED_COLOR,
            timestamp: $("cc-e-timestamp").checked,
            author: { name: $("cc-e-author").value, url: "", icon_url: "" },
            thumbnail_url: $("cc-e-thumbnail").value.trim(),
            image_url: $("cc-e-image").value.trim(),
            footer: { text: $("cc-e-footer").value, icon_url: "" },
            fields: [],
        };
    }

    function fillCommandEmbed(discordEmbed) {
        const e = EmbedBuilder.fromDiscord(discordEmbed) || EmbedBuilder.fromDiscord({});
        $("cc-e-title").value = e.title;
        $("cc-e-url").value = e.url;
        $("cc-e-description").value = e.description;
        setCommandColor(e.color);
        $("cc-e-author").value = e.author.name;
        $("cc-e-thumbnail").value = e.thumbnail_url;
        $("cc-e-image").value = e.image_url;
        $("cc-e-footer").value = e.footer.text;
        $("cc-e-timestamp").checked = e.timestamp;
        renderCommandPreview();
    }

    // the placeholders as they'd look when you use the command yourself
    function sampleText(text) {
        const values = {
            user: "@You", name: "You", username: "you", target: "@You", target_name: "You",
            server: "RBWR", channel: "#general", args: "…", site: location.origin,
        };
        return text.replace(/\{(\w+)\}/g, (m, key) => values[key] ?? m);
    }

    function renderCommandPreview() {
        const on = $("cc-use-embed").checked;
        const template = $("cc-template").value;
        $("cc-embed").classList.toggle("hidden", !on);
        $("cc-embed-fields").classList.toggle("hidden", !!template);
        if (!on) return;
        if (template) {
            $("cc-preview").innerHTML = `<div class="dc-empty">Posts the Embed Builder template “${esc(template)}”. Edit it in the Embed Builder.</div>`;
            return;
        }
        const md = (t) => EmbedBuilder.markdown(sampleText(t));
        const img = (url, cls) => /^https?:\/\//.test(sampleText(url)) ? `<img class="${cls}" src="${esc(sampleText(url))}" alt="" referrerpolicy="no-referrer">` : "";
        const e = readCommandEmbed();
        const content = $("cc-response").value.trim();
        const url = sampleText(e.url);
        const hasEmbed = e.title.trim() || e.description.trim() || e.author.name.trim() || e.footer.text.trim() || e.image_url || e.thumbnail_url;
        const now = new Date().toLocaleTimeString(AdminUtils.LOCALE, { hour: "2-digit", minute: "2-digit" });
        const footer = [e.footer.text.trim() && esc(sampleText(e.footer.text.trim())), e.timestamp && `Today at ${now}`].filter(Boolean);
        $("cc-preview").innerHTML = `
            <div class="dc-msg">
                <img class="dc-avatar" src="/static/favicon.png" alt="">
                <div class="dc-body">
                    <div class="dc-head"><span class="dc-name">RBWR Utility</span><span class="dc-app">APP</span><span class="dc-time">Today at ${now}</span></div>
                    ${content ? `<div class="dc-content">${md(content)}</div>` : ""}
                    ${hasEmbed ? `
                    <div class="dc-embed" style="border-left-color:${hexColor(e.color)}">
                        <div class="dc-embed-grid">
                            <div class="dc-embed-main">
                                ${e.author.name.trim() ? `<div class="dc-author">${esc(sampleText(e.author.name))}</div>` : ""}
                                ${e.title.trim() ? `<div class="dc-title">${/^https?:\/\//.test(url) ? `<a href="${esc(url)}" target="_blank" rel="noopener">${md(e.title)}</a>` : md(e.title)}</div>` : ""}
                                ${e.description.trim() ? `<div class="dc-desc">${md(e.description)}</div>` : ""}
                            </div>
                            ${img(e.thumbnail_url, "dc-thumb")}
                        </div>
                        ${img(e.image_url, "dc-image")}
                        ${footer.length ? `<div class="dc-footer"><span>${footer.join(" • ")}</span></div>` : ""}
                    </div>` : ""}
                    ${!hasEmbed && !content ? '<div class="dc-empty">Start typing to see the preview.</div>' : ""}
                </div>
            </div>`;
    }

    const commandBody = (c, overrides = {}) => ({
        name: c.name, aliases: c.aliases || [], response: c.response || "", template: c.template || "",
        embed: c.template || !c.embed ? null : EmbedBuilder.fromDiscord(c.embed),
        role_id: c.role_id || "", cooldown: c.cooldown || 0, reply: c.reply, delete_trigger: c.delete_trigger,
        enabled: c.enabled, original: c.name, ...overrides,
    });

    // ------------------------------------------------------------ wiring

    function bind() {
        // welcome & goodbye
        $("wl-forms").addEventListener("submit", async (e) => {
            e.preventDefault();
            const kind = e.target.dataset.greeting;
            try {
                renderWelcome(await api(`/api/admin/welcome/${kind}`, {
                    method: "PUT",
                    body: {
                        enabled: $(`wl-${kind}-enabled`).checked,
                        channel_id: $(`wl-${kind}-channel`).value,
                        message: $(`wl-${kind}-message`).value,
                        template: $(`wl-${kind}-template`).value,
                        avatar_thumbnail: $(`wl-${kind}-avatar`).checked,
                    },
                }));
                toast(`${GREETINGS[kind][0]} saved.`);
            } catch (err) { toast(err.message, "error"); }
        });
        $("wl-forms").addEventListener("click", async (e) => {
            const b = e.target.closest("button[data-greeting-test]");
            if (!b) return;
            b.disabled = true;
            try {
                await api(`/api/admin/welcome/${b.dataset.greetingTest}/test`, { method: "POST" });
                toast("Test message posted (the saved settings are used).");
            } catch (err) { toast(err.message, "error"); }
            b.disabled = false;
        });

        // faq
        $("faq-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                renderFaq(await api("/api/admin/faq", {
                    method: "POST",
                    body: {
                        name: $("faq-name").value.trim().toLowerCase(),
                        title: $("faq-title").value.trim(),
                        answer: $("faq-answer").value.trim(),
                        original: faq.editing || "",
                    },
                }));
                toast(faq.editing ? "FAQ entry saved." : "FAQ entry added.");
                editFaq(null);
            } catch (err) { toast(err.message, "error"); }
        });
        $("faq-cancel").addEventListener("click", () => editFaq(null));
        $("faq-body").addEventListener("click", async (e) => {
            const b = e.target.closest("button");
            if (!b) return;
            if (b.dataset.faqEdit) editFaq(faq.entries.find((x) => x.name === b.dataset.faqEdit));
            if (b.dataset.faqDelete) {
                if (!confirm(`Delete /faq ${b.dataset.faqDelete}?`)) return;
                try {
                    renderFaq(await api(`/api/admin/faq/${encodeURIComponent(b.dataset.faqDelete)}`, { method: "DELETE" }));
                    if (faq.editing === b.dataset.faqDelete) editFaq(null);
                    toast("FAQ entry deleted.");
                } catch (err) { toast(err.message, "error"); }
            }
        });

        // custom commands
        $("cc-form").addEventListener("submit", async (e) => {
            e.preventDefault();
            try {
                renderCommands(await api("/api/admin/commands", {
                    method: "POST",
                    body: {
                        name: $("cc-name").value.trim().toLowerCase(),
                        aliases: $("cc-aliases").value.split(",").map((a) => a.trim().toLowerCase()).filter(Boolean),
                        response: $("cc-response").value.trim(),
                        template: $("cc-use-embed").checked ? $("cc-template").value : "",
                        embed: $("cc-use-embed").checked && !$("cc-template").value ? readCommandEmbed() : null,
                        role_id: $("cc-role").value,
                        cooldown: Number($("cc-cooldown").value),
                        reply: $("cc-reply").checked,
                        delete_trigger: $("cc-delete").checked,
                        enabled: $("cc-enabled").checked,
                        original: cc.editing || "",
                    },
                }));
                toast(cc.editing ? "Command saved." : "Command added.");
                editCommand(null);
            } catch (err) { toast(err.message, "error"); }
        });
        $("cc-cancel").addEventListener("click", () => editCommand(null));
        $("cc-form").addEventListener("input", renderCommandPreview);
        $("cc-form").addEventListener("change", renderCommandPreview);
        $("cc-e-color").addEventListener("input", () => { $("cc-e-color-hex").value = $("cc-e-color").value.toUpperCase(); renderCommandPreview(); });
        $("cc-e-color-hex").addEventListener("change", () => setCommandColor(readCommandEmbed().color));
        // broken image links are hidden instead of showing the browser's broken-image icon
        $("cc-preview").addEventListener("error", (e) => { if (e.target.tagName === "IMG") e.target.remove(); }, true);
        $("cc-body").addEventListener("click", async (e) => {
            const b = e.target.closest("button");
            if (!b) return;
            const find = (name) => cc.data.commands.find((c) => c.name === name);
            if (b.dataset.ccEdit) editCommand(find(b.dataset.ccEdit));
            if (b.dataset.ccToggle) {
                const c = find(b.dataset.ccToggle);
                try {
                    renderCommands(await api("/api/admin/commands", { method: "POST", body: commandBody(c, { enabled: !c.enabled }) }));
                } catch (err) { toast(err.message, "error"); }
            }
            if (b.dataset.ccDelete) {
                if (!confirm(`Delete ${cc.data.prefix}${b.dataset.ccDelete}?`)) return;
                try {
                    renderCommands(await api(`/api/admin/commands/${encodeURIComponent(b.dataset.ccDelete)}`, { method: "DELETE" }));
                    if (cc.editing === b.dataset.ccDelete) editCommand(null);
                    toast("Command deleted.");
                } catch (err) { toast(err.message, "error"); }
            }
        });
        const savePrefix = async (prefix) => {
            try {
                renderCommands(await api("/api/admin/commands/prefix", { method: "PUT", body: { prefix } }), true);
                toast(`Prefix saved — commands now start with ${prefix}`);
            } catch (err) { toast(err.message, "error"); }
        };
        $("cc-prefix-form").addEventListener("submit", (e) => {
            e.preventDefault();
            savePrefix($("cc-prefix").value.trim());
        });
        $("cc-prefix-form").addEventListener("click", (e) => {
            const b = e.target.closest("button[data-cc-prefix]");
            if (b) savePrefix(b.dataset.ccPrefix);
        });

    }

    return {
        open(view) {
            if (!initialized) { bind(); initialized = true; }
            if (view === "welcome") loadWelcome();
            if (view === "faq") loadFaq();
            if (view === "commands") loadCommands();
        },
    };
})();
