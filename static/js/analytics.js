if (!window.chartColors) {
    window.chartColors = {
        'Road Damage': '#ff2a55',
        'Water Supply': '#00f5ff',
        'Electricity': '#ffb700',
        'Garbage Management': '#22c55e',
        'Drainage Sewage': '#a855f7',
        'Street Light': '#fef08a',
        'Traffic': '#f97316',
        'Public Transport': '#7f5af0',
        'Pollution': '#94a3b8',
        'Illegal Construction': '#ef4444',
        'Water Leakage': '#2dd4bf',
        'Network': '#3b82f6',
        'Animal Problems': '#fb923c',
        'Park Maintenance': '#166534',
        'Government Office': '#64748b',
        'Safety Security': '#dc2626',
        'Other': '#7f5af0',
        default: '#00f5ff'
    };
}

function initAnalytics() {
    fetchAnalyticsData();
}

function fetchAnalyticsData() {
    fetch('/api/analytics')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                console.error("API Error:", data.error);
                return;
            }
            
            updateStats(data);
            renderIssueTypeChart(data.by_issue); // Swapped to Hologram Bar
            renderTrendChart(data.trends);       // Line with tooltips
        })
        .catch(error => {
            console.error('Error fetching analytics data:', error);
        });
        
    fetch('/api/heatmap')
        .then(res => res.json())
        .then(data => {
            if(!data.error) renderHeatmap(data);
        });

    fetch('/api/insights')
        .then(res => res.json())
        .then(data => {
            if(!data.error) {
                renderPredictions(data.predictions);
                renderClusters(data.clusters);
                renderRecommendations(data.recommendations);
            }
        })
        .catch(err => console.error("Insights error:", err));
}

function animateValue(obj, start, end, duration) {
    if(!obj) return;
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // Exponential easing out for futuristic feel
        const easeOut = 1 - Math.pow(1 - progress, 3);
        obj.innerHTML = Math.floor(easeOut * (end - start) + start);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

function updateStats(data) {
    animateValue(document.getElementById('statTotal'), 0, data.total_complaints, 2000);
    animateValue(document.getElementById('statResolved'), 0, data.resolved_complaints, 2000);
    
    const active = data.total_complaints - data.resolved_complaints;
    animateValue(document.getElementById('statActive'), 0, active, 2000);
}

// Ensure charts object exists globally
window.charts = window.charts || {};

function renderIssueTypeChart(issueData) {
    const ctx = document.getElementById('issueTypeChart');
    if (!ctx) return;
    
    if (window.charts.issueType) window.charts.issueType.destroy();
    
    if (!issueData || issueData.length === 0) return;
    
    const labels = issueData.map(item => item.issue_type);
    const data = issueData.map(item => item.count);
    const backgroundColors = labels.map(label => window.chartColors[label] || window.chartColors.default);
    
    const canvasCtx = ctx.getContext('2d');
    const gradients = backgroundColors.map(color => {
        let gradient = canvasCtx.createLinearGradient(0, 0, 0, 400);
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, 'rgba(11, 15, 25, 0.1)'); // Fades into the dark background
        return gradient;
    });
    
    // Per requirement: Hologram Bar chart
    window.charts.issueType = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Complaints',
                data: data,
                backgroundColor: gradients,
                borderColor: backgroundColors,
                borderWidth: 2,
                borderRadius: 4
            }]
        },
        options: {
            animation: {
                duration: 2500,
                easing: 'easeOutQuart'
            },
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { 
                    beginAtZero: true, 
                    ticks: { precision: 0, color: '#eef2f6' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                x: {
                    ticks: { color: '#eef2f6' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(11, 46, 89, 0.9)',
                    padding: 12,
                    titleFont: { size: 14 },
                    bodyFont: { size: 13 },
                    callbacks: {
                        label: function(context) { return ` ${context.parsed.y} anomalies detected`; }
                    }
                }
            },
            interaction: { mode: 'index', intersect: false }
        }
    });
}

function renderTrendChart(trendData) {
    const ctx = document.getElementById('trendChart');
    if (!ctx) return;
    
    if (window.charts.trend) window.charts.trend.destroy();
    
    if (!trendData || trendData.length === 0) return;
    
    const labels = trendData.map(item => item.month); // Assuming YYYY-MM
    const data = trendData.map(item => item.count);
    
    window.charts.trend = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Volume',
                id: 'trendDataset',
                data: data,
                borderColor: window.chartColors.default,
                backgroundColor: 'rgba(11, 46, 89, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4, // smooth curves
                pointBackgroundColor: window.chartColors.default,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBorderColor: '#000',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { 
                    beginAtZero: true, 
                    ticks: { precision: 0, color: '#eef2f6' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                x: {
                    ticks: { color: '#eef2f6' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(11, 46, 89, 0.9)',
                    mode: 'index',
                    intersect: false
                }
            },
            interaction: { mode: 'nearest', axis: 'x', intersect: false }
        }
    });
}

function renderHeatmap(areaData) {
    const container = document.getElementById('issueMap');
    if(!container) return;
    
    if(window.heatmap) {
        window.heatmap.remove();
        window.heatmap = null;
    }
    
    // Default center
    const map = L.map('issueMap').setView([37.7749, -122.4194], 12);
    window.heatmap = map;
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    
    // Add dark filter to the map tiles for cinematic feel
    document.querySelector('.leaflet-layer').style.filter = "invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%)";
    
    const markers = [];
    areaData.forEach(area => {
        let color = '#00e676'; // Neon Green (<5)
        if(area.volume >= 10) color = '#ff2a55'; // Neon Red
        else if(area.volume >= 5) color = '#ffb700'; // Neon Yellow
        
        const radius = Math.min(200 + (area.volume * 50), 1000); // meters
        
        const circle = L.circle(area.coords, {
            color: color,
            fillColor: color,
            fillOpacity: 0.6,
            radius: radius
        }).addTo(map)
        .bindPopup(`<b>${area.area}</b><br>${area.volume} Complaints Reported`);
        
        markers.push(circle);
    });

    if (markers.length > 0) {
        const group = new L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.5));
    }

    setTimeout(() => { map.invalidateSize(); }, 200);
}

function renderPredictions(predictions) {
    const list = document.getElementById('predictionList');
    if (!list) return;
    
    if (!predictions || predictions.length === 0) {
        list.innerHTML = '<p class="text-muted">No high-risk areas predicted for the next 7 days.</p>';
        return;
    }
    
    list.innerHTML = predictions.map(p => `
        <div class="insight-item">
            <div>
                <strong>${p.area}</strong>
                <div style="font-size: 0.8rem; color: var(--text-muted)">Volume: ${p.recent_volume} | Growth: +${p.growth}%</div>
            </div>
            <span class="risk-badge ${p.risk_level === 'Critical' ? 'risk-critical pulse-alert' : 'risk-high'}">${p.risk_level}</span>
        </div>
    `).join('');
}

function renderClusters(clusters) {
    const list = document.getElementById('clusterList');
    if (!list) return;
    
    if (!clusters || clusters.length === 0) {
        list.innerHTML = '<p class="text-muted">No major issue clusters detected.</p>';
        return;
    }
    
    list.innerHTML = clusters.map(c => `
        <div class="insight-item">
            <div>
                <i class="fa-solid fa-location-dot" style="color: var(--secondary-color)"></i> 
                <strong>${c.area}</strong> - ${c.issue_type}
            </div>
            <span class="cluster-badge">${c.count} items</span>
        </div>
    `).join('');
}

function renderRecommendations(recommendations) {
    const list = document.getElementById('recommendationList');
    if (!list) return;
    
    if (!recommendations || recommendations.length === 0) {
        list.innerHTML = '<p class="text-muted">Insufficient data to generate recommendations.</p>';
        return;
    }
    
    const icons = {
        'Garbage': 'fa-trash-can',
        'Garbage Management': 'fa-trash-can',
        'Road': 'fa-road',
        'Road Damage': 'fa-road',
        'Water': 'fa-faucet',
        'Water Supply': 'fa-faucet',
        'Electricity': 'fa-bolt',
        'Electricity Problems': 'fa-bolt',
        'Drainage': 'fa-faucet-drip',
        'Drainage Sewage': 'fa-faucet-drip',
        'Street Light': 'fa-lightbulb',
        'Traffic': 'fa-car',
        'Public Transport': 'fa-bus',
        'Pollution': 'fa-smog',
        'Illegal Construction': 'fa-trowel-bricks',
        'Water Leakage': 'fa-droplet',
        'Network': 'fa-wifi',
        'Animal Problems': 'fa-dog',
        'Park Maintenance': 'fa-tree',
        'Government Office': 'fa-building-ngo',
        'Safety Security': 'fa-shield-halved',
        'default': 'fa-circle-info'
    };
    
    list.innerHTML = recommendations.map(r => `
        <div class="rec-card">
            <div class="rec-icon">
                <i class="fa-solid ${icons[r.issue] || icons.default}"></i>
            </div>
            <div class="rec-content">
                <div class="rec-tag">${r.action}</div>
                <h4>${r.issue} Issue - ${r.area}</h4>
                <p>${r.suggestion}</p>
            </div>
        </div>
    `).join('');
}

// Define globally but don't auto-init here (handled by main.js)
window.initAnalytics = initAnalytics;
window.fetchAnalyticsData = fetchAnalyticsData; // Support refresh button
