/**
 * auth.js — authentication: login, register, logout, and navbar
 * Depends on: common.js
 */

/* ========== AUTH STATE ========== */
let currentUser = null;
let authStateVersion = 0;

/* Check login status on page load (eager init to avoid race with orders.html) */
let loginStatusPromise = checkLoginStatus();

async function checkLoginStatus() {
    const requestVersion = ++authStateVersion;
    try {
        const resp = await fetch('/api/me', {
            credentials: 'same-origin',
            cache: 'no-store'
        });
        // A login/register/logout action may have completed while this request
        // was in flight. Never let an older /api/me response overwrite it.
        if (requestVersion !== authStateVersion) return currentUser;
        if (resp.ok) {
            const data = await resp.json();
            currentUser = data.user;
            updateNavbar(currentUser);
        } else {
            currentUser = null;
            updateNavbar(null);
        }
    } catch (err) {
        if (requestVersion !== authStateVersion) return currentUser;
        currentUser = null;
        updateNavbar(null);
    }
    return currentUser;
}

// Browsers may restore the function page from the back-forward cache without
// executing scripts again. Refresh auth state when that cached page reappears.
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        loginStatusPromise = checkLoginStatus();
    }
});

/* ========== NAVBAR ========== */
function updateNavbar(user) {
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const ordersLink = document.getElementById('orders-link');
    const navUser = document.getElementById('nav-user');
    const redeemBtn = document.getElementById('redeem-btn');

    if (user) {
        if (loginBtn) loginBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'inline-flex';
        if (ordersLink) ordersLink.style.display = 'inline-block';
        if (navUser) { navUser.style.display = 'inline-block'; navUser.textContent = user.email; }
        if (redeemBtn) redeemBtn.style.display = 'inline-flex';
        // Fetch balance
        fetch('/api/user/balance', { credentials: 'same-origin', cache: 'no-store' })
            .then(res => res.json())
            .then(data => {
                if (data.success !== false && typeof updateNavBalance === 'function') {
                    updateNavBalance(data.balance || 0);
                }
            })
            .catch(() => {});
    } else {
        if (loginBtn) loginBtn.style.display = 'inline-flex';
        if (logoutBtn) logoutBtn.style.display = 'none';
        if (ordersLink) ordersLink.style.display = 'none';
        if (navUser) navUser.style.display = 'none';
        if (redeemBtn) redeemBtn.style.display = 'none';
        if (typeof updateNavBalance === 'function') {
            updateNavBalance(0);
        }
    }
}

function updateNavBalance(balance) {
    const el = document.getElementById('nav-balance');
    if (!el) return;
    if (balance > 0) {
        el.textContent = balance + '词';
        el.style.display = 'inline-flex';
    } else {
        el.style.display = 'none';
    }
}

/* ========== AUTH MODAL ========== */
function showAuthModal(tab) {
    const modal = document.getElementById('auth-modal');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    switchAuthTab(tab);
    // Focus the close button for accessibility
    const closeBtn = modal.querySelector('.modal-close');
    if (closeBtn) setTimeout(() => closeBtn.focus(), 100);
}

function closeAuthModal() {
    const modal = document.getElementById('auth-modal');
    modal.style.display = 'none';
    document.body.style.overflow = '';
    // Clear errors
    const loginErr = document.getElementById('login-error');
    const regErr = document.getElementById('register-error');
    const regSuccess = document.getElementById('register-success');
    if (loginErr) loginErr.textContent = '';
    if (regErr) regErr.textContent = '';
    if (regSuccess) regSuccess.textContent = '';
    // Return focus to login button (only if visible)
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn && loginBtn.style.display !== 'none') loginBtn.focus();
}

/* Close auth modal on overlay click */
const authModalEl = document.getElementById('auth-modal');
if (authModalEl) {
    authModalEl.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeAuthModal();
    });
}

function switchAuthTab(tab) {
    // Update tabs
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    const tabEl = document.getElementById(`auth-tab-${tab}`);
    if (tabEl) tabEl.classList.add('active');

    // Show/hide forms
    const loginForm = document.getElementById('auth-form-login');
    const regForm = document.getElementById('auth-form-register');
    if (loginForm) loginForm.style.display = tab === 'login' ? 'flex' : 'none';
    if (regForm) regForm.style.display = tab === 'register' ? 'flex' : 'none';

    // Clear errors
    const loginErr = document.getElementById('login-error');
    const regErr = document.getElementById('register-error');
    const regSuccess = document.getElementById('register-success');
    if (loginErr) loginErr.textContent = '';
    if (regErr) regErr.textContent = '';
    if (regSuccess) regSuccess.textContent = '';
}

/* ========== LOGIN ========== */
async function handleLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');

    errorEl.textContent = '';

    if (!email || !password) {
        errorEl.textContent = '请填写邮箱和密码';
        return;
    }

    try {
        const resp = await _csrfFetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await resp.json();

        if (data.error) {
            errorEl.textContent = data.error;
            return;
        }

        authStateVersion++;
        currentUser = data.user;
        updateNavbar(currentUser);
        closeAuthModal();
        showToast(`欢迎回来，${currentUser.email}`, 'success');

        // Baidu Tongji: track login success
        if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'user', 'login_success']);

        if (typeof resumePendingPayment === 'function') resumePendingPayment();

        // Clear login fields
        document.getElementById('login-email').value = '';
        document.getElementById('login-password').value = '';
    } catch (err) {
        errorEl.textContent = '登录失败：' + getNetworkErrorMessage(err);
        console.error('登录出错:', err);
    }
}

/* ========== REGISTER ========== */
async function handleRegister() {
    const email = document.getElementById('register-email').value.trim();
    const password = document.getElementById('register-password').value;
    const confirm = document.getElementById('register-confirm').value;
    const errorEl = document.getElementById('register-error');
    const successEl = document.getElementById('register-success');

    errorEl.textContent = '';
    successEl.textContent = '';

    if (!email || !password || !confirm) {
        errorEl.textContent = '请填写所有字段';
        return;
    }

    if (password !== confirm) {
        errorEl.textContent = '两次密码输入不一致';
        return;
    }

    if (password.length < 6) {
        errorEl.textContent = '密码长度至少 6 位';
        return;
    }

    // Check password complexity: must include both letters and digits
    if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
        errorEl.textContent = '密码必须包含字母和数字';
        return;
    }
    if (!/[0-9]/.test(password)) {
        errorEl.textContent = '密码必须包含至少一个数字';
        return;
    }

    try {
        const resp = await _csrfFetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, confirm_password: confirm })
        });
        const data = await resp.json();

        if (data.error) {
            errorEl.textContent = data.error;
            return;
        }

        authStateVersion++;
        currentUser = data.user;
        updateNavbar(currentUser);
        closeAuthModal();
        showToast(`注册成功！欢迎，${currentUser.email}`, 'success');

        // Baidu Tongji: track register success
        if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'user', 'register_success']);

        if (typeof resumePendingPayment === 'function') resumePendingPayment();

        // Clear register fields
        document.getElementById('register-email').value = '';
        document.getElementById('register-password').value = '';
        document.getElementById('register-confirm').value = '';
    } catch (err) {
        errorEl.textContent = '注册失败：' + getNetworkErrorMessage(err);
        console.error('注册出错:', err);
    }
}

/* ========== PASSWORD VISIBILITY TOGGLE ========== */
function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    // Toggle eye icons
    const openIcon = btn.querySelector('.eye-open');
    const closedIcon = btn.querySelector('.eye-closed');
    if (openIcon && closedIcon) {
        openIcon.style.display = isPassword ? 'none' : '';
        closedIcon.style.display = isPassword ? '' : 'none';
    }
}

/* ========== LOGOUT ========== */
async function logout() {
    try {
        await _csrfFetch('/api/logout', { method: 'POST' });
        authStateVersion++;
        currentUser = null;
        updateNavbar(null);
        showToast('已退出登录', 'info');
    } catch (err) {
        showToast('退出失败', 'error');
    }
}

/* ========== DETAIL MODAL (used by orders page) ========== */
function showDetailModal(html) {
    // Create a temporary detail modal
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.style.display = 'flex';
    overlay.innerHTML = `
        <div class="modal" style="max-width:600px;">
            <button class="modal-close" onclick="closeDetailModal()">&times;</button>
            <div class="modal-body" style="text-align:left;">${html}</div>
        </div>
    `;
    overlay.id = 'detail-modal-overlay';
    overlay.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeDetailModal();
    });
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
}

function closeDetailModal() {
    const overlay = document.getElementById('detail-modal-overlay');
    if (overlay) {
        overlay.remove();
        document.body.style.overflow = '';
    }
}
