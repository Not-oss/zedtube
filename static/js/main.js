// Fonctions utilitaires
function getCSRFHeaders() {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    return {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
    };
}

function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `mb-4 p-4 rounded-lg ${type === 'error' ? 'bg-red-600' : 'bg-green-600'}`;
    alertDiv.textContent = message;
    document.querySelector('main').prepend(alertDiv);
    setTimeout(() => alertDiv.remove(), 5000);
}

// Gestion des dossiers
function setupFolderActions() {
    const container = document.getElementById('folders-container');
    if (!container) return;

    container.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const folderId = btn.closest('[data-folder-id]').dataset.folderId;
        const action = btn.dataset.action;

        try {
            if (action === 'delete') {
                // La suppression est gérée par le formulaire HTML
                return;
            }

            if (action === 'toggle-privacy') {
                const isPublic = btn.dataset.isPublic === 'true';
                await toggleFolderPrivacy(folderId, isPublic, btn);
            }

            if (action === 'change-thumbnail') {
                const input = document.createElement('input');
                input.type = 'file';
                input.accept = 'image/*';
                input.onchange = (e) => uploadFolderThumbnail(e.target, folderId);
                input.click();
            }
        } catch (error) {
            console.error('Error:', error);
            showAlert('Une erreur est survenue', 'error');
        }
    });
}

async function toggleFolderPrivacy(folderId, isCurrentlyPublic, button) {
    const response = await fetch(`/toggle_folder_privacy/${folderId}`, {
        method: 'POST',
        headers: getCSRFHeaders(),
        credentials: 'same-origin'
    });

    if (!response.ok) throw new Error('Erreur serveur');
    
    const data = await response.json();
    
    if (data.status === 'success') {
        const newState = !isCurrentlyPublic;
        button.dataset.isPublic = newState;
        button.title = newState ? 'Rendre privé' : 'Rendre public';
        button.classList.toggle('bg-blue-600', newState);
        button.classList.toggle('bg-black/70', !newState);
        showAlert(`Dossier ${newState ? 'public' : 'privé'} avec succès`);
    }
}

async function uploadFolderThumbnail(input, folderId) {
    if (!input.files[0]) return;

    const formData = new FormData();
    formData.append('thumbnail', input.files[0]);

    try {
        const response = await fetch(`/upload_folder_thumbnail/${folderId}`, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        });

        if (response.ok) {
            window.location.reload();
        } else {
            throw new Error('Erreur lors de l\'upload');
        }
    } catch (error) {
        console.error('Error:', error);
        showAlert('Erreur lors de l\'upload de la miniature', 'error');
    }
}

// Gestion des vidéos
function setupVideoActions() {
    const container = document.getElementById('videos-container');
    if (!container) return;

    container.addEventListener('click', async (e) => {
        const btn = e.target.closest('[data-action]');
        if (!btn) return;

        const videoId = btn.closest('[data-video-id]').dataset.videoId;
        const action = btn.dataset.action;

        try {
            if (action === 'delete-video') {
                // La suppression est gérée par le formulaire HTML
                return;
            }

            if (action === 'share') {
                await shareVideo(videoId);
            }
        } catch (error) {
            console.error('Error:', error);
            showAlert('Erreur lors du partage', 'error');
        }
    });
}

async function shareVideo(videoId) {
    try {
        const response = await fetch(`/generate_share_link/${videoId}`);
        if (!response.ok) throw new Error('Erreur serveur');
        
        const data = await response.json();
        
        try {
            await navigator.clipboard.writeText(data.share_link);
            showAlert('Lien copié dans le presse-papiers !');
        } catch (err) {
            // Fallback pour les navigateurs sans clipboard API
            const textarea = document.createElement('textarea');
            textarea.value = data.share_link;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            prompt('Copiez ce lien :', data.share_link);
        }
    } catch (error) {
        console.error('Error:', error);
        throw error;
    }
}

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    setupFolderActions();
    setupVideoActions();
});