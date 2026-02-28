// ==========================================
// 1. INITIALIZE THE MAP (OUTSIDE the button click)
// ==========================================
const map = L.map('map').setView([14.605, 120.985], 13);

// Add the OpenStreetMap tiles
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// Fix for grey map rendering issue
setTimeout(() => {
    map.invalidateSize();
}, 500);

let currentRouteLines =[]; // To store active colored lines :: CHECK TO SEE IF THIS IS NOT NEEDED

// Helper to handle the API calls for suggestions
async function fetchSuggestions(query, dropdownId, inputId) {
    const dropdown = document.getElementById(dropdownId);
    if (query.length < 3) {
        dropdown.style.display = 'none';
        return;
    }

    try {
        // Fetch from Nominatim (Filtering for Philippines)
        const response = await fetch(`https://nominatim.openstreetmap.org/search?q=${query}&format=json&addressdetails=1&limit=5&countrycodes=ph`);
        const data = await response.json();

        dropdown.innerHTML = '';
        if (data.length > 0) {
            dropdown.style.display = 'block';
            data.forEach(place => {
                const item = document.createElement('div');
                item.className = 'suggestion-item';
                item.innerText = place.display_name;
                item.onclick = () => {
                    document.getElementById(inputId).value = place.display_name;
                    dropdown.style.display = 'none';
                };
                dropdown.appendChild(item);
            });
        } else {
            dropdown.style.display = 'none';
        }
    } catch (err) {
        console.error("Autocomplete error:", err);
    }
}

// Debounce timer
let debounceTimer;
const setupAutocomplete = (inputId, dropdownId) => {
    document.getElementById(inputId).addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value;
        debounceTimer = setTimeout(() => fetchSuggestions(query, dropdownId, inputId), 300);
    });
};

// Initialize listeners
setupAutocomplete('origin', 'origin-suggestions');
setupAutocomplete('destination', 'destination-suggestions');

// Close suggestions if user clicks elsewhere
document.addEventListener('click', (e) => {
    if (!e.target.matches('.suggestion-item') && !e.target.matches('input')) {
        document.getElementById('origin-suggestions').style.display = 'none';
        document.getElementById('destination-suggestions').style.display = 'none';
    }
});

// ==========================================
// 2. BUTTON CLICK EVENT
// ==========================================
document.getElementById('find-routes-btn').addEventListener('click', async () => {
    const origin = document.getElementById('origin').value;
    const destination = document.getElementById('destination').value;
    const commuterType = document.getElementById('commuter-type').value;

    if (!origin || !destination) {
        alert("Please enter both origin and destination!");
        return;
    }

    const btn = document.getElementById('find-routes-btn');
    btn.innerText = "Calculating...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/routes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin, destination, commuterType })
        });
        
        const data = await response.json();
        
        // Handle errors if you typed a fake city or server failed
        if (!response.ok || data.error) {
            alert(data.error || "An error occurred.");
            return;
        }

        // Call the function to draw the routes
        displayRoutes(data.routes);
    } catch (err) {
        console.error("Error fetching routes:", err);
        alert("Failed to connect to the server. Check your terminal for python errors.");
    } finally {
        btn.innerText = "Find Safe Routes";
        btn.disabled = false;
    }
});

// ==========================================
// 3. THE MISSING FUNCTION: DRAW THE ROUTES
// ==========================================
function displayRoutes(routes) {
    const resultsDiv = document.getElementById('route-results');
    resultsDiv.innerHTML = ''; // Clear old cards
    
    // Remove old lines from the map
    currentRouteLines.forEach(line => map.removeLayer(line));
    currentRouteLines =[];

    // Loop through the routes sent by Python
    routes.forEach(route => {
        // 1. Draw Polyline on Map
        const polyline = L.polyline(route.coords, {
            color: route.color,
            weight: 6,
            opacity: 0.8
        }).addTo(map);
        currentRouteLines.push(polyline);

        // 2. Create the Route Card UI in the sidebar
        let safetyClass = "safe-high";
        if (route.safety_score < 80) safetyClass = "safe-med";
        if (route.safety_score < 50) safetyClass = "safe-low";

        const card = document.createElement('div');
        card.className = 'route-card';
        card.style.borderLeftColor = route.color;
        card.innerHTML = `
            <div class="route-title" style="color:${route.color}">${route.name}</div>
            <div class="route-stats">
                <span>🕒 ${route.time}</span>
                <span>📏 ${route.distance}</span>
            </div>
            <div class="route-safety ${safetyClass}">
                Safety Score: ${route.safety_score}/100 <br>
                Hazard: ${route.hazards_flagged}
            </div>
        `;

        // Highlight the route on the map when you hover over the card
        card.addEventListener('mouseenter', () => {
            polyline.setStyle({ weight: 10, opacity: 1 });
            polyline.bringToFront();
        });
        card.addEventListener('mouseleave', () => {
            polyline.setStyle({ weight: 6, opacity: 0.8 });
        });

        resultsDiv.appendChild(card);
    });

    if (routes.length > 0) {
        const startPoint = routes[0].coords[0];
        const endPoint = routes[0].coords[routes[0].coords.length - 1];

        if (originMarker) map.removeLayer(originMarker);
        if (destinationMarker) map.removeLayer(destinationMarker);

        originMarker = L.marker(startPoint, {icon: greenIcon}).addTo(map).bindPopup("Starting Location");
        destinationMarker = L.marker(endPoint, {icon: redIcon}).addTo(map).bindPopup("Destination");
    }

    // Automatically zoom the map to fit all the new lines
    if (currentRouteLines.length > 0) {
        const group = new L.featureGroup(currentRouteLines);
        map.fitBounds(group.getBounds(), { padding:[50, 50] });
    }

    // Fix grey map glitch again after drawing
    map.invalidateSize();
}

// Helper to handle the API calls for suggestions
async function fetchSuggestions(query, dropdownId, inputId) {
    const dropdown = document.getElementById(dropdownId);
    if (query.length < 3) {
        dropdown.style.display = 'none';
        return;
    }

    try {
        // Fetch from Nominatim (Filtering for Philippines)
        const response = await fetch(`https://nominatim.openstreetmap.org/search?q=${query}&format=json&addressdetails=1&limit=5&countrycodes=ph`);
        const data = await response.json();

        dropdown.innerHTML = '';
        if (data.length > 0) {
            dropdown.style.display = 'block';
            data.forEach(place => {
                const item = document.createElement('div');
                item.className = 'suggestion-item';
                item.innerText = place.display_name;
                item.onclick = () => {
                    document.getElementById(inputId).value = place.display_name;
                    dropdown.style.display = 'none';
                };
                dropdown.appendChild(item);
            });
        } else {
            dropdown.style.display = 'none';
        }
    } catch (err) {
        console.error("Autocomplete error:", err);
    }
}

let isPicking = false;
let pickStep = 'origin'; // 'origin' or 'destination'
let originMarker = null;
let destinationMarker = null;

const pickBtn = document.getElementById('map-pick-btn');
const pickStatus = document.getElementById('pick-status');

// Toggle Picking Mode
pickBtn.addEventListener('click', () => {
    isPicking = !isPicking;
    if (isPicking) {
        pickBtn.classList.add('active');
        pickStatus.style.display = 'block';
        pickStep = 'origin';
        pickStatus.innerText = "Click map to set Origin";
        document.getElementById('map').style.cursor = 'crosshair';
    } else {
        resetPickingMode();
    }
});

function resetPickingMode() {
    isPicking = false;
    pickBtn.classList.remove('active');
    pickStatus.style.display = 'none';
    document.getElementById('map').style.cursor = '';
}

const greenIcon = new L.Icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

const redIcon = new L.Icon({
    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png',
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

map.on('click', async (e) => {
    if (!isPicking) return;

    const { lat, lng } = e.latlng;
    const targetInputId = pickStep === 'origin' ? 'origin' : 'destination';
    const inputField = document.getElementById(targetInputId);
    
    inputField.value = "Fetching address...";

    try {
        const response = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`);
        const data = await response.json();
        const address = data.display_name;

        inputField.value = address;

        if (pickStep === 'origin') {
            // Remove old origin marker if it exists
            if (originMarker) map.removeLayer(originMarker);
            
            // Create GREEN marker for Origin
            originMarker = L.marker([lat, lng], { icon: greenIcon }).addTo(map)
                .bindPopup(`<b>Starting Location:</b><br>${address}`)
                .openPopup();
            
            pickStep = 'destination';
            pickStatus.innerText = "Click map to set Destination";
        } else {
            // Remove old destination marker if it exists
            if (destinationMarker) map.removeLayer(destinationMarker);
            
            // Create RED marker for Destination
            destinationMarker = L.marker([lat, lng], { icon: redIcon }).addTo(map)
                .bindPopup(`<b>Destination:</b><br>${address}`)
                .openPopup();
            
            resetPickingMode();
        }
    } catch (err) {
        console.error("Reverse geocoding error:", err);
        inputField.value = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
    }
});