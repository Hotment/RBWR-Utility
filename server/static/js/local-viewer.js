document.addEventListener("DOMContentLoaded", () => {
    const chart = new SARProgressionChart("localPointProgressionChart", "localChartContainer");

    const btnLocalSelectFile = document.getElementById("btnLocalSelectFile");
    const btnSwitchFile = document.getElementById("btnSwitchFile");
    const localFileInput = document.getElementById("localFileInput");
    const localDropzone = document.getElementById("localDropzone");
    const dropzoneContent = document.getElementById("dropzoneContent");
    const localDropzoneLoadingOverlay = document.getElementById("localDropzoneLoadingOverlay");
    const localLoadingTitle = document.getElementById("localLoadingTitle");
    const localLoadingProgressBar = document.getElementById("localLoadingProgressBar");
    const localLoadingStatusText = document.getElementById("localLoadingStatusText");
    const localLoadingPercentText = document.getElementById("localLoadingPercentText");

    const localDropzoneSection = document.getElementById("localDropzoneSection");
    const localDashboardContent = document.getElementById("localDashboardContent");

    const localValUnit1Points = document.getElementById("localValUnit1Points");
    const localValUnit2Points = document.getElementById("localValUnit2Points");
    const localValTotalPoints = document.getElementById("localValTotalPoints");
    const localValTotalGainedPoints = document.getElementById("localValTotalGainedPoints");
    const localGainedStatusTag = document.getElementById("localGainedStatusTag");
    const localAuditIgnoredGains = document.getElementById("localAuditIgnoredGains");
    const localAuditDiffText = document.getElementById("localAuditDiffText");

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

    const reconcileValHave = document.getElementById("reconcileValHave");
    const reconcileSubHave = document.getElementById("reconcileSubHave");
    const reconcileValGot = document.getElementById("reconcileValGot");
    const reconcileSubGot = document.getElementById("reconcileSubGot");
    const reconcileValDiff = document.getElementById("reconcileValDiff");
    const reconcileStatusBadge = document.getElementById("reconcileStatusBadge");
    const reconcileBarPct = document.getElementById("reconcileBarPct");
    const reconcileBarFill = document.getElementById("reconcileBarFill");
    const reconcileChipStandardVal = document.getElementById("reconcileChipStandardVal");
    const reconcileChipIgnoredVal = document.getElementById("reconcileChipIgnoredVal");
    const reconcileChipBalanceVal = document.getElementById("reconcileChipBalanceVal");
    const btnOpenAuditModal = document.getElementById("btnOpenAuditModal");

    const localAuditModal = document.getElementById("localAuditModal");
    const btnCloseAuditModal = document.getElementById("btnCloseAuditModal");
    const btnCloseAuditModalBtn = document.getElementById("btnCloseAuditModalBtn");
    const modalAuditHeldVal = document.getElementById("modalAuditHeldVal");
    const modalAuditHeldSub = document.getElementById("modalAuditHeldSub");
    const modalAuditGainedVal = document.getElementById("modalAuditGainedVal");
    const modalAuditGainedSub = document.getElementById("modalAuditGainedSub");
    const modalAuditDiffVal = document.getElementById("modalAuditDiffVal");
    const modalAuditDiffStatus = document.getElementById("modalAuditDiffStatus");
    const modalAuditIgnoredCount = document.getElementById("modalAuditIgnoredCount");
    const modalAuditIgnoredTableBody = document.getElementById("modalAuditIgnoredTableBody");

    const localBreakdownList = document.getElementById("localBreakdownList");
    const localBreakdownTotalSources = document.getElementById("localBreakdownTotalSources");
    const localMissionsTabBadge = document.getElementById("localMissionsTabBadge");
    const localBreakdownUnit1List = document.getElementById("localBreakdownUnit1List");
    const localBreakdownUnit2List = document.getElementById("localBreakdownUnit2List");

    const mStatTotalPoints = document.getElementById("mStatTotalPoints");
    const mStatTotalCount = document.getElementById("mStatTotalCount");
    const mStatCompletedPoints = document.getElementById("mStatCompletedPoints");
    const mStatCompletedCount = document.getElementById("mStatCompletedCount");
    const mStatAutoClaimedPoints = document.getElementById("mStatAutoClaimedPoints");
    const mStatAutoClaimedCount = document.getElementById("mStatAutoClaimedCount");
    const mStatAutoClaimPct = document.getElementById("mStatAutoClaimPct");
    const mCountAll = document.getElementById("mCountAll");
    const mCountCompleted = document.getElementById("mCountCompleted");
    const mCountAutoClaimed = document.getElementById("mCountAutoClaimed");
    const inputMissionSearch = document.getElementById("inputMissionSearch");
    const localMissionsList = document.getElementById("localMissionsList");

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

    const legendU1 = document.getElementById("localLegendUnit1");
    if (legendU1) {
        legendU1.addEventListener("click", () => {
            chart.toggleSeries("u1");
            legendU1.classList.toggle("opacity-50", !chart.showU1);
        });
    }

    const legendU2 = document.getElementById("localLegendUnit2");
    if (legendU2) {
        legendU2.addEventListener("click", () => {
            chart.toggleSeries("u2");
            legendU2.classList.toggle("opacity-50", !chart.showU2);
        });
    }

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
            const baseName = currentLoadedFileName ? currentLoadedFileName.replace(/\.(json|zip|gz)$/i, "") : "rbwr-point-history-local";
            const title = currentLoadedFileName ? `RBWR Point Progression · ${currentLoadedFileName}` : "RBWR Point History (Private Viewer)";
            chart.exportAsImage(`rbwr-points-${baseName}.png`, { title });
            showToast("Graph exported as PNG image!", "success");
        });
    }

    const bTabBtns = document.querySelectorAll(".b-tab-btn");
    const bTabPanes = {
        all: document.getElementById("tabPaneAll"),
        missions: document.getElementById("tabPaneMissions"),
        unit1: document.getElementById("tabPaneUnit1"),
        unit2: document.getElementById("tabPaneUnit2")
    };

    bTabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const tabKey = btn.getAttribute("data-tab");
            bTabBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");

            Object.entries(bTabPanes).forEach(([key, pane]) => {
                if (pane) {
                    const isTarget = key === tabKey;
                    pane.style.display = isTarget ? "flex" : "none";
                    pane.classList.toggle("active", isTarget);
                }
            });
        });
    });

    function showLoadingOverlay(show, title = "Reading Archive...", percent = 15, status = "Reading file bytes...") {
        if (localDropzoneLoadingOverlay) {
            localDropzoneLoadingOverlay.style.display = show ? "flex" : "none";
        }
        if (dropzoneContent) {
            dropzoneContent.style.display = show ? "none" : "block";
        }
        updateLoadingOverlay(status, percent, title);
    }

    function updateLoadingOverlay(status, percent, title) {
        if (localLoadingStatusText && status) localLoadingStatusText.textContent = status;
        if (localLoadingProgressBar && typeof percent === "number") {
            localLoadingProgressBar.style.width = Math.min(100, Math.max(0, percent)) + "%";
        }
        if (localLoadingPercentText && typeof percent === "number") {
            localLoadingPercentText.textContent = Math.round(percent) + "%";
        }
        if (localLoadingTitle && title) {
            localLoadingTitle.textContent = title;
        }
    }

    function groupBreakdownSources(breakdownData) {
        const entries = Array.isArray(breakdownData)
            ? breakdownData
            : Object.entries(breakdownData || {});

        const regularList = [];
        const missionList = [];
        let totalMissionPoints = 0;
        let totalCompletedPoints = 0;
        let totalAutoClaimedPoints = 0;

        entries.forEach(([cat, val]) => {
            const numVal = typeof val === "number" ? val : parseFloat(val) || 0;
            const trimmedCat = (cat || "").trim();
            if (!trimmedCat && numVal === 0) return;

            const isCompleted = /^mission\s*completed(?:\s*:|\s+)/i.test(trimmedCat);
            const isAutoClaimed = /^mission\s*auto[- ]?claimed(?:\s*:|\s+)/i.test(trimmedCat);

            if (isCompleted || isAutoClaimed) {
                const prefixRegex = isCompleted
                    ? /^mission\s*completed(?:\s*:|\s+)\s*/i
                    : /^mission\s*auto[- ]?claimed(?:\s*:|\s+)\s*/i;
                const cleanSubName = trimmedCat.replace(prefixRegex, "").trim();
                const missionType = isAutoClaimed ? "auto_claimed" : "completed";
                const typeLabel = isAutoClaimed ? "Auto-Claimed" : "Completed";

                missionList.push({
                    fullName: trimmedCat,
                    displayName: cleanSubName || trimmedCat,
                    missionType: missionType,
                    typeLabel: typeLabel,
                    value: numVal
                });
                totalMissionPoints += numVal;
                if (isCompleted) totalCompletedPoints += numVal;
                if (isAutoClaimed) totalAutoClaimedPoints += numVal;
            } else {
                regularList.push({
                    isGroup: false,
                    name: trimmedCat || "Unknown",
                    value: numVal
                });
            }
        });

        if (missionList.length > 0) {
            missionList.sort((a, b) => b.value - a.value);
            const completedCount = missionList.filter(m => m.missionType === "completed").length;
            const autoClaimedCount = missionList.filter(m => m.missionType === "auto_claimed").length;

            regularList.push({
                isGroup: true,
                groupKey: "missions",
                name: "Missions",
                value: totalMissionPoints,
                count: missionList.length,
                completedCount: completedCount,
                autoClaimedCount: autoClaimedCount,
                completedPoints: totalCompletedPoints,
                autoClaimedPoints: totalAutoClaimedPoints,
                subItems: missionList
            });
        }

        regularList.sort((a, b) => b.value - a.value);
        return regularList;
    }

    function renderBreakdownItems(containerEl, groupedItems, totalBasePoints, isModal = false) {
        if (!containerEl) return;
        containerEl.innerHTML = "";

        if (!groupedItems || groupedItems.length === 0) {
            containerEl.innerHTML = `<p style="color: var(--text-muted); font-size: 0.82rem; padding: 10px 0;">No sub-category breakdown recorded for this event.</p>`;
            return;
        }

        const denom = totalBasePoints || groupedItems.reduce((sum, item) => sum + item.value, 0) || 1;
        const prefix = isModal ? "+" : "";

        groupedItems.forEach((item, idx) => {
            const pct = Math.min(100, Math.max(0, ((item.value / denom) * 100))).toFixed(1);
            const barPct = isModal ? Math.min(100, Math.max(4, pct)) : pct;

            const itemEl = document.createElement("div");

            if (!item.isGroup) {
                itemEl.className = "breakdown-item";
                itemEl.innerHTML = `
                    <div class="breakdown-item-header">
                        <span class="breakdown-name">${item.name}</span>
                        <span class="breakdown-val">${prefix}${item.value.toLocaleString()} pts (${pct}%)</span>
                    </div>
                    <div class="breakdown-bar-bg">
                        <div class="breakdown-bar-fill" style="width: ${barPct}%;"></div>
                    </div>
                `;
            } else {
                const groupId = `breakdownGroup_${isModal ? 'modal_' : ''}${idx}`;
                itemEl.className = "breakdown-item breakdown-group";
                itemEl.id = groupId;

                let subItemsHtml = "";
                item.subItems.forEach(sub => {
                    const subPctOfTotal = Math.min(100, Math.max(0, ((sub.value / denom) * 100))).toFixed(1);
                    const subPctOfGroup = item.value > 0 ? ((sub.value / item.value) * 100).toFixed(1) : "0";
                    const subBarPct = Math.min(100, Math.max(3, subPctOfGroup));
                    const dotColor = sub.missionType === "auto_claimed" ? "#06b6d4" : "#60a5fa";

                    subItemsHtml += `
                        <div class="breakdown-subitem">
                            <div class="breakdown-subitem-header">
                                <span class="breakdown-subitem-name" title="${sub.fullName}">
                                    <span class="breakdown-subitem-dot" style="background: ${dotColor};"></span>
                                    <span class="mission-type-tag mission-tag-${sub.missionType}">${sub.typeLabel}</span>
                                    <span>${sub.displayName}</span>
                                </span>
                                <span class="breakdown-subitem-val">${prefix}${sub.value.toLocaleString()} pts <span class="breakdown-subitem-pct">(${subPctOfTotal}% total · ${subPctOfGroup}% of missions)</span></span>
                            </div>
                            <div class="breakdown-subitem-bar-bg">
                                <div class="breakdown-subitem-bar-fill" style="width: ${subBarPct}%; background: ${dotColor};"></div>
                            </div>
                        </div>
                    `;
                });

                const autoBadgeHtml = item.autoClaimedCount > 0
                    ? `<span class="breakdown-sub-badge badge-auto">${item.autoClaimedCount} Auto-Claimed</span>`
                    : '';
                const compBadgeHtml = item.completedCount > 0
                    ? `<span class="breakdown-sub-badge badge-comp">${item.completedCount} Completed</span>`
                    : '';

                itemEl.innerHTML = `
                    <div class="breakdown-item-header breakdown-group-header" role="button" tabindex="0" title="Click to view all ${item.count} individual missions">
                        <div class="breakdown-group-title-box">
                            <svg class="breakdown-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                            <span class="breakdown-name">${item.name}</span>
                            <span class="breakdown-group-badge">${item.count} Missions</span>
                            ${compBadgeHtml}
                            ${autoBadgeHtml}
                        </div>
                        <div class="breakdown-group-right">
                            <span class="breakdown-val">${prefix}${item.value.toLocaleString()} pts (${pct}%)</span>
                            <span class="breakdown-expand-hint">Expand</span>
                        </div>
                    </div>
                    <div class="breakdown-bar-bg">
                        <div class="breakdown-bar-fill" style="width: ${barPct}%;"></div>
                    </div>
                    <div class="breakdown-subitems-list">
                        <div class="breakdown-subitems-meta">
                            <span>Individual Missions Breakdown (${item.count} total · ${item.completedCount || 0} completed, ${item.autoClaimedCount || 0} auto-claimed)</span>
                            <span>Points</span>
                        </div>
                        ${subItemsHtml}
                    </div>
                `;

                const header = itemEl.querySelector(".breakdown-group-header");
                const hint = itemEl.querySelector(".breakdown-expand-hint");
                const toggleFn = (e) => {
                    e.stopPropagation();
                    const isExpanded = itemEl.classList.toggle("expanded");
                    if (hint) hint.textContent = isExpanded ? "Collapse" : "Expand";
                };
                if (header) {
                    header.addEventListener("click", toggleFn);
                    header.addEventListener("keydown", (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleFn(e);
                        }
                    });
                }
            }

            containerEl.appendChild(itemEl);
        });
    }

    let currentMissionsData = [];
    let currentTotalMissionPoints = 0;
    let currentMissionsFilter = "all";
    let currentMissionsSearch = "";

    function renderMissionsTab(missionsList, totalMissionPoints) {
        currentMissionsData = missionsList || [];
        currentTotalMissionPoints = totalMissionPoints || 0;

        const totalCount = currentMissionsData.length;
        const completedList = currentMissionsData.filter(m => m.missionType === "completed");
        const autoClaimedList = currentMissionsData.filter(m => m.missionType === "auto_claimed");

        const completedPoints = completedList.reduce((s, m) => s + m.value, 0);
        const autoClaimedPoints = autoClaimedList.reduce((s, m) => s + m.value, 0);
        const autoClaimPct = currentTotalMissionPoints > 0
            ? ((autoClaimedPoints / currentTotalMissionPoints) * 100).toFixed(1)
            : "0.0";

        if (mStatTotalPoints) mStatTotalPoints.textContent = `+${currentTotalMissionPoints.toLocaleString()} pts`;
        if (mStatTotalCount) mStatTotalCount.textContent = `${totalCount} mission${totalCount !== 1 ? 's' : ''} total`;
        if (mStatCompletedPoints) mStatCompletedPoints.textContent = `+${completedPoints.toLocaleString()} pts`;
        if (mStatCompletedCount) mStatCompletedCount.textContent = `${completedList.length} completed`;
        if (mStatAutoClaimedPoints) mStatAutoClaimedPoints.textContent = `+${autoClaimedPoints.toLocaleString()} pts`;
        if (mStatAutoClaimedCount) mStatAutoClaimedCount.textContent = `${autoClaimedList.length} auto-claimed`;
        if (mStatAutoClaimPct) mStatAutoClaimPct.textContent = `${autoClaimPct}%`;

        if (mCountAll) mCountAll.textContent = totalCount;
        if (mCountCompleted) mCountCompleted.textContent = completedList.length;
        if (mCountAutoClaimed) mCountAutoClaimed.textContent = autoClaimedList.length;
        if (localMissionsTabBadge) localMissionsTabBadge.textContent = totalCount;

        applyMissionsFilterAndRender();
    }

    function applyMissionsFilterAndRender() {
        if (!localMissionsList) return;
        localMissionsList.innerHTML = "";

        const searchLower = (currentMissionsSearch || "").trim().toLowerCase();
        const filtered = currentMissionsData.filter(m => {
            if (currentMissionsFilter === "completed" && m.missionType !== "completed") return false;
            if (currentMissionsFilter === "auto_claimed" && m.missionType !== "auto_claimed") return false;
            if (searchLower) {
                return (m.displayName || "").toLowerCase().includes(searchLower) ||
                    (m.fullName || "").toLowerCase().includes(searchLower);
            }
            return true;
        });

        if (filtered.length === 0) {
            localMissionsList.innerHTML = `
                <div style="padding: 30px; text-align: center; color: var(--text-muted); font-size: 0.82rem;">
                    No missions found matching your search.
                </div>
            `;
            return;
        }

        const denom = currentTotalMissionPoints || 1;
        filtered.forEach(m => {
            const pct = Math.min(100, Math.max(0, ((m.value / denom) * 100))).toFixed(1);
            const barPct = Math.min(100, Math.max(3, pct));
            const isAuto = m.missionType === "auto_claimed";
            const color = isAuto ? "#06b6d4" : "#3b82f6";

            const card = document.createElement("div");
            card.className = "mission-row-card";
            card.innerHTML = `
                <div class="mission-row-header">
                    <div class="mission-row-title-box">
                        <span class="mission-type-tag mission-tag-${m.missionType}">${m.typeLabel}</span>
                        <span class="mission-row-title" title="${m.fullName}">${m.displayName}</span>
                    </div>
                    <span class="breakdown-val">+${m.value.toLocaleString()} pts <span class="breakdown-subitem-pct">(${pct}% of missions)</span></span>
                </div>
                <div class="breakdown-bar-bg" style="height: 6px;">
                    <div class="breakdown-bar-fill" style="width: ${barPct}%; background: ${color};"></div>
                </div>
            `;
            localMissionsList.appendChild(card);
        });
    }

    const mPills = document.querySelectorAll(".m-pill");
    mPills.forEach(pill => {
        pill.addEventListener("click", () => {
            mPills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            currentMissionsFilter = pill.getAttribute("data-filter") || "all";
            applyMissionsFilterAndRender();
        });
    });

    if (inputMissionSearch) {
        inputMissionSearch.addEventListener("input", (e) => {
            currentMissionsSearch = e.target.value || "";
            applyMissionsFilterAndRender();
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
            if (d.breakdown && typeof d.breakdown === "object" && Object.keys(d.breakdown).length > 0) {
                const grouped = groupBreakdownSources(d.breakdown);
                const totalChange = d.change || grouped.reduce((sum, item) => sum + item.value, 0) || 1;
                renderBreakdownItems(localModalDpBreakdownList, grouped, totalChange, true);
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

    function openAuditModal() {
        if (localAuditModal) localAuditModal.style.display = "flex";
    }

    function closeAuditModal() {
        if (localAuditModal) localAuditModal.style.display = "none";
    }

    if (btnOpenAuditModal) btnOpenAuditModal.addEventListener("click", openAuditModal);
    if (btnCloseAuditModal) btnCloseAuditModal.addEventListener("click", closeAuditModal);
    if (btnCloseAuditModalBtn) btnCloseAuditModalBtn.addEventListener("click", closeAuditModal);

    function showToast(message, type = "info") {
        const container = document.getElementById("toastContainer");
        if (!container) return;
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

        let totalPointsGained = 0;
        let normalPointsGained = 0;
        let ignoredPointsGained = 0;
        let normalPointLogsCount = 0;
        let ignoredPointLogsCount = 0;
        const ignoredDetails = [];

        logs.forEach(log => {
            if (!log) return;
            const isPointType = log.type === "POINTS";
            const ignored = isIgnoredPointLog(log);

            if (isPointType || ignored) {
                let changeAmt = parseInt(log.changeAmount || 0, 10);
                if (changeAmt === 0 && ignored) {
                    if (log.finalValue) changeAmt = parseInt(log.finalValue, 10);
                    else if (log.points) changeAmt = parseInt(log.points, 10);
                    else if (log.amount) changeAmt = parseInt(log.amount, 10);
                }

                const ptype = log.pointType || (log.unit === 1 ? "UNIT_1" : log.unit === 2 ? "UNIT_2" : "OVERALL");

                if (ignored) {
                    ignoredPointsGained += changeAmt;
                    ignoredPointLogsCount++;
                    const msg = [log.message, log.reason, log.details, log.description, log.note].filter(Boolean).join(" - ") || "Roblox DataStore Import";
                    ignoredDetails.push({
                        message: msg,
                        amount: changeAmt,
                        date: log.createdAt ? log.createdAt.substring(0, 19).replace('T', ' ') : "N/A",
                        type: ptype
                    });
                } else {
                    normalPointsGained += changeAmt;
                    normalPointLogsCount++;
                }

                totalPointsGained += changeAmt;
            }
        });

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

        const diffHeldMinusGained = totalPoints - totalPointsGained;
        const diffAbs = Math.abs(diffHeldMinusGained);
        const ratioPct = totalPoints > 0 ? ((totalPointsGained / totalPoints) * 100).toFixed(1) : "100.0";

        if (localValUnit1Points) localValUnit1Points.textContent = latestU1.toLocaleString();
        if (localValUnit2Points) localValUnit2Points.textContent = latestU2.toLocaleString();
        if (localValTotalPoints) localValTotalPoints.textContent = totalPoints.toLocaleString();
        if (localValTotalGainedPoints) localValTotalGainedPoints.textContent = totalPointsGained.toLocaleString();

        if (localGainedStatusTag) {
            if (diffHeldMinusGained === 0) {
                localGainedStatusTag.className = "kpi-tag tag-match";
                localGainedStatusTag.textContent = "✓ 100% Match";
            } else if (diffHeldMinusGained > 0) {
                localGainedStatusTag.className = "kpi-tag tag-surplus";
                localGainedStatusTag.textContent = `+${diffAbs.toLocaleString()} Surplus`;
            } else {
                localGainedStatusTag.className = "kpi-tag tag-diff";
                localGainedStatusTag.textContent = `-${diffAbs.toLocaleString()} Diff`;
            }
        }

        if (localAuditIgnoredGains) {
            localAuditIgnoredGains.textContent = `+${ignoredPointsGained.toLocaleString()} from ${ignoredPointLogsCount} Roblox import${ignoredPointLogsCount !== 1 ? 's' : ''}`;
        }
        if (localAuditDiffText) {
            if (diffHeldMinusGained === 0) {
                localAuditDiffText.textContent = "Matches profile balance exactly";
            } else {
                localAuditDiffText.textContent = `${ratioPct}% of balance (${diffHeldMinusGained > 0 ? '+' : '-'}${diffAbs.toLocaleString()} pts)`;
            }
        }

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

        if (reconcileValHave) reconcileValHave.textContent = `${totalPoints.toLocaleString()} pts`;
        if (reconcileSubHave) reconcileSubHave.textContent = `Unit 1: ${latestU1.toLocaleString()} · Unit 2: ${latestU2.toLocaleString()}`;
        if (reconcileValGot) reconcileValGot.textContent = `${totalPointsGained.toLocaleString()} pts`;
        if (reconcileSubGot) reconcileSubGot.textContent = `${normalPointsGained.toLocaleString()} standard + ${ignoredPointsGained.toLocaleString()} Roblox imports`;
        if (reconcileValDiff) reconcileValDiff.textContent = `${diffHeldMinusGained === 0 ? '0 pts' : (diffHeldMinusGained > 0 ? '+' : '-') + diffAbs.toLocaleString() + ' pts'}`;

        if (reconcileStatusBadge) {
            reconcileStatusBadge.className = `reconcile-status-badge ${diffHeldMinusGained === 0 ? 'badge-match' : (diffHeldMinusGained > 0 ? 'badge-surplus' : 'badge-diff')}`;
            reconcileStatusBadge.textContent = diffHeldMinusGained === 0
                ? "✓ Exact Balance Match"
                : (diffHeldMinusGained > 0 ? `Account Surplus (+${diffAbs.toLocaleString()} pts)` : `Discrepancy (-${diffAbs.toLocaleString()} pts)`);
        }

        if (reconcileBarPct) reconcileBarPct.textContent = `${ratioPct}% accounted for`;
        if (reconcileBarFill) {
            const barFillWidth = Math.min(100, Math.max(0, (totalPointsGained / (totalPoints || 1)) * 100));
            reconcileBarFill.style.width = `${barFillWidth}%`;
        }

        if (reconcileChipStandardVal) reconcileChipStandardVal.textContent = `${normalPointsGained.toLocaleString()} pts`;
        if (reconcileChipIgnoredVal) reconcileChipIgnoredVal.textContent = `+${ignoredPointsGained.toLocaleString()} pts`;
        if (reconcileChipBalanceVal) reconcileChipBalanceVal.textContent = `${totalPoints.toLocaleString()} pts`;

        if (modalAuditHeldVal) modalAuditHeldVal.textContent = `${totalPoints.toLocaleString()} pts`;
        if (modalAuditHeldSub) modalAuditHeldSub.textContent = `Unit 1: ${latestU1.toLocaleString()} · Unit 2: ${latestU2.toLocaleString()}`;
        if (modalAuditGainedVal) modalAuditGainedVal.textContent = `${totalPointsGained.toLocaleString()} pts`;
        if (modalAuditGainedSub) modalAuditGainedSub.textContent = `${normalPointsGained.toLocaleString()} standard + ${ignoredPointsGained.toLocaleString()} Roblox imports`;
        if (modalAuditDiffVal) modalAuditDiffVal.textContent = `${diffHeldMinusGained === 0 ? '0' : (diffHeldMinusGained > 0 ? '+' : '-') + diffAbs.toLocaleString()} pts`;
        if (modalAuditDiffStatus) {
            modalAuditDiffStatus.textContent = diffHeldMinusGained === 0 ? "Exact Match (100% reconciled)" : (diffHeldMinusGained > 0 ? "Account Surplus" : "Discrepancy");
            modalAuditDiffStatus.style.color = diffHeldMinusGained === 0 ? "#34d399" : (diffHeldMinusGained > 0 ? "#fbbf24" : "#f87171");
        }
        if (modalAuditIgnoredCount) modalAuditIgnoredCount.textContent = `${ignoredPointLogsCount} Event${ignoredPointLogsCount !== 1 ? 's' : ''}`;

        if (modalAuditIgnoredTableBody) {
            if (ignoredDetails.length === 0) {
                modalAuditIgnoredTableBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 16px;">No Roblox import or overwritten log entries found in this archive.</td></tr>`;
            } else {
                modalAuditIgnoredTableBody.innerHTML = ignoredDetails.map(item => `
                    <tr>
                        <td>${item.date}</td>
                        <td style="color: #fbbf24;">${item.message}</td>
                        <td><span class="dp-type-badge tag-${item.type === 'UNIT_1' ? 'u1' : (item.type === 'UNIT_2' ? 'u2' : 'total')}">${item.type}</span></td>
                        <td style="text-align: right; font-weight: bold; color: #22d3ee;">+${item.amount.toLocaleString()}</td>
                    </tr>
                `).join('');
            }
        }

        const localFileBadgeBox = document.getElementById("localFileBadgeBox");
        if (localFileBadgeBox) localFileBadgeBox.style.display = "flex";
        if (localFileNameBadge) localFileNameBadge.textContent = fileName;
        if (localFileSizeBadge) localFileSizeBadge.textContent = `${fileSizeMb} MB`;
        if (btnSwitchFile) btnSwitchFile.style.display = "inline-flex";

        if (localStatDateRange) localStatDateRange.textContent = timeline.length > 0 ? `${timeline[0].formatted_date}, 2026 → ${timeline[timeline.length - 1].formatted_date}, 2026` : "N/A";
        if (localStatTimelinePoints) localStatTimelinePoints.textContent = `${timeline.length} Events`;
        if (localStatPlayerId) localStatPlayerId.textContent = player.id || player.username || "Local Player";

        const groupedOverall = groupBreakdownSources(categoryTotals.OVERALL);
        const overallPoints = groupedOverall.reduce((sum, item) => sum + item.value, 0) || 1;
        if (localBreakdownTotalSources) localBreakdownTotalSources.textContent = `${groupedOverall.length} Categories`;

        if (localBreakdownList) {
            renderBreakdownItems(localBreakdownList, groupedOverall, overallPoints, false);
        }

        const groupedU1 = groupBreakdownSources(categoryTotals.UNIT_1);
        const u1BasePoints = groupedU1.reduce((sum, item) => sum + item.value, 0) || 1;
        if (localBreakdownUnit1List) {
            renderBreakdownItems(localBreakdownUnit1List, groupedU1, u1BasePoints, false);
        }

        const groupedU2 = groupBreakdownSources(categoryTotals.UNIT_2);
        const u2BasePoints = groupedU2.reduce((sum, item) => sum + item.value, 0) || 1;
        if (localBreakdownUnit2List) {
            renderBreakdownItems(localBreakdownUnit2List, groupedU2, u2BasePoints, false);
        }

        const missionsGroupItem = groupedOverall.find(item => item.groupKey === "missions");
        if (missionsGroupItem) {
            renderMissionsTab(missionsGroupItem.subItems, missionsGroupItem.value);
        } else {
            renderMissionsTab([], 0);
        }

        if (localDropzoneSection) localDropzoneSection.style.display = "none";
        if (localDashboardContent) localDashboardContent.style.display = "flex";

        chart.setData(timeline);
        showToast(`Parsed ${timeline.length} events offline! Total earned: ${totalPointsGained.toLocaleString()} pts`, "success");
    }

    async function handleFile(file) {
        if (!file) return;

        const isZip = file.name.toLowerCase().endsWith(".zip");
        const isGz = file.name.toLowerCase().endsWith(".gz");
        const isJson = file.name.toLowerCase().endsWith(".json");

        if (!isJson && !isZip && !isGz) {
            showToast("Please select a valid .json file or archive (.zip, .gz).", "error");
            return;
        }

        const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
        showLoadingOverlay(true, `Reading ${file.name} (${sizeMb} MB)...`, 15, "Opening file stream...");

        try {
            let jsonText = "";

            if (isZip) {
                updateLoadingOverlay("Inspecting ZIP archive...", 5);
                if (typeof JSZip === "undefined") {
                    showLoadingOverlay(false);
                    showToast("ZIP archive detected. Please extract 'sar_data.json' or check your internet connection for JSZip.", "error");
                    return;
                }

                const jszip = new JSZip();
                const zip = await jszip.loadAsync(file, (metadata) => {
                    const p = Math.min(40, Math.round((metadata.percent || 0) * 0.4));
                    updateLoadingOverlay(`Reading ZIP directory: ${metadata.percent.toFixed(0)}%`, p);
                });

                let jsonFileInZip = null;
                zip.forEach((relativePath, zipEntry) => {
                    if (!zipEntry.dir && (relativePath.toLowerCase().endsWith("sar_data.json") || relativePath.toLowerCase().endsWith(".json"))) {
                        if (!jsonFileInZip || relativePath.toLowerCase().endsWith("sar_data.json")) {
                            jsonFileInZip = zipEntry;
                        }
                    }
                });

                if (!jsonFileInZip) {
                    showLoadingOverlay(false);
                    showToast("No .json file found inside the zip archive.", "error");
                    return;
                }

                jsonText = await jsonFileInZip.async("string", (metadata) => {
                    const decompPercent = metadata.percent || 0;
                    const p = Math.min(80, 40 + Math.round(decompPercent * 0.4));
                    updateLoadingOverlay(`Decompressing ${jsonFileInZip.name}: ${decompPercent.toFixed(0)}%`, p);
                });
            } else if (isGz) {
                updateLoadingOverlay("Initializing gzip decompression...", 5);
                if (typeof DecompressionStream !== "undefined") {
                    let loadedBytes = 0;
                    const totalBytes = file.size || 1;
                    const progressStream = new TransformStream({
                        transform(chunk, controller) {
                            loadedBytes += chunk.length;
                            const p = Math.min(80, Math.round((loadedBytes / totalBytes) * 80));
                            const kbLoaded = (loadedBytes / 1024).toFixed(0);
                            const kbTotal = (totalBytes / 1024).toFixed(0);
                            updateLoadingOverlay(`Decompressing gzip archive (${kbLoaded} / ${kbTotal} KB)...`, p);
                            controller.enqueue(chunk);
                        }
                    });

                    const ds = new DecompressionStream("gzip");
                    const stream = file.stream().pipeThrough(progressStream).pipeThrough(ds);
                    const response = new Response(stream);
                    jsonText = await response.text();
                } else {
                    showLoadingOverlay(false);
                    showToast("Gzip decompression stream not supported in this browser.", "error");
                    return;
                }
            } else {
                updateLoadingOverlay("Reading file from disk...", 5);
                jsonText = await new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onprogress = (e) => {
                        if (e.lengthComputable && e.total > 0) {
                            const p = Math.min(80, Math.round((e.loaded / e.total) * 80));
                            const mbLoaded = (e.loaded / (1024 * 1024)).toFixed(1);
                            const mbTotal = (e.total / (1024 * 1024)).toFixed(1);
                            updateLoadingOverlay(`Reading file (${mbLoaded} / ${mbTotal} MB)...`, p);
                        }
                    };
                    reader.onload = (e) => resolve(e.target.result);
                    reader.onerror = () => reject(new Error("File read error"));
                    reader.readAsText(file);
                });
            }

            updateLoadingOverlay("Parsing telemetry records...", 85);
            await new Promise(r => setTimeout(r, 20));

            const parsed = JSON.parse(jsonText);
            const logsCount = (parsed.activityLogs || []).length;
            updateLoadingOverlay(`Reconciling ${logsCount.toLocaleString()} activity logs...`, 92);
            await new Promise(r => setTimeout(r, 20));

            processLocalJson(parsed, file.name, sizeMb);
            updateLoadingOverlay("Loaded successfully!", 100);
            setTimeout(() => showLoadingOverlay(false), 200);
        } catch (err) {
            console.error("Error reading file:", err);
            showLoadingOverlay(false);
            showToast("Failed to process file: " + err.message, "error");
        }
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
    if (btnSwitchFile) btnSwitchFile.addEventListener("click", () => localFileInput.click());

    if (localDropzone) {
        localDropzone.addEventListener("click", (e) => {
            if (e.target.closest(".dropzone-loading-overlay")) return;
            localFileInput.click();
        });
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
