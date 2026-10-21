export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

export function toast(message, error = false) {
    const region = document.getElementById('toast-region');
    const node = document.createElement('div');
    node.className = error ? 'toast toast-error' : 'toast';
    node.textContent = message;
    region.append(node);
    while (region.children.length > 3) region.firstElementChild.remove();
    setTimeout(() => node.remove(), 5000);
}

export async function api(url, data, { method = 'POST', signal } = {}) {
    const response = await fetch(url, {
        method, signal, credentials: 'same-origin',
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
        },
        ...(method === 'GET' ? {} : { body: JSON.stringify(data ?? {}) }),
    });
    let payload;
    try {
        payload = await response.json();
    } catch {
        throw new ApiError('Не удалось выполнить запрос. Обновите страницу и повторите.', response.status);
    }
    if (!response.ok) throw new ApiError(payload.message || 'Не удалось выполнить действие.', response.status);
    return payload;
}

export function confirmAction(message) {
    const dialog = document.getElementById('confirm-dialog');
    document.getElementById('confirm-message').textContent = message;
    return new Promise(resolve => {
        const accept = document.getElementById('confirm-accept');
        const cancel = document.getElementById('confirm-cancel');
        const onAccept = () => dialog.close('yes');
        const onCancel = () => dialog.close('no');
        const onClose = () => {
            accept.removeEventListener('click', onAccept);
            cancel.removeEventListener('click', onCancel);
            resolve(dialog.returnValue === 'yes');
        };
        accept.addEventListener('click', onAccept);
        cancel.addEventListener('click', onCancel);
        dialog.addEventListener('close', onClose, { once: true });
        dialog.returnValue = '';
        dialog.showModal();
        cancel.focus();
    });
}
