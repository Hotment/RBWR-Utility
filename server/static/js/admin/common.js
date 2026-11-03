/* Shared helpers for the admin panel's Discord bot sections. */
const AdminUtils = (() => {
    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function errorText(data, status) {
        if (data) {
            if (typeof data.detail === "string") return data.detail;
            if (Array.isArray(data.detail)) {
                return data.detail.map((d) => {
                    const field = (d.loc || []).slice(-1)[0];
                    return field ? `${field}: ${d.msg}` : d.msg;
                }).join("; ");
            }
            if (data.error) return data.error;
        }
        if (status === 401) return "Your admin session expired — reload the page and log in again.";
        return status === 429 ? "Too many requests. Please wait a moment." : `Request failed (${status}).`;
    }

    async function api(url, { method = "GET", body } = {}) {
        const res = await fetch(url, {
            method,
            credentials: "same-origin",
            headers: body !== undefined ? { "Content-Type": "application/json" } : {},
            body: body !== undefined ? JSON.stringify(body) : undefined,
        });
        let data = null;
        try { data = await res.json(); } catch (_) { /* empty body */ }
        if (!res.ok) throw new Error(errorText(data, res.status));
        return data;
    }

    const LOCALE = "en-US";

    function timeAgo(iso) {
        const t = Date.parse(iso);
        if (!t) return "";
        const s = Math.max(0, (Date.now() - t) / 1000);
        if (s < 60) return "just now";
        if (s < 3600) return `${Math.floor(s / 60)}m ago`;
        if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
        if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
        return new Date(t).toLocaleDateString(LOCALE);
    }

    function fmtDate(iso) {
        const t = Date.parse(iso);
        return t ? new Date(t).toLocaleString(LOCALE) : "";
    }

    function avatar(url, name, cls = "") {
        if (url) return `<img class="avatar ${cls}" src="${esc(url)}" alt="" referrerpolicy="no-referrer">`;
        return `<span class="avatar avatar-fallback ${cls}">${esc((name || "?").charAt(0).toUpperCase())}</span>`;
    }

    function toast(message, type = "success") {
        let wrap = document.querySelector(".toast-wrap");
        if (!wrap) {
            wrap = document.createElement("div");
            wrap.className = "toast-wrap";
            wrap.setAttribute("role", "status");
            document.body.appendChild(wrap);
        }
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.textContent = message;
        wrap.appendChild(el);
        setTimeout(() => {
            el.style.opacity = "0";
            el.style.transform = "translateY(6px)";
            setTimeout(() => el.remove(), 250);
        }, 4200);
    }

    return { esc, api, LOCALE, timeAgo, fmtDate, avatar, toast };
})();