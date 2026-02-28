document.getElementById('find-routes-btn').addEventListener('click', async () => {
    const origin = document.getElementById('origin').value;
    const destination = document.getElementById('destination').value;
    const commuterType = document.getElementById('commuter-type').value;

    if(!origin || !destination) {
        alert("Please enter both origin and destination!");
        return;
    }

    document.getElementById('find-routes-btn').innerText = "Calculating...";

    try {
        const response = await fetch('/api/routes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin, destination, commuterType })
        });
        
        const data = await response.json();
        
        // Handle errors if you typed a fake city
        if (!response.ok || data.error) {
            alert(data.error || "An error occurred.");
            return;
        }

        displayRoutes(data.routes);
    } catch (err) {
        console.error("Error fetching routes:", err);
        alert("Failed to connect to the server.");
    } finally {
        document.getElementById('find-routes-btn').innerText = "Find Safe Routes";
    }
});