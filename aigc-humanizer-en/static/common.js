/**
 * common.js — shared utilities, globals, and helpers
 * Loaded first; all other scripts depend on this.
 */

/* ========== CSRF HELPER ========== */
async function _csrfFetch(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const needsCsrf = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);
    let requestOptions = { ...options, credentials: 'same-origin' };

    /* Attach the token rendered into the page. */
    if (needsCsrf) {
        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        if (token) {
            requestOptions.headers = {
                ...requestOptions.headers,
                'X-CSRFToken': token
            };
        }
    }

    let response = await fetch(url, requestOptions);

    /*
     * A stale/restored page can hold a token from an expired server session.
     * Refresh it and retry exactly once when the backend identifies a CSRF
     * failure. Other 400 responses must pass through unchanged.
     */
    if (needsCsrf && response.status === 400 &&
        response.headers.get('X-CSRF-Error') === '1') {
        const tokenResponse = await fetch('/api/csrf-token', {
            credentials: 'same-origin',
            cache: 'no-store'
        });
        if (!tokenResponse.ok) return response;

        const data = await tokenResponse.json();
        if (!data.csrf_token) return response;

        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) meta.content = data.csrf_token;
        requestOptions.headers = {
            ...requestOptions.headers,
            'X-CSRFToken': data.csrf_token
        };
        response = await fetch(url, requestOptions);
    }

    return response;
}

/* ========== DOM REFS ========== */
/* Note: These may be null on pages like /orders — guard with null checks */
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const textInput = document.getElementById('text-input');
const analyzeBtn = document.getElementById('analyze-btn');
const uploadForm = document.getElementById('upload-form');

/* ========== SHARED STATE ========== */
let uploadedFile = null;

/* Store latest result info for download */
let latestResult = null;

/* ========== GET CURRENT TEXT ========== */
function getCurrentText() {
    const text = textInput ? textInput.value.trim() : '';
    if (text) return text;
    const extractedText = sessionStorage.getItem('lastExtractedText');
    return extractedText || null;
}

/* ========== ESCAPE HTML ========== */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/* ========== WORD DIFF (LCS algorithm) ========== */
let _rewriteOriginalText = '';
let _rewriteNewText = '';

/**
 * Word-level diff using simplified LCS algorithm.
 * Returns array of { type: 'added'|'deleted'|'unchanged', text: string }
 */
function computeWordDiff(original, modified) {
    // Tokenize into words + spaces/punctuation
    function tokenize(text) {
        return text.match(/\S+|\s+/g) || [];
    }

    const origTokens = tokenize(original);
    const newTokens = tokenize(modified);
    const m = origTokens.length;
    const n = newTokens.length;

    // LCS DP (limit size to avoid performance issues on very long texts)
    const MAX_LCS = 3000;
    let useLCS = m <= MAX_LCS && n <= MAX_LCS;

    if (useLCS) {
        // Build LCS table
        const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));
        for (let i = 1; i <= m; i++) {
            for (let j = 1; j <= n; j++) {
                if (origTokens[i - 1] === newTokens[j - 1]) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
                }
            }
        }

        // Backtrack to produce diff
        const result = [];
        let i = m, j = n;
        while (i > 0 || j > 0) {
            if (i > 0 && j > 0 && origTokens[i - 1] === newTokens[j - 1]) {
                result.push({ type: 'unchanged', text: origTokens[i - 1] });
                i--; j--;
            } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
                result.push({ type: 'added', text: newTokens[j - 1] });
                j--;
            } else {
                result.push({ type: 'deleted', text: origTokens[i - 1] });
                i--;
            }
        }
        result.reverse();
        return result;
    } else {
        // Fallback for very long texts: just show as-is
        return [{ type: 'unchanged', text: modified }];
    }
}

/**
 * Render diff as HTML
 */
function renderDiffHTML(diff) {
    return diff.map(item => {
        const escaped = escapeHtml(item.text);
        if (item.type === 'added') {
            return `<span class="diff-added">${escaped}</span>`;
        } else if (item.type === 'deleted') {
            return `<span class="diff-deleted">${escaped}</span>`;
        }
        return escaped;
    }).join('');
}

/**
 * Toggle between plain text and diff view
 */
function toggleDiffView() {
    const checked = document.getElementById('diff-toggle-checkbox').checked;
    const container = document.getElementById('rewrite-new-text');
    const legend = document.getElementById('diff-legend');

    if (checked) {
        const diff = computeWordDiff(_rewriteOriginalText, _rewriteNewText);
        container.innerHTML = renderDiffHTML(diff);
        legend.style.display = 'flex';
    } else {
        container.textContent = _rewriteNewText;
        legend.style.display = 'none';
    }
}

/* ========== RESET ========== */
function resetAnalysis() {
    const rs = document.getElementById('rewrite-section');
    if (rs) rs.style.display = 'none';
    uploadedFile = null;
    latestResult = null;
    if (dropZone) {
        dropZone.classList.remove('has-file');
        const dropTextEl = dropZone.querySelector('.drop-text');
        if (dropTextEl) dropTextEl.textContent = '拖拽文档到此处，或 点击选择文件';
    }
    if (textInput) textInput.value = '';
    if (fileInput) fileInput.value = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function resetAll() {
    resetAnalysis();
}

/* ========== SCROLLING ========== */
function scrollToUpload() {
    document.getElementById('upload-area').scrollIntoView({ behavior: 'smooth' });
}

function scrollToResults() {
    const rs = document.getElementById('rewrite-section');
    if (rs && rs.style.display !== 'none') {
        rs.scrollIntoView({ behavior: 'smooth' });
    } else {
        scrollToUpload();
    }
}

/* ========== LOADING ========== */
// 改写流程步骤定义（与 index.html #loading-steps 的 data-step 对应）
const LOADING_STEPS = ['parse', 'detect', 'rewrite', 'detect_again'];
// 每个步骤在等待期间的展示时长（ms）——用于在没有后端进度推送时按节奏推进
const LOADING_STEP_DURATION = 2000;
let _loadingStepsTimer = null;

function showLoading() {
    document.getElementById('loading-section').style.display = 'block';
    document.getElementById('rewrite-section').style.display = 'none';
    resetLoadingSteps();
    // 自动滚动到加载区域，避免用户停留在上传区看不到进度
    const ls = document.getElementById('loading-section');
    if (ls && typeof ls.scrollIntoView === 'function') {
        ls.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function hideLoading() {
    stopLoadingSteps();
    document.getElementById('loading-section').style.display = 'none';
}

function resetLoadingSteps() {
    // 重置所有步骤为"待执行"状态，并高亮第一步
    const stepsEl = document.getElementById('loading-steps');
    if (stepsEl) {
        stepsEl.querySelectorAll('.loading-step').forEach(li => {
            li.classList.remove('active', 'done');
        });
    }
    setLoadingStep(LOADING_STEPS[0]);
}

/**
 * 启动按节奏自动推进步骤的定时器（无后端推送时的兜底方案）。
 * 依次高亮 parse → detect → rewrite → detect_again，最后一步停留直到请求返回。
 * 返回一个 stop 清理函数；hideLoading 或请求返回时调用。
 */
function startLoadingSteps() {
    stopLoadingSteps();
    let idx = 0;
    resetLoadingSteps();
    _loadingStepsTimer = setInterval(() => {
        idx += 1;
        if (idx < LOADING_STEPS.length) {
            setLoadingStep(LOADING_STEPS[idx]);
        }
        // 到最后一站（detect_again）后不再推进，保持该步骤高亮
    }, LOADING_STEP_DURATION);
    return stopLoadingSteps;
}

function stopLoadingSteps() {
    if (_loadingStepsTimer) {
        clearInterval(_loadingStepsTimer);
        _loadingStepsTimer = null;
    }
}

/**
 * 标记某个步骤的状态。
 * @param {string} step - 步骤标识：parse | detect | rewrite | detect_again
 * @param {string} [status] - active（进行中，默认）| done（已完成）
 */
function setLoadingStep(step, status = 'active') {
    const stepsEl = document.getElementById('loading-steps');
    if (!stepsEl) return;
    const li = stepsEl.querySelector(`.loading-step[data-step="${step}"]`);
    if (!li) return;

    if (status === 'done') {
        li.classList.remove('active');
        li.classList.add('done');
    } else {
        // 激活当前步骤；同一步之前的步骤也标记为 done（按顺序推进）
        const items = Array.from(stepsEl.querySelectorAll('.loading-step'));
        let reached = false;
        items.forEach(it => {
            if (it === li) {
                reached = true;
                it.classList.add('active');
                it.classList.remove('done');
            } else if (!reached) {
                it.classList.add('done');
                it.classList.remove('active');
            } else {
                it.classList.remove('active', 'done');
            }
        });
    }
}

/* ========== COPY ========== */
function copyResult() {
    navigator.clipboard.writeText(_rewriteNewText).then(() => {
        showToast('已复制到剪贴板', 'success');
    });
}

async function downloadOrderFile(orderId, format = 'txt') {
    const url = `/api/download/${encodeURIComponent(orderId)}?format=${encodeURIComponent(format)}`;
    const deadline = Date.now() + 60 * 1000;
    let waitingShown = false;

    while (Date.now() < deadline) {
        const response = await fetch(url, { credentials: 'same-origin' });
        if (response.status === 202) {
            if (!waitingShown) {
                showToast('Word 文档正在生成，完成后将自动下载', 'info');
                waitingShown = true;
            }
            await new Promise(resolve => setTimeout(resolve, 1000));
            continue;
        }
        if (!response.ok) {
            let message = '下载失败，请稍后重试';
            try {
                const data = await response.json();
                if (data.error) message = data.error;
            } catch (err) { /* response was not JSON */ }
            throw new Error(message);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
        const filename = utf8Match
            ? decodeURIComponent(utf8Match[1])
            : (plainMatch ? plainMatch[1] : `humanized.${format}`);
        const blobUrl = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(blobUrl);
        return;
    }
    throw new Error('文档生成时间较长，请稍后重试下载');
}

async function runDownloadWithButton(button, action) {
    if (button?.disabled) return;
    const originalText = button?.textContent;
    if (button) {
        button.disabled = true;
        button.textContent = '正在准备...';
    }
    try {
        await action();
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}

/* ========== ANIMATE COUNTER ========== */
function animateCounter(elementId, start, end, duration) {
    const el = document.getElementById(elementId);
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + (end - start) * eased;
        el.textContent = Math.round(current);

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

/* ========== NETWORK ERROR HELPER ========== */
function getNetworkErrorMessage(err) {
    if (err instanceof TypeError && err.message === 'Failed to fetch') {
        return '网络连接失败，请检查网络后重试';
    }
    if (err instanceof TypeError && err.message.includes('NetworkError')) {
        return '网络连接失败，请检查网络后重试';
    }
    if (err instanceof SyntaxError) {
        return '服务器响应格式异常，请重试';
    }
    if (err.name === 'AbortError') {
        return '请求超时，请重试';
    }
    if (err.message && err.message.includes('timeout')) {
        return '请求超时，请重试';
    }
    if (err.message && err.message.includes('HTTP')) {
        return '服务器暂时不可用，请稍后重试';
    }
    // Fallback: return a generic message that still includes the error name for debugging
    return '请求失败，请重试';
}

/* ========== TOAST ========== */
function showToast(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/* (paragraph-list removed — no longer shown in results) */
