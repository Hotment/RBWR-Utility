class SARProgressionChart {
    constructor(svgElementId, containerId, tooltipId) {
        this.container = typeof containerId === "string" ? document.getElementById(containerId) : containerId;
        this.svg = typeof svgElementId === "string" ? document.getElementById(svgElementId) : svgElementId;

        if (!this.svg && this.container) {
            this.svg = this.container.querySelector("svg");
            if (!this.svg) {
                this.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                this.svg.id = typeof svgElementId === "string" ? svgElementId : "pointProgressionChart";
                this.svg.setAttribute("preserveAspectRatio", "none");
                this.container.appendChild(this.svg);
            }
        }

        if (!this.svg) return;

        this._ensureLayers();

        this.gridGroup = this.svg.querySelector(".grid-layer") || document.getElementById("gridGroup") || document.getElementById("localGridGroup");
        this.areasGroup = this.svg.querySelector(".areas-layer") || document.getElementById("areasGroup") || document.getElementById("localAreasGroup");
        this.linesGroup = this.svg.querySelector(".lines-layer") || document.getElementById("linesGroup") || document.getElementById("localLinesGroup");
        this.axesGroup = this.svg.querySelector(".axes-layer") || document.getElementById("axesGroup") || document.getElementById("localAxesGroup");
        this.crosshairGroup = this.svg.querySelector(".crosshair-layer") || document.getElementById("crosshairGroup") || document.getElementById("localCrosshairGroup");

        this.areaU1 = this.svg.querySelector(".area-u1") || document.getElementById("areaUnit1") || document.getElementById("localAreaUnit1");
        this.areaU2 = this.svg.querySelector(".area-u2") || document.getElementById("areaUnit2") || document.getElementById("localAreaUnit2");
        this.lineU1 = this.svg.querySelector(".line-u1") || document.getElementById("lineUnit1") || document.getElementById("localLineUnit1");
        this.lineU2 = this.svg.querySelector(".line-u2") || document.getElementById("lineUnit2") || document.getElementById("localLineUnit2");
        this.crosshairLine = this.svg.querySelector(".crosshair-v") || document.getElementById("crosshairLine") || document.getElementById("localCrosshairLine");

        const tid = tooltipId || "chartTooltip";
        this.tooltip = document.getElementById(tid) || (this.container ? this.container.querySelector(".chart-tooltip") : null) || document.getElementById("chartTooltip") || document.getElementById("localChartTooltip");

        if (this.tooltip && this.tooltip.parentElement !== document.body) {
            document.body.appendChild(this.tooltip);
        }

        this.rawTimeline = [];
        this.filteredTimeline = [];
        this.showU1 = true;
        this.showU2 = true;
        this.showArea = true;
        this.activeRange = "all";
        this.activePoint = null;
        this.onPointClick = null;
        this.onZoomChange = null;

        this.viewMinEpoch = null;
        this.viewMaxEpoch = null;
        this.baseMinEpoch = null;
        this.baseMaxEpoch = null;

        this.viewMinY = null;
        this.viewMaxY = null;
        this.baseMinY = 0;
        this.baseMaxY = 1000;

        this.isZoomed = false;

        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;
        this.dragStartMinEpoch = 0;
        this.dragStartMaxEpoch = 0;
        this.dragStartMinY = 0;
        this.dragStartMaxY = 0;
        this.hasDraggedDistance = false;

        this.initialPinchDistance = null;
        this.initialPinchMinEpoch = null;
        this.initialPinchMaxEpoch = null;
        this.initialPinchMinY = null;
        this.initialPinchMaxY = null;

        this.padding = { top: 35, right: 35, bottom: 55, left: 75 };

        if (this.container) {
            this.container.style.cursor = "crosshair";
            this.container.style.userSelect = "none";
            this.container.style.touchAction = "none";
        }

        this._initEvents();
    }

    _ensureLayers() {
        if (!this.svg) return;
        const ns = "http://www.w3.org/2000/svg";

        let defs = this.svg.querySelector("defs");
        if (!defs) {
            defs = document.createElementNS(ns, "defs");
            this.svg.insertBefore(defs, this.svg.firstChild);
        }

        let clipPath = defs.querySelector("#chartPlotClip");
        if (!clipPath) {
            clipPath = document.createElementNS(ns, "clipPath");
            clipPath.setAttribute("id", "chartPlotClip");
            const clipRect = document.createElementNS(ns, "rect");
            clipRect.setAttribute("id", "chartClipRect");
            clipPath.appendChild(clipRect);
            defs.appendChild(clipPath);
        }

        let gridGroup = this.svg.querySelector(".grid-layer");
        if (!gridGroup) {
            gridGroup = document.createElementNS(ns, "g");
            gridGroup.setAttribute("class", "grid-layer");
            this.svg.appendChild(gridGroup);
        }

        let areasGroup = this.svg.querySelector(".areas-layer");
        if (!areasGroup) {
            areasGroup = document.createElementNS(ns, "g");
            areasGroup.setAttribute("class", "areas-layer");
            areasGroup.setAttribute("clip-path", "url(#chartPlotClip)");
            this.svg.appendChild(areasGroup);
        } else {
            areasGroup.setAttribute("clip-path", "url(#chartPlotClip)");
        }

        let areaU1 = areasGroup.querySelector(".area-u1");
        if (!areaU1) {
            areaU1 = document.createElementNS(ns, "path");
            areaU1.setAttribute("class", "chart-area area-u1");
            areaU1.setAttribute("fill", "rgba(82, 148, 226, 0.18)");
            areasGroup.appendChild(areaU1);
        }

        let areaU2 = areasGroup.querySelector(".area-u2");
        if (!areaU2) {
            areaU2 = document.createElementNS(ns, "path");
            areaU2.setAttribute("class", "chart-area area-u2");
            areaU2.setAttribute("fill", "rgba(240, 113, 93, 0.15)");
            areasGroup.appendChild(areaU2);
        }

        let linesGroup = this.svg.querySelector(".lines-layer");
        if (!linesGroup) {
            linesGroup = document.createElementNS(ns, "g");
            linesGroup.setAttribute("class", "lines-layer");
            linesGroup.setAttribute("clip-path", "url(#chartPlotClip)");
            this.svg.appendChild(linesGroup);
        } else {
            linesGroup.setAttribute("clip-path", "url(#chartPlotClip)");
        }

        let lineU1 = linesGroup.querySelector(".line-u1");
        if (!lineU1) {
            lineU1 = document.createElementNS(ns, "path");
            lineU1.setAttribute("class", "chart-line line-u1");
            lineU1.setAttribute("stroke", "#5294e2");
            linesGroup.appendChild(lineU1);
        }

        let lineU2 = linesGroup.querySelector(".line-u2");
        if (!lineU2) {
            lineU2 = document.createElementNS(ns, "path");
            lineU2.setAttribute("class", "chart-line line-u2");
            lineU2.setAttribute("stroke", "#f0715d");
            linesGroup.appendChild(lineU2);
        }

        let axesGroup = this.svg.querySelector(".axes-layer");
        if (!axesGroup) {
            axesGroup = document.createElementNS(ns, "g");
            axesGroup.setAttribute("class", "axes-layer");
            this.svg.appendChild(axesGroup);
        }

        let crosshairGroup = this.svg.querySelector(".crosshair-layer");
        if (!crosshairGroup) {
            crosshairGroup = document.createElementNS(ns, "g");
            crosshairGroup.setAttribute("class", "crosshair-layer");
            crosshairGroup.style.display = "none";

            const line = document.createElementNS(ns, "line");
            line.setAttribute("class", "crosshair-v");
            crosshairGroup.appendChild(line);

            this.svg.appendChild(crosshairGroup);
        }
    }

    _initEvents() {
        if (!this.svg) return;
        window.addEventListener("resize", () => this.render());

        if (this.container) {
            this.container.addEventListener("wheel", (e) => this._handleWheel(e), { passive: false });
        }

        this.svg.addEventListener("mousedown", (e) => this._handleMouseDown(e));
        window.addEventListener("mousemove", (e) => this._handleMouseMove(e));
        window.addEventListener("mouseup", (e) => this._handleMouseUp(e));
        this.svg.addEventListener("mouseleave", () => this._handlePointerLeave());
        this.svg.addEventListener("dblclick", () => this.resetZoom());

        this.svg.addEventListener("touchstart", (e) => this._handleTouchStart(e), { passive: false });
        this.svg.addEventListener("touchmove", (e) => this._handleTouchMove(e), { passive: false });
        this.svg.addEventListener("touchend", (e) => this._handleTouchEnd(e));

        if (this.tooltip) {
            this.tooltip.style.cursor = "pointer";
            this.tooltip.addEventListener("click", () => {
                if (this.activePoint && typeof this.onPointClick === "function") {
                    this.onPointClick(this.activePoint);
                }
            });
        }
    }

    _handleWheel(e) {
        if (!this.plotBounds || !this.filteredTimeline || this.filteredTimeline.length < 2) return;

        const rect = this.svg.getBoundingClientRect();
        const clientX = e.clientX;
        const clientY = e.clientY;

        if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) return;

        e.preventDefault();

        const scaleX = this.width / (rect.width || 1);
        const scaleY = this.height / (rect.height || 1);
        const mouseX = (clientX - rect.left) * scaleX;
        const mouseY = (clientY - rect.top) * scaleY;

        const clampedMouseX = Math.max(this.plotBounds.x, Math.min(this.plotBounds.x + this.plotBounds.w, mouseX));
        const cursorRatioX = (clampedMouseX - this.plotBounds.x) / (this.plotBounds.w || 1);

        const clampedMouseY = Math.max(this.plotBounds.y, Math.min(this.plotBounds.baselineY, mouseY));
        const cursorRatioY = (this.plotBounds.baselineY - clampedMouseY) / (this.plotBounds.h || 1);

        const zoomFactor = e.deltaY > 0 ? 1.18 : 0.82;

        const currentMinX = this.viewMinEpoch !== null ? this.viewMinEpoch : this.baseMinEpoch;
        const currentMaxX = this.viewMaxEpoch !== null ? this.viewMaxEpoch : this.baseMaxEpoch;
        const currentSpanX = currentMaxX - currentMinX;

        let newSpanX = currentSpanX * zoomFactor;
        const totalSpanX = this.baseMaxEpoch - this.baseMinEpoch;
        const minSpanX = Math.min(60 * 1000, totalSpanX);
        newSpanX = Math.max(minSpanX, Math.min(totalSpanX, newSpanX));

        const cursorEpoch = currentMinX + (currentSpanX * cursorRatioX);
        let newMinX = cursorEpoch - (newSpanX * cursorRatioX);
        let newMaxX = cursorEpoch + (newSpanX * (1 - cursorRatioX));

        if (newMinX < this.baseMinEpoch) {
            newMinX = this.baseMinEpoch;
            newMaxX = Math.min(this.baseMaxEpoch, newMinX + newSpanX);
        }
        if (newMaxX > this.baseMaxEpoch) {
            newMaxX = this.baseMaxEpoch;
            newMinX = Math.max(this.baseMinEpoch, newMaxX - newSpanX);
        }

        const currentMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
        const currentMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
        const currentSpanY = currentMaxY - currentMinY;

        let newSpanY = currentSpanY * zoomFactor;
        const totalSpanY = this.baseMaxY - this.baseMinY;
        const minSpanY = Math.max(10, totalSpanY * 0.05);
        newSpanY = Math.max(minSpanY, Math.min(totalSpanY, newSpanY));

        const cursorValY = currentMinY + (currentSpanY * cursorRatioY);
        let newMinY = cursorValY - (newSpanY * cursorRatioY);
        let newMaxY = cursorValY + (newSpanY * (1 - cursorRatioY));

        if (newMinY < this.baseMinY) {
            newMinY = this.baseMinY;
            newMaxY = Math.min(this.baseMaxY, newMinY + newSpanY);
        }
        if (newMaxY > this.baseMaxY) {
            newMaxY = this.baseMaxY;
            newMinY = Math.max(this.baseMinY, newMaxY - newSpanY);
        }

        this.viewMinEpoch = newMinX;
        this.viewMaxEpoch = newMaxX;
        this.viewMinY = newMinY;
        this.viewMaxY = newMaxY;

        this.isZoomed = (newSpanX < totalSpanX * 0.998) || (newSpanY < totalSpanY * 0.998) || (newMinX > this.baseMinEpoch + 1000) || (newMaxX < this.baseMaxEpoch - 1000) || (newMinY > this.baseMinY + 1);

        this._triggerZoomChange();
        this.render();
        this._handlePointerMove(clientX, clientY);
    }

    _handleMouseDown(e) {
        if (e.button !== 0) return;
        if (!this.plotBounds || !this.filteredTimeline || this.filteredTimeline.length < 2) return;

        this.isDragging = true;
        this.dragStartX = e.clientX;
        this.dragStartY = e.clientY;
        this.dragStartMinEpoch = this.viewMinEpoch !== null ? this.viewMinEpoch : this.baseMinEpoch;
        this.dragStartMaxEpoch = this.viewMaxEpoch !== null ? this.viewMaxEpoch : this.baseMaxEpoch;
        this.dragStartMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
        this.dragStartMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
        this.hasDraggedDistance = false;
        if (this.container) this.container.style.cursor = "grabbing";
    }

    _handleMouseMove(e) {
        if (this.isDragging) {
            const deltaX = e.clientX - this.dragStartX;
            const deltaY = e.clientY - this.dragStartY;

            if (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4) {
                this.hasDraggedDistance = true;
                this._handlePointerLeave();
            }

            if (this.hasDraggedDistance) {
                const rect = this.svg.getBoundingClientRect();
                const scaleX = this.width / (rect.width || 1);
                const scaleY = this.height / (rect.height || 1);

                const currentSpanX = this.dragStartMaxEpoch - this.dragStartMinEpoch;
                const timeDelta = -((deltaX * scaleX) / this.plotBounds.w) * currentSpanX;

                let newMinX = this.dragStartMinEpoch + timeDelta;
                let newMaxX = this.dragStartMaxEpoch + timeDelta;

                if (newMinX < this.baseMinEpoch) {
                    newMinX = this.baseMinEpoch;
                    newMaxX = newMinX + currentSpanX;
                }
                if (newMaxX > this.baseMaxEpoch) {
                    newMaxX = this.baseMaxEpoch;
                    newMinX = newMaxX - currentSpanX;
                }

                const currentSpanY = this.dragStartMaxY - this.dragStartMinY;
                const yValDelta = ((deltaY * scaleY) / this.plotBounds.h) * currentSpanY;

                let newMinY = this.dragStartMinY + yValDelta;
                let newMaxY = this.dragStartMaxY + yValDelta;

                if (newMinY < this.baseMinY) {
                    newMinY = this.baseMinY;
                    newMaxY = newMinY + currentSpanY;
                }
                if (newMaxY > this.baseMaxY) {
                    newMaxY = this.baseMaxY;
                    newMinY = newMaxY - currentSpanY;
                }

                this.viewMinEpoch = newMinX;
                this.viewMaxEpoch = newMaxX;
                this.viewMinY = newMinY;
                this.viewMaxY = newMaxY;

                const totalSpanX = this.baseMaxEpoch - this.baseMinEpoch;
                const totalSpanY = this.baseMaxY - this.baseMinY;
                this.isZoomed = (currentSpanX < totalSpanX * 0.998) || (currentSpanY < totalSpanY * 0.998) || (newMinX > this.baseMinEpoch + 1000) || (newMaxX < this.baseMaxEpoch - 1000) || (newMinY > this.baseMinY + 1);

                this._triggerZoomChange();
                this.render();
            }
        } else {
            const rect = this.svg.getBoundingClientRect();
            if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
                this._handlePointerMove(e.clientX, e.clientY);
            }
        }
    }

    _handleMouseUp(e) {
        if (this.isDragging) {
            this.isDragging = false;
            if (this.container) this.container.style.cursor = "crosshair";
            if (!this.hasDraggedDistance && this.activePoint && typeof this.onPointClick === "function") {
                this.onPointClick(this.activePoint);
            }
        }
    }

    _handleTouchStart(e) {
        if (!this.plotBounds || !this.filteredTimeline || this.filteredTimeline.length < 2) return;

        if (e.touches.length === 2) {
            e.preventDefault();
            this.isDragging = false;
            this.initialPinchDistance = Math.hypot(
                e.touches[0].clientX - e.touches[1].clientX,
                e.touches[0].clientY - e.touches[1].clientY
            );
            this.initialPinchMinEpoch = this.viewMinEpoch !== null ? this.viewMinEpoch : this.baseMinEpoch;
            this.initialPinchMaxEpoch = this.viewMaxEpoch !== null ? this.viewMaxEpoch : this.baseMaxEpoch;
            this.initialPinchMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
            this.initialPinchMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
        } else if (e.touches.length === 1) {
            this.isDragging = true;
            this.dragStartX = e.touches[0].clientX;
            this.dragStartY = e.touches[0].clientY;
            this.dragStartMinEpoch = this.viewMinEpoch !== null ? this.viewMinEpoch : this.baseMinEpoch;
            this.dragStartMaxEpoch = this.viewMaxEpoch !== null ? this.viewMaxEpoch : this.baseMaxEpoch;
            this.dragStartMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
            this.dragStartMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
            this.hasDraggedDistance = false;
        }
    }

    _handleTouchMove(e) {
        if (e.touches.length === 2 && this.initialPinchDistance) {
            e.preventDefault();
            const currentDist = Math.hypot(
                e.touches[0].clientX - e.touches[1].clientX,
                e.touches[0].clientY - e.touches[1].clientY
            );
            if (currentDist > 0) {
                const scale = this.initialPinchDistance / currentDist;

                const currentSpanX = this.initialPinchMaxEpoch - this.initialPinchMinEpoch;
                const totalSpanX = this.baseMaxEpoch - this.baseMinEpoch;
                const newSpanX = Math.max(60000, Math.min(totalSpanX, currentSpanX * scale));
                const midEpoch = (this.initialPinchMinEpoch + this.initialPinchMaxEpoch) / 2;

                let newMinX = midEpoch - (newSpanX / 2);
                let newMaxX = midEpoch + (newSpanX / 2);
                if (newMinX < this.baseMinEpoch) {
                    newMinX = this.baseMinEpoch;
                    newMaxX = Math.min(this.baseMaxEpoch, newMinX + newSpanX);
                }
                if (newMaxX > this.baseMaxEpoch) {
                    newMaxX = this.baseMaxEpoch;
                    newMinX = Math.max(this.baseMinEpoch, newMaxX - newSpanX);
                }

                const currentSpanY = this.initialPinchMaxY - this.initialPinchMinY;
                const totalSpanY = this.baseMaxY - this.baseMinY;
                const newSpanY = Math.max(10, Math.min(totalSpanY, currentSpanY * scale));
                const midValY = (this.initialPinchMinY + this.initialPinchMaxY) / 2;

                let newMinY = midValY - (newSpanY / 2);
                let newMaxY = midValY + (newSpanY / 2);
                if (newMinY < this.baseMinY) {
                    newMinY = this.baseMinY;
                    newMaxY = Math.min(this.baseMaxY, newMinY + newSpanY);
                }
                if (newMaxY > this.baseMaxY) {
                    newMaxY = this.baseMaxY;
                    newMinY = Math.max(this.baseMinY, newMaxY - newSpanY);
                }

                this.viewMinEpoch = newMinX;
                this.viewMaxEpoch = newMaxX;
                this.viewMinY = newMinY;
                this.viewMaxY = newMaxY;
                this.isZoomed = true;
                this._triggerZoomChange();
                this.render();
            }
        } else if (e.touches.length === 1 && this.isDragging) {
            const deltaX = e.touches[0].clientX - this.dragStartX;
            const deltaY = e.touches[0].clientY - this.dragStartY;

            if (Math.abs(deltaX) > 6 || Math.abs(deltaY) > 6) {
                e.preventDefault();
                this.hasDraggedDistance = true;
                this._handlePointerLeave();

                const rect = this.svg.getBoundingClientRect();
                const scaleX = this.width / (rect.width || 1);
                const scaleY = this.height / (rect.height || 1);

                const currentSpanX = this.dragStartMaxEpoch - this.dragStartMinEpoch;
                const timeDelta = -((deltaX * scaleX) / this.plotBounds.w) * currentSpanX;

                let newMinX = this.dragStartMinEpoch + timeDelta;
                let newMaxX = this.dragStartMaxEpoch + timeDelta;
                if (newMinX < this.baseMinEpoch) {
                    newMinX = this.baseMinEpoch;
                    newMaxX = newMinX + currentSpanX;
                }
                if (newMaxX > this.baseMaxEpoch) {
                    newMaxX = this.baseMaxEpoch;
                    newMinX = newMaxX - currentSpanX;
                }

                const currentSpanY = this.dragStartMaxY - this.dragStartMinY;
                const yValDelta = ((deltaY * scaleY) / this.plotBounds.h) * currentSpanY;

                let newMinY = this.dragStartMinY + yValDelta;
                let newMaxY = this.dragStartMaxY + yValDelta;
                if (newMinY < this.baseMinY) {
                    newMinY = this.baseMinY;
                    newMaxY = newMinY + currentSpanY;
                }
                if (newMaxY > this.baseMaxY) {
                    newMaxY = this.baseMaxY;
                    newMinY = newMaxY - currentSpanY;
                }

                this.viewMinEpoch = newMinX;
                this.viewMaxEpoch = newMaxX;
                this.viewMinY = newMinY;
                this.viewMaxY = newMaxY;
                this.isZoomed = true;
                this._triggerZoomChange();
                this.render();
            } else {
                this._handlePointerMove(e.touches[0].clientX, e.touches[0].clientY);
            }
        }
    }

    _handleTouchEnd(e) {
        if (e.touches.length === 0) {
            if (!this.hasDraggedDistance && this.activePoint && typeof this.onPointClick === "function") {
                this.onPointClick(this.activePoint);
            }
            this.isDragging = false;
            this.initialPinchDistance = null;
            this._handlePointerLeave();
        }
    }

    resetZoom() {
        this.viewMinEpoch = this.baseMinEpoch;
        this.viewMaxEpoch = this.baseMaxEpoch;
        this.viewMinY = this.baseMinY;
        this.viewMaxY = this.baseMaxY;
        this.isZoomed = false;
        this._triggerZoomChange();
        this.render();
    }

    _triggerZoomChange() {
        if (typeof this.onZoomChange === "function") {
            this.onZoomChange(this.isZoomed);
        }
    }

    setData(timeline) {
        this.rawTimeline = timeline || [];
        this.applyFilter(this.activeRange);
    }

    setRange(range) {
        return this.applyFilter(range);
    }

    applyFilter(range) {
        this.activeRange = range;
        if (!this.rawTimeline.length) {
            this.filteredTimeline = [];
            this.baseMinEpoch = null;
            this.baseMaxEpoch = null;
            this.viewMinEpoch = null;
            this.viewMaxEpoch = null;
            this.baseMinY = 0;
            this.baseMaxY = 1000;
            this.viewMinY = null;
            this.viewMaxY = null;
            this.isZoomed = false;
            this._triggerZoomChange();
            this.render();
            return;
        }

        if (range === "all") {
            this.filteredTimeline = [...this.rawTimeline];
        } else {
            const daysMap = { "30d": 30, "14d": 14, "7d": 7, "24h": 1, "1d": 1 };
            const days = daysMap[range] || 30;
            const latestEpoch = this.rawTimeline[this.rawTimeline.length - 1].timestamp_epoch;
            const cutoffEpoch = latestEpoch - (days * 24 * 3600 * 1000);

            this.filteredTimeline = this.rawTimeline.filter(d => d.timestamp_epoch >= cutoffEpoch);
            if (this.filteredTimeline.length === 0) {
                this.filteredTimeline = [...this.rawTimeline];
            }
        }

        let minVal = Infinity;
        let maxVal = -Infinity;
        for (const d of this.filteredTimeline) {
            if (this.showU1 && typeof d.u1 === "number") {
                if (d.u1 < minVal) minVal = d.u1;
                if (d.u1 > maxVal) maxVal = d.u1;
            }
            if (this.showU2 && typeof d.u2 === "number") {
                if (d.u2 < minVal) minVal = d.u2;
                if (d.u2 > maxVal) maxVal = d.u2;
            }
            if (!this.showU1 && !this.showU2) {
                if (typeof d.u1 === "number") {
                    if (d.u1 < minVal) minVal = d.u1;
                    if (d.u1 > maxVal) maxVal = d.u1;
                }
                if (typeof d.u2 === "number") {
                    if (d.u2 < minVal) minVal = d.u2;
                    if (d.u2 > maxVal) maxVal = d.u2;
                }
            }
        }
        if (!isFinite(minVal)) minVal = 0;
        if (!isFinite(maxVal) || maxVal === 0) maxVal = 1000;

        if (range === "all") {
            if (minVal <= 0 || (maxVal > 0 && minVal / maxVal < 0.2)) {
                this.baseMinY = 0;
                this.baseMaxY = this._calculateNiceMax(maxVal * 1.05);
            } else {
                const span = maxVal - minVal;
                const pad = span > 0 ? span * 0.10 : Math.max(10, maxVal * 0.05);
                this.baseMinY = Math.max(0, Math.floor(minVal - pad));
                this.baseMaxY = Math.ceil(maxVal + pad);
            }
        } else {
            const span = maxVal - minVal;
            const pad = span > 0 ? span * 0.10 : Math.max(10, maxVal * 0.05);
            this.baseMinY = Math.max(0, Math.floor(minVal - pad));
            this.baseMaxY = Math.ceil(maxVal + pad);
        }

        this.baseMinEpoch = this.filteredTimeline[0].timestamp_epoch;
        this.baseMaxEpoch = this.filteredTimeline[this.filteredTimeline.length - 1].timestamp_epoch;
        if (this.baseMinEpoch === this.baseMaxEpoch) {
            this.baseMinEpoch -= 60000;
            this.baseMaxEpoch += 60000;
        }

        this.viewMinEpoch = this.baseMinEpoch;
        this.viewMaxEpoch = this.baseMaxEpoch;

        this.viewMinY = this.baseMinY;
        this.viewMaxY = this.baseMaxY;

        this.isZoomed = false;
        this._triggerZoomChange();
        this.render();
    }

    toggleArea() {
        this.showArea = !this.showArea;
        if (this.areasGroup) {
            this.areasGroup.style.display = this.showArea ? "block" : "none";
        }
        this.render();
        return this.showArea;
    }

    toggleSeries(seriesName) {
        if (seriesName === "u1") {
            this.showU1 = !this.showU1;
        } else if (seriesName === "u2") {
            this.showU2 = !this.showU2;
        }
        if (!this.isZoomed) {
            this.applyFilter(this.activeRange);
        } else {
            this.render();
        }
    }

    _formatPoints(val) {
        const rounded = Math.round(val);
        if (rounded >= 1000000) {
            const formatted = (rounded / 1000000).toFixed(1).replace(/\.0$/, '');
            return `${formatted}M`;
        }
        if (rounded >= 1000) {
            const formatted = (rounded / 1000).toFixed(0);
            return `${formatted}K`;
        }
        return rounded.toLocaleString();
    }

    _formatXTick(epoch, timeSpan) {
        const d = new Date(epoch);
        const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const month = months[d.getUTCMonth()];
        const day = d.getUTCDate();
        const hh = String(d.getUTCHours()).padStart(2, '0');
        const mm = String(d.getUTCMinutes()).padStart(2, '0');
        const ss = String(d.getUTCSeconds()).padStart(2, '0');

        if (timeSpan > 2 * 24 * 3600 * 1000) {
            return `${month} ${day}`;
        } else if (timeSpan > 6 * 3600 * 1000) {
            return `${month} ${day} ${hh}:${mm}`;
        } else {
            return `${hh}:${mm}:${ss}`;
        }
    }

    render() {
        if (!this.container || !this.svg) return;

        const rect = this.container.getBoundingClientRect();
        const width = Math.max(300, rect.width || 800);
        const height = Math.max(260, rect.height || 480);

        this.width = width;
        this.height = height;
        this.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

        const isMobile = width < 640;
        this.padding = {
            top: isMobile ? 25 : 35,
            right: isMobile ? 18 : 35,
            bottom: isMobile ? 42 : 55,
            left: isMobile ? 54 : 75
        };

        if (this.gridGroup) this.gridGroup.innerHTML = "";
        if (this.axesGroup) this.axesGroup.innerHTML = "";

        const data = this.filteredTimeline;
        if (!data || data.length === 0) {
            if (this.lineU1) this.lineU1.setAttribute("d", "");
            if (this.lineU2) this.lineU2.setAttribute("d", "");
            if (this.areaU1) this.areaU1.setAttribute("d", "");
            if (this.areaU2) this.areaU2.setAttribute("d", "");
            return;
        }

        const plotX = this.padding.left;
        const plotY = this.padding.top;
        const plotW = width - this.padding.left - this.padding.right;
        const plotH = height - this.padding.top - this.padding.bottom;
        const baselineY = plotY + plotH;

        this.plotBounds = { x: plotX, y: plotY, w: plotW, h: plotH, baselineY };

        const clipRect = this.svg.querySelector("#chartClipRect");
        if (clipRect) {
            clipRect.setAttribute("x", plotX);
            clipRect.setAttribute("y", plotY - 4);
            clipRect.setAttribute("width", plotW);
            clipRect.setAttribute("height", plotH + 8);
        }

        const viewMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
        const viewMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
        const spanY = Math.max(1, viewMaxY - viewMinY);

        const yTickCount = isMobile ? 4 : 5;
        for (let i = 0; i <= yTickCount; i++) {
            const tickVal = viewMinY + (spanY / yTickCount) * i;
            const yPos = baselineY - (plotH * (i / yTickCount));

            if (this.gridGroup) {
                const gridLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
                gridLine.setAttribute("x1", plotX);
                gridLine.setAttribute("x2", plotX + plotW);
                gridLine.setAttribute("y1", yPos);
                gridLine.setAttribute("y2", yPos);
                gridLine.setAttribute("class", "grid-line");
                this.gridGroup.appendChild(gridLine);
            }

            if (this.axesGroup) {
                const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                text.setAttribute("x", plotX - (isMobile ? 8 : 12));
                text.setAttribute("y", yPos + 4);
                text.setAttribute("text-anchor", "end");
                text.setAttribute("class", "axis-text");
                text.textContent = this._formatPoints(tickVal);
                this.axesGroup.appendChild(text);
            }
        }

        if (this.axesGroup) {
            const yTitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
            yTitle.setAttribute("x", -((plotY + (plotH / 2))));
            yTitle.setAttribute("y", isMobile ? 14 : 22);
            yTitle.setAttribute("transform", "rotate(-90)");
            yTitle.setAttribute("text-anchor", "middle");
            yTitle.setAttribute("class", "axis-title");
            yTitle.textContent = "Points";
            this.axesGroup.appendChild(yTitle);
        }

        const viewMinEpoch = this.viewMinEpoch !== null ? this.viewMinEpoch : (data[0].timestamp_epoch);
        const viewMaxEpoch = this.viewMaxEpoch !== null ? this.viewMaxEpoch : (data[data.length - 1].timestamp_epoch);
        const spanEpoch = Math.max(1, viewMaxEpoch - viewMinEpoch);

        this.pointsU1 = [];
        this.pointsU2 = [];

        for (let i = 0; i < data.length; i++) {
            const d = data[i];
            const ratioX = (d.timestamp_epoch - viewMinEpoch) / spanEpoch;
            const x = plotX + (plotW * ratioX);

            const ratioY1 = (d.u1 - viewMinY) / spanY;
            const ratioY2 = (d.u2 - viewMinY) / spanY;

            const y1 = baselineY - (plotH * ratioY1);
            const y2 = baselineY - (plotH * ratioY2);

            this.pointsU1.push({ x, y: y1, data: d });
            this.pointsU2.push({ x, y: y2, data: d });
        }

        const xTickCount = isMobile ? 3 : 6;
        for (let i = 0; i < xTickCount; i++) {
            const tickRatio = i / (xTickCount - 1 || 1);
            const tickEpoch = viewMinEpoch + (spanEpoch * tickRatio);
            const tickX = plotX + (plotW * tickRatio);

            if (this.axesGroup) {
                const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                text.setAttribute("x", tickX);
                text.setAttribute("y", baselineY + (isMobile ? 18 : 22));
                text.setAttribute("text-anchor", i === 0 ? "start" : (i === xTickCount - 1 ? "end" : "middle"));
                text.setAttribute("class", "axis-text");
                text.textContent = this._formatXTick(tickEpoch, spanEpoch);
                this.axesGroup.appendChild(text);
            }
        }

        if (this.axesGroup) {
            const xTitle = document.createElementNS("http://www.w3.org/2000/svg", "text");
            xTitle.setAttribute("x", plotX + (plotW / 2));
            xTitle.setAttribute("y", height - (isMobile ? 6 : 12));
            xTitle.setAttribute("text-anchor", "middle");
            xTitle.setAttribute("class", "axis-title");
            xTitle.textContent = "Timeline";
            this.axesGroup.appendChild(xTitle);
        }

        if (this.showU1 && this.pointsU1.length > 0 && this.lineU1) {
            const pathD = this._generateCleanPath(this.pointsU1);
            this.lineU1.setAttribute("d", pathD);
            if (this.areaU1 && this.showArea) {
                const firstX = this.pointsU1[0].x;
                const lastX = this.pointsU1[this.pointsU1.length - 1].x;
                this.areaU1.setAttribute("d", `${pathD} L ${lastX} ${baselineY} L ${firstX} ${baselineY} Z`);
                this.areaU1.style.display = "block";
            } else if (this.areaU1) {
                this.areaU1.setAttribute("d", "");
                this.areaU1.style.display = "none";
            }
        } else if (this.lineU1) {
            this.lineU1.setAttribute("d", "");
            if (this.areaU1) this.areaU1.setAttribute("d", "");
        }

        if (this.showU2 && this.pointsU2.length > 0 && this.lineU2) {
            const pathD = this._generateCleanPath(this.pointsU2);
            this.lineU2.setAttribute("d", pathD);
            if (this.areaU2 && this.showArea) {
                const firstX = this.pointsU2[0].x;
                const lastX = this.pointsU2[this.pointsU2.length - 1].x;
                this.areaU2.setAttribute("d", `${pathD} L ${lastX} ${baselineY} L ${firstX} ${baselineY} Z`);
                this.areaU2.style.display = "block";
            } else if (this.areaU2) {
                this.areaU2.setAttribute("d", "");
                this.areaU2.style.display = "none";
            }
        } else if (this.lineU2) {
            this.lineU2.setAttribute("d", "");
            if (this.areaU2) this.areaU2.setAttribute("d", "");
        }
    }

    _calculateNiceMax(val) {
        if (val <= 0) return 1000;
        const magnitude = Math.pow(10, Math.floor(Math.log10(val)));
        const normalized = val / magnitude;
        let niceNorm;
        if (normalized <= 1) niceNorm = 1;
        else if (normalized <= 2) niceNorm = 2;
        else if (normalized <= 2.5) niceNorm = 2.5;
        else if (normalized <= 5) niceNorm = 5;
        else if (normalized <= 8) niceNorm = 8;
        else niceNorm = 10;
        return niceNorm * magnitude;
    }

    _generateCleanPath(points) {
        if (!points || points.length === 0) return "";
        if (points.length === 1) return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;

        let d = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x.toFixed(1)} ${points[i].y.toFixed(1)}`;
        }
        return d;
    }

    _handlePointerMove(clientX, clientY) {
        if (this.isDragging) return;
        if (!this.plotBounds || !this.pointsU1 || this.pointsU1.length === 0 || !this.svg) return;

        const rect = this.svg.getBoundingClientRect();
        const scaleX = this.width / (rect.width || 1);
        const mouseX = (clientX - rect.left) * scaleX;

        if (mouseX < this.plotBounds.x || mouseX > this.plotBounds.x + this.plotBounds.w) {
            this._handlePointerLeave();
            return;
        }

        let closestIdx = 0;
        let minDiff = Infinity;
        for (let i = 0; i < this.pointsU1.length; i++) {
            const diff = Math.abs(this.pointsU1[i].x - mouseX);
            if (diff < minDiff) {
                minDiff = diff;
                closestIdx = i;
            }
        }

        const pt1 = this.pointsU1[closestIdx];
        const pt2 = this.pointsU2[closestIdx];
        if (!pt1 || !pt2) return;
        const d = pt1.data;

        if (pt1.x < this.plotBounds.x || pt1.x > this.plotBounds.x + this.plotBounds.w) {
            this._handlePointerLeave();
            return;
        }

        if (this.crosshairGroup) {
            this.crosshairGroup.style.display = "block";
            if (!this.crosshairDotU1) {
                this.crosshairDotU1 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                this.crosshairDotU1.setAttribute("r", "4.5");
                this.crosshairDotU1.setAttribute("fill", "#5294e2");
                this.crosshairDotU1.setAttribute("stroke", "#ffffff");
                this.crosshairDotU1.setAttribute("stroke-width", "2");
                this.crosshairGroup.appendChild(this.crosshairDotU1);
            }
            if (!this.crosshairDotU2) {
                this.crosshairDotU2 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                this.crosshairDotU2.setAttribute("r", "4.5");
                this.crosshairDotU2.setAttribute("fill", "#f0715d");
                this.crosshairDotU2.setAttribute("stroke", "#ffffff");
                this.crosshairDotU2.setAttribute("stroke-width", "2");
                this.crosshairGroup.appendChild(this.crosshairDotU2);
            }

            if (this.crosshairLine) {
                this.crosshairLine.setAttribute("x1", pt1.x);
                this.crosshairLine.setAttribute("x2", pt1.x);
                this.crosshairLine.setAttribute("y1", this.plotBounds.y);
                this.crosshairLine.setAttribute("y2", this.plotBounds.baselineY);
            }
            if (this.crosshairDotU1) {
                this.crosshairDotU1.setAttribute("cx", pt1.x);
                this.crosshairDotU1.setAttribute("cy", pt1.y);
                this.crosshairDotU1.style.display = this.showU1 ? "block" : "none";
            }
            if (this.crosshairDotU2) {
                this.crosshairDotU2.setAttribute("cx", pt2.x);
                this.crosshairDotU2.setAttribute("cy", pt2.y);
                this.crosshairDotU2.style.display = this.showU2 ? "block" : "none";
            }
        }

        const dateEl = document.getElementById("tooltipDate") || document.getElementById("localTooltipDate");
        const timeEl = document.getElementById("tooltipTime") || document.getElementById("localTooltipTime");
        const valU1El = document.getElementById("tooltipValU1") || document.getElementById("localTooltipValU1");
        const valU2El = document.getElementById("tooltipValU2") || document.getElementById("localTooltipValU2");
        const valTotalEl = document.getElementById("tooltipValTotal") || document.getElementById("localTooltipValTotal");

        if (dateEl) dateEl.textContent = d.formatted_date + ", 2026";
        if (timeEl) timeEl.textContent = (d.formatted_datetime ? d.formatted_datetime.split(" ")[2] : "") || "";
        if (valU1El) valU1El.textContent = d.u1.toLocaleString();
        if (valU2El) valU2El.textContent = d.u2.toLocaleString();
        if (valTotalEl) valTotalEl.textContent = (d.u1 + d.u2).toLocaleString();

        const deltaU1El = document.getElementById("tooltipDeltaU1") || document.getElementById("localTooltipDeltaU1");
        const deltaU2El = document.getElementById("tooltipDeltaU2") || document.getElementById("localTooltipDeltaU2");

        if (deltaU1El && deltaU2El) {
            if (d.point_type === "UNIT_1") {
                deltaU1El.textContent = `+${d.change.toLocaleString()}`;
                deltaU1El.style.display = "inline-block";
                deltaU2El.style.display = "none";
            } else if (d.point_type === "UNIT_2") {
                deltaU2El.textContent = `+${d.change.toLocaleString()}`;
                deltaU2El.style.display = "inline-block";
                deltaU1El.style.display = "none";
            } else {
                deltaU1El.style.display = "none";
                deltaU2El.style.display = "none";
            }
        }

        this.activePoint = d;

        if (this.tooltip) {
            this.tooltip.style.display = "block";
            this.tooltip.style.position = "fixed";
            this.tooltip.style.zIndex = "999999";
            this.tooltip.style.pointerEvents = "none";
            this.tooltip.style.margin = "0";

            const tooltipWidth = this.tooltip.offsetWidth || 240;
            const tooltipHeight = this.tooltip.offsetHeight || 140;

            let tooltipX = clientX + 18;
            let tooltipY = clientY - (tooltipHeight / 2);

            if (tooltipX + tooltipWidth > window.innerWidth - 16) {
                tooltipX = clientX - tooltipWidth - 18;
            }
            if (tooltipX < 12) {
                tooltipX = 12;
            }

            if (tooltipY + tooltipHeight > window.innerHeight - 12) {
                tooltipY = window.innerHeight - tooltipHeight - 12;
            }
            if (tooltipY < 12) {
                tooltipY = 12;
            }

            this.tooltip.style.left = `${Math.round(tooltipX)}px`;
            this.tooltip.style.top = `${Math.round(tooltipY)}px`;
            this.tooltip.style.transform = "none";
        }
    }

    _handlePointerLeave() {
        if (this.crosshairGroup) this.crosshairGroup.style.display = "none";
        if (this.tooltip) this.tooltip.style.display = "none";
    }

    exportAsImage(customFilename, meta = {}) {
        const data = this.filteredTimeline;
        if (!data || data.length === 0) {
            alert("No chart data available to export.");
            return;
        }

        const W = 1920;
        const H = 1080;
        const canvas = document.createElement("canvas");
        canvas.width = W;
        canvas.height = H;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        ctx.fillStyle = "#0c0d12";
        ctx.fillRect(0, 0, W, H);

        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineWidth = 2;
        ctx.strokeRect(1, 1, W - 2, H - 2);

        ctx.fillStyle = "rgba(255, 255, 255, 0.02)";
        ctx.fillRect(40, 30, W - 80, 95);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
        ctx.strokeRect(40, 30, W - 80, 95);

        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 28px Outfit, Inter, system-ui, -apple-system, sans-serif";
        ctx.textAlign = "left";
        ctx.textBaseline = "middle";
        ctx.fillText(meta.title || "RBWR Point Progression History", 65, 65);

        ctx.fillStyle = "#9ca3af";
        ctx.font = "14px JetBrains Mono, monospace";
        const metaDate = meta.dateRange || (data.length > 0 ? `${data[0].formatted_date} - ${data[data.length - 1].formatted_date}, 2026` : "");
        ctx.fillText(`Timeline Range: ${metaDate}   ·   Events: ${data.length.toLocaleString()}`, 65, 98);

        const padLeft = 110;
        const padRight = 80;
        const padTop = 170;
        const padBottom = 110;
        const pW = W - padLeft - padRight;
        const pH = H - padTop - padBottom;
        const pBaseY = padTop + pH;

        const viewMinY = this.viewMinY !== null ? this.viewMinY : this.baseMinY;
        const viewMaxY = this.viewMaxY !== null ? this.viewMaxY : this.baseMaxY;
        const spanY = Math.max(1, viewMaxY - viewMinY);

        const yTicks = 6;
        for (let i = 0; i <= yTicks; i++) {
            const val = viewMinY + (spanY / yTicks) * i;
            const y = pBaseY - (pH * (i / yTicks));

            ctx.strokeStyle = i === 0 ? "rgba(255, 255, 255, 0.12)" : "rgba(255, 255, 255, 0.04)";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(padLeft, y);
            ctx.lineTo(padLeft + pW, y);
            ctx.stroke();

            ctx.fillStyle = "#6b7280";
            ctx.font = "14px JetBrains Mono, monospace";
            ctx.textAlign = "right";
            ctx.textBaseline = "middle";
            ctx.fillText(this._formatPoints(val), padLeft - 16, y);
        }

        const viewMinEpoch = this.viewMinEpoch !== null ? this.viewMinEpoch : data[0].timestamp_epoch;
        const viewMaxEpoch = this.viewMaxEpoch !== null ? this.viewMaxEpoch : data[data.length - 1].timestamp_epoch;
        const spanEpoch = Math.max(1, viewMaxEpoch - viewMinEpoch);

        const pts1 = [];
        const pts2 = [];
        for (let i = 0; i < data.length; i++) {
            const d = data[i];
            const ratioX = (d.timestamp_epoch - viewMinEpoch) / spanEpoch;
            const x = padLeft + (pW * ratioX);
            const ratioY1 = (d.u1 - viewMinY) / spanY;
            const ratioY2 = (d.u2 - viewMinY) / spanY;
            const y1 = pBaseY - (pH * ratioY1);
            const y2 = pBaseY - (pH * ratioY2);
            pts1.push({ x, y: y1 });
            pts2.push({ x, y: y2 });
        }

        const xTicks = 8;
        for (let i = 0; i < xTicks; i++) {
            const tickRatio = i / (xTicks - 1);
            const tickEpoch = viewMinEpoch + (spanEpoch * tickRatio);
            const x = padLeft + (pW * tickRatio);

            ctx.fillStyle = "#6b7280";
            ctx.font = "14px JetBrains Mono, monospace";
            ctx.textAlign = i === 0 ? "left" : (i === xTicks - 1 ? "right" : "middle");
            ctx.textBaseline = "top";
            ctx.fillText(this._formatXTick(tickEpoch, spanEpoch), x, pBaseY + 16);
        }

        ctx.save();
        ctx.beginPath();
        ctx.rect(padLeft, padTop, pW, pH);
        ctx.clip();

        if (this.showArea && pts1.length > 0) {
            ctx.fillStyle = "rgba(82, 148, 226, 0.12)";
            ctx.beginPath();
            ctx.moveTo(pts1[0].x, pts1[0].y);
            for (let i = 1; i < pts1.length; i++) ctx.lineTo(pts1[i].x, pts1[i].y);
            ctx.lineTo(pts1[pts1.length - 1].x, pBaseY);
            ctx.lineTo(pts1[0].x, pBaseY);
            ctx.closePath();
            ctx.fill();
        }

        if (this.showArea && pts2.length > 0) {
            ctx.fillStyle = "rgba(240, 113, 93, 0.10)";
            ctx.beginPath();
            ctx.moveTo(pts2[0].x, pts2[0].y);
            for (let i = 1; i < pts2.length; i++) ctx.lineTo(pts2[i].x, pts2[i].y);
            ctx.lineTo(pts2[pts2.length - 1].x, pBaseY);
            ctx.lineTo(pts2[0].x, pBaseY);
            ctx.closePath();
            ctx.fill();
        }

        if (this.showU1 && pts1.length > 0) {
            ctx.strokeStyle = "#5294e2";
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(pts1[0].x, pts1[0].y);
            for (let i = 1; i < pts1.length; i++) ctx.lineTo(pts1[i].x, pts1[i].y);
            ctx.stroke();
        }

        if (this.showU2 && pts2.length > 0) {
            ctx.strokeStyle = "#f0715d";
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(pts2[0].x, pts2[0].y);
            for (let i = 1; i < pts2.length; i++) ctx.lineTo(pts2[i].x, pts2[i].y);
            ctx.stroke();
        }

        ctx.restore();

        const dataUrl = canvas.toDataURL("image/png");
        const a = document.createElement("a");
        a.href = dataUrl;
        a.download = customFilename || "rbwr-point-history.png";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}
