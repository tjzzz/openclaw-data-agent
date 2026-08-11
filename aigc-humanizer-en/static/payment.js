/**
 * payment.js — payment flow, QR code, polling, rewrite result display
 * Depends on: common.js, auth.js
 * Only loaded on index page (not orders page).
 */

/* ========== PAYMENT CONFIG ========== */
let paymentConfig = {
    adapter_type: 'mock',
    is_mock: true,
    recharge_packages: [2000, 5000, 10000]
};

async function fetchPaymentConfig() {
    try {
        const resp = await fetch('/api/payment-config');
        const data = await resp.json();
        if (data.adapter_type !== undefined) {
            paymentConfig = data;
        }
    } catch (err) {
        console.error('Failed to fetch payment config:', err);
        // Default to mock mode if fetch fails
        paymentConfig = {
            adapter_type: 'mock',
            is_mock: true,
            recharge_packages: [2000, 5000, 10000]
        };
    }
}

/* ========== PAYMENT MODAL ========== */
function showPaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        // Focus the close button for accessibility
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) setTimeout(() => closeBtn.focus(), 100);
    }
}

function showPaymentModalWithAiScore(wordCount, price, aiScore, balance = 0, shortfall = wordCount) {
    // Update display values
    document.getElementById('pay-word-count').textContent = `${wordCount} 词`;
    document.getElementById('pay-price').textContent = price === 0 ? '免费' : `¥${price.toFixed(2)}`;
    document.getElementById('pay-current-balance').textContent = `${balance} 词`;
    document.getElementById('pay-recharge-words').textContent = `${shortfall} 词`;

    // Update AI score display
    const aiScoreDisplay = document.getElementById('ai-score-display');
    if (aiScoreDisplay) {
        aiScoreDisplay.textContent = `${aiScore}%`;
        // Set color based on score
        if (aiScore < 20) {
            aiScoreDisplay.style.color = '#10b981';
        } else if (aiScore < 40) {
            aiScoreDisplay.style.color = '#f59e0b';
        } else if (aiScore < 60) {
            aiScoreDisplay.style.color = '#f97316';
        } else {
            aiScoreDisplay.style.color = '#ef4444';
        }
    }

    // Show QR loading state while API generates the QR code
    showQRLoading();

    // Show modal
    showPaymentModal();
}

function closePaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';

        // Clear polling timer to prevent leaks
        if (pollInterval) {
            clearInterval(pollInterval);
            pollInterval = null;
        }

        // Restore default payment UI state
        const qrSection = document.getElementById('payment-qr-section');
        if (qrSection) qrSection.style.display = 'none';

        // Return focus to the element that triggered the modal
        const rewriteBtn = document.getElementById('rewrite-btn');
        if (rewriteBtn) rewriteBtn.focus();
    }
}

/* Close modal on overlay click */
const paymentModal = document.getElementById('payment-modal');
if (paymentModal) {
    paymentModal.addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closePaymentModal();
    });
}

/* ========== QR LOADING HELPER ========== */
function showQRLoading() {
    const qs = document.getElementById('payment-qr-section');
    if (qs) qs.style.display = 'block';
    document.getElementById('qrcode-container').innerHTML = '';
    document.getElementById('poll-status').innerHTML = '⏳ 正在生成二维码...';
}

/* ========== QR CODE ========== */
function renderPaymentQR(order, wordCount, price) {
    const qrCode = order.qr_code;
    const formHtml = order.form_html;

    // Update payment modal content
    const actualWordCount = order.word_count || wordCount;
    const actualPrice = order.price !== undefined ? order.price : price;
    document.getElementById('pay-word-count').textContent = actualWordCount + ' 词';
    document.getElementById('pay-current-balance').textContent = `${order.balance || 0} 词`;
    document.getElementById('pay-recharge-words').textContent = `${order.recharge_words || 0} 词`;
    document.getElementById('pay-price').textContent = '¥' + parseFloat(actualPrice).toFixed(2);
    renderRechargeOptions(order);

    // Show QR section in modal
    const qrSection = document.getElementById('payment-qr-section');
    qrSection.style.display = 'block';

    // ★ P1: 将 mode 存入 data 属性，供 refreshQRCode 读取
    qrSection.dataset.payMode = order.mode || 'median';
    qrSection.dataset.rechargeWords = order.recharge_words || 0;
    // Reset poll status
    document.getElementById('poll-status').innerHTML = '⏳ 等待支付中...';
    document.getElementById('poll-timer').textContent = '';

    // Hide refresh button initially
    const refreshSection = document.getElementById('qr-refresh-section');
    if (refreshSection) {
        refreshSection.style.display = 'none';
    }

    // Show/hide mock payment button based on config
    const mockPaymentSection = document.getElementById('mock-payment-section');
    const mockBtn = document.getElementById('mock-pay-btn');

    if (paymentConfig.is_mock) {
        // Mock mode: show mock payment button
        if (mockPaymentSection) {
            mockPaymentSection.style.display = 'block';
        }
        if (mockBtn) {
            mockBtn.style.display = 'inline-block';
            // Remove old listeners by cloning
            const newMockBtn = mockBtn.cloneNode(true);
            mockBtn.parentNode.replaceChild(newMockBtn, mockBtn);
            newMockBtn.addEventListener('click', async () => {
                newMockBtn.disabled = true;
                newMockBtn.textContent = '处理中...';
                try {
                    const resp = await _csrfFetch(`/api/test/mock-payment/${order.order_id}`, { method: 'POST' });
                    const data = await resp.json();
                    if (data.success) {
                        showToast('充值成功，正在自动扣费并改写！', 'success');
                        document.getElementById('poll-status').innerHTML = '✅ 充值成功，正在改写...';
                    } else {
                        showToast(data.error || '模拟失败', 'error');
                        newMockBtn.disabled = false;
                        newMockBtn.textContent = '🧪 模拟支付成功（测试用）';
                    }
                } catch (err) {
                    showToast('请求失败', 'error');
                    newMockBtn.disabled = false;
                    newMockBtn.textContent = '🧪 模拟支付成功（测试用）';
                }
            });
        }
    } else {
        // Real payment mode: hide mock payment button
        if (mockPaymentSection) {
            mockPaymentSection.style.display = 'none';
        }
        if (mockBtn) {
            mockBtn.style.display = 'none';
        }
    }

    // Render QR code — two methods:
    // 1. iframe srcdoc (preferred): for qr_pay_mode=4 form_html
    // 2. qrcode.js (fallback): for qr_pay_mode=1 qr_code string
    const container = document.getElementById('qrcode-container');
    if (!container) return;

    container.innerHTML = '';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';

    if (formHtml) {
        // ★ 方案一：iframe + document.write 写入支付宝表单（qr_pay_mode=4）
        const iframe = document.createElement('iframe');
        iframe.width = '200';
        iframe.height = '200';
        iframe.frameBorder = '0';
        iframe.scrolling = 'no';
        iframe.style.border = 'none';
        iframe.style.overflow = 'hidden';
        container.appendChild(iframe);

        // 将表单 HTML 写入 iframe 文档
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        doc.open();
        doc.write(formHtml);
        doc.close();

        // ★ P4: iframe 自动提交超时检测 — 5秒后 iframe 未导航则显示兜底链接
        const iframeFallbackTimer = setTimeout(() => {
            try {
                // 检查 iframe 当前 URL 是否还是 about:blank 或 srcdoc
                const currentSrc = iframe.contentWindow?.location?.href || '';
                if (currentSrc === 'about:blank' || currentSrc.includes('about:srcdoc')) {
                    console.warn('[支付宝] iframe 表单提交可能被阻止，显示备用链接');
                    const fallbackLink = document.createElement('a');
                    fallbackLink.href = '#';
                    fallbackLink.textContent = '🔗 点击前往支付宝支付';
                    fallbackLink.style.cssText =
                        'display:block;margin-top:8px;color:var(--primary);font-size:0.85rem;';
                    fallbackLink.onclick = (e) => {
                        e.preventDefault();
                        // ★ P4(P3): 在新窗口中完整写入 form HTML，自动 POST 提交（非直接打开 action URL）
                        const win = window.open('', '_blank');
                        if (win) {
                            win.document.write(formHtml);
                            win.document.close();
                        }
                    };
                    container.parentNode?.appendChild(fallbackLink);
                }
            } catch (e) {
                // 跨域安全限制下 contentWindow 不可访问，属于正常情况（已导航到支付宝域名）
                // 跨域说明 iframe 已离开空白页并进入支付宝。
            }
        }, 5000);

        // iframe 加载表单后自动执行 <script>document.forms[0].submit();</script>
        // 表单提交后 iframe 自动导航到支付宝网关，展示二维码页面
    } else if (qrCode && typeof QRCode !== 'undefined') {
        // ★ 方案二（降级）：qrcode.js 渲染（qr_pay_mode=1 或其他）
        new QRCode(container, {
            text: qrCode,
            width: 150,
            height: 150,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.M
        });
    } else if (qrCode) {
        // 最差降级：二维码链接
        container.innerHTML = `<a href="${qrCode}" target="_blank" style="color:var(--primary);font-size:0.85rem;">点击打开支付宝付款</a>`;
    }
}

function renderRechargeOptions(order) {
    const container = document.getElementById('recharge-options');
    if (!container) return;
    const shortfall = Number(order.shortfall || order.recharge_words || 0);
    const current = Number(order.recharge_words || shortfall);
    const configuredPackages = Array.isArray(paymentConfig.recharge_packages)
        ? paymentConfig.recharge_packages.map(Number).filter(Number.isFinite)
        : [2000, 5000, 10000];
    const choices = [shortfall, ...configuredPackages]
        .filter(words => words >= shortfall)
        .filter((words, index, array) => array.indexOf(words) === index);

    container.innerHTML = `
        <div class="recharge-options-label">选择充值档位</div>
        <div class="recharge-option-list">
            ${choices.map(words => `
                <button type="button" class="recharge-option ${words === current ? 'active' : ''}"
                        onclick="changeRechargePackage(${words})">
                    ${words === shortfall ? '刚好补足' : Number(words).toLocaleString('zh-CN') + '词'}
                    <small>${Number(words).toLocaleString('zh-CN')}词</small>
                </button>
            `).join('')}
        </div>`;
}

async function changeRechargePackage(rechargeWords) {
    const qrSection = document.getElementById('payment-qr-section');
    const wordCount = parseInt(document.getElementById('pay-word-count').textContent.replace(/[^0-9]/g, ''));
    const mode = qrSection ? (qrSection.dataset.payMode || 'median') : 'median';
    if (Number(qrSection?.dataset.rechargeWords || 0) === rechargeWords) return;
    showQRLoading();
    await createPaymentOrder(wordCount, null, mode, rechargeWords);
}

async function refreshQRCode() {
    const refreshBtn = document.getElementById('qr-refresh-btn');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.textContent = '刷新中...';
    }

    try {
        const wordCount = parseInt(document.getElementById('pay-word-count').textContent.replace(/[^0-9]/g, ''));
        // ★ P1: 从 data 属性读取用户之前选的 mode，避免硬编码丢失
        const qrSection = document.getElementById('payment-qr-section');
        const payMode = qrSection ? (qrSection.dataset.payMode || 'median') : 'median';
        const rechargeWords = Number(qrSection?.dataset.rechargeWords || 0) || null;

        await createPaymentOrder(wordCount, null, payMode, rechargeWords);

        showToast('二维码已刷新', 'success');
    } catch (err) {
        showToast('刷新失败，请重试', 'error');
        console.error('Failed to refresh QR code:', err);
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = '🔄 刷新二维码';
        }
    }
}

/* ========== PAYMENT POLLING ========== */
let pollInterval = null;
let pollCount = 0;
const MAX_POLL_COUNT = 600; // ★ P5: 30 minutes (原200=10分钟，但后台改写可能排队)
const POLL_INTERVAL_MS = 3000;

function startPaymentPolling(orderId) {
    // Clear any existing polling
    if (pollInterval) {
        clearInterval(pollInterval);
        }
        pollCount = 0;

        // 倒计时初始值（与支付宝 timeout_express 一致）
        const TOTAL_TIMEOUT = 600; // 10 minutes in seconds

        pollInterval = setInterval(async () => {
            pollCount++;

            // 更新倒计时
            const remaining = Math.max(0, TOTAL_TIMEOUT - pollCount * Math.round(POLL_INTERVAL_MS / 1000));
            const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
            const ss = String(remaining % 60).padStart(2, '0');
            document.getElementById('poll-status').innerHTML = `⏳ 等待支付中 ${mm}:${ss}`;

            if (pollCount > MAX_POLL_COUNT) {
            clearInterval(pollInterval);
            document.getElementById('poll-status').innerHTML = '⏰ 支付超时，请联系客服';
            return;
        }

        try {
            const resp = await fetch(`/api/payment-status/${orderId}`);
            if (!resp.ok) {
                let message = '支付状态查询失败，请稍后重试';
                try {
                    const errorData = await resp.json();
                    if (errorData.error) message = errorData.error;
                } catch (_) {
                    // 非 JSON 错误响应使用通用提示。
                }
                clearInterval(pollInterval);
                pollInterval = null;
                document.getElementById('poll-status').textContent = '❌ ' + message;
                showToast(message, 'error');
                return;
            }
            const data = await resp.json();

            if (data.error) {
                // Order not found or access denied — stop polling
                clearInterval(pollInterval);
                document.getElementById('poll-status').innerHTML = '❌ ' + data.error;
                return;
            }

            if (data.status === 'awaiting_balance') {
                clearInterval(pollInterval);
                document.getElementById('poll-status').innerHTML = '⚠️ ' + (data.message || '余额仍不足');
                if (typeof updateNavBalance === 'function' && data.balance_after !== null) {
                    updateNavBalance(data.balance_after);
                }
                return;
            }

            if (data.payment_status === 'paid' || data.status === 'processing') {
                // 充值成功，进入改写阶段：切换到主页面真实进度页，而不是停在充值弹窗
                document.getElementById('poll-status').innerHTML = '✅ 充值成功，正在改写...';
                clearInterval(pollInterval);
                pollInterval = null;
                closePaymentModal();
                startBalanceRewritePolling(orderId, data.balance_after);
                return;
            }

            if (data.status === 'failed') {
                clearInterval(pollInterval);
                document.getElementById('poll-status').innerHTML = '❌ 改写失败，请稍后重试';
                showToast('改写失败，请稍后重试', 'error');
            } else if (data.payment_status === 'expired') {
                clearInterval(pollInterval);
                document.getElementById('poll-status').innerHTML = '⏰ 订单已超时，请重新检测';
                showToast('订单已超时', 'error');
            }
        } catch (err) {
            // Silently continue polling on error
            console.warn('Payment polling error:', err);
        }
    }, 3000);
}

/* ========== CREATE PAYMENT ORDER ========== */
function savePendingPayment(wordCount, price, mode, rechargeWords) {
    sessionStorage.setItem('pendingPaidAnalysis', 'true');
    sessionStorage.setItem('pendingPaymentInfo', JSON.stringify({
        wordCount,
        price,
        mode: mode || 'median',
        rechargeWords
    }));
}

function resumePendingPayment() {
    if (!currentUser || sessionStorage.getItem('pendingPaidAnalysis') !== 'true') return false;

    let pendingInfo;
    try {
        pendingInfo = JSON.parse(sessionStorage.getItem('pendingPaymentInfo') || 'null');
    } catch (err) {
        pendingInfo = null;
    }

    const wordCount = Number(pendingInfo?.wordCount);
    const price = Number(pendingInfo?.price);
    if (!Number.isFinite(wordCount) || wordCount <= 0 ||
        !Number.isFinite(price) || price < 0) {
        sessionStorage.removeItem('pendingPaidAnalysis');
        sessionStorage.removeItem('pendingPaymentInfo');
        return false;
    }

    sessionStorage.removeItem('pendingPaidAnalysis');
    sessionStorage.removeItem('pendingPaymentInfo');
    setTimeout(() => {
        const aiScore = Number(sessionStorage.getItem('lastAiScore') || 0);
        const shortfall = Number(pendingInfo.rechargeWords) || wordCount;
        const balance = Math.max(0, wordCount - shortfall);
        showPaymentModalWithAiScore(wordCount, price, aiScore, balance, shortfall);
        createPaymentOrder(
            wordCount,
            price,
            pendingInfo.mode || 'median',
            pendingInfo.rechargeWords ?? null
        );
    }, 300);
    return true;
}

async function createPaymentOrder(wordCount, price, mode = 'median', rechargeWords = null) {
    // Check login first
    if (!currentUser) {
        savePendingPayment(wordCount, price, mode, rechargeWords);
        showAuthModal('login');
        showToast('请先登录，登录后将自动创建订单', 'info');
        return;
    }

    const text = getCurrentText();
    if (!text) {
        showToast('没有可分析的文本，请重新上传', 'error');
        closePaymentModal();
        return;
    }

    try {
        const resp = await _csrfFetch('/api/create-payment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                mode: mode || 'median',
                recharge_words: rechargeWords
            })
        });
        const data = await resp.json();

        if (data.error) {
            if (data.login_required) {
                savePendingPayment(wordCount, price, mode, rechargeWords);
                closePaymentModal();
                showAuthModal('login');
                return;
            }
            showToast(data.error, 'error');
            closePaymentModal();
            return;
        }

        // Render payment UI with QR code in modal
        renderPaymentQR(data.order, wordCount, data.order.price);

        // Start polling for payment status
        startPaymentPolling(data.order.order_id);

        // Baidu Tongji: track payment start
        if (typeof _hmt !== 'undefined') _hmt.push(['_trackEvent', 'ecommerce', 'payment_start', '', data.order.price]);

    } catch (err) {
        showToast(getNetworkErrorMessage(err), 'error');
        console.error('创建订单失败:', err);
        // Don't close modal, let user try again
    }
}

/* ========== LEGACY: PAID ANALYSIS ========== */
async function startPaidAnalysis() {
    if (!currentUser) {
        showAuthModal('login');
        showToast('请先登录后继续', 'info');
        return;
    }
    createPaymentOrder();
}

/* ========== DISPLAY REWRITE RESULT ========== */
function displayRewriteResult(data) {
    const section = document.getElementById('rewrite-section');
    section.style.display = 'block';

    document.getElementById('rewrite-order-id').textContent = `订单号：${data.order_id}`;

    // Store latest result for download
    // Note: PDF originals are downloaded as DOCX (backend auto-converts)
    let origFormat = data.original_format || sessionStorage.getItem('lastOriginalFormat') || 'txt';
    if (origFormat === 'pdf') origFormat = 'docx';
    latestResult = {
        orderId: data.order_id,
        originalFormat: origFormat,
        originalFilename: data.original_filename || sessionStorage.getItem('lastOriginalFilename') || 'humanized'
    };

    // Update download button text with format hint
    const fmt = latestResult.originalFormat;
    const downloadBtn = document.getElementById('download-btn');
    downloadBtn.textContent = `⬇️ 下载为 ${fmt.toUpperCase()}`;

    // Original
    document.getElementById('orig-score-badge').textContent = `预估 AI 率 ${data.original.ai_score}%`;
    document.getElementById('orig-score-badge').style.background =
        data.original.ai_score > 40 ? '#fde8e8' : data.original.ai_score > 20 ? '#fef3c7' : '#d1fae5';
    document.getElementById('orig-risk').textContent = data.original.risk_level;
    document.getElementById('rewrite-original-text').textContent = data.original.text;

    // Rewritten
    document.getElementById('new-score-badge').textContent = `预估 AI 率 ${data.rewritten.ai_score}%`;
    document.getElementById('new-risk').textContent = data.rewritten.risk_level;
    document.getElementById('improvement-badge').textContent = `↓ ${data.improvement}%`;
    document.getElementById('improvement-badge').style.background =
        data.improvement > 30 ? '#10b981' : data.improvement > 15 ? '#f59e0b' : '#6b7280';

    // Store raw texts for diff comparison
    _rewriteOriginalText = data.original.text;
    _rewriteNewText = data.rewritten.text;
    document.getElementById('rewrite-new-text').textContent = _rewriteNewText;

    // Reset diff toggle
    document.getElementById('diff-toggle-checkbox').checked = false;
    document.getElementById('diff-legend').style.display = 'none';

    showToast(`✅ 改写完成！预估 AI 率从 ${data.original.ai_score}% 降至 ${data.rewritten.ai_score}%`, 'success');

    setTimeout(() => {
        section.scrollIntoView({ behavior: 'smooth' });
    }, 300);
}

/* ========== DOWNLOAD ========== */
async function downloadResult() {
    const downloadBtn = document.getElementById('download-btn');
    if (latestResult) {
        try {
            await runDownloadWithButton(
                downloadBtn,
                () => downloadOrderFile(latestResult.orderId, latestResult.originalFormat)
            );
        } catch (err) {
            showToast(err.message || '下载失败，请稍后重试', 'error');
        }
    } else {
        // Fallback: client-side text download
        const blob = new Blob([_rewriteNewText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'humanized_text.txt';
        a.click();
        URL.revokeObjectURL(url);
    }
}

/* ========== GLOBAL ESCAPE KEY ========== */
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const paymentModalEl = document.getElementById('payment-modal');
        const authModalEl = document.getElementById('auth-modal');
        const redeemModalEl = document.getElementById('redeem-modal');
        if (paymentModalEl && paymentModalEl.style.display === 'flex') {
            closePaymentModal();
        } else if (authModalEl && authModalEl.style.display === 'flex') {
            closeAuthModal();
        } else if (redeemModalEl && redeemModalEl.style.display === 'flex') {
            closeRedeemModal();
        }
    }
});

/* ========== DOM READY: INIT & RESTORE SESSION ========== */
document.addEventListener('DOMContentLoaded', () => {
    // Fetch payment config on page load
    fetchPaymentConfig();

    loginStatusPromise.then((user) => {
        if (user) resumePendingPayment();
    });
});
