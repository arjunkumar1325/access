/**
 * AccessAI — Intelligent Accessible Route Planning
 * Interactive Leaflet Mapping, Accessible Routing, Barrier Reporting, and Real Geocoding
 */

(function () {
    'use strict';

    // 1. Configuration & Global State
    let config = {
        centerLat: 12.9716,
        centerLon: 77.5946,
        areaName: 'Cubbon Park & Central Campus, Bengaluru',
        bounds: { minLat: 12.965, maxLat: 12.978, minLon: 77.588, maxLon: 77.601 }
    };

    // Load server configuration from script block
    try {
        const configEl = document.getElementById('accessai-config-data');
        if (configEl && configEl.textContent.trim()) {
            const parsed = JSON.parse(configEl.textContent);
            config = { ...config, ...parsed };
        }
    } catch (e) {
        console.warn('Using default coordinates configuration:', e);
    }

    // State Variables
    let map = null;
    let startMarker = null;
    let endMarker = null;
    let accessibleRouteLine = null;
    let shortestRouteLine = null;
    let barriersLayer = L.layerGroup();
    let currentPickTarget = null; // 'start', 'end', or 'barrier'
    let currentBarriers = [];
    let currentRouteStart = null;
    let currentRouteEnd = null;
    let currentRouteMode = 'accessible'; // 'accessible' or 'shortest'
    let lastRouteData = null; // cache of last calculated route for instant mode toggling
    let activeAccessProfile = 'wheelchair'; // 'wheelchair' or 'low-vision'
    let userGpsMarker = null;
    let userGpsCircle = null;
    let gpsWatchId = null;
    let isNavigating = false;
    let currentNavStepIndex = 0;
    let currentNavSteps = [];

    // Preset Campus Demo Coordinates (for optional Demo Mode only)
    const cLat = config.centerLat;
    const cLon = config.centerLon;
    const DEMO_PRESETS = {
        'preset-1': {
            name: 'East Gate → Central Library',
            start: [cLat - 0.0025, cLon + 0.0035],
            end: [cLat + 0.0020, cLon - 0.0025]
        },
        'preset-2': {
            name: 'Science Block → Cafeteria',
            start: [cLat + 0.0018, cLon + 0.0015],
            end: [cLat - 0.0022, cLon - 0.0018]
        },
        'preset-3': {
            name: 'Sports Complex → Admin Building',
            start: [cLat - 0.0030, cLon - 0.0020],
            end: [cLat + 0.0025, cLon + 0.0020]
        }
    };

    // ==========================================================================
    // 2. Map Initialization
    // ==========================================================================
    function initMap() {
        map = L.map('map', {
            center: [config.centerLat, config.centerLon],
            zoom: 16,
            zoomControl: true
        });

        // OpenStreetMap Tile Layer with Attribution & graceful network error handling
        const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors | AccessAI'
        }).addTo(map);

        tileLayer.on('tileerror', function () {
            console.warn('OpenStreetMap tile could not be loaded. Please verify your internet connection.');
        });

        barriersLayer.addTo(map);

        // Map Click Listener for interactive point picking
        map.on('click', handleMapClick);

        // Load active community barriers and map info
        fetchMapInfo();
        fetchBarriers();
    }

    async function fetchMapInfo() {
        try {
            const resp = await fetch('/api/map-info');
            const data = await resp.json();
            if (data && data.success) {
                config.areaName = data.area_name;
                config.bounds = data.bounds;
                config.centerLat = data.center.lat;
                config.centerLon = data.center.lon;

                const nameEl = document.getElementById('coverage-area-name');
                if (nameEl) nameEl.textContent = data.area_name;
            }
        } catch (e) {
            console.warn('Could not fetch map info:', e);
        }
    }

    // Custom HTML Pin Markers
    function createPinIcon(type, label) {
        return L.divIcon({
            className: `custom-map-marker marker-${type}`,
            iconSize: [32, 32],
            iconAnchor: [16, 32],
            popupAnchor: [0, -32],
            html: `
                ${type === 'barrier' ? '<div class="barrier-pulse-halo"></div>' : ''}
                <div class="marker-pin">
                    <span class="marker-pin-inner">${label}</span>
                </div>
            `
        });
    }

    // ==========================================================================
    // 3. Real Geocoding & Coordinate Parsing
    // ==========================================================================
    function parseCoordString(str) {
        if (!str || typeof str !== 'string') return null;
        const parts = str.split(',').map(s => s.trim());
        if (parts.length === 2) {
            const lat = parseFloat(parts[0]);
            const lon = parseFloat(parts[1]);
            if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                return [lat, lon];
            }
        }
        return null;
    }

    async function resolveLocation(inputVal) {
        const directCoords = parseCoordString(inputVal);
        if (directCoords) {
            return {
                coords: directCoords,
                name: `${directCoords[0].toFixed(5)}, ${directCoords[1].toFixed(5)}`,
                in_bounds: isPointWithinBounds(directCoords[0], directCoords[1])
            };
        }

        // Real Nominatim geocoding via compliant backend proxy
        try {
            showLoading(true, `Searching location "${inputVal}"...`);
            const url = `/api/geocode?q=${encodeURIComponent(inputVal)}`;
            const resp = await fetch(url);
            const data = await resp.json();

            if (data && data.success && data.results && data.results.length > 0) {
                const best = data.results[0];
                return {
                    coords: [best.lat, best.lon],
                    name: best.display_name,
                    in_bounds: best.in_graph_bounds
                };
            }
        } catch (e) {
            console.warn('Geocoding request failed:', e);
        } finally {
            showLoading(false);
        }

        return null;
    }

    function isPointWithinBounds(lat, lon) {
        const b = config.bounds;
        if (!b) return true;
        // Adding generous padding (~400m = ~0.0035 degrees) for initial quick client check
        const pad = 0.004;
        return (
            lat >= b.minLat - pad &&
            lat <= b.maxLat + pad &&
            lon >= b.minLon - pad &&
            lon <= b.maxLon + pad
        );
    }

    // Autocomplete Suggestions Dropdown
    function setupAutocomplete(inputId, dropdownId, onSelect) {
        const input = document.getElementById(inputId);
        const dropdown = document.getElementById(dropdownId);
        let debounceTimer = null;

        input.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            const query = input.value.trim();

            if (query.length < 3 || parseCoordString(query)) {
                dropdown.classList.add('hidden');
                dropdown.innerHTML = '';
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const resp = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
                    const data = await resp.json();
                    dropdown.innerHTML = '';

                    if (data && data.success && data.results && data.results.length > 0) {
                        data.results.forEach(item => {
                            const div = document.createElement('div');
                            div.className = 'suggestion-item';
                            const badgeClass = item.in_graph_bounds ? 'badge-in-bounds' : 'badge-dynamic-bounds';
                            const badgeText = item.in_graph_bounds ? '✓ Local Campus' : '🌐 Dynamic Route';

                            div.innerHTML = `
                                <span class="suggestion-name">${escapeHtml(item.display_name.split(',')[0])}</span>
                                <span class="suggestion-sub">
                                    <span>${escapeHtml(item.display_name.substring(0, 45))}...</span>
                                    <span class="${badgeClass}">${badgeText}</span>
                                </span>
                            `;

                            div.addEventListener('click', () => {
                                input.value = item.display_name;
                                dropdown.classList.add('hidden');
                                onSelect([item.lat, item.lon], item);
                            });

                            dropdown.appendChild(div);
                        });
                        dropdown.classList.remove('hidden');
                    } else {
                        dropdown.classList.add('hidden');
                    }
                } catch (err) {
                    console.warn('Autocomplete fetch error:', err);
                }
            }, 350);
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!input.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.classList.add('hidden');
            }
        });
    }

    // ==========================================================================
    // 4. Map Click & Point Picking
    // ==========================================================================
    function setPickingMode(target) {
        currentPickTarget = target;
        const banner = document.getElementById('picking-mode-banner');
        const text = document.getElementById('picking-mode-text');
        const pickStartBtn = document.getElementById('btn-pick-start');
        const pickEndBtn = document.getElementById('btn-pick-end');

        pickStartBtn.classList.remove('active');
        pickEndBtn.classList.remove('active');

        if (target) {
            banner.classList.remove('hidden');
            if (target === 'start') {
                text.textContent = '📍 Click on the map to set Start location (A)';
                pickStartBtn.classList.add('active');
            } else if (target === 'end') {
                text.textContent = '📍 Click on the map to set Destination (B)';
                pickEndBtn.classList.add('active');
            } else if (target === 'barrier') {
                text.textContent = '⚠️ Click on the map to set Barrier obstacle spot';
            }
        } else {
            banner.classList.add('hidden');
        }
    }

    function handleMapClick(e) {
        const lat = parseFloat(e.latlng.lat.toFixed(6));
        const lon = parseFloat(e.latlng.lng.toFixed(6));

        if (currentPickTarget === 'start') {
            setStartLocation([lat, lon]);
            setPickingMode(null);
            clearErrorBanner();
        } else if (currentPickTarget === 'end') {
            setEndLocation([lat, lon]);
            setPickingMode(null);
            clearErrorBanner();
        } else if (currentPickTarget === 'barrier') {
            document.getElementById('barrier-lat').value = lat;
            document.getElementById('barrier-lon').value = lon;
            setPickingMode(null);
            document.getElementById('barrier-modal').showModal();
        }
    }

    function setStartLocation(coords) {
        const val = `${coords[0].toFixed(5)}, ${coords[1].toFixed(5)}`;
        document.getElementById('start-input').value = val;
        currentRouteStart = coords;

        if (startMarker) map.removeLayer(startMarker);
        startMarker = L.marker(coords, {
            icon: createPinIcon('start', 'A'),
            draggable: true
        }).addTo(map);

        startMarker.bindTooltip('Start Location (A) - Drag to adjust', { permanent: false, direction: 'top' });
        startMarker.on('dragend', function (ev) {
            const pos = ev.target.getLatLng();
            const newCoords = [pos.lat, pos.lng];
            document.getElementById('start-input').value = `${newCoords[0].toFixed(5)}, ${newCoords[1].toFixed(5)}`;
            currentRouteStart = newCoords;
            if (document.getElementById('end-input').value.trim()) {
                calculateRoute();
            }
        });
    }

    function setEndLocation(coords) {
        const val = `${coords[0].toFixed(5)}, ${coords[1].toFixed(5)}`;
        document.getElementById('end-input').value = val;
        currentRouteEnd = coords;

        if (endMarker) map.removeLayer(endMarker);
        endMarker = L.marker(coords, {
            icon: createPinIcon('end', 'B'),
            draggable: true
        }).addTo(map);

        endMarker.bindTooltip('Destination (B) - Drag to adjust', { permanent: false, direction: 'top' });
        endMarker.on('dragend', function (ev) {
            const pos = ev.target.getLatLng();
            const newCoords = [pos.lat, pos.lng];
            document.getElementById('end-input').value = `${newCoords[0].toFixed(5)}, ${newCoords[1].toFixed(5)}`;
            currentRouteEnd = newCoords;
            if (document.getElementById('start-input').value.trim()) {
                calculateRoute();
            }
        });
    }

    // ==========================================================================
    // 5. Accessible Route Calculation
    // ==========================================================================
    async function calculateRoute() {
        clearErrorBanner();

        const startVal = document.getElementById('start-input').value.trim();
        const endVal = document.getElementById('end-input').value.trim();

        if (!startVal) {
            showErrorBanner('Missing Location', 'Please enter a Start location (place name or coordinates).');
            document.getElementById('start-input').focus();
            return;
        }
        if (!endVal) {
            showErrorBanner('Missing Location', 'Please enter a Destination (place name or coordinates).');
            document.getElementById('end-input').focus();
            return;
        }

        showLoading(true, 'Resolving locations and calculating accessible route...');

        try {
            const startResult = await resolveLocation(startVal);
            const endResult = await resolveLocation(endVal);

            if (!startResult) {
                showErrorBanner(
                    'Location Not Found',
                    `Could not locate "${startVal}". Please check the spelling, enter coordinates, or click the map pin.`
                );
                return;
            }
            if (!endResult) {
                showErrorBanner(
                    'Location Not Found',
                    `Could not locate "${endVal}". Please check the spelling, enter coordinates, or click the map pin.`
                );
                return;
            }

            const startCoords = startResult.coords;
            const endCoords = endResult.coords;

            setStartLocation(startCoords);
            setEndLocation(endCoords);

            currentRouteStart = startCoords;
            currentRouteEnd = endCoords;

            const response = await fetch('/api/route', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start: startCoords,
                    end: endCoords,
                    mode: currentRouteMode
                })
            });

            const data = await response.json();

            if (!response.ok || !data.success) {
                lastRouteData = null;
                handleRoutingError(data);
                return;
            }

            lastRouteData = data;
            renderRouteResults(data);
        } catch (err) {
            showErrorBanner('Routing Error', err.message);
        } finally {
            showLoading(false);
        }
    }

    function setRouteMode(mode) {
        currentRouteMode = mode;

        const btnAcc = document.getElementById('btn-mode-accessible');
        const btnShort = document.getElementById('btn-mode-shortest');
        const btnSelSafest = document.getElementById('btn-select-safest');
        const btnSelShortest = document.getElementById('btn-select-shortest');
        const findBtn = document.getElementById('btn-find-route');

        const isAcc = (mode === 'accessible');

        if (btnAcc) {
            btnAcc.classList.toggle('active', isAcc);
            btnAcc.setAttribute('aria-checked', isAcc ? 'true' : 'false');
        }
        if (btnShort) {
            btnShort.classList.toggle('active', !isAcc);
            btnShort.setAttribute('aria-checked', !isAcc ? 'true' : 'false');
        }

        if (btnSelSafest) {
            btnSelSafest.classList.toggle('active', isAcc);
            btnSelSafest.setAttribute('aria-checked', isAcc ? 'true' : 'false');
        }
        if (btnSelShortest) {
            btnSelShortest.classList.toggle('active', !isAcc);
            btnSelShortest.setAttribute('aria-checked', !isAcc ? 'true' : 'false');
        }

        if (findBtn) {
            findBtn.innerHTML = `
                <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none">
                    <polygon points="3 11 22 2 13 21 11 13 3 11"></polygon>
                </svg>
                <span>${isAcc ? 'Find Accessible Route' : 'Find Shortest Route'}</span>
            `;
        }

        if (lastRouteData) {
            renderRouteResults(lastRouteData);
        }
    }

    function setAccessProfile(profile) {
        activeAccessProfile = profile;
        const chipWheelchair = document.getElementById('chip-mode-wheelchair');
        const chipLowVision = document.getElementById('chip-mode-low-vision');
        const routeHeading = document.getElementById('route-heading');
        const speedBasis = document.getElementById('route-speed-basis');

        if (profile === 'low-vision') {
            if (chipLowVision) {
                chipLowVision.classList.add('active');
                chipLowVision.setAttribute('aria-checked', 'true');
            }
            if (chipWheelchair) {
                chipWheelchair.classList.remove('active');
                chipWheelchair.setAttribute('aria-checked', 'false');
            }
            document.body.classList.add('low-vision-mode');
            if (routeHeading) {
                routeHeading.textContent = 'Low-vision accessible route (Prototype)';
            }
            if (speedBasis) {
                speedBasis.textContent = 'High-contrast visual aid mode with high-visibility waypoints and verbalized turns (Prototype).';
            }
        } else {
            if (chipWheelchair) {
                chipWheelchair.classList.add('active');
                chipWheelchair.setAttribute('aria-checked', 'true');
            }
            if (chipLowVision) {
                chipLowVision.classList.remove('active');
                chipLowVision.setAttribute('aria-checked', 'false');
            }
            document.body.classList.remove('low-vision-mode');
            if (routeHeading) {
                routeHeading.textContent = (currentRouteMode === 'shortest') 
                    ? 'Standard shortest walking route' 
                    : 'Wheelchair-accessible route';
            }
            if (speedBasis && lastRouteData && lastRouteData.accessible_route) {
                speedBasis.textContent = lastRouteData.accessible_route.speed_basis || 'Calculated at 1.0 m/s standard wheelchair travel pace.';
            }
        }
    }

    function handleRoutingError(data) {
        if (data.error_type === 'OUT_OF_BOUNDS') {
            const errLower = (data.error || '').toLowerCase();
            if (errLower.includes('pedestrian routing distance') || errLower.includes('apart')) {
                showErrorBanner(
                    'Location Beyond Walking Range',
                    data.error,
                    '💡 Pedestrian route calculation supports distances up to 25 km. Please choose points within a walkable reach.'
                );
            } else if (errLower.includes('nearest mapped') || errLower.includes('footpath') || errLower.includes('away from')) {
                showErrorBanner(
                    'No Mapped Footpath Nearby',
                    data.error,
                    '💡 The selected location is far from any mapped pedestrian path or sidewalk. Please click closer to an accessible walkway or road.'
                );
            } else {
                showErrorBanner(
                    'Location Outside Map Coverage',
                    data.error,
                    `💡 Dynamic loading is active for all walkable areas. Please verify your selected points.`
                );
            }
        } else if (data.error_type === 'COVERAGE_ERROR') {
            showErrorBanner(
                'Map Coverage Error',
                data.error,
                '💡 Could not download the walking network for this area from OpenStreetMap. Please verify your internet connection or try another location.'
            );
        } else if (data.error_type === 'DISCONNECTED_NETWORK') {
            showErrorBanner(
                'Disconnected Pedestrian Network',
                data.error,
                '💡 The selected points appear to be separated by fences, highways, or unmapped sections. Please choose a spot on an adjacent open walkway.'
            );
        } else {
            showErrorBanner('Routing Error', data.error || 'Failed to calculate route.');
        }

        // Hide old results and restore welcome panel
        document.getElementById('route-results').classList.add('hidden');
        const welcomePanel = document.getElementById('welcome-panel');
        if (welcomePanel) welcomePanel.classList.remove('hidden');

        if (accessibleRouteLine) map.removeLayer(accessibleRouteLine);
        if (shortestRouteLine) map.removeLayer(shortestRouteLine);
    }

    function showErrorBanner(title, message, advice = '') {
        const banner = document.getElementById('route-error-banner');
        document.getElementById('route-error-title').textContent = title;
        document.getElementById('route-error-msg').textContent = message;
        const adviceEl = document.getElementById('route-error-advice');
        if (advice) {
            adviceEl.textContent = advice;
            adviceEl.classList.remove('hidden');
        } else {
            adviceEl.classList.add('hidden');
        }
        banner.classList.remove('hidden');
    }

    function clearErrorBanner() {
        const banner = document.getElementById('route-error-banner');
        if (banner) banner.classList.add('hidden');
    }

    function renderRouteResults(data) {
        clearErrorBanner();

        // Clear old route lines
        if (accessibleRouteLine) map.removeLayer(accessibleRouteLine);
        if (shortestRouteLine) map.removeLayer(shortestRouteLine);

        const accRoute = data.accessible_route;
        const shortRoute = data.shortest_route;
        const isShortestMode = (currentRouteMode === 'shortest');

        // Update Heading matching requirement: Wheelchair-accessible route or Low-vision prototype
        const routeHeading = document.getElementById('route-heading');
        const routeStatusBadge = document.getElementById('route-subtitle-status');
        if (routeHeading) {
            if (activeAccessProfile === 'low-vision') {
                routeHeading.textContent = 'Low-vision accessible route (Prototype)';
            } else if (isShortestMode) {
                routeHeading.textContent = 'Standard shortest walking route';
            } else {
                routeHeading.textContent = 'Wheelchair-accessible route';
            }
        }
        if (routeStatusBadge) {
            let statusText = isShortestMode 
                ? 'Direct Path (May include stairs / obstacles)' 
                : 'Verified Accessible Network';
            if (data.area_info && data.area_info.source === 'osm_dynamic_download') {
                statusText += ' • 🌐 Dynamic OSM Network';
            } else if (data.area_info && (data.area_info.source === 'disk_cache' || data.area_info.source === 'memory_cache')) {
                statusText += ' • ⚡ Dynamic Cache';
            }
            routeStatusBadge.textContent = statusText;
        }


        // Synchronize Route Choice Buttons (Safest vs Shortest)
        const btnSelSafest = document.getElementById('btn-select-safest');
        const btnSelShortest = document.getElementById('btn-select-shortest');
        if (btnSelSafest && btnSelShortest) {
            btnSelSafest.classList.toggle('active', !isShortestMode);
            btnSelSafest.setAttribute('aria-checked', !isShortestMode ? 'true' : 'false');
            btnSelShortest.classList.toggle('active', isShortestMode);
            btnSelShortest.setAttribute('aria-checked', isShortestMode ? 'true' : 'false');
        }

        // 1. Draw Shortest Route (comparison or primary)
        if (shortRoute && shortRoute.coordinates && shortRoute.coordinates.length > 0) {
            shortestRouteLine = L.polyline(shortRoute.coordinates, {
                color: '#f59e0b',
                weight: isShortestMode ? 6 : 3.5,
                dashArray: isShortestMode ? null : '6, 8',
                opacity: isShortestMode ? 0.95 : 0.7
            }).addTo(map);
            shortestRouteLine.bindTooltip('Standard Shortest Route (may include stairs)', { sticky: true });
        }

        // 2. Draw Accessible Route (prominent green polyline or comparison)
        if (accRoute && accRoute.coordinates && accRoute.coordinates.length > 0) {
            accessibleRouteLine = L.polyline(accRoute.coordinates, {
                color: '#10b981',
                weight: isShortestMode ? 3.5 : 6,
                dashArray: isShortestMode ? '6, 8' : null,
                opacity: isShortestMode ? 0.7 : 0.95
            }).addTo(map);
            accessibleRouteLine.bindTooltip('Accessible Wheelchair Route', { sticky: true });

            if (isShortestMode && shortestRouteLine) {
                shortestRouteLine.bringToFront();
            } else {
                accessibleRouteLine.bringToFront();
            }

            // Fit map to show active route and markers
            const activeLine = isShortestMode ? (shortestRouteLine || accessibleRouteLine) : accessibleRouteLine;
            const group = new L.featureGroup([activeLine, startMarker, endMarker]);
            map.fitBounds(group.getBounds(), { padding: [40, 40] });
        }

        // 3. Update Sidebar Cards and Active Selection State
        const welcomePanel = document.getElementById('welcome-panel');
        if (welcomePanel) welcomePanel.classList.add('hidden');
        document.getElementById('route-results').classList.remove('hidden');

        const cardAcc = document.getElementById('card-accessible');
        const cardShort = document.getElementById('card-shortest');
        if (cardAcc && cardShort) {
            if (isShortestMode) {
                cardShort.classList.add('active');
                cardAcc.classList.remove('active');
            } else {
                cardAcc.classList.add('active');
                cardShort.classList.remove('active');
            }
        }

        // Accessible Card Stats
        document.getElementById('accessible-time').textContent = accRoute.duration_minutes ? `${accRoute.duration_minutes} min` : 'Unavailable';
        document.getElementById('accessible-distance').textContent = (accRoute.distance_meters != null) ? formatDistance(accRoute.distance_meters) : 'Unavailable';

        const stairsAvoided = Math.max(0, (shortRoute.steps_count || 0) - (accRoute.steps_count || 0));
        const stairsEl = document.getElementById('accessible-stairs');
        if (stairsEl) {
            if (shortRoute.steps_count > 0 && accRoute.steps_count === 0) {
                stairsEl.textContent = `${stairsAvoided} Stairs Avoided`;
            } else if (accRoute.steps_count > 0) {
                stairsEl.textContent = `${accRoute.steps_count} Steps along path`;
            } else {
                stairsEl.textContent = '0 Steps (Step-free)';
            }
        }

        // Speed Basis
        const speedBasisEl = document.getElementById('route-speed-basis');
        if (speedBasisEl) {
            if (activeAccessProfile === 'low-vision') {
                speedBasisEl.textContent = 'High-contrast visual aid mode with high-visibility waypoints and verbalized turns (Prototype).';
            } else {
                speedBasisEl.textContent = accRoute.speed_basis || 'Calculated at 1.0 m/s standard wheelchair travel pace.';
            }
        }

        // Reasons Explanation
        const reasonsContainer = document.getElementById('route-reasons-list');
        reasonsContainer.innerHTML = '';
        if (data.reasons && data.reasons.length > 0) {
            data.reasons.forEach(reason => {
                const item = document.createElement('div');
                item.textContent = '✓ ' + reason;
                reasonsContainer.appendChild(item);
            });
        }

        // Shortest Card Stats
        document.getElementById('shortest-distance').textContent = (shortRoute.distance_meters != null) ? formatDistance(shortRoute.distance_meters) : 'Unavailable';
        document.getElementById('shortest-stairs').textContent = `${shortRoute.steps_count || 0} Steps`;

        const hazardPill = document.getElementById('shortest-hazard-pill');
        if (shortRoute.steps_count > 0) {
            hazardPill.textContent = `${shortRoute.steps_count} Flight(s) of Steps`;
            hazardPill.className = 'route-pill pill-amber';
        } else {
            hazardPill.textContent = 'No Mapped Steps';
            hazardPill.className = 'route-pill pill-green';
        }

        // Warnings List
        const warningsList = document.getElementById('warnings-list');
        warningsList.innerHTML = '';
        if (data.warnings && data.warnings.length > 0) {
            data.warnings.forEach(warn => {
                const li = document.createElement('li');
                li.textContent = warn;
                warningsList.appendChild(li);
            });
        }
    }

    function formatDistance(meters) {
        if (!meters || isNaN(meters)) return '0 m';
        if (meters >= 1000) {
            return `${(meters / 1000).toFixed(2)} km`;
        }
        return `${Math.round(meters)} m`;
    }

    function clearRoute() {
        stopNavigation();

        if (accessibleRouteLine) map.removeLayer(accessibleRouteLine);
        if (shortestRouteLine) map.removeLayer(shortestRouteLine);
        if (startMarker) map.removeLayer(startMarker);
        if (endMarker) map.removeLayer(endMarker);

        accessibleRouteLine = null;
        shortestRouteLine = null;
        startMarker = null;
        endMarker = null;
        currentRouteStart = null;
        currentRouteEnd = null;
        lastRouteData = null;

        document.getElementById('start-input').value = '';
        document.getElementById('end-input').value = '';
        const demoSelect = document.getElementById('demo-presets');
        if (demoSelect) demoSelect.value = '';
        document.getElementById('route-results').classList.add('hidden');
        const welcomePanel = document.getElementById('welcome-panel');
        if (welcomePanel) welcomePanel.classList.remove('hidden');

        clearErrorBanner();
        setPickingMode(null);

        map.setView([config.centerLat, config.centerLon], 16);
    }

    // ==========================================================================
    // 5B. Step-by-Step Navigation & GPS Tracking
    // ==========================================================================
    function getTurnIconSvg(direction) {
        switch (direction) {
            case 'right':
            case 'slight_right':
            case 'sharp_right':
                return `<svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" stroke-width="2.5" fill="none"><polyline points="9 6 18 6 18 15"></polyline><path d="M6 18c0-6.627 5.373-12 12-12"></path></svg>`;
            case 'left':
            case 'slight_left':
            case 'sharp_left':
                return `<svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" stroke-width="2.5" fill="none"><polyline points="15 6 6 6 6 15"></polyline><path d="M18 18c0-6.627-5.373-12-12-12"></path></svg>`;
            case 'u_turn':
                return `<svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" stroke-width="2.5" fill="none"><path d="M18 18V8a5 5 0 0 0-10 0v10"></path><polyline points="14 14 8 20 2 14"></polyline></svg>`;
            case 'arrive':
                return `<svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" stroke-width="2.5" fill="none"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`;
            case 'depart':
            case 'straight':
            default:
                return `<svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" stroke-width="2.5" fill="none"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>`;
        }
    }

    function buildFallbackGuidanceSteps(coords) {
        if (!coords || coords.length === 0) return [];
        if (coords.length === 1) {
            return [{
                step_number: 1,
                instruction: "Proceed to destination",
                direction: "arrive",
                distance_meters: 0,
                coords: coords[0]
            }];
        }
        return [
            {
                step_number: 1,
                instruction: "Depart along accessible pathway",
                direction: "depart",
                distance_meters: 50,
                coords: coords[0]
            },
            {
                step_number: 2,
                instruction: "Follow designated accessible corridor",
                direction: "straight",
                distance_meters: 100,
                coords: coords[Math.floor(coords.length / 2)]
            },
            {
                step_number: 3,
                instruction: "Arrive at destination",
                direction: "arrive",
                distance_meters: 0,
                coords: coords[coords.length - 1]
            }
        ];
    }

    function startNavigation() {
        if (!lastRouteData) {
            alert('Please calculate an accessible route first before starting navigation.');
            return;
        }

        const route = (currentRouteMode === 'shortest') 
            ? lastRouteData.shortest_route 
            : lastRouteData.accessible_route;

        if (!route || !route.coordinates || route.coordinates.length < 2) {
            alert('No valid route path available for navigation.');
            return;
        }

        currentNavSteps = (route.guidance_steps && route.guidance_steps.length > 0) 
            ? route.guidance_steps 
            : buildFallbackGuidanceSteps(route.coordinates);

        currentNavStepIndex = 0;
        isNavigating = true;

        const overlay = document.getElementById('nav-turn-overlay');
        if (overlay) overlay.classList.remove('hidden');

        updateNavStepView();
        startGpsTracking();
    }

    function stopNavigation() {
        isNavigating = false;
        stopGpsTracking();

        const overlay = document.getElementById('nav-turn-overlay');
        if (overlay) overlay.classList.add('hidden');

        if (lastRouteData) {
            const activeLine = (currentRouteMode === 'shortest') 
                ? (shortestRouteLine || accessibleRouteLine) 
                : (accessibleRouteLine || shortestRouteLine);
            if (activeLine && startMarker && endMarker) {
                const group = new L.featureGroup([activeLine, startMarker, endMarker]);
                map.fitBounds(group.getBounds(), { padding: [40, 40] });
            }
        }
    }

    function updateNavStepView() {
        if (!currentNavSteps || currentNavSteps.length === 0) return;

        if (currentNavStepIndex < 0) currentNavStepIndex = 0;
        if (currentNavStepIndex >= currentNavSteps.length) {
            currentNavStepIndex = currentNavSteps.length - 1;
        }

        const step = currentNavSteps[currentNavStepIndex];

        const instructionEl = document.getElementById('nav-step-instruction');
        const distanceEl = document.getElementById('nav-step-distance');
        const indexEl = document.getElementById('nav-current-step-index');
        const iconBox = document.getElementById('nav-step-icon');

        if (instructionEl) instructionEl.textContent = step.instruction;
        if (distanceEl) {
            if (step.direction === 'arrive') {
                distanceEl.textContent = 'Destination reached';
            } else if (step.distance_meters > 0) {
                distanceEl.textContent = `In ${Math.round(step.distance_meters)} meters`;
            } else {
                distanceEl.textContent = 'At current waypoint';
            }
        }
        if (indexEl) {
            indexEl.textContent = `Step ${currentNavStepIndex + 1} of ${currentNavSteps.length}`;
        }

        if (iconBox) {
            iconBox.innerHTML = getTurnIconSvg(step.direction);
        }

        if (step.coords && step.coords.length === 2) {
            map.panTo(step.coords, { animate: true });
        }
    }

    function nextNavStep() {
        if (currentNavStepIndex < currentNavSteps.length - 1) {
            currentNavStepIndex++;
            updateNavStepView();
        } else {
            alert('You have reached your destination!');
        }
    }

    function prevNavStep() {
        if (currentNavStepIndex > 0) {
            currentNavStepIndex--;
            updateNavStepView();
        }
    }

    function startGpsTracking() {
        const gpsIndicator = document.getElementById('nav-gps-indicator');

        if (!navigator.geolocation) {
            if (gpsIndicator) gpsIndicator.textContent = 'Manual Navigation (GPS not supported)';
            return;
        }

        if (gpsIndicator) gpsIndicator.textContent = 'Requesting GPS access...';

        gpsWatchId = navigator.geolocation.watchPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                const accuracy = Math.round(pos.coords.accuracy || 0);

                if (gpsIndicator) {
                    gpsIndicator.textContent = `GPS Active (±${accuracy}m accuracy)`;
                }

                if (!userGpsMarker) {
                    userGpsMarker = L.circleMarker([lat, lon], {
                        radius: 8,
                        color: '#ffffff',
                        weight: 2,
                        fillColor: '#3b82f6',
                        fillOpacity: 0.95
                    }).addTo(map);
                    userGpsMarker.bindTooltip('Your Current Location', { permanent: false });
                } else {
                    userGpsMarker.setLatLng([lat, lon]);
                }

                if (!userGpsCircle) {
                    userGpsCircle = L.circle([lat, lon], {
                        radius: accuracy,
                        color: '#3b82f6',
                        weight: 1,
                        fillColor: '#3b82f6',
                        fillOpacity: 0.15
                    }).addTo(map);
                } else {
                    userGpsCircle.setLatLng([lat, lon]);
                    userGpsCircle.setRadius(accuracy);
                }

                // Check distance to current navigation waypoint
                if (isNavigating && currentNavSteps && currentNavSteps[currentNavStepIndex]) {
                    const target = currentNavSteps[currentNavStepIndex].coords;
                    if (target && target.length === 2) {
                        const distToStep = map.distance([lat, lon], target);
                        if (distToStep < 15 && currentNavStepIndex < currentNavSteps.length - 1) {
                            currentNavStepIndex++;
                            updateNavStepView();
                        }
                    }
                }
            },
            (err) => {
                console.warn('Geolocation access error:', err);
                if (gpsIndicator) {
                    gpsIndicator.textContent = 'Manual Navigation Mode (Location permission not granted)';
                }
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 }
        );
    }

    function stopGpsTracking() {
        if (gpsWatchId !== null && navigator.geolocation) {
            navigator.geolocation.clearWatch(gpsWatchId);
            gpsWatchId = null;
        }
        if (userGpsMarker) {
            map.removeLayer(userGpsMarker);
            userGpsMarker = null;
        }
        if (userGpsCircle) {
            map.removeLayer(userGpsCircle);
            userGpsCircle = null;
        }
    }

    // ==========================================================================
    // 5C. Safety Details Modal
    // ==========================================================================
    function openSafetyDetails() {
        if (!lastRouteData) {
            alert('Please calculate an accessible route first to view its safety verification details.');
            return;
        }

        const data = lastRouteData;
        const accRoute = data.accessible_route;
        const shortRoute = data.shortest_route;

        // 1. Route Selection Rationale
        const rationaleList = document.getElementById('safety-rationale-list');
        if (rationaleList) {
            rationaleList.innerHTML = '';
            if (data.reasons && data.reasons.length > 0) {
                data.reasons.forEach(r => {
                    const div = document.createElement('div');
                    div.className = 'safety-rationale-item';
                    div.style.padding = '4px 0';
                    div.textContent = '✓ ' + r;
                    rationaleList.appendChild(div);
                });
            } else {
                rationaleList.textContent = 'Verified safe accessible corridor based on available OpenStreetMap tags.';
            }
        }

        // 2. Stairs Avoided Count
        const stairsAvoided = Math.max(0, (shortRoute.steps_count || 0) - (accRoute.steps_count || 0));
        const stairsCountEl = document.getElementById('safety-stairs-count');
        if (stairsCountEl) {
            if (shortRoute.steps_count > 0 && accRoute.steps_count === 0) {
                stairsCountEl.textContent = `${stairsAvoided} Steps Avoided (${shortRoute.steps_count} flight(s) on direct path)`;
            } else if (accRoute.steps_count > 0) {
                stairsCountEl.textContent = `${accRoute.steps_count} Steps on path (unavoidable in current network)`;
            } else {
                stairsCountEl.textContent = '0 Steps (Entire corridor is step-free)';
            }
        }

        // 3. Rough Surfaces Avoided Count
        const roughCountEl = document.getElementById('safety-rough-count');
        if (roughCountEl) {
            if ((accRoute.rough_surface_count || 0) === 0) {
                roughCountEl.textContent = '0 Rough Sections (Smooth paved surfaces prioritized)';
            } else {
                roughCountEl.textContent = `${accRoute.rough_surface_count} Sections with unpaved/rough surface`;
            }
        }

        // 4. Active Community Barriers
        const barriersList = document.getElementById('safety-barriers-list');
        if (barriersList) {
            barriersList.innerHTML = '';
            if (currentBarriers && currentBarriers.length > 0) {
                currentBarriers.forEach(b => {
                    const item = document.createElement('div');
                    item.className = 'safety-barrier-entry';
                    item.style.marginBottom = '6px';
                    item.innerHTML = `
                        <strong>⚠️ ${escapeHtml(b.category)}</strong>: 
                        ${escapeHtml(b.note || b.description || 'Reported obstacle')} 
                        <span class="text-xs text-muted">(${b.verification_status || 'Community reported'})</span>
                    `;
                    barriersList.appendChild(item);
                });
            } else {
                barriersList.innerHTML = '<div class="text-xs text-muted">No active community obstacles currently reported along this zone.</div>';
            }
        }

        const modal = document.getElementById('safety-modal');
        if (modal) modal.showModal();
    }

    // ==========================================================================
    // 6. Community Barrier Reporting & Layer
    // ==========================================================================
    async function fetchBarriers() {
        try {
            const resp = await fetch('/api/barriers');
            const data = await resp.json();
            if (data && data.success) {
                currentBarriers = data.barriers || [];
                renderBarriersOnMap(currentBarriers);
                renderBarriersList(currentBarriers);
            }
        } catch (e) {
            console.warn('Failed to fetch barriers:', e);
        }
    }

    function renderBarriersOnMap(barriers) {
        barriersLayer.clearLayers();

        barriers.forEach(b => {
            const marker = L.marker([b.lat, b.lon], {
                icon: createPinIcon('barrier', '!')
            });

            const photoHtml = b.image_filename ?
                `<div style="margin-top: 6px;"><img src="/uploads/${encodeURIComponent(b.image_filename)}" alt="${b.category}" style="width: 100%; border-radius: 4px; max-height: 120px; object-fit: cover;"></div>` : '';

            const popupContent = `
                <div style="min-width: 200px; font-family: sans-serif;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: #ef4444; text-transform: uppercase;">${escapeHtml(b.category)}</div>
                    <div style="font-size: 0.85rem; margin-top: 4px; color: #f3f4f6;">${escapeHtml(b.note || b.description || 'Reported barrier')}</div>
                    ${photoHtml}
                    <div style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #374151; padding-top: 6px;">
                        <span style="font-size: 0.7rem; color: #9ca3af;">${b.verification_status || 'Community reported'}</span>
                        <button type="button" class="btn-link" style="color: #10b981; font-size: 0.75rem; cursor: pointer;" onclick="window.resolveBarrierItem(${b.id})">Mark Resolved</button>
                    </div>
                </div>
            `;

            marker.bindPopup(popupContent);
            barriersLayer.addLayer(marker);
        });

        document.getElementById('barrier-count').textContent = `${barriers.length} Active`;
    }

    function renderBarriersList(barriers) {
        const list = document.getElementById('barriers-quick-list');
        list.innerHTML = '';

        if (barriers.length === 0) {
            list.innerHTML = '<div class="text-muted text-xs">No active barriers reported in this zone.</div>';
            return;
        }

        barriers.slice(0, 6).forEach(b => {
            const item = document.createElement('div');
            item.className = 'barrier-item';
            item.innerHTML = `
                <div class="barrier-item-header">
                    <span class="barrier-category-tag">⚠️ ${escapeHtml(b.category)}</span>
                    <button type="button" class="barrier-resolve-btn" onclick="window.resolveBarrierItem(${b.id})">Mark Fixed</button>
                </div>
                <div class="barrier-item-desc">${escapeHtml(b.note || b.description || 'Barrier reported')}</div>
            `;
            item.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON') {
                    map.setView([b.lat, b.lon], 18);
                }
            });
            list.appendChild(item);
        });
    }

    // Expose resolver to global scope for popup clicks
    window.resolveBarrierItem = async function (id) {
        if (!confirm('Mark this barrier as cleared/resolved? The routing penalty will be removed.')) return;
        try {
            showLoading(true, 'Updating barrier status...');
            const resp = await fetch(`/api/barriers/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'resolved' })
            });
            const res = await resp.json();
            if (res.success) {
                map.closePopup();
                await fetchBarriers();
                // If a route was active, recalculate immediately to reflect cleared barrier
                if (currentRouteStart && currentRouteEnd) {
                    calculateRoute();
                }
            } else {
                alert('Could not resolve barrier: ' + res.error);
            }
        } catch (e) {
            alert('Error resolving barrier: ' + e.message);
        } finally {
            showLoading(false);
        }
    };

    async function handleBarrierFormSubmit(e) {
        e.preventDefault();
        const form = document.getElementById('barrier-form');
        const formData = new FormData(form);

        const lat = parseFloat(formData.get('lat'));
        const lon = parseFloat(formData.get('lon'));

        if (isNaN(lat) || isNaN(lon)) {
            alert('Please provide valid latitude and longitude coordinates.');
            return;
        }

        showLoading(true, 'Saving barrier report...');

        try {
            const resp = await fetch('/api/barriers', {
                method: 'POST',
                body: formData
            });

            const data = await resp.json();
            if (!resp.ok || !data.success) {
                throw new Error(data.error || 'Failed to submit barrier report.');
            }

            document.getElementById('barrier-modal').close();
            form.reset();
            document.getElementById('barrier-photo-preview').classList.add('hidden');

            alert('Barrier report saved! The routing engine has updated.');

            await fetchBarriers();

            // If a route is active, recalculate immediately to show detour
            if (currentRouteStart && currentRouteEnd) {
                calculateRoute();
            }
        } catch (err) {
            alert('Submission error: ' + err.message);
        } finally {
            showLoading(false);
        }
    }

    // ==========================================================================
    // 7. AI Photo Classifier (CLIP)
    // ==========================================================================
    let aiSelectedFile = null;

    function setupAiScanner() {
        const dropzone = document.getElementById('ai-dropzone');
        const fileInput = document.getElementById('ai-file-input');
        const previewContainer = document.getElementById('ai-image-preview-container');
        const previewImg = document.getElementById('ai-image-preview');
        const scanBtn = document.getElementById('btn-run-ai-scan');
        const resultsBox = document.getElementById('ai-results-box');

        dropzone.addEventListener('click', () => fileInput.click());

        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                handleAiFile(fileInput.files[0]);
            }
        });

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                handleAiFile(e.dataTransfer.files[0]);
            }
        });

        function handleAiFile(file) {
            aiSelectedFile = file;
            const reader = new FileReader();
            reader.onload = function (ev) {
                previewImg.src = ev.target.result;
                previewContainer.classList.remove('hidden');
                scanBtn.disabled = false;
                resultsBox.classList.add('hidden');
            };
            reader.readAsDataURL(file);
        }

        scanBtn.addEventListener('click', async () => {
            if (!aiSelectedFile) return;

            showLoading(true, 'Analyzing photo with AI classifier...');
            const formData = new FormData();
            formData.append('image', aiSelectedFile);

            try {
                const resp = await fetch('/api/analyze-image', {
                    method: 'POST',
                    body: formData
                });
                const res = await resp.json();

                resultsBox.classList.remove('hidden');

                if (res.success) {
                    document.getElementById('ai-result-label').textContent = res.predicted_label;
                    document.getElementById('ai-result-confidence').textContent = res.confidence_percentage + ' match';
                } else {
                    document.getElementById('ai-result-label').textContent = 'AI Model Inactive';
                    document.getElementById('ai-result-confidence').textContent = 'Demo Mode';
                    alert('AI Notice: ' + (res.error || res.warning));
                }
            } catch (e) {
                alert('Analysis request failed: ' + e.message);
            } finally {
                showLoading(false);
            }
        });

        // "Use in Barrier Report" button links AI findings to barrier report form
        document.getElementById('btn-use-ai-in-report').addEventListener('click', () => {
            const detected = document.getElementById('ai-result-label').textContent.toLowerCase();
            document.getElementById('ai-modal').close();

            const barrierModal = document.getElementById('barrier-modal');
            const categorySelect = document.getElementById('barrier-category');

            if (detected.includes('stair')) {
                categorySelect.value = 'Stairs';
            } else if (detected.includes('ramp')) {
                categorySelect.value = 'Broken ramp';
            } else if (detected.includes('obstacle') || detected.includes('blocked')) {
                categorySelect.value = 'Blocked footpath';
            }

            document.getElementById('barrier-note').value = `Auto-detected via AI: ${detected}`;
            barrierModal.showModal();
        });
    }

    // ==========================================================================
    // 8. Helpers, Event Listeners & Setup
    // ==========================================================================
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showLoading(show, message = 'Loading...') {
        const overlay = document.getElementById('loading-overlay');
        const text = document.getElementById('loading-text');
        if (text) text.textContent = message;
        if (show) {
            overlay.classList.remove('hidden');
        } else {
            overlay.classList.add('hidden');
        }
    }

    function setupEventListeners() {
        // Find Route Button
        document.getElementById('route-form').addEventListener('submit', calculateRoute);
        document.getElementById('btn-find-route').addEventListener('click', calculateRoute);
        document.getElementById('btn-clear-route').addEventListener('click', clearRoute);

        // Route Mode Selector Buttons
        const btnModeAcc = document.getElementById('btn-mode-accessible');
        if (btnModeAcc) {
            btnModeAcc.addEventListener('click', () => setRouteMode('accessible'));
        }
        const btnModeShort = document.getElementById('btn-mode-shortest');
        if (btnModeShort) {
            btnModeShort.addEventListener('click', () => setRouteMode('shortest'));
        }

        // Clickable Summary Cards to Switch Route Modes
        const cardAcc = document.getElementById('card-accessible');
        if (cardAcc) {
            cardAcc.addEventListener('click', () => setRouteMode('accessible'));
        }
        const cardShort = document.getElementById('card-shortest');
        if (cardShort) {
            cardShort.addEventListener('click', () => setRouteMode('shortest'));
        }

        // Setup Autocomplete for Start and End inputs
        setupAutocomplete('start-input', 'start-suggestions', (coords, item) => {
            setStartLocation(coords);
            clearErrorBanner();
            if (document.getElementById('end-input').value.trim()) {
                calculateRoute();
            }
        });

        setupAutocomplete('end-input', 'end-suggestions', (coords, item) => {
            setEndLocation(coords);
            clearErrorBanner();
            if (document.getElementById('start-input').value.trim()) {
                calculateRoute();
            }
        });

        // Trigger new backend route calculation when either location input changes
        const startInputEl = document.getElementById('start-input');
        const endInputEl = document.getElementById('end-input');
        if (startInputEl) {
            startInputEl.addEventListener('change', () => {
                if (startInputEl.value.trim() && endInputEl && endInputEl.value.trim()) {
                    calculateRoute();
                }
            });
        }
        if (endInputEl) {
            endInputEl.addEventListener('change', () => {
                if (startInputEl && startInputEl.value.trim() && endInputEl.value.trim()) {
                    calculateRoute();
                }
            });
        }

        // Accessibility Profile Chips (Wheelchair vs Low-Vision Prototype)
        const chipWheelchair = document.getElementById('chip-mode-wheelchair');
        if (chipWheelchair) {
            chipWheelchair.addEventListener('click', () => setAccessProfile('wheelchair'));
        }
        const chipLowVision = document.getElementById('chip-mode-low-vision');
        if (chipLowVision) {
            chipLowVision.addEventListener('click', () => setAccessProfile('low-vision'));
        }

        // Route Choice Optimization Buttons (Safest vs Shortest)
        const btnSelSafest = document.getElementById('btn-select-safest');
        if (btnSelSafest) {
            btnSelSafest.addEventListener('click', () => setRouteMode('accessible'));
        }
        const btnSelShortest = document.getElementById('btn-select-shortest');
        if (btnSelShortest) {
            btnSelShortest.addEventListener('click', () => setRouteMode('shortest'));
        }

        // Start Navigation & Step Controls
        const btnStartNav = document.getElementById('btn-start-navigation');
        if (btnStartNav) {
            btnStartNav.addEventListener('click', startNavigation);
        }
        const btnStopNav = document.getElementById('btn-stop-navigation');
        if (btnStopNav) {
            btnStopNav.addEventListener('click', stopNavigation);
        }
        const btnNavPrev = document.getElementById('btn-nav-prev');
        if (btnNavPrev) {
            btnNavPrev.addEventListener('click', prevNavStep);
        }
        const btnNavNext = document.getElementById('btn-nav-next');
        if (btnNavNext) {
            btnNavNext.addEventListener('click', nextNavStep);
        }

        // Safety Details Modal
        const btnOpenSafety = document.getElementById('btn-open-safety-details');
        if (btnOpenSafety) {
            btnOpenSafety.addEventListener('click', openSafetyDetails);
        }
        const btnCloseSafety = document.getElementById('btn-close-safety-modal');
        if (btnCloseSafety) {
            btnCloseSafety.addEventListener('click', () => {
                const modal = document.getElementById('safety-modal');
                if (modal) modal.close();
            });
        }
        const btnCloseSafetyFooter = document.getElementById('btn-close-safety-footer');
        if (btnCloseSafetyFooter) {
            btnCloseSafetyFooter.addEventListener('click', () => {
                const modal = document.getElementById('safety-modal');
                if (modal) modal.close();
            });
        }

        // Report Barrier from Route Results
        const btnRouteBarrier = document.getElementById('btn-route-report-barrier');
        if (btnRouteBarrier) {
            btnRouteBarrier.addEventListener('click', () => {
                const modal = document.getElementById('barrier-modal');
                if (modal) {
                    if (currentRouteStart && !document.getElementById('barrier-lat').value) {
                        document.getElementById('barrier-lat').value = currentRouteStart[0].toFixed(5);
                        document.getElementById('barrier-lon').value = currentRouteStart[1].toFixed(5);
                    }
                    modal.showModal();
                }
            });
        }

        // Swap Locations Button
        document.getElementById('btn-swap-locations').addEventListener('click', () => {
            const startInput = document.getElementById('start-input');
            const endInput = document.getElementById('end-input');
            const tempVal = startInput.value;
            startInput.value = endInput.value;
            endInput.value = tempVal;

            if (startMarker && endMarker) {
                const startPos = startMarker.getLatLng();
                const endPos = endMarker.getLatLng();
                setStartLocation([endPos.lat, endPos.lng]);
                setEndLocation([startPos.lat, startPos.lng]);
            }
            if (startInput.value.trim() && endInput.value.trim()) {
                calculateRoute();
            }
        });

        // Use GPS Current Location for Start with Graceful Permission Denial Handling
        document.getElementById('btn-locate-start').addEventListener('click', () => {
            if (!navigator.geolocation) {
                showErrorBanner('Geolocation Unavailable', 'Geolocation is not supported by your browser. Please enter a place name or click on the map.');
                return;
            }
            showLoading(true, 'Acquiring GPS location...');
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    showLoading(false);
                    const coords = [pos.coords.latitude, pos.coords.longitude];
                    setStartLocation(coords);
                    map.setView(coords, 17);
                    clearErrorBanner();
                    if (document.getElementById('end-input').value.trim()) {
                        calculateRoute();
                    }
                },
                (err) => {
                    showLoading(false);
                    let msg = 'Could not acquire location.';
                    if (err.code === 1) { // PERMISSION_DENIED
                        msg = 'Location permission was denied. You can manually enter a place name, coordinates, or click the map pin.';
                    } else if (err.code === 2) { // POSITION_UNAVAILABLE
                        msg = 'Location signal unavailable. Please type a place name or select on the map.';
                    } else if (err.code === 3) { // TIMEOUT
                        msg = 'Location acquisition timed out. Please try again or type a place name.';
                    }
                    showErrorBanner('Location Access Notice', msg);
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        });

        // Welcome Panel Report Barrier Button
        const btnWelcomeReport = document.getElementById('btn-welcome-report-barrier');
        if (btnWelcomeReport) {
            btnWelcomeReport.addEventListener('click', () => {
                const modal = document.getElementById('barrier-modal');
                if (modal) modal.showModal();
            });
        }

        // Map Legend Report Barrier Button
        const btnLegendReport = document.getElementById('btn-legend-report-barrier');
        if (btnLegendReport) {
            btnLegendReport.addEventListener('click', () => {
                const modal = document.getElementById('barrier-modal');
                if (modal) modal.showModal();
            });
        }

        // Map Pick Buttons
        document.getElementById('btn-pick-start').addEventListener('click', () => {
            setPickingMode(currentPickTarget === 'start' ? null : 'start');
        });

        document.getElementById('btn-pick-end').addEventListener('click', () => {
            setPickingMode(currentPickTarget === 'end' ? null : 'end');
        });

        document.getElementById('btn-cancel-pick').addEventListener('click', () => {
            setPickingMode(null);
        });

        // Isolated Demo Presets (explicitly in Demo Mode dropdown only)
        const demoPresetsEl = document.getElementById('demo-presets');
        if (demoPresetsEl) {
            demoPresetsEl.addEventListener('change', (e) => {
                const val = e.target.value;
                if (val && DEMO_PRESETS[val]) {
                    const p = DEMO_PRESETS[val];
                    setStartLocation(p.start);
                    setEndLocation(p.end);
                    calculateRoute();
                }
            });
        }

        // Recenter Map Button
        document.getElementById('btn-recenter-map').addEventListener('click', () => {
            map.setView([config.centerLat, config.centerLon], 16);
        });

        // Toggle Barrier Markers Layer
        let barriersVisible = true;
        document.getElementById('btn-toggle-barriers-layer').addEventListener('click', (e) => {
            barriersVisible = !barriersVisible;
            if (barriersVisible) {
                map.addLayer(barriersLayer);
                e.currentTarget.style.color = '#1e293b';
            } else {
                map.removeLayer(barriersLayer);
                e.currentTarget.style.color = '#9ca3af';
            }
        });

        // Barrier Reporting Modal & Photo Preview
        const barrierModal = document.getElementById('barrier-modal');
        document.getElementById('btn-open-report').addEventListener('click', () => {
            barrierModal.showModal();
        });
        document.getElementById('btn-close-barrier-modal').addEventListener('click', () => {
            barrierModal.close();
        });
        document.getElementById('btn-cancel-barrier').addEventListener('click', () => {
            barrierModal.close();
        });
        document.getElementById('btn-click-map-barrier').addEventListener('click', () => {
            barrierModal.close();
            setPickingMode('barrier');
        });

        const barrierPhotoInput = document.getElementById('barrier-photo');
        barrierPhotoInput.addEventListener('change', () => {
            if (barrierPhotoInput.files && barrierPhotoInput.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const img = document.getElementById('preview-img');
                    img.src = e.target.result;
                    document.getElementById('barrier-photo-preview').classList.remove('hidden');
                };
                reader.readAsDataURL(barrierPhotoInput.files[0]);
            }
        });

        document.getElementById('barrier-form').addEventListener('submit', handleBarrierFormSubmit);

        // AI Modal
        const aiModal = document.getElementById('ai-modal');
        document.getElementById('btn-toggle-ai').addEventListener('click', () => {
            aiModal.showModal();
        });
        document.getElementById('btn-close-ai-modal').addEventListener('click', () => {
            aiModal.close();
        });
        document.getElementById('btn-close-ai-footer').addEventListener('click', () => {
            aiModal.close();
        });

        setupAiScanner();
    }

    // Boot
    window.addEventListener('DOMContentLoaded', () => {
        initMap();
        setupEventListeners();
    });

})();
