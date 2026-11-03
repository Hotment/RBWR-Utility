/* Discord embed builder for the owner admin panel. */
window.EmbedBuilder = (() => {
    const { esc, api, toast } = AdminUtils;
    const $ = (id) => document.getElementById(id);
    const MAX_FIELDS = 25;
    const DEFAULT_COLOR = 0x00d1ff;

    let initialized = false;
    let fields = [];          // [{name, value, inline}]
    let channels = [];
    let roles = [];           // [{id, name, color, mentionable}]
    let canPingAll = false;
    let templates = [];
    let history = [];

    // ------------------------------------------------------------ form <-> data

    const hex = (n) => "#" + Number(n).toString(16).padStart(6, "0").toUpperCase();
    const parseHex = (s) => {
        const m = /^#?([0-9a-f]{6})$/i.exec((s || "").trim());
        return m ? parseInt(m[1], 16) : null;
    };

    /** Typed "@Role Name" -> "<@&id>", the only form Discord turns into a role ping. */
    function rolePings(text) {
        if (!roles.length || !text.includes("@")) return text;
        const names = roles.filter((r) => !/^@?everyone$/i.test(r.name)).sort((a, b) => b.name.length - a.name.length);
        return names.reduce((s, r) => {
            const escaped = r.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            return s.replace(new RegExp(`(^|[^<\\w])@${escaped}(?![\\w])`, "g"), `$1<@&${r.id}>`);
        }, text);
    }

    function readForm() {
        return {
            content: rolePings($("eb-content").value),
            allow_mentions: $("eb-mentions").checked,
            embed: {
                title: $("eb-title").value,
                url: $("eb-url").value.trim(),
                description: rolePings($("eb-description").value),
                color: parseHex($("eb-color-hex").value) ?? DEFAULT_COLOR,
                timestamp: $("eb-timestamp").checked,
                author: { name: $("eb-author-name").value, url: $("eb-author-url").value.trim(), icon_url: $("eb-author-icon").value.trim() },
                thumbnail_url: $("eb-thumbnail").value.trim(),
                image_url: $("eb-image").value.trim(),
                footer: { text: $("eb-footer-text").value, icon_url: $("eb-footer-icon").value.trim() },
                fields: fields.filter((f) => f.name.trim() || f.value.trim()).map((f) => ({ ...f, value: rolePings(f.value) })),
            },
        };
    }

    function fillForm(msg) {
        const e = msg.embed || {};
        $("eb-content").value = msg.content || "";
        $("eb-mentions").checked = !!msg.allow_mentions;
        $("eb-title").value = e.title || "";
        $("eb-url").value = e.url || "";
        $("eb-description").value = e.description || "";
        setColor(e.color ?? DEFAULT_COLOR);
        $("eb-timestamp").checked = !!e.timestamp;
        $("eb-author-name").value = e.author?.name || "";
        $("eb-author-url").value = e.author?.url || "";
        $("eb-author-icon").value = e.author?.icon_url || "";
        $("eb-thumbnail").value = e.thumbnail_url || "";
        $("eb-image").value = e.image_url || "";
        $("eb-footer-text").value = e.footer?.text || "";
        $("eb-footer-icon").value = e.footer?.icon_url || "";
        fields = (e.fields || []).slice(0, MAX_FIELDS).map((f) => ({ name: f.name || "", value: f.value || "", inline: !!f.inline }));
        renderFields();
        update();
    }

    /** Discord API embed JSON -> builder data (for imports and messages posted from Discord). */
    function fromDiscord(embed) {
        if (!embed) return null;
        return {
            title: embed.title || "",
            url: embed.url || "",
            description: embed.description || "",
            color: typeof embed.color === "number" ? embed.color : DEFAULT_COLOR,
            timestamp: !!embed.timestamp,
            author: { name: embed.author?.name || "", url: embed.author?.url || "", icon_url: embed.author?.icon_url || "" },
            thumbnail_url: embed.thumbnail?.url || "",
            image_url: embed.image?.url || "",
            footer: { text: embed.footer?.text || "", icon_url: embed.footer?.icon_url || "" },
            fields: (embed.fields || []).map((f) => ({ name: f.name || "", value: f.value || "", inline: !!f.inline })),
        };
    }

    /** Builder data -> Discord API embed JSON (for exports). */
    function toDiscord(e) {
        const out = { color: e.color };
        if (e.title.trim()) out.title = e.title.trim();
        if (e.url) out.url = e.url;
        if (e.description.trim()) out.description = e.description.trim();
        if (e.timestamp) out.timestamp = new Date().toISOString();
        if (e.author.name.trim()) out.author = { name: e.author.name.trim(), ...(e.author.url && { url: e.author.url }), ...(e.author.icon_url && { icon_url: e.author.icon_url }) };
        if (e.thumbnail_url) out.thumbnail = { url: e.thumbnail_url };
        if (e.image_url) out.image = { url: e.image_url };
        if (e.footer.text.trim()) out.footer = { text: e.footer.text.trim(), ...(e.footer.icon_url && { icon_url: e.footer.icon_url }) };
        if (e.fields.length) out.fields = e.fields;
        return out;
    }

    function setColor(n) {
        $("eb-color").value = hex(n).toLowerCase();
        $("eb-color-hex").value = hex(n);
    }

    // ------------------------------------------------------------ fields editor

    function renderFields() {
        $("eb-field-count").textContent = `(${fields.length} / ${MAX_FIELDS})`;
        $("eb-add-field").disabled = fields.length >= MAX_FIELDS;
        $("eb-fields").innerHTML = fields.map((f, i) => `
            <div class="eb-field" data-i="${i}">
                <div class="eb-field-top">
                    <span class="tk-sub">Field ${i + 1}</span>
                    <div class="btn-row">
                        <label class="adm-check" style="font-size:0.8rem"><input type="checkbox" data-k="inline" ${f.inline ? "checked" : ""}> Inline</label>
                        <button type="button" class="qbtn c-grey" data-act="up" ${i === 0 ? "disabled" : ""} aria-label="Move up">&uarr;</button>
                        <button type="button" class="qbtn c-grey" data-act="down" ${i === fields.length - 1 ? "disabled" : ""} aria-label="Move down">&darr;</button>
                        <button type="button" class="qbtn c-red" data-act="remove">Remove</button>
                    </div>
                </div>
                <label class="hidden" for="eb-f-name-${i}">Field ${i + 1} name</label>
                <input id="eb-f-name-${i}" class="adm-input" data-k="name" maxlength="256" placeholder="Name" value="${esc(f.name)}">
                <label class="hidden" for="eb-f-value-${i}">Field ${i + 1} value</label>
                <textarea id="eb-f-value-${i}" class="adm-textarea" data-k="value" maxlength="1024" rows="2" placeholder="Value" style="min-height:56px;margin-top:6px">${esc(f.value)}</textarea>
            </div>`).join("");
    }

    // ------------------------------------------------------------ preview (Discord look)

    function markdown(text) {
        let s = esc(text);
        const blocks = [];
        const keep = (html) => { blocks.push(html); return `\u0000${blocks.length - 1}\u0000`; };
        s = s.replace(/```(?:\w+\n)?([\s\S]*?)```/g, (_, code) => keep(`<pre class="dc-code">${code}</pre>`));
        s = s.replace(/`([^`\n]+)`/g, (_, code) => keep(`<code>${code}</code>`));
        s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, text, url) => keep(`<a href="${url}" target="_blank" rel="noopener">${text}</a>`));
        s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
        s = s.replace(/__([^_]+)__/g, "<u>$1</u>");
        s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
        s = s.replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");
        s = s.replace(/~~([^~]+)~~/g, "<s>$1</s>");
        s = s.replace(/\|\|([^|]+)\|\|/g, '<span class="dc-spoiler">$1</span>');
        s = s.replace(/&lt;@&amp;(\d+)&gt;/g, (m, id) => {
            const role = roles.find((r) => r.id === id);
            if (!role) return '<span class="dc-mention">@unknown-role</span>';
            const style = role.color ? ` style="color:${role.color};background:${role.color}26"` : "";
            return `<span class="dc-mention"${style}>@${esc(role.name)}</span>`;
        });
        s = s.replace(/&lt;@!?\d+&gt;|@everyone|@here/g, (m) => `<span class="dc-mention">${m.startsWith("@") ? m : "@user"}</span>`);
        s = s.replace(/&lt;#\d+&gt;/g, '<span class="dc-mention">#channel</span>');
        s = s.split("\n").map((line) => {
            if (/^### /.test(line)) return `<span class="dc-h3">${line.slice(4)}</span>`;
            if (/^## /.test(line)) return `<span class="dc-h2">${line.slice(3)}</span>`;
            if (/^# /.test(line)) return `<span class="dc-h1">${line.slice(2)}</span>`;
            if (/^&gt; /.test(line)) return `<span class="dc-quote">${line.slice(5)}</span>`;
            if (/^[-*] /.test(line)) return `<span class="dc-li">• ${line.slice(2)}</span>`;
            return line;
        }).join("<br>");
        s = s.replace(/<\/span><br>/g, "</span>");
        return s.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[Number(i)]);
    }

    // no inline onerror handler (would need script-src 'unsafe-inline'); broken images are hidden
    // by the capturing "error" listener on the preview container set up in init()
    const img = (url, cls) => url && /^https?:\/\//.test(url)
        ? `<img class="${cls}" src="${esc(url)}" alt="" referrerpolicy="no-referrer">` : "";

    function renderPreview(msg) {
        const e = msg.embed;
        const hasEmbed = e.title.trim() || e.description.trim() || e.author.name.trim() || e.footer.text.trim() || e.fields.length || e.image_url || e.thumbnail_url;
        const now = new Date().toLocaleTimeString(AdminUtils.LOCALE, { hour: "2-digit", minute: "2-digit" });
        const fieldsHtml = e.fields.length ? `<div class="dc-fields">${e.fields.map((f) =>
            `<div class="dc-field${f.inline ? " inline" : ""}"><div class="dc-field-name">${markdown(f.name)}</div><div class="dc-field-value">${markdown(f.value)}</div></div>`).join("")}</div>` : "";
        const footerBits = [e.footer.text.trim() && esc(e.footer.text.trim()), e.timestamp && `Today at ${now}`].filter(Boolean);

        $("eb-preview").innerHTML = `
            <div class="dc-msg">
                <img class="dc-avatar" src="/static/favicon.png" alt="">
                <div class="dc-body">
                    <div class="dc-head"><span class="dc-name">RBWR Utility</span><span class="dc-app">APP</span><span class="dc-time">Today at ${now}</span></div>
                    ${msg.content.trim() ? `<div class="dc-content">${markdown(msg.content)}</div>` : ""}
                    ${hasEmbed ? `
                    <div class="dc-embed" style="border-left-color:${hex(e.color)}">
                        <div class="dc-embed-grid">
                            <div class="dc-embed-main">
                                ${e.author.name.trim() ? `<div class="dc-author">${img(e.author.icon_url, "dc-author-icon")}${e.author.url ? `<a href="${esc(e.author.url)}" target="_blank" rel="noopener">${esc(e.author.name)}</a>` : esc(e.author.name)}</div>` : ""}
                                ${e.title.trim() ? `<div class="dc-title">${e.url ? `<a href="${esc(e.url)}" target="_blank" rel="noopener">${markdown(e.title)}</a>` : markdown(e.title)}</div>` : ""}
                                ${e.description.trim() ? `<div class="dc-desc">${markdown(e.description)}</div>` : ""}
                                ${fieldsHtml}
                            </div>
                            ${img(e.thumbnail_url, "dc-thumb")}
                        </div>
                        ${img(e.image_url, "dc-image")}
                        ${footerBits.length ? `<div class="dc-footer">${img(e.footer.icon_url, "dc-footer-icon")}<span>${footerBits.join(" • ")}</span></div>` : ""}
                    </div>` : ""}
                    ${!hasEmbed && !msg.content.trim() ? '<div class="dc-empty">Start typing to see the preview.</div>' : ""}
                </div>
            </div>`;
    }

    function update() {
        $("eb-desc-count").textContent = $("eb-description").value.length;
        renderPreview(readForm());
    }

    // ------------------------------------------------------------ data loading

    async function loadChannels() {
        const sel = $("eb-channel");
        const previous = sel.value;
        sel.innerHTML = '<option value="">Loading channels…</option>';
        try {
            ({ channels } = await api("/api/admin/discord/channels"));
            const groups = {};
            channels.forEach((c) => (groups[c.category || "No category"] ||= []).push(c));
            sel.innerHTML = '<option value="">Select a channel…</option>' + Object.entries(groups).map(([cat, list]) =>
                `<optgroup label="${esc(cat)}">${list.map((c) => `<option value="${c.id}">#${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
            if (previous) sel.value = previous;
        } catch (err) {
            sel.innerHTML = `<option value="">${esc(err.message)}</option>`;
        }
    }

    async function loadRoles() {
        const sel = $("eb-role");
        try {
            ({ roles, can_ping_all: canPingAll } = await api("/api/admin/discord/roles"));
            sel.innerHTML = '<option value="">Ping a role…</option>' + roles.map((r) =>
                `<option value="${r.id}">@${esc(r.name)}${r.mentionable || canPingAll ? "" : " (won't notify — not mentionable)"}</option>`).join("");
        } catch (err) {
            sel.innerHTML = `<option value="">Roles unavailable: ${esc(err.message)}</option>`;
        }
        update();
    }

    function insertRole(id) {
        const box = $("eb-content");
        const mention = `<@&${id}> `;
        const at = box.selectionStart ?? box.value.length;
        box.value = box.value.slice(0, at) + mention + box.value.slice(box.selectionEnd ?? at);
        box.focus();
        box.setSelectionRange(at + mention.length, at + mention.length);
        $("eb-mentions").checked = true;  // a role ping does nothing with pings turned off
        update();
    }

    async function loadSaved() {
        try {
            ({ templates, history } = await api("/api/admin/embeds"));
        } catch (err) {
            toast(err.message, "error");
            return;
        }
        $("eb-templates").innerHTML = templates.length ? templates.map((t, i) => `
            <div class="eb-item">
                <div class="eb-item-main"><strong>${esc(t.name)}</strong><span class="tk-sub">by ${esc(t.updated_by || "?")} · ${esc(AdminUtils.timeAgo(t.updated_at))}</span></div>
                <div class="btn-row">
                    <button type="button" class="qbtn c-gold" data-tpl="load" data-i="${i}">Load</button>
                    <button type="button" class="qbtn c-red" data-tpl="delete" data-i="${i}">Delete</button>
                </div>
            </div>`).join("") : '<div class="adm-hint">No templates yet.</div>';

        $("eb-history").innerHTML = history.length ? history.map((h, i) => {
            const title = h.embed?.title || h.content || h.embed?.description || "(embed)";
            return `
            <div class="eb-item">
                <div class="eb-item-main">
                    <strong>${esc(title.slice(0, 60))}</strong>
                    <span class="tk-sub">#${esc(h.channel_name || "?")} · ${esc(h.sent_by || "?")} · ${esc(AdminUtils.timeAgo(h.sent_at))}${h.source === "discord" ? " · via /embed" : ""}${h.edited ? " · edited" : ""}</span>
                </div>
                <div class="btn-row">
                    <button type="button" class="qbtn c-gold" data-hist="load" data-i="${i}">Load</button>
                    <button type="button" class="qbtn c-blue" data-hist="edit" data-i="${i}">Edit</button>
                    ${h.jump_url ? `<a class="qbtn c-grey" href="${esc(h.jump_url)}" target="_blank" rel="noopener">Open</a>` : ""}
                </div>
            </div>`;
        }).join("") : '<div class="adm-hint">Nothing sent yet.</div>';
    }

    const savedToMessage = (s) => ({ content: s.content || "", allow_mentions: !!s.allow_mentions, embed: s.data || fromDiscord(s.embed) || fromDiscord({}) });

    // ------------------------------------------------------------ actions

    async function send() {
        const channel_id = $("eb-channel").value;
        if (!channel_id) return toast("Select a channel first.", "error");
        const edit_message_id = $("eb-edit-id").value.trim() || null;
        const msg = readForm();
        if (edit_message_id && !confirm(`Edit message ${edit_message_id} in this channel?`)) return;
        if (!edit_message_id && msg.allow_mentions && /@everyone|@here/.test(msg.content + msg.embed.description) && !confirm("This message will ping @everyone/@here. Send it?")) return;
        if (!msg.allow_mentions && /<@&\d+>/.test(msg.content)) {
            if (confirm("The message mentions a role but \"Allow pings\" is off, so nobody will be notified. Turn pings on?")) {
                $("eb-mentions").checked = msg.allow_mentions = true;
            }
        }
        $("eb-send").disabled = true;
        $("eb-result").innerHTML = "";
        try {
            const res = await api("/api/admin/embeds/send", { method: "POST", body: { ...msg, channel_id, edit_message_id } });
            $("eb-result").innerHTML = `<div class="alert success">${edit_message_id ? "Message updated" : "Sent"} in #${esc(res.channel_name)}. <a href="${esc(res.jump_url)}" target="_blank" rel="noopener">Open in Discord</a></div>`;
            loadSaved();
        } catch (err) {
            $("eb-result").innerHTML = `<div class="alert error">${esc(err.message)}</div>`;
        } finally {
            $("eb-send").disabled = false;
        }
    }

    async function saveTemplate() {
        const name = $("eb-template-name").value.trim();
        if (!name) return toast("Give the template a name.", "error");
        if (templates.some((t) => t.name === name) && !confirm(`Overwrite template "${name}"?`)) return;
        try {
            await api("/api/admin/embeds/templates", { method: "POST", body: { ...readForm(), name } });
            toast(`Template "${name}" saved.`);
            loadSaved();
        } catch (err) { toast(err.message, "error"); }
    }

    function importJson() {
        let parsed;
        try { parsed = JSON.parse($("eb-json").value); } catch (_) { return toast("That isn't valid JSON.", "error"); }
        const embed = Array.isArray(parsed.embeds) ? parsed.embeds[0] : (parsed.embed || (parsed.title || parsed.description || parsed.fields ? parsed : null));
        fillForm({ content: parsed.content || "", allow_mentions: false, embed: fromDiscord(embed || {}) });
        toast("Imported.");
    }

    function exportJson() {
        const msg = readForm();
        const out = { content: msg.content || null, embeds: [toDiscord(msg.embed)] };
        $("eb-json").value = JSON.stringify(out, null, 2);
        navigator.clipboard?.writeText($("eb-json").value).then(() => toast("JSON copied to clipboard."), () => { });
    }

    function clearForm() {
        fillForm({ content: "", allow_mentions: false, embed: fromDiscord({}) });
        $("eb-edit-id").value = "";
        $("eb-result").innerHTML = "";
    }

    // ------------------------------------------------------------ wiring

    function init() {
        // hide broken preview images (the <img> carries no inline onerror, to keep a strict CSP);
        // "error" doesn't bubble, so listen in the capture phase
        $("eb-preview").addEventListener("error", (e) => {
            if (e.target.tagName === "IMG") e.target.style.display = "none";
        }, true);
        document.querySelector("#view-embeds .eb-form").addEventListener("input", (e) => {
            if (e.target.id === "eb-color") $("eb-color-hex").value = e.target.value.toUpperCase();
            if (e.target.id === "eb-color-hex") {
                const n = parseHex(e.target.value);
                if (n !== null) $("eb-color").value = hex(n).toLowerCase();
            }
            const fieldEl = e.target.closest(".eb-field");
            if (fieldEl && e.target.dataset.k) {
                const f = fields[Number(fieldEl.dataset.i)];
                f[e.target.dataset.k] = e.target.type === "checkbox" ? e.target.checked : e.target.value;
            }
            update();
        });
        $("eb-add-field").addEventListener("click", () => {
            if (fields.length >= MAX_FIELDS) return;
            fields.push({ name: "", value: "", inline: false });
            renderFields();
            $(`eb-f-name-${fields.length - 1}`).focus();
        });
        $("eb-fields").addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-act]");
            if (!btn) return;
            const i = Number(btn.closest(".eb-field").dataset.i);
            if (btn.dataset.act === "remove") fields.splice(i, 1);
            if (btn.dataset.act === "up" && i > 0) [fields[i - 1], fields[i]] = [fields[i], fields[i - 1]];
            if (btn.dataset.act === "down" && i < fields.length - 1) [fields[i + 1], fields[i]] = [fields[i], fields[i + 1]];
            renderFields();
            update();
        });
        $("eb-templates").addEventListener("click", async (e) => {
            const btn = e.target.closest("button[data-tpl]");
            if (!btn) return;
            const t = templates[Number(btn.dataset.i)];
            if (btn.dataset.tpl === "load") {
                fillForm(savedToMessage(t));
                $("eb-template-name").value = t.name;
                $("eb-edit-id").value = "";
                toast(`Template "${t.name}" loaded.`);
            } else if (confirm(`Delete template "${t.name}"?`)) {
                try {
                    await api(`/api/admin/embeds/templates/${encodeURIComponent(t.name)}`, { method: "DELETE" });
                    loadSaved();
                } catch (err) { toast(err.message, "error"); }
            }
        });
        $("eb-history").addEventListener("click", (e) => {
            const btn = e.target.closest("button[data-hist]");
            if (!btn) return;
            const h = history[Number(btn.dataset.i)];
            fillForm(savedToMessage(h));
            if (btn.dataset.hist === "edit") {
                $("eb-channel").value = h.channel_id;
                $("eb-edit-id").value = h.message_id;
                toast("Loaded — change it and click Send to update the message.");
            } else {
                $("eb-edit-id").value = "";
            }
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
        $("eb-reload-channels").addEventListener("click", () => { loadChannels(); loadRoles(); });
        $("eb-role").addEventListener("change", (e) => {
            if (e.target.value) insertRole(e.target.value);
            e.target.value = "";
        });
        $("eb-send").addEventListener("click", send);
        $("eb-clear").addEventListener("click", () => { if (confirm("Clear the whole form?")) clearForm(); });
        $("eb-save-template").addEventListener("click", saveTemplate);
        $("eb-import").addEventListener("click", importJson);
        $("eb-export").addEventListener("click", exportJson);
        renderFields();
        update();
    }

    return {
        markdown,  // also used by the /download preview in botconfig.js
        fromDiscord,  // and by the custom command embeds there
        open() {
            if (!initialized) {
                initialized = true;
                init();
            }
            loadChannels();
            loadRoles();
            loadSaved();
        },
    };
})();