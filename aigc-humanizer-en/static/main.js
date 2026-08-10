/**
 * main.js — main page flow: upload, analyze, results display
 *          + orders page functions
 * Depends on: common.js, auth.js, payment.js (for index page)
 * Loaded last.
 */

/* ========== FILE UPLOAD ========== */
/* Click to upload (only on main page) */
if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) handleFileSelect(file);
    });

    // Drag & drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) handleFileSelect(file);
    });
}

function handleFileSelect(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['docx', 'txt', 'md'].includes(ext)) {
        showToast('仅支持 .docx、.txt、.md 格式', 'error');
        return;
    }
    if (file.size > 20 * 1024 * 1024) {
        showToast('文件大小不能超过 20MB', 'error');
        return;
    }
    uploadedFile = file;
    if (dropZone) {
        dropZone.classList.add('has-file');
        const dropTextEl = dropZone.querySelector('.drop-text');
        if (dropTextEl) dropTextEl.textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    }
    if (textInput) textInput.value = '';
    showToast(`已选择文件：${file.name}`, 'success');
}

/* ========== ANALYZE ========== */
if (uploadForm) {
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await analyzeText();
    });
}

async function analyzeText() {
    // Baidu Tongji: track analysis start
    if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'engagement', 'analyze_start']);
    showLoading();

    try {
        // File takes priority
        if (uploadedFile) {
            const formData = new FormData();
            formData.append('file', uploadedFile);
            const resp = await _csrfFetch('/api/analyze', { method: 'POST', body: formData });
            const data = await resp.json();
            await handleAnalyzeResponse(data);
        } else {
            const text = textInput.value.trim();
            if (!text) {
                hideLoading();
                showToast('请上传文档或粘贴英文文本', 'error');
                return;
            }
            const wordCount = text.split(/\s+/).filter(Boolean).length;
            if (wordCount < 10) {
                hideLoading();
                showToast('文本太短，请提供至少 50 个字符', 'error');
                return;
            }
            const resp = await _csrfFetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });
            const data = await resp.json();
            await handleAnalyzeResponse(data);
        }
    } catch (err) {
        hideLoading();
        showToast(getNetworkErrorMessage(err), 'error');
        console.error('分析出错:', err);
    }
}

async function handleAnalyzeResponse(data) {
    hideLoading();
    if (data.error) {
        if (data.login_required) {
            // 检测现在要求登录
            showToast('请先登录，注册即送 200 词免费额度', 'info');
            showAuthModal('login');
        } else {
            showToast(data.error, 'error');
        }
        return;
    }

    // Store format info for later download
    if (data.original_format) {
        sessionStorage.setItem('lastOriginalFormat', data.original_format);
        sessionStorage.setItem('lastOriginalFilename', data.original_filename || 'humanized');
    } else {
        sessionStorage.setItem('lastOriginalFormat', 'txt');
        sessionStorage.setItem('lastOriginalFilename', 'humanized');
    }

    // Store the full text in sessionStorage so it's available for rewrite
    // regardless of login state or server session persistence.
    if (data.text) {
        sessionStorage.setItem('lastExtractedText', data.text);
    }

    const wordCount = data.word_count;
    const price = data.price;
    const aiScore = data.analysis?.ai_score || 0;

    // Store AI score for display
    sessionStorage.setItem('lastAiScore', aiScore);

    // 检测完成，不展示分析结果页，直接进入一键改写流程
    const statusEl = document.getElementById('rewrite-status');
    if (statusEl) statusEl.textContent = '✅ 检测完成，正在改写...';
    updateRewriteButton(wordCount, price);
    scrollToResults();

    // 自动触发改写（余额够→对比，不够→充值）
    triggerRewrite(wordCount, price);

    // Baidu Tongji: track analysis complete
    if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'engagement', 'analyze_complete', '', aiScore]);

}

/* ========== REWRITE BUTTON STATE ========== */
const _rewriteController = { current: null };

function updateRewriteButton(wordCount, price) {
    const btn = document.getElementById('rewrite-btn');
    const btnText = document.getElementById('rewrite-btn-text');
    if (!btn || !btnText) return;

    // Cancel previous listeners (AbortController), preserving other listeners on the element
    if (_rewriteController.current) _rewriteController.current.abort();
    const ac = new AbortController();
    _rewriteController.current = ac;
    const signal = ac.signal;

    btnText.textContent = '🚀 一键改写';

    if (!currentUser) {
        // 未登录：点击提示注册登录（注册即送200词）
        btnText.textContent = '🚀 一键改写（登录后使用）';
        btn.addEventListener('click', () => {
            // Baidu Tongji: track rewrite button click (not logged in)
            if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'engagement', 'rewrite_click', 'not_logged_in']);
            showToast('请先登录，注册即送 200 词免费额度', 'info');
            showAuthModal('login');
        }, { signal });
        return;
    }

    // 已登录：绑定点击调用一键改写
    btn.addEventListener('click', () => {
        triggerRewrite(wordCount, price);
    }, { signal });
}

/* 读取当前选中的改写模式（下拉，默认 median） */
let _currentMode = 'median';
function getSelectedMode() {
    return _currentMode;
}

/* 初始化改写模式下拉（内嵌在"一键改写"按钮内） */
function initModeDropdown() {
    const toggle = document.getElementById('mode-toggle');
    const dropdown = document.getElementById('mode-dropdown');
    if (!toggle || !dropdown) return;

    // 点击箭头：只展开/收起下拉，不触发表单提交（改写）
    toggle.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const isOpen = dropdown.classList.toggle('open');
        toggle.classList.toggle('open', isOpen);
    });

    // 点击下拉选项：选中模式，不触发表单提交
    dropdown.querySelectorAll('.mode-dd-option').forEach((opt) => {
        opt.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            _currentMode = opt.dataset.mode;
            dropdown.querySelectorAll('.mode-dd-option').forEach(o => o.classList.remove('active'));
            opt.classList.add('active');
            dropdown.classList.remove('open');
            toggle.classList.remove('open');
        });
    });

    // 点击下拉内部空白处不关闭
    dropdown.addEventListener('click', (e) => e.stopPropagation());

    // 点击外部关闭
    document.addEventListener('click', () => {
        dropdown.classList.remove('open');
        toggle.classList.remove('open');
    });
}

initModeDropdown();

/* 一键改写：余额够→直接改写对比，不够→跳支付宝充值 */
async function triggerRewrite(wordCount, price) {
    let paymentBalance = 0;
    let paymentShortfall = wordCount;
    const mode = getSelectedMode();
    const statusEl = document.getElementById('rewrite-status');
    if (statusEl) statusEl.textContent = '⏳ 正在改写...';
    showLoading();
    try {
        const text = getCurrentText();
        const resp = await _csrfFetch('/api/rewrite', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, mode })
        });
        const data = await resp.json();

        if (data.success) {
            hideLoading();
            if (statusEl) statusEl.textContent = '';
            displayRewriteResult(data);

            // 更新余额显示
            if (data.payment_status === 'balance' && data.balance_remaining !== undefined) {
                if (typeof updateNavBalance === 'function') {
                    updateNavBalance(data.balance_remaining);
                }
                showToast(`✅ 改写完成！余额剩余 ${data.balance_remaining} 词`, 'success');
            } else {
                showToast('改写完成！', 'success');
            }

            // Baidu Tongji
            if (typeof _hmt !== 'undefined') {
                _hmt.push(['_trackEvent', 'engagement', 'rewrite_complete', data.payment_status || '']);
            }
            return;
        }

        hideLoading();
        if (statusEl) statusEl.textContent = '';

        if (data.need_payment) {
            paymentBalance = data.balance || 0;
            paymentShortfall = data.shortfall || wordCount;
            if (data.balance > 0) {
                showToast(`余额不足（当前 ${data.balance} 词，还差 ${data.shortfall} 词）`, 'info');
            }
        } else {
            showToast(data.error || '改写失败', 'error');
            return;
        }
    } catch (err) {
        hideLoading();
        if (statusEl) statusEl.textContent = '';
        console.warn('Balance rewrite failed, falling back to payment:', err);
    }

    // 余额不足：创建精确自动充值
    showPaymentModalWithAiScore(
        wordCount,
        paymentShortfall / wordCount * price,
        sessionStorage.getItem('lastAiScore') || 0,
        paymentBalance,
        paymentShortfall
    );
    setTimeout(() => {
        createPaymentOrder(wordCount, null, mode, paymentShortfall);
    }, 300);
}

/* ========== FAQ ACCORDION ========== */
document.querySelectorAll('.faq-question').forEach(btn => {
    btn.addEventListener('click', () => {
        const item = btn.parentElement;
        const isOpen = item.classList.contains('open');

        // Close all
        document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));

        // Toggle current
        if (!isOpen) item.classList.add('open');
    });
});

/* ========== KEYBOARD SHORTCUT ========== */
if (textInput) {
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            analyzeText();
        }
    });
}

/* ========== ORDERS PAGE ========== */
/* These functions are used by orders.html */
let currentOrderPage = 1;
let orderTotalPages = 1;

async function loadOrders(page) {
    // Ensure login status is fresh before loading orders
    if (!currentUser) {
        await checkLoginStatus();
        if (!currentUser) {
            window.location.href = '/';
            return;
        }
    }

    try {
        const resp = await fetch(`/api/orders?page=${page}&per_page=10`);
        if (resp.status === 401) {
            currentUser = null;
            updateNavbar(null);
            window.location.href = '/';
            return;
        }
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        currentOrderPage = data.page;
        orderTotalPages = data.pages;
        renderOrders(data.orders, data.total, data.page, data.pages);
    } catch (err) {
        showToast(getNetworkErrorMessage(err), 'error');
        console.error('加载订单失败:', err);
    }
}

function renderOrders(orders, total, page, pages) {
    const container = document.getElementById('orders-list');
    const emptyState = document.getElementById('orders-empty');
    const pagination = document.getElementById('orders-pagination');

    if (!container) return; // Not on orders page

    if (!orders || orders.length === 0) {
        container.innerHTML = '';
        if (emptyState) emptyState.style.display = 'block';
        if (pagination) pagination.style.display = 'none';
        return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (pagination) pagination.style.display = 'flex';

    container.innerHTML = orders.map(o => {
        const origScore = o.original_score || 0;
        const rewScore = o.rewritten_score || 0;
        const improvement = (origScore - rewScore).toFixed(1);
        const improved = improvement > 0 ? 'improved' : 'worsened';
        const improvementSign = improvement > 0 ? '↓' : '↑';
        const statusMap = {
            completed: ['已完成', 'completed'],
            processing: ['处理中', 'processing'],
            failed: ['处理失败', 'failed'],
            awaiting_balance: ['待补足余额', 'pending']
        };
        const [statusText, statusClass] = statusMap[o.status] || ['处理中', 'processing'];
        const isCompleted = o.status === 'completed';

        const createdDate = o.created_at ? new Date(o.created_at).toLocaleString('zh-CN') : '';
        const formatLabel = (o.original_format === 'pdf' ? 'DOCX' : (o.original_format || 'txt').toUpperCase());
        const rechargeMeta = o.recharge_words > 0
            ? `<span>💳 充值 ${Number(o.recharge_words).toLocaleString('zh-CN')} 词</span>`
            : '';
        const canRehumanize = ['paid', 'balance'].includes(o.payment_status);
        const actions = isCompleted ? `
            <button class="btn btn-outline btn-sm" onclick="viewOrderDetail('${o.order_id}')">查看详情</button>
            <button class="btn btn-outline btn-sm" onclick="reDownload('${o.order_id}', '${o.original_format === 'pdf' ? 'docx' : (o.original_format || 'txt')}')">⬇️ 下载</button>
            ${canRehumanize ? `<button class="btn btn-primary btn-sm" onclick="reHumanize('${o.order_id}')">🔄 继续优化</button>` : ''}
        ` : '';

        return `
            <div class="order-card">
                <div class="order-info">
                    <div class="order-id-line">
                        <div class="order-id-text">${o.order_id}</div>
                        <span class="order-status ${statusClass}">${statusText}</span>
                    </div>
                    <div class="order-meta">
                        <span>📅 ${createdDate}</span>
                        <span>📝 ${o.word_count || 0} 词</span>
                        <span class="order-format-badge">${formatLabel}</span>
                        ${rechargeMeta}
                        ${isCompleted ? `<span class="order-score-change ${improved}">
                            ${improvementSign} ${Math.abs(improvement)}%
                        </span>` : ''}
                    </div>
                </div>
                <div class="order-actions">
                    ${actions}
                </div>
            </div>
        `;
    }).join('');

    // Update pagination
    const pageInfo = document.getElementById('page-info');
    if (pageInfo) {
        pageInfo.textContent = `第 ${page} / ${pages} 页`;
    }

    const prevBtn = document.getElementById('page-prev');
    const nextBtn = document.getElementById('page-next');
    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= pages;
}

function goToPage(page) {
    if (page < 1 || page > orderTotalPages) return;
    loadOrders(page);
}

async function viewOrderDetail(orderId) {
    try {
        const resp = await fetch(`/api/orders/${orderId}`);
        if (!resp.ok) {
            showToast('获取订单详情失败', 'error');
            return;
        }
        const data = await resp.json();
        const order = data.order;

        const origScore = (order.original_score || 0).toFixed(1);
        const rewScore = (order.rewritten_score || 0).toFixed(1);
        const improvement = (order.original_score - order.rewritten_score).toFixed(1);

        const createdDate = order.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '';
        const expiresDate = order.expires_at ? new Date(order.expires_at).toLocaleString('zh-CN') : '';

        // Show detail in a modal-like overlay using the existing modal system
        const modalBody = `
            <div class="modal-icon">📋</div>
            <h3 class="modal-title">${order.order_id}</h3>
            <div class="order-detail-row">
                <span class="order-detail-label">原文预估 AI 率</span>
                <span class="order-detail-value">${origScore}%</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">改写后预估 AI 率</span>
                <span class="order-detail-value">${rewScore}%</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">改善</span>
                <span class="order-detail-value" style="color:var(--success)">↓ ${improvement}%</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">词数</span>
                <span class="order-detail-value">${order.word_count || 0} 词</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">格式</span>
                <span class="order-detail-value">${order.original_format === 'pdf' ? 'DOCX (原PDF)' : (order.original_format || 'txt').toUpperCase()}</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">创建时间</span>
                <span class="order-detail-value">${createdDate}</span>
            </div>
            <div class="order-detail-row">
                <span class="order-detail-label">过期时间</span>
                <span class="order-detail-value">${expiresDate}</span>
            </div>

            <div class="order-detail-actions">
                <button class="btn btn-primary btn-full" onclick="closeDetailModal(); reDownload('${order.order_id}', '${order.original_format === 'pdf' ? 'docx' : (order.original_format || 'txt')}')">⬇️ 下载</button>
            </div>
        `;

        showDetailModal(modalBody);

    } catch (err) {
        showToast(getNetworkErrorMessage(err), 'error');
        console.error('获取订单详情失败:', err);
    }
}

function reDownload(orderId, format) {
    window.open(`/api/download/${orderId}?format=${format || 'txt'}`, '_blank');
}

async function reHumanize(orderId) {
    const mode = getSelectedMode(); // 跟随当前改写模式（默认 median）
    try {
        showToast('⏳ 正在重新改写...', 'info');
        const resp = await _csrfFetch(`/api/orders/${orderId}/rehumanize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
        });
        const data = await resp.json();

        if (data.error) {
            showToast(data.error, 'error');
            return;
        }

        showToast(`✅ 改写完成！预估 AI 率降至 ${data.rewritten.ai_score}%`, 'success');

        // Navigate to home page and show result
        sessionStorage.setItem('rehumanizeResult', JSON.stringify(data));
        window.location.href = '/';

    } catch (err) {
        showToast(getNetworkErrorMessage(err), 'error');
        console.error('改写出错:', err);
    }
}
