/**
 * Comprehensive Session Management Service
 * Handles user session state, token refresh, and activity tracking
 */
class SessionManager {
    constructor() {
        this.accessToken = null;
        this.refreshToken = null;
        this.user = null;
        this.isAuthenticated = false;
        this.refreshTimer = null;
        this.activityTimer = null;
        this.sessionTimeout = 8 * 60 * 60 * 1000; // 8 hours
        this.refreshBuffer = 60 * 60 * 1000; // 1 hour before expiry
        this.lastActivity = Date.now();
        this.isRefreshing = false;
        this.refreshQueue = [];
        
        // Event listeners
        this.eventListeners = {
            'sessionExpired': [],
            'tokenRefreshed': [],
            'userActivity': [],
            'logout': []
        };
        
        this.init();
    }

    /**
     * Initialize session manager
     */
    init() {
        this.loadSession();
        this.setupActivityTracking();
        this.startTokenRefreshTimer();
        this.startSessionTimeoutTimer();
    }

    /**
     * Load session from localStorage
     */
    loadSession() {
        try {
            const accessToken = localStorage.getItem('access_token');
            const refreshToken = localStorage.getItem('refresh_token');
            const userData = localStorage.getItem('user');
            const lastActivity = localStorage.getItem('last_activity');

            if (accessToken && refreshToken && userData) {
                this.accessToken = accessToken;
                this.refreshToken = refreshToken;
                this.user = JSON.parse(userData);
                this.isAuthenticated = true;
                
                if (lastActivity) {
                    this.lastActivity = parseInt(lastActivity);
                }

                // Check if session is still valid
                if (this.isTokenExpired(accessToken)) {
                    console.log('Access token expired, attempting refresh...');
                    this.refreshAccessToken();
                } else {
                    console.log('Session restored successfully');
                    this.emit('tokenRefreshed', { user: this.user });
                }
            }
        } catch (error) {
            console.error('Error loading session:', error);
            this.clearSession();
        }
    }

    /**
     * Save session to localStorage
     */
    saveSession() {
        try {
            if (this.accessToken) {
                localStorage.setItem('access_token', this.accessToken);
            }
            if (this.refreshToken) {
                localStorage.setItem('refresh_token', this.refreshToken);
            }
            if (this.user) {
                localStorage.setItem('user', JSON.stringify(this.user));
            }
            localStorage.setItem('last_activity', this.lastActivity.toString());
        } catch (error) {
            console.error('Error saving session:', error);
        }
    }

    /**
     * Clear session data
     */
    clearSession() {
        this.accessToken = null;
        this.refreshToken = null;
        this.user = null;
        this.isAuthenticated = false;
        this.lastActivity = Date.now();
        
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('last_activity');
        
        this.stopTimers();
        this.emit('logout');
    }

    /**
     * Set authentication data
     */
    setAuthData(accessToken, refreshToken, user) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
        this.user = user;
        this.isAuthenticated = true;
        this.lastActivity = Date.now();
        
        this.saveSession();
        this.startTokenRefreshTimer();
        this.startSessionTimeoutTimer();
        
        this.emit('tokenRefreshed', { user: this.user });
    }

    /**
     * Check if token is expired or will expire soon
     */
    isTokenExpired(token, buffer = 0) {
        if (!token) return true;
        
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const now = Math.floor(Date.now() / 1000);
            return payload.exp <= (now + buffer);
        } catch (error) {
            console.error('Error parsing token:', error);
            return true;
        }
    }

    /**
     * Get time until token expires (in milliseconds)
     */
    getTokenExpiryTime(token) {
        if (!token) return 0;
        
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const now = Math.floor(Date.now() / 1000);
            return (payload.exp - now) * 1000;
        } catch (error) {
            console.error('Error parsing token expiry:', error);
            return 0;
        }
    }

    /**
     * Refresh access token
     */
    async refreshAccessToken() {
        if (this.isRefreshing) {
            // If already refreshing, queue the request
            return new Promise((resolve, reject) => {
                this.refreshQueue.push({ resolve, reject });
            });
        }

        if (!this.refreshToken) {
            this.clearSession();
            this.emit('sessionExpired');
            return;
        }

        this.isRefreshing = true;

        try {
            const response = await fetch('/auth/refresh', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ refresh_token: this.refreshToken }),
            });

            if (response.ok) {
                const data = await response.json();
                this.setAuthData(data.access_token, data.refresh_token, data.user);
                
                // Resolve queued requests
                this.refreshQueue.forEach(({ resolve }) => resolve());
                this.refreshQueue = [];
                
                console.log('Token refreshed successfully');
                return data;
            } else {
                throw new Error('Token refresh failed');
            }
        } catch (error) {
            console.error('Token refresh error:', error);
            this.clearSession();
            this.emit('sessionExpired');
            
            // Reject queued requests
            this.refreshQueue.forEach(({ reject }) => reject(error));
            this.refreshQueue = [];
            
            throw error;
        } finally {
            this.isRefreshing = false;
        }
    }

    /**
     * Make authenticated request with automatic token refresh
     */
    async authenticatedRequest(url, options = {}) {
        // Check if token needs refresh
        if (this.isTokenExpired(this.accessToken, this.refreshBuffer / 1000)) {
            try {
                await this.refreshAccessToken();
            } catch (error) {
                throw new Error('Authentication failed');
            }
        }

        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${this.accessToken}`,
            ...options.headers
        };

        const response = await fetch(url, {
            ...options,
            headers
        });

        // If 401, try to refresh token and retry
        if (response.status === 401) {
            try {
                await this.refreshAccessToken();
                
                // Retry with new token
                const retryHeaders = {
                    ...headers,
                    'Authorization': `Bearer ${this.accessToken}`
                };
                
                return await fetch(url, {
                    ...options,
                    headers: retryHeaders
                });
            } catch (error) {
                throw new Error('Authentication failed');
            }
        }

        return response;
    }

    /**
     * Start token refresh timer
     */
    startTokenRefreshTimer() {
        this.stopTokenRefreshTimer();
        
        if (!this.accessToken) return;

        const expiryTime = this.getTokenExpiryTime(this.accessToken);
        const refreshTime = Math.max(expiryTime - this.refreshBuffer, 60000); // At least 1 minute

        this.refreshTimer = setTimeout(() => {
            this.refreshAccessToken().catch(error => {
                console.error('Background token refresh failed:', error);
            });
        }, refreshTime);

        console.log(`Token refresh scheduled in ${Math.round(refreshTime / 1000)} seconds`);
    }

    /**
     * Stop token refresh timer
     */
    stopTokenRefreshTimer() {
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    /**
     * Start session timeout timer
     */
    startSessionTimeoutTimer() {
        this.stopSessionTimeoutTimer();
        
        this.activityTimer = setTimeout(() => {
            const timeSinceActivity = Date.now() - this.lastActivity;
            if (timeSinceActivity >= this.sessionTimeout) {
                console.log('Session timeout due to inactivity');
                this.clearSession();
                this.emit('sessionExpired');
            } else {
                // Restart timer with remaining time
                this.startSessionTimeoutTimer();
            }
        }, this.sessionTimeout);
    }

    /**
     * Stop session timeout timer
     */
    stopSessionTimeoutTimer() {
        if (this.activityTimer) {
            clearTimeout(this.activityTimer);
            this.activityTimer = null;
        }
    }

    /**
     * Stop all timers
     */
    stopTimers() {
        this.stopTokenRefreshTimer();
        this.stopSessionTimeoutTimer();
    }

    /**
     * Setup activity tracking
     */
    setupActivityTracking() {
        const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
        
        const updateActivity = () => {
            this.lastActivity = Date.now();
            this.saveSession();
            this.emit('userActivity');
        };

        // Throttle activity updates to avoid excessive calls
        let activityTimeout;
        const throttledUpdateActivity = () => {
            clearTimeout(activityTimeout);
            activityTimeout = setTimeout(updateActivity, 1000);
        };

        events.forEach(event => {
            document.addEventListener(event, throttledUpdateActivity, true);
        });

        // Also track visibility changes
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                updateActivity();
            }
        });
    }

    /**
     * Get current user
     */
    getCurrentUser() {
        return this.user;
    }

    /**
     * Get access token
     */
    getAccessToken() {
        return this.accessToken;
    }

    /**
     * Check if user is authenticated
     */
    isUserAuthenticated() {
        return this.isAuthenticated && this.accessToken && !this.isTokenExpired(this.accessToken);
    }

    /**
     * Get session info
     */
    getSessionInfo() {
        return {
            isAuthenticated: this.isAuthenticated,
            user: this.user,
            tokenExpiry: this.accessToken ? this.getTokenExpiryTime(this.accessToken) : 0,
            lastActivity: this.lastActivity,
            timeSinceActivity: Date.now() - this.lastActivity
        };
    }

    /**
     * Logout user
     */
    logout() {
        this.clearSession();
        this.emit('logout');
    }

    /**
     * Add event listener
     */
    on(event, callback) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].push(callback);
        }
    }

    /**
     * Remove event listener
     */
    off(event, callback) {
        if (this.eventListeners[event]) {
            this.eventListeners[event] = this.eventListeners[event].filter(cb => cb !== callback);
        }
    }

    /**
     * Emit event
     */
    emit(event, data) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in event listener for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Extend session timeout
     */
    extendSession() {
        this.lastActivity = Date.now();
        this.saveSession();
        this.startSessionTimeoutTimer();
    }

    /**
     * Get time until session expires
     */
    getTimeUntilSessionExpiry() {
        const timeSinceActivity = Date.now() - this.lastActivity;
        return Math.max(0, this.sessionTimeout - timeSinceActivity);
    }

    /**
     * Check if session is about to expire (within 5 minutes)
     */
    isSessionAboutToExpire() {
        return this.getTimeUntilSessionExpiry() <= 5 * 60 * 1000; // 5 minutes
    }
}

// Create global instance
window.sessionManager = new SessionManager();

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SessionManager;
}
