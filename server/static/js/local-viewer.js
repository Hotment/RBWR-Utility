document.addEventListener("DOMContentLoaded", () => {
    const chart = new SARProgressionChart("localPointProgressionChart", "localChartContainer");

    const btnLocalSelectFile = document.getElementById("btnLocalSelectFile");
    const localFileInput = document.getElementById("localFileInput");
    const localDropzone = document.getElementById("localDropzone");
    const localDropzoneSection = document.getElementById("localDropzoneSection");
    const localDashboardContent = document.getElementById("localDashboardContent");

    const localValUnit1Points = document.getElementById("localValUnit1Points");
    const localValUnit2Points = document.getElementById("localValUnit2Points");
    const localValTotalPoints = document.getElementById("localValTotalPoints");
    const localU1Gain24h = document.getElementById("localU1Gain24h");
    const localU2Gain24h = document.getElementById("localU2Gain24h");
    const localU1Gain7d = document.getElementById("localU1Gain7d");
    const localU2Gain7d = document.getElementById("localU2Gain7d");
    const localU1Percent = document.getElementById("localU1Percent");
    const localU2Percent = document.getElementById("localU2Percent");
    const localTotalGain24h = document.getElementById("localTotalGain24h");
    const localValPointEvents = document.getElementById("localValPointEvents");
    const localValTotalLogs = document.getElementById("localValTotalLogs");
    const localFileNameBadge = document.getElementById("localFileNameBadge");
    const localFileSizeBadge = document.getElementById("localFileSizeBadge");
    const localStatDateRange = document.getElementById("localStatDateRange");
    const localStatTimelinePoints = document.getElementById("localStatTimelinePoints");
    const localStatPlayerId = document.getElementById("localStatPlayerId");

    const localBreakdownList = document.getElementById("localBreakdownList");
    const localBreakdownTotalSources = document.getElementById("localBreakdownTotalSources");

    const localDatapointModal = document.getElementById("localDatapointModal");
    const btnCloseLocalDatapointModal = document.getElementById("btnCloseLocalDatapointModal");
    const btnCloseLocalDatapointModalBtn = document.getElementById("btnCloseLocalDatapointModalBtn");
    const localModalDpDate = document.getElementById("localModalDpDate");
    const localModalDpTime = document.getElementById("localModalDpTime");
    const localModalDpTypeBadge = document.getElementById("localModalDpTypeBadge");
    const localModalDpChange = document.getElementById("localModalDpChange");
    const localModalDpU1 = document.getElementById("localModalDpU1");
    const localModalDpU2 = document.getElementById("localModalDpU2");
    const localModalDpTotal = document.getElementById("localModalDpTotal");
    const localModalDpBreakdownList = document.getElementById("localModalDpBreakdownList");
    const localModalDpMetaRow = document.getElementById("localModalDpMetaRow");
    const localModalDpMetaCode = document.getElementById("localModalDpMetaCode");

    document.getElementById("localLegendUnit1").addEventListener("click", () => {
        chart.toggleSeries("u1");
        document.getElementById("localLegendUnit1").classList.toggle("opacity-50", !chart.showU1);
    });

    document.getElementById("localLegendUnit2").addEventListener("click", () => {
        chart.toggleSeries("u2");
        document.getElementById("localLegendUnit2").classList.toggle("opacity-50", !chart.showU2);
    });

    const filterBtns = document.querySelectorAll("#localTimeFilterGroup .filter-btn");
    filterBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            filterBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const range = btn.getAttribute("data-range");
            chart.applyFilter(range);
        });
    });

    let currentLoadedFileName = "sar_data.json";

    const localBtnResetZoom = document.getElementById("localBtnResetZoom");
    if (localBtnResetZoom) {
        localBtnResetZoom.addEventListener("click", () => {
            chart.resetZoom();
        });
    }

    chart.onZoomChange = (isZoomed) => {
        if (localBtnResetZoom) {
            localBtnResetZoom.style.display = isZoomed ? "inline-flex" : "none";
        }
    };

    const localBtnToggleArea = document.getElementById("localBtnToggleArea");
    if (localBtnToggleArea) {
        localBtnToggleArea.addEventListener("click", () => {
            const isArea = chart.toggleArea();
            localBtnToggleArea.classList.toggle("active", isArea);
        });
    }

    const localBtnExportImage = document.getElementById("localBtnExportImage");
    if (localBtnExportImage) {
        localBtnExportImage.addEventListener("click", () => {
            const baseName = currentLoadedFileName ? currentLoadedFileName.replace(/\.json$/i, "") : "rbwr-point-history-local";
            const title = currentLoadedFileName ? `RBWR Point Progression · ${currentLoadedFileName}` : "RBWR Point History (Private Viewer)";
            chart.exportAsImage(`rbwr-points-${baseName}.png`, { title });
            showToast("Graph exported as PNG image!", "success");
        });
    }

    function showDatapointModal(d) {
        if (!d || !localDatapointModal) return;
        if (localModalDpDate) localModalDpDate.textContent = (d.formatted_date || "") + ", 2026";
        if (localModalDpTime) localModalDpTime.textContent = d.formatted_datetime ? (d.formatted_datetime.split(" ")[2] || "") + " UTC" : "";
        if (localModalDpTypeBadge) {
            localModalDpTypeBadge.textContent = d.point_type || "POINTS";
            localModalDpTypeBadge.className = `dp-type-badge tag-${d.point_type === "UNIT_1" ? "u1" : "u2"}`;
        }

        if (localModalDpChange) localModalDpChange.textContent = `+${(d.change || 0).toLocaleString()}`;
        if (localModalDpU1) localModalDpU1.textContent = (d.u1 || 0).toLocaleString();
        if (localModalDpU2) localModalDpU2.textContent = (d.u2 || 0).toLocaleString();
        if (localModalDpTotal) localModalDpTotal.textContent = ((d.u1 || 0) + (d.u2 || 0)).toLocaleString();

        if (localModalDpBreakdownList) {
            localModalDpBreakdownList.innerHTML = "";
            if (d.breakdown && typeof d.breakdown === "object" && Object.keys(d.breakdown).length > 0) {
                const entries = Object.entries(d.breakdown).sort((a, b) => b[1] - a[1]);
                const totalChange = d.change || entries.reduce((sum, item) => sum + item[1], 0) || 1;

                entries.forEach(([cat, val]) => {
                    const pct = Math.min(100, Math.max(5, ((val / totalChange) * 100).toFixed(1)));
                    const item = document.createElement("div");
                    item.className = "breakdown-item";
                    item.innerHTML = `
                        <div class="breakdown-item-header">
                            <span class="breakdown-name">${cat}</span>
                            <span class="breakdown-val">+${val.toLocaleString()} pts (${((val / totalChange) * 100).toFixed(1)}%)</span>
                        </div>
                        <div class="breakdown-bar-bg">
                            <div class="breakdown-bar-fill" style="width: ${pct}%;"></div>
                        </div>
                    `;
                    localModalDpBreakdownList.appendChild(item);
                });
            } else {
                localModalDpBreakdownList.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; padding: 10px 0;">No sub-category breakdown recorded for this event.</p>`;
            }
        }

        if (localModalDpMetaRow && localModalDpMetaCode) {
            if (d.serverId || d.message) {
                localModalDpMetaRow.style.display = "flex";
                localModalDpMetaCode.textContent = d.message || `Server: ${d.serverId}`;
            } else {
                localModalDpMetaRow.style.display = "none";
            }
        }

        localDatapointModal.style.display = "flex";
    }

    function closeDatapointModal() {
        if (localDatapointModal) localDatapointModal.style.display = "none";
    }

    if (btnCloseLocalDatapointModal) btnCloseLocalDatapointModal.addEventListener("click", closeDatapointModal);
    if (btnCloseLocalDatapointModalBtn) btnCloseLocalDatapointModalBtn.addEventListener("click", closeDatapointModal);

    chart.onPointClick = (d) => showDatapointModal(d);

    function showToast(message, type = "info") {
        const container = document.getElementById("toastContainer");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        let icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;
        if (type === "success") {
            icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`;
        } else if (type === "error") {
            icon = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`;
        }

        toast.innerHTML = `${icon}<span>${message}</span>`;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = "0";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function processLocalJson(jsonData, fileName, fileSizeMb) {
        if (fileName) currentLoadedFileName = fileName;
        if (!jsonData || typeof jsonData !== "object") {
            showToast("Invalid JSON: root must be a JSON object.", "error");
            return;
        }

        const player = jsonData.player || {};
        const logs = jsonData.activityLogs || [];

        if (!player && logs.length === 0) {
            showToast("JSON file does not contain player or activityLogs.", "error");
            return;
        }

        const IGNORED_LOG_MESSAGES = [
            "imported from roblox (reaktorordereddatastore)",
            "imported from roblox (reaktorordereddatastore2)",
            "imported from roblox",
            "points overwritten from roblox",
            "overwritten from roblox"
        ];

        function isIgnoredPointLog(l) {
            if (!l) return true;
            const fieldsToScan = [l.message, l.reason, l.details, l.description, l.note];
            const text = fieldsToScan.filter(Boolean).join(" ").trim().toLowerCase();
            if (!text) return false;
            for (const pattern of IGNORED_LOG_MESSAGES) {
                if (text.includes(pattern)) return true;
            }
            return false;
        }

        const pointLogs = logs.filter(l => l && l.type === "POINTS" && l.createdAt && !isIgnoredPointLog(l));
        pointLogs.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));

        const timeline = [];
        let curU1 = 0;
        let curU2 = 0;

        const categoryTotals = { OVERALL: {}, UNIT_1: {}, UNIT_2: {} };

        pointLogs.forEach(log => {
            const ptype = log.pointType;
            const finalVal = parseInt(log.finalValue || 0, 10);
            const changeAmt = parseInt(log.changeAmount || 0, 10);
            const createdStr = log.createdAt || "";

            let breakdownDict = {};
            if (log.breakdown) {
                if (typeof log.breakdown === "string") {
                    try { breakdownDict = JSON.parse(log.breakdown); } catch (e) { breakdownDict = {}; }
                } else if (typeof log.breakdown === "object") {
                    breakdownDict = log.breakdown;
                }
            }

            Object.entries(breakdownDict).forEach(([cat, amt]) => {
                if (typeof amt === "number") {
                    categoryTotals.OVERALL[cat] = (categoryTotals.OVERALL[cat] || 0) + amt;
                    if (ptype in categoryTotals) {
                        categoryTotals[ptype][cat] = (categoryTotals[ptype][cat] || 0) + amt;
                    }
                }
            });

            if (ptype === "UNIT_1") curU1 = finalVal;
            else if (ptype === "UNIT_2") curU2 = finalVal;

            let formattedDate = createdStr.substring(0, 10);
            let formattedDatetime = createdStr;
            let timestampEpoch = 0;

            try {
                const dt = new Date(createdStr);
                const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                formattedDate = `${months[dt.getUTCMonth()]} ${String(dt.getUTCDate()).padStart(2, '0')}`;
                formattedDatetime = `${formattedDate}, 2026 ${String(dt.getUTCHours()).padStart(2, '0')}:${String(dt.getUTCMinutes()).padStart(2, '0')}:${String(dt.getUTCSeconds()).padStart(2, '0')}`;
                timestampEpoch = dt.getTime();
            } catch (e) {
                timestampEpoch = 0;
            }

            timeline.push({
                id: log.id,
                timestamp: createdStr,
                timestamp_epoch: timestampEpoch,
                date: createdStr.substring(0, 10),
                formatted_date: formattedDate,
                formatted_datetime: formattedDatetime,
                point_type: ptype,
                change: changeAmt,
                u1: curU1,
                u2: curU2,
                total: curU1 + curU2,
                breakdown: breakdownDict,
                message: log.message,
                serverId: log.serverId
            });
        });

        const latestU1 = parseInt(player.unit1Points || curU1 || 0, 10);
        const latestU2 = parseInt(player.unit2Points || curU2 || 0, 10);
        const totalPoints = latestU1 + latestU2;

        let u1Gain24h = 0, u2Gain24h = 0, u1Gain7d = 0, u2Gain7d = 0;
        if (timeline.length > 0) {
            const latestTs = timeline[timeline.length - 1].timestamp_epoch;
            const epoch24h = latestTs - (24 * 3600 * 1000);
            const epoch7d = latestTs - (7 * 86400 * 1000);

            timeline.forEach(t => {
                if (t.timestamp_epoch >= epoch24h) {
                    if (t.point_type === "UNIT_1") u1Gain24h += t.change;
                    if (t.point_type === "UNIT_2") u2Gain24h += t.change;
                }
                if (t.timestamp_epoch >= epoch7d) {
                    if (t.point_type === "UNIT_1") u1Gain7d += t.change;
                    if (t.point_type === "UNIT_2") u2Gain7d += t.change;
                }
            });
        }

        if (localValUnit1Points) localValUnit1Points.textContent = latestU1.toLocaleString();
        if (localValUnit2Points) localValUnit2Points.textContent = latestU2.toLocaleString();
        if (localValTotalPoints) localValTotalPoints.textContent = totalPoints.toLocaleString();

        if (localU1Gain24h) localU1Gain24h.textContent = `+${u1Gain24h.toLocaleString()} (24h)`;
        if (localU2Gain24h) localU2Gain24h.textContent = `+${u2Gain24h.toLocaleString()} (24h)`;
        if (localU1Gain7d) localU1Gain7d.textContent = `+${u1Gain7d.toLocaleString()} (7d gain)`;
        if (localU2Gain7d) localU2Gain7d.textContent = `+${u2Gain7d.toLocaleString()} (7d gain)`;

        const u1Pct = totalPoints > 0 ? ((latestU1 / totalPoints) * 100).toFixed(1) : 50;
        const u2Pct = totalPoints > 0 ? ((latestU2 / totalPoints) * 100).toFixed(1) : 50;
        if (localU1Percent) localU1Percent.textContent = `${u1Pct}% of total`;
        if (localU2Percent) localU2Percent.textContent = `${u2Pct}% of total`;

        if (localTotalGain24h) localTotalGain24h.textContent = `+${(u1Gain24h + u2Gain24h).toLocaleString()} 24h total`;
        if (localValPointEvents) localValPointEvents.textContent = `${timeline.length.toLocaleString()} point updates`;
        if (localValTotalLogs) localValTotalLogs.textContent = `${(logs.length / 1000).toFixed(1)}K total logs`;

        const localFileBadgeBox = document.getElementById("localFileBadgeBox");
        if (localFileBadgeBox) localFileBadgeBox.style.display = "flex";
        if (localFileNameBadge) localFileNameBadge.textContent = fileName;
        if (localFileSizeBadge) localFileSizeBadge.textContent = `${fileSizeMb} MB`;

        if (localStatDateRange) localStatDateRange.textContent = timeline.length > 0 ? `${timeline[0].formatted_date}, 2026 → ${timeline[timeline.length - 1].formatted_date}, 2026` : "N/A";
        if (localStatTimelinePoints) localStatTimelinePoints.textContent = `${timeline.length} Events`;
        if (localStatPlayerId) localStatPlayerId.textContent = player.id || player.username || "Local Player";

        const sortedBreakdown = Object.entries(categoryTotals.OVERALL).sort((a, b) => b[1] - a[1]);
        const overallPoints = sortedBreakdown.reduce((sum, item) => sum + item[1], 0) || 1;
        if (localBreakdownTotalSources) localBreakdownTotalSources.textContent = `${sortedBreakdown.length} Categories`;

        if (localBreakdownList) {
            localBreakdownList.innerHTML = "";
            sortedBreakdown.forEach(([cat, val]) => {
                const pct = ((val / overallPoints) * 100).toFixed(1);
                const item = document.createElement("div");
                item.className = "breakdown-item";
                item.innerHTML = `
                    <div class="breakdown-item-header">
                        <span class="breakdown-name">${cat}</span>
                        <span class="breakdown-val">${val.toLocaleString()} pts (${pct}%)</span>
                    </div>
                    <div class="breakdown-bar-bg">
                        <div class="breakdown-bar-fill" style="width: ${pct}%"></div>
                    </div>
                `;
                localBreakdownList.appendChild(item);
            });
        }

        if (localDropzoneSection) localDropzoneSection.style.display = "none";
        if (localDashboardContent) localDashboardContent.style.display = "flex";

        chart.setData(timeline);
        showToast(`Successfully parsed ${timeline.length} events offline!`, "success");
    }

    function handleFile(file) {
        if (!file.name.endsWith(".json")) {
            showToast("Please select a valid .json file.", "error");
            return;
        }

        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        showToast(`Reading ${file.name} locally (${sizeMb} MB)...`, "info");

        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const parsed = JSON.parse(e.target.result);
                processLocalJson(parsed, file.name, sizeMb);
            } catch (err) {
                showToast("Failed to parse JSON: " + err.message, "error");
            }
        };
        reader.onerror = () => showToast("Error reading file locally.", "error");
        reader.readAsText(file);
    }

    function handlePastedJson(rawText, sourceLabel = "pasted_data.json") {
        if (!rawText || !rawText.trim()) {
            showToast("Please paste raw JSON into the text field.", "error");
            return false;
        }
        try {
            const parsed = JSON.parse(rawText.trim());
            const byteSize = new Blob([rawText]).size;
            const sizeMb = (byteSize / (1024 * 1024)).toFixed(2);
            processLocalJson(parsed, sourceLabel, sizeMb);
            return true;
        } catch (err) {
            showToast("Invalid JSON syntax: " + err.message, "error");
            return false;
        }
    }

    const localJsonTextInput = document.getElementById("localJsonTextInput");
    const btnLocalProcessPaste = document.getElementById("btnLocalProcessPaste");
    if (btnLocalProcessPaste) {
        btnLocalProcessPaste.addEventListener("click", () => {
            const raw = localJsonTextInput ? localJsonTextInput.value : "";
            handlePastedJson(raw, "pasted_sar.json");
        });
    }

    const btnOpenLocalPasteModal = document.getElementById("btnOpenLocalPasteModal");
    const localPasteModal = document.getElementById("localPasteModal");
    const btnCloseLocalPasteModal = document.getElementById("btnCloseLocalPasteModal");
    const btnCancelLocalPaste = document.getElementById("btnCancelLocalPaste");
    const modalLocalJsonTextInput = document.getElementById("modalLocalJsonTextInput");
    const btnSubmitLocalPaste = document.getElementById("btnSubmitLocalPaste");

    function closePasteModal() {
        if (localPasteModal) localPasteModal.style.display = "none";
    }

    if (btnOpenLocalPasteModal) {
        btnOpenLocalPasteModal.addEventListener("click", () => {
            if (modalLocalJsonTextInput) modalLocalJsonTextInput.value = "";
            if (localPasteModal) localPasteModal.style.display = "flex";
            if (modalLocalJsonTextInput) modalLocalJsonTextInput.focus();
        });
    }

    if (btnCloseLocalPasteModal) btnCloseLocalPasteModal.addEventListener("click", closePasteModal);
    if (btnCancelLocalPaste) btnCancelLocalPaste.addEventListener("click", closePasteModal);

    if (btnSubmitLocalPaste) {
        btnSubmitLocalPaste.addEventListener("click", () => {
            const raw = modalLocalJsonTextInput ? modalLocalJsonTextInput.value : "";
            const success = handlePastedJson(raw, "pasted_sar.json");
            if (success) {
                closePasteModal();
            }
        });
    }

    if (btnLocalSelectFile) btnLocalSelectFile.addEventListener("click", () => localFileInput.click());
    if (localDropzone) {
        localDropzone.addEventListener("click", () => localFileInput.click());
        localDropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            localDropzone.classList.add("dragover");
        });
        localDropzone.addEventListener("dragleave", () => localDropzone.classList.remove("dragover"));
        localDropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            localDropzone.classList.remove("dragover");
            if (e.dataTransfer.files.length > 0) {
                handleFile(e.dataTransfer.files[0]);
            }
        });
    }

    if (localFileInput) {
        localFileInput.addEventListener("change", (e) => {
            if (e.target.files.length > 0) {
                handleFile(e.target.files[0]);
            }
        });
    }
});
