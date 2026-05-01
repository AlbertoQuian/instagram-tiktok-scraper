function uiText(key) {
    return (window.APP_TEXT && window.APP_TEXT[key]) || key;
}

function showToast(message, type) {
    const container = document.getElementById('toast-container');
    if (!container) {
        alert(message);
        return;
    }
    const toast = document.createElement('div');
    toast.className = 'toast ' + (type || 'info');
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('visible'));
    setTimeout(() => {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 180);
    }, 3600);
}

function setButtonBusy(button, busyText) {
    if (!button) return '';
    const originalText = button.textContent;
    button.dataset.originalText = originalText;
    button.disabled = true;
    button.textContent = busyText;
    return originalText;
}

function restoreButton(button) {
    if (!button) return;
    button.disabled = false;
    button.textContent = button.dataset.originalText || button.textContent;
}

function postJSON(endpoint, payload) {
    return fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
    }).then(response => response.json().then(data => ({ ok: response.ok, data })));
}

function runTask(endpoint, payload, button) {
    setButtonBusy(button, uiText('starting'));
    postJSON(endpoint, payload).then(result => {
        if (!result.ok || result.data.error) {
            restoreButton(button);
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        if (result.data.task_id) {
            watchTask(result.data.task_id, button);
        } else if (result.data.success) {
            restoreButton(button);
            showToast(result.data.message || uiText('completed'), 'success');
        }
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function watchTask(taskId, button) {
    const panel = document.getElementById('task-panel');
    const logElement = document.getElementById('task-log');
    const statusElement = document.getElementById('task-status');
    if (!panel || !logElement || !statusElement) return;

    panel.classList.add('active');
    logElement.textContent = '';
    statusElement.className = 'task-status running';
    statusElement.textContent = uiText('running');
    let renderedLines = 0;

    const interval = setInterval(() => {
        fetch('/api/task/' + encodeURIComponent(taskId))
            .then(response => response.json())
            .then(task => {
                const lines = task.log || [];
                for (let index = renderedLines; index < lines.length; index += 1) {
                    const line = document.createElement('div');
                    line.textContent = lines[index];
                    logElement.appendChild(line);
                }
                renderedLines = lines.length;
                logElement.scrollTop = logElement.scrollHeight;

                if (task.status === 'completed') {
                    clearInterval(interval);
                    statusElement.className = 'task-status completed';
                    statusElement.textContent = uiText('completed');
                    restoreButton(button);
                } else if (task.status === 'failed') {
                    clearInterval(interval);
                    statusElement.className = 'task-status failed';
                    statusElement.textContent = uiText('failed') + (task.error ? ': ' + task.error : '');
                    restoreButton(button);
                }
            })
            .catch(error => {
                clearInterval(interval);
                statusElement.className = 'task-status failed';
                statusElement.textContent = uiText('connection_error');
                restoreButton(button);
                showToast(error.message, 'error');
            });
    }, 1200);
}

function selectedRunAccounts(platform) {
    const selected = [];
    document.querySelectorAll('.run-account:checked').forEach(input => {
        const instagram = input.dataset.instagram || '';
        const tiktok = input.dataset.tiktok || '';
        if ((platform === 'all' || platform === 'instagram') && instagram) selected.push(instagram);
        if ((platform === 'all' || platform === 'tiktok') && tiktok) selected.push(tiktok);
    });
    return selected;
}

function toggleRunAccounts(checked) {
    document.querySelectorAll('.run-account').forEach(input => { input.checked = checked; });
}

function launchScrape(button) {
    const platform = document.getElementById('run-platform')?.value || 'all';
    const accounts = selectedRunAccounts(platform);
    if (document.querySelectorAll('.run-account').length > 0 && accounts.length === 0) {
        showToast(uiText('select_account'), 'error');
        return;
    }
    const payload = {
        platform,
        category: document.getElementById('run-category')?.value || 'all',
        start_date: document.getElementById('run-start')?.value || '',
        end_date: document.getElementById('run-end')?.value || '',
        max_posts: document.getElementById('run-max-posts')?.value || '',
        download_media: document.getElementById('run-download-media')?.checked !== false,
        take_screenshots: document.getElementById('run-take-screenshots')?.checked !== false,
        export_after: document.getElementById('run-export-after')?.checked !== false,
        accounts,
    };
    runTask('/api/run/scrape', payload, button);
}

function launchScreenshots(button) {
    const platform = document.getElementById('run-platform')?.value || 'all';
    runTask('/api/run/screenshots', { platform }, button);
}

function exportCSV(button) {
    setButtonBusy(button, uiText('exporting'));
    postJSON('/api/run/export', {}).then(result => {
        restoreButton(button);
        if (!result.ok || result.data.error) {
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        window.location.href = '/download/csv';
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function collectAccounts() {
    const accounts = [];
    document.querySelectorAll('#accounts-editor .account-row:not(.account-row-head)').forEach(row => {
        const account = {
            account_name: row.querySelector('.account-name')?.value.trim() || '',
            account_id: row.querySelector('.account-id')?.value.trim() || '',
            category: row.querySelector('.account-category')?.value.trim() || '',
            instagram: row.querySelector('.account-instagram')?.value.trim() || '',
            tiktok: row.querySelector('.account-tiktok')?.value.trim() || '',
        };
        if (account.account_name || account.instagram || account.tiktok) accounts.push(account);
    });
    return accounts;
}

function addAccountRow() {
    const editor = document.getElementById('accounts-editor');
    if (!editor) return;
    const row = document.createElement('div');
    row.className = 'account-row';
    row.innerHTML = `
        <input class="input account-name" placeholder="${uiText('account_name_placeholder')}">
        <input class="input account-id" placeholder="${uiText('account_id_placeholder')}">
        <input class="input account-category" placeholder="${uiText('category_placeholder')}">
        <input class="input account-instagram" placeholder="${uiText('instagram_placeholder')}">
        <input class="input account-tiktok" placeholder="${uiText('tiktok_placeholder')}">
        <button type="button" class="btn danger compact-only" onclick="removeAccountRow(this)">${uiText('remove')}</button>
    `;
    editor.appendChild(row);
}

function removeAccountRow(button) {
    button.closest('.account-row')?.remove();
}

function saveAccounts(button) {
    setButtonBusy(button, uiText('saving'));
    postJSON('/api/settings/accounts', { accounts: collectAccounts() }).then(result => {
        restoreButton(button);
        if (!result.ok || result.data.error) {
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        showToast(result.data.message || uiText('saved'), 'success');
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function saveProjectSettings(button) {
    const payload = {
        project: document.getElementById('settings-project')?.value || '',
        start: document.getElementById('settings-start')?.value || '',
        end: document.getElementById('settings-end')?.value || '',
    };
    setButtonBusy(button, uiText('saving'));
    postJSON('/api/settings/project', payload).then(result => {
        restoreButton(button);
        if (!result.ok || result.data.error) {
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        showToast(result.data.message || uiText('saved'), 'success');
        setTimeout(() => window.location.reload(), 500);
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function saveInstagramCookies(button) {
    const cookies = document.getElementById('instagram-cookies')?.value || '';
    if (!cookies.trim()) {
        showToast(uiText('empty_cookies'), 'error');
        return;
    }
    try {
        JSON.parse(cookies);
    } catch (error) {
        showToast(uiText('invalid_json'), 'error');
        return;
    }
    setButtonBusy(button, uiText('saving'));
    postJSON('/api/cookies/instagram', { cookies }).then(result => {
        restoreButton(button);
        if (!result.ok || result.data.error) {
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        showToast(result.data.message || uiText('saved'), 'success');
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function saveTikTokCookies(button) {
    const cookies = document.getElementById('tiktok-cookies')?.value || '';
    if (!cookies.trim()) {
        showToast(uiText('empty_cookies'), 'error');
        return;
    }
    setButtonBusy(button, uiText('saving'));
    postJSON('/api/cookies/tiktok', { cookies }).then(result => {
        restoreButton(button);
        if (!result.ok || result.data.error) {
            showToast(result.data.error || uiText('failed'), 'error');
            return;
        }
        showToast(result.data.message || uiText('saved'), 'success');
    }).catch(error => {
        restoreButton(button);
        showToast(uiText('connection_error') + ': ' + error.message, 'error');
    });
}

function applyDataFilters() {
    const params = new URLSearchParams({
        platform: document.getElementById('filter-platform')?.value || 'all',
        category: document.getElementById('filter-category')?.value || 'all',
        account: document.getElementById('filter-account')?.value || 'all',
    });
    window.location.href = '/data?' + params.toString();
}
