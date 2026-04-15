class SpaRouter {
    constructor() {
        this.appContent = document.getElementById('app-content');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        // Store current scripts to clean them up on nav
        this.activeScripts = [];
        this.bindEvents();
        
        // Handle browser back/forward buttons
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.url) {
                this.loadPage(e.state.url, false);
            }
        });
        
        // Push initial state
        window.history.replaceState({url: window.location.pathname + window.location.search}, '', window.location.href);

        // Run initial entry logic
        try {
            this.initPageInteractions();
        } catch (e) {
            console.error("Initial Interaction Error:", e);
        }
        
        // Final reveal: clear the initial loading state
        this.hideLoading();
    }

    bindEvents() {
        document.body.addEventListener('click', (e) => {
            // Find closest link
            const target = e.target.closest('a');
            
            // Allow default for external links, same-page hashes, or links marked with data-no-spa
            if (!target || 
                target.host !== window.location.host || 
                target.hash || 
                target.hasAttribute('data-no-spa') ||
                e.ctrlKey || e.shiftKey || e.metaKey) {
                return;
            }

            e.preventDefault();
            this.handleNavigation(target);
        });
        
        // Intercept Forms dynamically mapped to #app-content
        document.body.addEventListener('submit', (e) => {
            if (e.target.hasAttribute('data-no-spa')) return;
            
            e.preventDefault();
            const form = e.target;
            const url = form.action || window.location.href;
            const method = (form.method || 'GET').toUpperCase();
            
            // Show loading on submit button
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalBtnHTML = submitBtn ? submitBtn.innerHTML : '';
            if (submitBtn) {
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
                submitBtn.disabled = true;
            }

            const formData = new FormData(form);
            
            let fetchOptions = {
                method: method,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            };
            
            let fetchUrl = url;
            
            if (method === 'GET') {
                const params = new URLSearchParams(formData);
                const joiner = url.includes('?') ? '&' : '?';
                fetchUrl = `${url}${joiner}${params.toString()}`;
            } else {
                fetchOptions.body = formData;
            }
            
            this.showLoading();
            
            fetch(fetchUrl, fetchOptions)
                .then(response => {
                    // Just use the response text directly, whether redirected or not
                    return response.text().then(html => ({html, url: response.url}));
                })
                .then(data => {
                    if (data && data.html) {
                        this.renderPage(data.html, data.url);
                        if (method === 'GET') {
                            window.history.pushState({url: data.url}, '', data.url);
                        }
                    }
                })
                .catch(err => {
                    console.error('Form submission failed:', err);
                })
                .finally(() => {
                    if (submitBtn) {
                        submitBtn.innerHTML = originalBtnHTML;
                        submitBtn.disabled = false;
                    }
                    this.hideLoading();
                });
        });
    }

    handleNavigation(link) {
        const url = link.href;
        
        if (url === window.location.href) {
            // Smooth scroll to top if already on page
            window.scrollTo({ top: 0, behavior: 'smooth' });
            return;
        }

        // Close mobile menu if open
        const navLinks = document.getElementById('navLinks');
        const mobileMenuBtn = document.getElementById('mobileMenuBtn');
        if (navLinks && navLinks.classList.contains('show')) {
            navLinks.classList.remove('show');
            const icon = mobileMenuBtn.querySelector('i');
            icon.classList.remove('fa-xmark');
            icon.classList.add('fa-bars');
        }

        this.loadPage(url, true);
    }

    loadPage(url, pushState = true) {
        this.showLoading();
        
        // Slide out animation
        this.appContent.classList.add('page-leave');
        requestAnimationFrame(() => {
            this.appContent.classList.add('page-leave-active');
        });

        const sep = url.includes('?') ? '&' : '?';
        const cacheBustUrl = `${url}${sep}_t=${Date.now()}`;

        fetch(cacheBustUrl, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            cache: 'no-cache'
        })
        .then(response => {
            if (response.status === 401 || response.status === 403) {
                 window.location.href = url; // Fallback to full reload for auth boundaries
                 throw new Error('Auth boundary');
            }
            // Handle flask redirects
            if(response.redirected) {
                url = response.url;
            }
            return response.text();
        })
        .then(html => {
            this.renderPage(html, url);
            if (pushState) {
                window.history.pushState({url}, '', url);
            }
            this.updateActiveNavLinks(url);
        })
        .catch(err => {
            console.error('SPA Navigation Error:', err);
            // Fallback to standard navigation on hard failure
            if (err.message !== 'Auth boundary') {
                window.location.href = url;
            }
        })
        .finally(() => {
            this.hideLoading();
        });
    }

    renderPage(html, newUrl) {
        // Parse the new HTML string into a DOM
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');

        // Extract the <main id="app-content"> from the new doc if it's a full page (Flask template rendering)
        const newAppContent = doc.getElementById('app-content');
        
        let newContent = '';
        if (newAppContent) {
            newContent = newAppContent.innerHTML;
            document.title = doc.title;
        } else {
            // If the server was smart and only returned the partial
            newContent = html;
        }
        
        // Clean up previous event bindings before overwriting HTML
        this.cleanup();

        // Swap Content with enter animation
        this.appContent.classList.remove('page-leave', 'page-leave-active');
        this.appContent.innerHTML = newContent;
        this.appContent.classList.add('page-enter');
        
        // Re-execute scripts logic and wait for them to load
        this.executeScripts(this.appContent).then(() => {
            // Scroll to top
            window.scrollTo({ top: 0, behavior: 'smooth' });

            requestAnimationFrame(() => {
                this.appContent.classList.add('page-enter-active');
                setTimeout(() => {
                    this.appContent.classList.remove('page-enter', 'page-enter-active');
                    this.initPageInteractions();
                }, 400); // match css transition speed
            });
        });
    }
    
    executeScripts(container) {
        // Find all scripts within the injected content
        const scripts = container.querySelectorAll('script');
        if (scripts.length === 0) return Promise.resolve();

        const promises = Array.from(scripts).map(oldScript => {
            return new Promise((resolve) => {
                const newScript = document.createElement('script');
                newScript.async = false; // Maintain order
                Array.from(oldScript.attributes).forEach(attr => {
                    newScript.setAttribute(attr.name, attr.value);
                });
                // Copy inline content
                if (oldScript.innerHTML) {
                    newScript.innerHTML = oldScript.innerHTML;
                }
                
                // If it has a src, wait for it to load
                if (newScript.src) {
                    newScript.onload = () => resolve();
                    newScript.onerror = () => resolve(); // Resolve anyway to not block forever
                } else {
                    // Inline scripts execute immediately
                    resolve();
                }

                // Replace old with new to force browser execution
                oldScript.parentNode.replaceChild(newScript, oldScript);
                this.activeScripts.push(newScript);
            });
        });

        return Promise.all(promises);
    }
    
    cleanup() {
        // Inform custom scripts logic to unmount (e.g., destroy Chart.js instances to avoid memory leaks)
        if (window.charts) {
            Object.values(window.charts).forEach(chart => {
                if(chart && typeof chart.destroy === 'function') chart.destroy();
            });
            window.charts = {};
        }
        
        if (window.heatmap) {
             window.heatmap.remove();
             window.heatmap = null;
        }

        if (window.liveMapInstance) {
            try {
                window.liveMapInstance.remove();
            } catch (e) {
                console.warn("Map cleanup failed:", e);
            }
            window.liveMapInstance = null;
        }
        
        // Remove dynamically added scripts
        this.activeScripts.forEach(script => {
             if(script.parentNode) script.parentNode.removeChild(script);
        });
        this.activeScripts = [];
    }

    updateActiveNavLinks(url) {
        const path = new URL(url, window.location.origin).pathname;
        const navLinks = document.querySelectorAll('.nav-link');
        
        navLinks.forEach(link => {
            link.classList.remove('active');
            const linkPath = new URL(link.href, window.location.origin).pathname;
            if (linkPath === path) {
                link.classList.add('active');
            } else if (path !== '/' && linkPath !== '/' && path.startsWith(linkPath)) {
                // Secondary match for nested routes
                link.classList.add('active');
            }
        });
    }

    showLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.classList.add('active');
        }
    }

    hideLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.classList.remove('active');
        }
    }
    
    initPageInteractions() {
        // Any global interaction binding that needs to happen after new HTML paints
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(alert => {
            setTimeout(() => {
                alert.style.opacity = '0';
                setTimeout(() => {
                    alert.remove();
                }, 300);
            }, 5000);
        });
        
        // Specific Route Initializations
        if (document.getElementById('issueTypeChart')) { // Sniffing if we are on Analytics
            if (typeof initAnalytics === 'function') initAnalytics();
        }

        if (document.getElementById('map') && !window.liveMapInstance) {
            this.initLiveMap();
        }

        // Setup Smooth Scroll Fade-in Animations
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('fade-visible');
                    // Stop observing once visible if we don't want it to fade out again:
                    // observer.unobserve(entry.target); 
                }
            });
        }, { threshold: 0.15 });

        document.querySelectorAll('.card, .hero, .netflix-card, table').forEach(el => {
            el.classList.add('scroll-fade');
            observer.observe(el);
        });

        // Skeleton loading AI simulation
        const complexCards = document.querySelectorAll('.card, .netflix-card, .stat-card');
        complexCards.forEach(card => card.classList.add('skeleton'));
        setTimeout(() => {
            complexCards.forEach(card => card.classList.remove('skeleton'));
        }, 800);
        
        // 3D Tilt disabled - was causing page jump on dashboard mousemove events
    }

    initLiveMap() {
        const mapDiv = document.getElementById('map');
        if (!mapDiv || window.liveMapInstance) return;

        console.log("Central SPA Router: Initializing Live Monitor...");

        try {
            const map = L.map('map').setView([20.5937, 78.9629], 5);
            window.liveMapInstance = map;

            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                attribution: '&copy; <a href="https://carto.com/attributions">CARTO</a>'
            }).addTo(map);

            fetch('/api/live_complaints')
                .then(res => res.json())
                .then(data => {
                    data.forEach(c => {
                        let color = "#00f5ff";
                        if(c.issue_type === "Road") color = "#ff2a55";
                        else if(c.issue_type === "Electricity") color = "#ffb700";
                        else if(c.issue_type === "Garbage") color = "#22c55e";

                        const icon = L.divIcon({
                            className: 'custom-div-icon',
                            html: `<div style="width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; background: ${color}; box-shadow: 0 0 12px 2px ${color}, inset 0 0 4px rgba(0,0,0,0.5);"></div>`,
                            iconSize: [14, 14],
                            iconAnchor: [7, 7]
                        });

                        const popupHTML = `
                            <div style="min-width: 200px; padding: 5px; font-family: 'Poppins', sans-serif;">
                                ${c.image_url ? `
                                <div style="width: 100%; height: 130px; background: #000; border-radius: 8px; overflow: hidden; margin-bottom: 12px; border: 1px solid rgba(255,255,255,0.1);">
                                    <img src="${c.image_url}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='/static/img/placeholder.png'">
                                </div>` : ''}
                                <div style="color: ${color}; font-weight: 800; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px; letter-spacing: 1px;">${c.issue_type} REPORT</div>
                                <div style="font-weight: 700; font-size: 1.1rem; margin-bottom: 4px; color: #fff;">${c.id}</div>
                                <div style="font-size: 0.85rem; margin-bottom: 8px; color: #00f5ff; font-weight: 500;"><i class="fa-solid fa-location-dot"></i> ${c.area}</div>
                                <div style="font-size: 0.85rem; line-height: 1.6; color: rgba(255,255,255,0.8); max-height: 100px; overflow-y: auto;">
                                    ${c.description}
                                </div>
                            </div>
                        `;

                        // Add marker but handle the coordinates mapping if they are missing
                        const lat = c.lat || 20.5937;
                        const lng = c.lng || 78.9629;
                        L.marker([lat, lng], { icon }).addTo(map).bindPopup(popupHTML);
                    });
                })
                .catch(err => console.error("Map Data Sync Error:", err));
        } catch (e) {
            console.error("Map Initialization Failed:", e);
        }
    }
}


document.addEventListener('DOMContentLoaded', () => {
    // Initialize standard interactions that persist outside the #app-content
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const navLinks = document.getElementById('navLinks');

    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener('click', () => {
            navLinks.classList.toggle('show');
            const icon = mobileMenuBtn.querySelector('i');
            if (navLinks.classList.contains('show')) {
                icon.classList.remove('fa-bars');
                icon.classList.add('fa-xmark');
            } else {
                icon.classList.remove('fa-xmark');
                icon.classList.add('fa-bars');
            }
        });
    }
    
    // Auto-hide initial flashes
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    });

    // Start SPA
    window.spa = new SpaRouter();
});
