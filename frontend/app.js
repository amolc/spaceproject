// Cesium Viewer Setup (using local OpenStreetMap to bypass access tokens)
Cesium.Ion.defaultAccessToken = "";

const viewer = new Cesium.Viewer("cesiumContainer", {
    imageryProvider: new Cesium.OpenStreetMapImageryProvider({
        url: "https://a.tile.openstreetmap.org/"
    }),
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    timeline: false,
    animation: false,
    infoBox: false,
    selectionIndicator: false,
    creditContainer: document.createElement("div") // Hides the credit label
});

// Configure viewer scene
viewer.scene.globe.enableLighting = true;
viewer.scene.globe.depthTestAgainstTerrain = false;

// Load local world map vector outline datasource
Cesium.GeoJsonDataSource.load("/static/world.geojson", {
    stroke: Cesium.Color.fromCssColorString("#39ff14").withAlpha(0.25),
    fill: Cesium.Color.TRANSPARENT,
    strokeWidth: 1.5
}).then((dataSource) => {
    viewer.dataSources.add(dataSource);
}).catch((err) => {
    console.error("Failed to load world map outlines:", err);
});

// Global variables
let satellitesMap = new Map(); // norad_id -> Cesium Entity
let groundStationsMap = new Map(); // station_id -> Cesium Entity
let routeEntities = [];
let selectedSatId = null;
let currentTelemetryData = new Map(); // norad_id -> telemetry dict
let showOrbits = true;
let showCones = true;
let showSats = true;

// Interactive links & list state
let groundStationsList = []; // Ground station model instances
let latestSatPositions = new Map(); // norad_id -> { lat, lon, name }
let expandedGroundStationId = null; // Currently expanded ground station ID

// Distance calculator helper (Haversine formula)
function getDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// 1. Fetch Ground Stations from Django API at startup
async function loadGroundStations() {
    const listEl = document.getElementById("ground-stations-list");
    try {
        const response = await fetch("http://127.0.0.1:8000/api/ground-stations/");
        if (!response.ok) throw new Error("Django server offline");
        const stations = await response.json();
        
        groundStationsList = stations; // Store globally
        
        // Update header counter
        const stationsCountEl = document.getElementById("stat-stations-count");
        if (stationsCountEl) {
            stationsCountEl.textContent = stations.length;
        }
        
        listEl.innerHTML = "";
        if (stations.length === 0) {
            listEl.innerHTML = "<div class='loading-text'>No ground stations registered.</div>";
            return;
        }

        stations.forEach(gs => {
            // Draw Ground Station on Cesium Globe
            const pos = Cesium.Cartesian3.fromDegrees(gs.longitude, gs.latitude, 0);
            
            // GS Pin
            const gsEntity = viewer.entities.add({
                name: gs.name,
                position: pos,
                point: {
                    pixelSize: 12,
                    color: Cesium.Color.YELLOW,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2
                },
                label: {
                    text: gs.name,
                    font: "11px Share Tech Mono",
                    fillColor: Cesium.Color.YELLOW,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    pixelOffset: new Cesium.Cartesian2(0, 15)
                }
            });

            // Visibility/Reception Cone (translucent cylinder)
            const coneEntity = viewer.entities.add({
                position: Cesium.Cartesian3.fromDegrees(gs.longitude, gs.latitude, 500000.0), // center height
                cylinder: {
                    length: 1000000.0, // length in meters (1000 km)
                    topRadius: 500000.0, // 500 km radius
                    bottomRadius: 0.0,
                    material: Cesium.Color.YELLOW.withAlpha(0.08),
                    outline: true,
                    outlineColor: Cesium.Color.YELLOW.withAlpha(0.25),
                    outlineWidth: 1
                },
                show: showCones
            });

            groundStationsMap.set(gs.station_id, { pin: gsEntity, cone: coneEntity });
        });

        // Initial render of the sidebar list
        updateGroundStationsListUI();

        logEvent("System", `Loaded ${stations.length} ground stations from PostgreSQL database.`);
    } catch (e) {
        listEl.innerHTML = `<div class='loading-text' style='color:#ff007f;'>PostgreSQL Registry Unreachable: ${e.message}</div>`;
        logEvent("Error", `Failed to retrieve ground stations: ${e.message}`);
    }
}

// Render or update the ground station list in the sidebar with in-range satellites
function updateGroundStationsListUI() {
    const listEl = document.getElementById("ground-stations-list");
    if (!listEl) return;
    
    listEl.innerHTML = "";
    
    if (groundStationsList.length === 0) {
        listEl.innerHTML = "<div class='loading-text'>No ground stations registered.</div>";
        return;
    }
    
    groundStationsList.forEach(gs => {
        const item = document.createElement("div");
        item.className = "list-item";
        if (gs.station_id === expandedGroundStationId) {
            item.classList.add("expanded");
        }
        
        // Find satellites in range (3500 km)
        const satsInRange = [];
        latestSatPositions.forEach((pos, satId) => {
            const dist = getDistanceKm(gs.latitude, gs.longitude, pos.lat, pos.lon);
            if (dist < 3500.0) {
                satsInRange.push({
                    norad_id: satId,
                    name: pos.name,
                    distance: dist
                });
            }
        });
        
        // Sort closest first
        satsInRange.sort((a, b) => a.distance - b.distance);
        
        const isOnline = gs.status === "ONLINE";
        
        item.innerHTML = `
            <div class="list-item-header">
                <span class="item-name">${gs.name}</span>
                <span class="item-meta">${gs.station_id} <span style="font-size: 8px; font-weight: bold; color: ${isOnline ? '#39ff14' : '#ff007f'};">[${gs.status}]</span></span>
            </div>
            <div class="list-item-body">
                <div class="in-range-title">Visible Satellites (${satsInRange.length})</div>
                ${satsInRange.length > 0 ? `
                    <ul class="in-range-sats">
                        ${satsInRange.map(sat => `
                            <li class="in-range-sat-item" data-sat-id="${sat.norad_id}">
                                <span>${sat.name.split(" ")[0]}</span>
                                <span class="sat-dist">${Math.round(sat.distance)} km</span>
                            </li>
                        `).join("")}
                    </ul>
                ` : `
                    <div style="font-size: 10px; color: var(--text-muted); padding: 4px 0;">No satellites in range</div>
                `}
            </div>
        `;
        
        // Setup header click toggle expansion
        const header = item.querySelector(".list-item-header");
        header.addEventListener("click", (e) => {
            e.stopPropagation();
            if (expandedGroundStationId === gs.station_id) {
                expandedGroundStationId = null;
            } else {
                expandedGroundStationId = gs.station_id;
            }
            updateGroundStationsListUI();
        });
        
        // Setup satellite sub-items clicks
        const satItems = item.querySelectorAll(".in-range-sat-item");
        satItems.forEach(satEl => {
            satEl.addEventListener("click", (e) => {
                e.stopPropagation();
                const satId = satEl.getAttribute("data-sat-id");
                const satEntity = satellitesMap.get(satId);
                if (satEntity) {
                    selectSatellite(satId, satEntity);
                }
            });
        });
        
        listEl.appendChild(item);
    });
}

let activeTab = "stations"; // "stations" or "satellites"

// Tab Switching logic
function setupSidebarTabs() {
    const tabStations = document.getElementById("tab-stations");
    const tabSatellites = document.getElementById("tab-satellites");
    const listStations = document.getElementById("ground-stations-list");
    const listSatellites = document.getElementById("active-satellites-list");

    if (!tabStations || !tabSatellites) return;

    tabStations.addEventListener("click", () => {
        activeTab = "stations";
        tabStations.classList.add("active");
        tabSatellites.classList.remove("active");
        listStations.classList.remove("hidden");
        listSatellites.classList.add("hidden");
    });

    tabSatellites.addEventListener("click", () => {
        activeTab = "satellites";
        tabSatellites.classList.add("active");
        tabStations.classList.remove("active");
        listSatellites.classList.remove("hidden");
        listStations.classList.add("hidden");
        // Re-render satellite list immediately
        updateActiveSatellitesListUI();
    });

    // Switch tabs when top header metrics are clicked
    const metricStations = document.getElementById("metric-stations");
    const metricSats = document.getElementById("metric-sats");

    if (metricStations) {
        metricStations.addEventListener("click", () => {
            tabStations.click();
            // Auto expand sidebar if collapsed
            const sidebar = document.getElementById("left-sidebar");
            const btn = document.getElementById("btn-toggle-left");
            if (sidebar && sidebar.classList.contains("collapsed")) {
                sidebar.classList.remove("collapsed");
                if (btn) btn.textContent = "◀";
                logEvent("UI", "Expanded left sidebar via Ground Stations metric header.");
            }
        });
    }

    if (metricSats) {
        metricSats.addEventListener("click", () => {
            tabSatellites.click();
            // Auto expand sidebar if collapsed
            const sidebar = document.getElementById("left-sidebar");
            const btn = document.getElementById("btn-toggle-left");
            if (sidebar && sidebar.classList.contains("collapsed")) {
                sidebar.classList.remove("collapsed");
                if (btn) btn.textContent = "◀";
                logEvent("UI", "Expanded left sidebar via Active Sats metric header.");
            }
        });
    }
}

// Render or update the active satellites list in the sidebar
function updateActiveSatellitesListUI() {
    const listEl = document.getElementById("active-satellites-list");
    if (!listEl || listEl.classList.contains("hidden")) return;
    
    listEl.innerHTML = "";
    
    if (latestSatPositions.size === 0) {
        listEl.innerHTML = "<div class='loading-text'>Waiting for active satellites...</div>";
        return;
    }
    
    // Sort satellites by name/ID
    const sortedSats = [];
    latestSatPositions.forEach((pos, satId) => {
        const tel = currentTelemetryData.get(satId) || {};
        sortedSats.push({
            norad_id: satId,
            name: pos.name,
            connectionCount: tel.connection_count || 0
        });
    });
    sortedSats.sort((a, b) => a.name.localeCompare(b.name));
    
    sortedSats.forEach(sat => {
        const item = document.createElement("div");
        item.className = "list-item";
        if (sat.norad_id === selectedSatId) {
            item.classList.add("expanded");
        }
        
        item.innerHTML = `
            <div class="list-item-header">
                <span class="item-name">${sat.name.split(" ")[0]}</span>
                <span class="item-meta">ID: ${sat.norad_id}</span>
            </div>
        `;
        
        item.addEventListener("click", (e) => {
            e.stopPropagation();
            const satEntity = satellitesMap.get(sat.norad_id);
            if (satEntity) {
                selectSatellite(sat.norad_id, satEntity);
            }
        });
        
        listEl.appendChild(item);
    });
}

// 2. Connect to FastAPI WebSocket Coordinates & Ingestion feed
function connectWebSocket() {
    const wsProto = window.location.protocol === "https:" ? "wss://" : "ws://";
    const wsUrl = wsProto + window.location.host + "/ws/live/";
    const ws = new WebSocket(wsUrl);
    const statusEl = document.getElementById("ws-status");

    ws.onopen = () => {
        statusEl.className = "status-val online";
        statusEl.textContent = "CONNECTED";
        logEvent("System", "FastAPI Live coordinates feeds WebSocket established.");
    };

    ws.onclose = () => {
        statusEl.className = "status-val offline";
        statusEl.textContent = "OFFLINE";
        logEvent("Warning", "WebSocket connection lost. Retrying in 4 seconds...");
        setTimeout(connectWebSocket, 4000);
    };

    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        
        if (payload.type === "coordinates") {
            updateSatellites3D(payload.satellites);
        } else if (payload.type === "telemetry") {
            handleLiveTelemetry(payload.norad_id, payload.data);
        }
    };
}

// Update or create 3D satellite entities on the globe
function updateSatellites3D(satellites) {
    const now = Cesium.JulianDate.now();
    
    // Update active count
    document.getElementById("stat-active-count").textContent = satellites.length;

    let totalCpu = 0;
    let totalTemp = 0;
    let totalThroughput = 0;
    let count = 0;

    satellites.forEach(sat => {
        const satPos = Cesium.Cartesian3.fromDegrees(sat.lon, sat.lat, sat.altitude_km * 1000);
        
        // Cache satellite positions globally
        latestSatPositions.set(sat.norad_id, {
            lat: sat.lat,
            lon: sat.lon,
            name: sat.name || `Sat ${sat.norad_id}`
        });

        // Calculate dynamic averages if telemetry data exists
        const tel = currentTelemetryData.get(sat.norad_id) || {};
        totalCpu += tel.cpu_usage_pct || 30.0;
        totalTemp += tel.battery_temp_c || 25.0;
        totalThroughput += tel.throughput_mbps || 150.0;
        count++;

        if (satellitesMap.has(sat.norad_id)) {
            // Update position
            const entity = satellitesMap.get(sat.norad_id);
            entity.position = satPos;
        } else {
            // Create new satellite entity
            const entity = viewer.entities.add({
                id: `sat:${sat.norad_id}`,
                name: sat.name || `Sat ${sat.norad_id}`,
                position: satPos,
                show: showSats,
                point: {
                    pixelSize: 10,
                    color: Cesium.Color.CYAN,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2
                },
                label: {
                    text: sat.name ? sat.name.split(" ")[0] : sat.norad_id,
                    font: "10px Share Tech Mono",
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    pixelOffset: new Cesium.Cartesian2(0, -14)
                },
                path: {
                    resolution: 60,
                    leadTime: 0,
                    trailTime: 5400, // 1.5 hours path trail
                    width: 1.5,
                    material: Cesium.Color.CYAN.withAlpha(0.2),
                    show: showOrbits
                }
            });
            
            satellitesMap.set(sat.norad_id, entity);
            logEvent("Constellation", `Created 3D tracking entity for satellite ${sat.name} (${sat.norad_id})`);
        }
    });

    if (count > 0) {
        document.getElementById("stat-avg-cpu").textContent = `${Math.round(totalCpu / count)}%`;
        document.getElementById("stat-avg-temp").textContent = `${Math.round(totalTemp / count)}°C`;
        document.getElementById("stat-total-throughput").textContent = `${(totalThroughput / 1000).toFixed(2)} Gbps`;
    }

    // Refresh Ground Stations sidebar list coordinates and distances in real-time
    updateGroundStationsListUI();
    // Refresh Active Satellites list in real-time
    updateActiveSatellitesListUI();
}

// Receive live telemetry push from MongoDB collection watch events via WebSocket
function handleLiveTelemetry(norad_id, data) {
    currentTelemetryData.set(norad_id, data);
    
    // Log MongoDB inserts
    logEvent("MongoDB Write", `Ingested telemetry for Sat ${norad_id} -> CPU: ${data.cpu_usage_pct}%, Temp: ${data.battery_temp_c}°C, Connections: ${data.connection_count}`);

    // Update inspected details if this satellite is currently selected
    if (selectedSatId === norad_id) {
        document.getElementById("inspect-temp").textContent = `${data.battery_temp_c.toFixed(1)}°C`;
        document.getElementById("inspect-signal").textContent = `${data.signal_strength_dbm} dBm`;
        document.getElementById("inspect-throughput").textContent = `${data.throughput_mbps.toFixed(1)} Mbps`;
        document.getElementById("inspect-terminals").textContent = data.connection_count;
        
        // Vitals
        document.getElementById("gauge-battery-text").textContent = `${Math.round(data.battery_soc_pct)}%`;
        document.getElementById("gauge-battery-path").setAttribute("stroke-dasharray", `${data.battery_soc_pct}, 100`);

        document.getElementById("gauge-cpu-text").textContent = `${Math.round(data.cpu_usage_pct)}%`;
        document.getElementById("gauge-cpu-path").setAttribute("stroke-dasharray", `${data.cpu_usage_pct}, 100`);
    }
}

// 3. User Selection Click Handler in Cesium
const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
handler.setInputAction((click) => {
    const pickedObject = viewer.scene.pick(click.position);
    if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.id.startsWith("sat:")) {
        const satId = pickedObject.id.id.split(":")[1];
        selectSatellite(satId, pickedObject.id);
    } else {
        // Deselect
        selectedSatId = null;
        expandedGroundStationId = null;
        updateGroundStationsListUI();
        document.getElementById("sat-telemetry-panel").classList.add("hidden");
        document.getElementById("no-sat-selected").classList.remove("hidden");

        // Globe coordinates pick on Left Click
        const ray = viewer.camera.getPickRay(click.position);
        const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
        
        if (Cesium.defined(cartesian)) {
            const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
            const lat = Cesium.Math.toDegrees(cartographic.latitude);
            const lon = Cesium.Math.toDegrees(cartographic.longitude);
            
            document.getElementById("route-lat").value = lat.toFixed(4);
            document.getElementById("route-lon").value = lon.toFixed(4);
            
            logEvent("UI Interaction", `Set user terminal query coordinates via Left Click to: Lat ${lat.toFixed(4)}°, Lon ${lon.toFixed(4)}°`);
            
            // Auto calculate optimal route
            document.getElementById("btn-calc-route").click();
        }
    }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

function selectSatellite(satId, entity) {
    selectedSatId = satId;
    
    document.getElementById("no-sat-selected").classList.add("hidden");
    const panel = document.getElementById("sat-telemetry-panel");
    panel.classList.remove("hidden");

    // Populate initial static metadata fields from Cesium properties
    document.getElementById("inspect-sat-name").textContent = entity.name || `Sat ${satId}`;
    document.getElementById("inspect-norad-id").textContent = satId;
    
    const pos = entity.position.getValue(Cesium.JulianDate.now());
    const cartographic = Cesium.Cartographic.fromCartesian(pos);
    
    const alt_km = cartographic.height / 1000;
    document.getElementById("inspect-altitude").textContent = `${alt_km.toFixed(1)} km`;
    document.getElementById("inspect-speed").textContent = "7.63 km/s"; // default LEO speed approximation

    // Pull last cached telemetry data if present
    const data = currentTelemetryData.get(satId);
    if (data) {
        handleLiveTelemetry(satId, data);
    } else {
        // Reset gauges
        document.getElementById("gauge-battery-text").textContent = "--";
        document.getElementById("gauge-cpu-text").textContent = "--";
    }

    // Dynamic range calculations: Visible Ground Stations and ISL Neighbors
    const satPos = latestSatPositions.get(satId);
    const visibleGsEl = document.getElementById("inspect-visible-gs");
    const visibleIslEl = document.getElementById("inspect-visible-isl");

    if (satPos) {
        // Find visible ground stations (< 3500 km)
        const visibleGs = [];
        let minDistance = Infinity;
        let nearestGsId = null;

        groundStationsList.forEach(gs => {
            const dist = getDistanceKm(gs.latitude, gs.longitude, satPos.lat, satPos.lon);
            if (dist < 3500.0) {
                visibleGs.push({
                    name: gs.name,
                    station_id: gs.station_id,
                    distance: dist
                });
            }
            if (dist < minDistance) {
                minDistance = dist;
                nearestGsId = gs.station_id;
            }
        });

        // Expand the nearest ground station list if within visibility range!
        if (nearestGsId && minDistance < 3500.0) {
            expandedGroundStationId = nearestGsId;
            updateGroundStationsListUI();
            logEvent("Constellation", `Sat ${satId} is nearest to Ground Station ${nearestGsId} (${Math.round(minDistance)} km). Expanding station list.`);
        }

        // Render visible GS list
        visibleGs.sort((a, b) => a.distance - b.distance);
        if (visibleGs.length > 0) {
            visibleGsEl.innerHTML = visibleGs.map(gs => `
                <li class="gs-conn">
                    <span class="conn-name">${gs.name}</span>
                    <span class="conn-dist">${Math.round(gs.distance)} km</span>
                </li>
            `).join("");
        } else {
            visibleGsEl.innerHTML = `<li style="color: var(--text-muted); font-size: 9.5px; border: none; padding: 2px 0;">None in range</li>`;
        }

        // Find visible ISL neighbors (< 4500 km)
        const visibleIsl = [];
        latestSatPositions.forEach((otherPos, otherSatId) => {
            if (otherSatId !== satId) {
                const dist = getDistanceKm(satPos.lat, satPos.lon, otherPos.lat, otherPos.lon);
                if (dist < 4500.0) {
                    visibleIsl.push({
                        norad_id: otherSatId,
                        name: otherPos.name,
                        distance: dist
                    });
                }
            }
        });

        visibleIsl.sort((a, b) => a.distance - b.distance);
        if (visibleIsl.length > 0) {
            visibleIslEl.innerHTML = visibleIsl.map(sat => `
                <li class="isl-conn">
                    <span class="conn-name">${sat.name.split(" ")[0]}</span>
                    <span class="conn-dist">${Math.round(sat.distance)} km</span>
                </li>
            `).join("");
        } else {
            visibleIslEl.innerHTML = `<li style="color: var(--text-muted); font-size: 9.5px; border: none; padding: 2px 0;">None in range</li>`;
        }
    }
    
    // Switch left sidebar tab to active satellites and highlight
    const tabSatellites = document.getElementById("tab-satellites");
    if (tabSatellites) {
        activeTab = "satellites";
        tabSatellites.classList.add("active");
        const tabStations = document.getElementById("tab-stations");
        if (tabStations) tabStations.classList.remove("active");
        
        const listStations = document.getElementById("ground-stations-list");
        const listSatellites = document.getElementById("active-satellites-list");
        if (listStations) listStations.classList.add("hidden");
        if (listSatellites) listSatellites.classList.remove("hidden");
        
        updateActiveSatellitesListUI();
    }
    
    logEvent("UI Selection", `Inspecting satellite metadata for NORAD ID: ${satId}`);
}

// 4. Calculate dynamic Dijkstra shortest-path routing
document.getElementById("btn-calc-route").addEventListener("click", async () => {
    const lat = parseFloat(document.getElementById("route-lat").value);
    const lon = parseFloat(document.getElementById("route-lon").value);
    const btn = document.getElementById("btn-calc-route");
    const resultContainer = document.getElementById("route-result-container");
    
    if (isNaN(lat) || isNaN(lon)) return;
    
    btn.textContent = "CALCULATING PATH...";
    btn.disabled = true;

    // Remove previous path drawing from Cesium viewer
    routeEntities.forEach(ent => viewer.entities.remove(ent));
    routeEntities = [];

    try {
        const response = await fetch(`/api/orbit/nearest/?lat=${lat}&lon=${lon}`);
        if (!response.ok) throw new Error("FastAPI routing calculations failed.");
        const res = await response.json();
        
        resultContainer.classList.remove("hidden");
        btn.textContent = "CALCULATE OPTIMAL ROUTE";
        btn.disabled = false;

        document.getElementById("route-val-cost").textContent = res.routing_cost || "INFINITE";
        document.getElementById("route-val-hops").textContent = res.routing_path.length;

        // Populate hops list
        const hopsEl = document.getElementById("route-hops-list-items");
        hopsEl.innerHTML = "";
        
        if (res.routing_path.length === 0) {
            hopsEl.innerHTML = "<li style='color:#ff007f;'>No available path to ground stations. Try adjusting terminal coordinates.</li>";
            logEvent("Routing Error", "No routing path calculated. All overhead space links disconnected.");
            return;
        }

        // Draw Terminal Point
        const termEntity = viewer.entities.add({
            name: "Subscriber Terminal",
            position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
            point: {
                pixelSize: 14,
                color: Cesium.Color.GREEN,
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2
            }
        });
        routeEntities.push(termEntity);

        // Draw Terminal Range Circle (3000 km search radius)
        const rangeEntity = viewer.entities.add({
            name: "Terminal Coverage Range (3000 km)",
            position: Cesium.Cartesian3.fromDegrees(lon, lat, 0),
            ellipse: {
                semiMinorAxis: 3000000.0, // 3000 km in meters
                semiMajorAxis: 3000000.0,
                material: Cesium.Color.GREEN.withAlpha(0.04),
                outline: true,
                outlineColor: Cesium.Color.GREEN.withAlpha(0.25),
                outlineWidth: 1.5
            }
        });
        routeEntities.push(rangeEntity);

        // Draw Evaluated Graph Mesh Edges (thin translucent lines to show impact)
        // A. Terminal to visible satellites (within 3000 km)
        latestSatPositions.forEach((pos, satId) => {
            const dist = getDistanceKm(lat, lon, pos.lat, pos.lon);
            if (dist < 3000.0) {
                const satHeight = 550000.0;
                const line = viewer.entities.add({
                    polyline: {
                        positions: [
                            Cesium.Cartesian3.fromDegrees(lon, lat, 0),
                            Cesium.Cartesian3.fromDegrees(pos.lon, pos.lat, satHeight)
                        ],
                        width: 1,
                        material: Cesium.Color.CYAN.withAlpha(0.15)
                    }
                });
                routeEntities.push(line);
            }
        });

        // B. Inter-Satellite Links (ISL) (within 4500 km)
        const processedPairs = new Set();
        latestSatPositions.forEach((pos1, sat1) => {
            latestSatPositions.forEach((pos2, sat2) => {
                if (sat1 === sat2) return;
                const pairId = [sat1, sat2].sort().join("-");
                if (processedPairs.has(pairId)) return;
                processedPairs.add(pairId);
                
                const dist = getDistanceKm(pos1.lat, pos1.lon, pos2.lat, pos2.lon);
                if (dist < 4500.0) {
                    const line = viewer.entities.add({
                        polyline: {
                            positions: [
                                Cesium.Cartesian3.fromDegrees(pos1.lon, pos1.lat, 550000.0),
                                Cesium.Cartesian3.fromDegrees(pos2.lon, pos2.lat, 550000.0)
                            ],
                            width: 1,
                            material: Cesium.Color.CYAN.withAlpha(0.08)
                        }
                    });
                    routeEntities.push(line);
                }
            });
        });

        // C. Satellite to Ground Station links (within 3500 km)
        groundStationsList.forEach(gs => {
            latestSatPositions.forEach((pos, satId) => {
                const dist = getDistanceKm(gs.latitude, gs.longitude, pos.lat, pos.lon);
                if (dist < 3500.0) {
                    const line = viewer.entities.add({
                        polyline: {
                            positions: [
                                Cesium.Cartesian3.fromDegrees(pos.lon, pos.lat, 550000.0),
                                Cesium.Cartesian3.fromDegrees(gs.longitude, gs.latitude, 0)
                            ],
                            width: 1,
                            material: Cesium.Color.YELLOW.withAlpha(0.1)
                        }
                    });
                    routeEntities.push(line);
                }
            });
        });

        // Populate hops
        res.path_coordinates.forEach((node, idx) => {
            const li = document.createElement("li");
            li.textContent = `${idx + 1}. [${node.type.toUpperCase()}] ${node.name}`;
            hopsEl.appendChild(li);
        });

        // Convert path coordinates list to Cesium line arrays
        const positions = res.path_coordinates.map(node => {
            const height = node.type === "satellite" ? 550000.0 : 0.0;
            return Cesium.Cartesian3.fromDegrees(node.lon, node.lat, height);
        });

        // Draw routing lines (poly-lines) in glowing neon green
        const polylineEntity = viewer.entities.add({
            polyline: {
                positions: positions,
                width: 4,
                material: new Cesium.PolylineGlowMaterialProperty({
                    glowPower: 0.25,
                    color: Cesium.Color.GREEN
                })
            }
        });
        routeEntities.push(polylineEntity);
        
        logEvent("Dijkstra Routing", `Optimal route found with ${res.routing_path.length} hops. Latency cost: ${res.routing_cost}ms`);

    } catch (e) {
        btn.textContent = "CALCULATE OPTIMAL ROUTE";
        btn.disabled = false;
        alert(`Routing Request Failed: ${e.message}`);
    }
});

// Click on the globe to set Routing terminal position coordinates
const globeHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
globeHandler.setInputAction((click) => {
    const ray = viewer.camera.getPickRay(click.position);
    const cartesian = viewer.scene.globe.pick(ray, viewer.scene);
    
    if (Cesium.defined(cartesian)) {
        const cartographic = Cesium.Cartographic.fromCartesian(cartesian);
        const lat = Cesium.Math.toDegrees(cartographic.latitude);
        const lon = Cesium.Math.toDegrees(cartographic.longitude);
        
        document.getElementById("route-lat").value = lat.toFixed(4);
        document.getElementById("route-lon").value = lon.toFixed(4);
        
        logEvent("UI Interaction", `Set user terminal query coordinates to: Lat ${lat.toFixed(4)}°, Lon ${lon.toFixed(4)}°`);
        
        // Auto calculate optimal route
        document.getElementById("btn-calc-route").click();
    }
}, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

// Sidebar logs feed helper
function logEvent(source, msg) {
    const logsEl = document.getElementById("logs-container");
    const line = document.createElement("div");
    
    let sourceClass = "system-msg";
    if (source.includes("MongoDB")) sourceClass = "write-msg";
    if (source.includes("Dijkstra") || source.includes("Routing")) sourceClass = "route-msg";

    const timestamp = new Date().toLocaleTimeString();
    line.className = `log-line ${sourceClass}`;
    line.textContent = `[${timestamp}] [${source.toUpperCase()}] ${msg}`;
    
    logsEl.appendChild(line);
    // Auto scroll bottom
    logsEl.scrollTop = logsEl.scrollHeight;
}

// Reset viewer camera
document.getElementById("btn-reset-view").addEventListener("click", () => {
    viewer.camera.flyHome(2.0);
    logEvent("UI", "Reset camera view on Earth.");
});

// Sidebar collapse/expand handlers
document.getElementById("btn-toggle-left").addEventListener("click", () => {
    const sidebar = document.getElementById("left-sidebar");
    const btn = document.getElementById("btn-toggle-left");
    const isCollapsed = sidebar.classList.toggle("collapsed");
    btn.textContent = isCollapsed ? "▶" : "◀";
    logEvent("UI", isCollapsed ? "Collapsed left sidebar." : "Expanded left sidebar.");
});

document.getElementById("btn-toggle-right").addEventListener("click", () => {
    const sidebar = document.getElementById("right-sidebar");
    const btn = document.getElementById("btn-toggle-right");
    const isCollapsed = sidebar.classList.toggle("collapsed");
    btn.textContent = isCollapsed ? "◀" : "▶";
    logEvent("UI", isCollapsed ? "Collapsed right sidebar." : "Expanded right sidebar.");
});

// Map Layer Checkbox controls
document.getElementById("layer-orbits").addEventListener("change", (e) => {
    showOrbits = e.target.checked;
    satellitesMap.forEach(sat => {
        if (sat.path) sat.path.show = showOrbits;
    });
    logEvent("UI", `Toggled satellite orbits: ${showOrbits ? "ON" : "OFF"}`);
});

document.getElementById("layer-cones").addEventListener("change", (e) => {
    showCones = e.target.checked;
    groundStationsMap.forEach(gs => {
        if (gs.cone) gs.cone.show = showCones;
    });
    logEvent("UI", `Toggled coverage cones: ${showCones ? "ON" : "OFF"}`);
});

document.getElementById("layer-stations").addEventListener("change", (e) => {
    const showStations = e.target.checked;
    groundStationsMap.forEach(gs => {
        if (gs.pin) gs.pin.show = showStations;
    });
    logEvent("UI", `Toggled ground stations: ${showStations ? "ON" : "OFF"}`);
});

document.getElementById("layer-sats").addEventListener("change", (e) => {
    showSats = e.target.checked;
    satellitesMap.forEach(sat => {
        sat.show = showSats;
    });
    logEvent("UI", `Toggled satellite entities: ${showSats ? "ON" : "OFF"}`);
});

// Dynamic UTC clock
function startClock() {
    const clockEl = document.getElementById("utc-clock");
    setInterval(() => {
        const now = new Date();
        const utcStr = now.toISOString().substring(11, 19);
        clockEl.textContent = utcStr;
    }, 1000);
}

// Initialization
window.addEventListener("DOMContentLoaded", () => {
    loadGroundStations();
    connectWebSocket();
    startClock();
    setupSidebarTabs();
});
