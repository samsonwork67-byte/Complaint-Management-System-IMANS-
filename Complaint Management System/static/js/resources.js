// resources.js — Resources section dynamic loading and admin CRUD

const RESOURCE_ICONS = {
    book: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>`,
    document: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
    </svg>`,
    people: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>`,
    shield: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>`
};

let resourcesData = [];

async function loadResources() {
    try {
        const res = await fetch('/api/resources');
        resourcesData = await res.json();
        renderResources();
    } catch (err) {
        console.error('Failed to load resources:', err);
    }
}

function renderResources() {
    const grid = document.querySelector('.resources-grid');
    if (!grid) return;
    grid.innerHTML = '';

    resourcesData.forEach(resource => {
        const card = document.createElement('div');
        card.className = 'resource-card reveal';

        card.innerHTML = `
            <div class="resource-icon-wrapper">
                ${RESOURCE_ICONS[resource.icon] || RESOURCE_ICONS.document}
            </div>
            ${isAdmin ? `
            <div class="card-menu resource-card-menu">
                <button class="menu-btn" onclick="toggleResourceMenu(${resource.id})" aria-label="Resource actions">...</button>
                <div id="resource-menu-${resource.id}" class="menu-dropdown">
                    <button onclick="openEditResourceForm(${resource.id})">Edit</button>
                    <button onclick="deleteResource(${resource.id})">Delete</button>
                </div>
            </div>` : ''}
            <h3>${escapeHtml(resource.title)}</h3>
            <p class="resource-meta">PDF • ${escapeHtml(resource.file_size)} • Updated ${escapeHtml(resource.updated_date)}</p>
            <a href="${escapeHtml(resource.file_url)}" download class="btn btn-outline-teal" style="margin-top:auto;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                    stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                Download
            </a>
        `;

        grid.appendChild(card);

        // re-observe for reveal animation
        if (window.__revealObserver) {
            window.__revealObserver.observe(card);
        } else {
            card.classList.add('active');
        }
    });

    if (isAdmin) {
        const addCard = document.createElement('div');
        addCard.className = 'resource-card add-resource-card';
        addCard.innerHTML = `
            <button type="button" class="add-resource-btn" onclick="openAddResourceForm()">+ Add Resource</button>
        `;
        grid.appendChild(addCard);
    }
}

function toggleResourceMenu(id) {
    const menu = document.getElementById(`resource-menu-${id}`);
    if (!menu) return;
    document.querySelectorAll('.resource-card-menu .menu-dropdown').forEach(dropdown => {
        if (dropdown !== menu) dropdown.style.display = 'none';
    });
    menu.style.display = menu.style.display === 'flex' ? 'none' : 'flex';
}

function ensureResourceFormOverlay() {
    let overlay = document.getElementById('resourceFormOverlay');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.id = 'resourceFormOverlay';
    overlay.className = 'overlay';
    overlay.innerHTML = `
        <div class="overlay-content">
            <h3 id="resourceFormTitle">Add Resource</h3>
            <form id="resourceForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="resourceTitle" class="form-control" required>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="resourceDescription" class="form-control"></textarea>
                </div>
                <div class="form-group">
                    <label>Icon</label>
                    <select id="resourceIcon" class="form-control">
                        <option value="document">Document</option>
                        <option value="book">Book</option>
                        <option value="people">People</option>
                        <option value="shield">Shield</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Updated Date (e.g. May 2026)</label>
                    <input type="text" id="resourceUpdatedDate" class="form-control" required>
                </div>
                <div class="form-group">
                    <label>Upload File (PDF)</label>
                    <input type="file" id="resourceFile" class="form-control" accept=".pdf,.doc,.docx">
                    <small id="resourceFileHint" style="color:var(--text-medium);display:none;">Leave blank to keep current file.</small>
                </div>
                <div style="margin-top:15px; text-align:right;">
                    <button type="submit" class="btn btn-success">Save</button>
                    <button type="button" class="btn btn-secondary" id="resourceFormCancel">Cancel</button>
                </div>
            </form>
        </div>
    `;

    overlay.querySelector('#resourceFormCancel').addEventListener('click', closeResourceForm);
    overlay.addEventListener('click', e => {
        if (e.target === overlay) closeResourceForm();
    });
    overlay.querySelector('#resourceForm').addEventListener('submit', submitResourceForm);
    document.body.appendChild(overlay);
    return overlay;
}

function openAddResourceForm() {
    const overlay = ensureResourceFormOverlay();
    overlay.querySelector('#resourceFormTitle').textContent = 'Add Resource';
    overlay.querySelector('#resourceForm').reset();
    overlay.querySelector('#resourceForm').dataset.editId = '';
    overlay.querySelector('#resourceFile').required = true;
    overlay.querySelector('#resourceFileHint').style.display = 'none';
    overlay.style.display = 'flex';
}

function openEditResourceForm(id) {
    const resource = resourcesData.find(r => r.id === id);
    if (!resource) return;

    const overlay = ensureResourceFormOverlay();
    overlay.querySelector('#resourceFormTitle').textContent = 'Edit Resource';
    overlay.querySelector('#resourceTitle').value = resource.title;
    overlay.querySelector('#resourceDescription').value = resource.description || '';
    overlay.querySelector('#resourceIcon').value = resource.icon || 'document';
    overlay.querySelector('#resourceUpdatedDate').value = resource.updated_date;
    overlay.querySelector('#resourceForm').dataset.editId = id;
    overlay.querySelector('#resourceFile').required = false;
    overlay.querySelector('#resourceFileHint').style.display = 'block';
    overlay.style.display = 'flex';
}

function closeResourceForm() {
    const overlay = document.getElementById('resourceFormOverlay');
    if (overlay) overlay.style.display = 'none';
}

async function submitResourceForm(e) {
    e.preventDefault();
    // Close modal immediately on Save click
    closeResourceForm();
    const overlay = document.getElementById('resourceFormOverlay');
    const editId = overlay.querySelector('#resourceForm').dataset.editId;

    const formData = new FormData();
    formData.append('title', overlay.querySelector('#resourceTitle').value);
    formData.append('description', overlay.querySelector('#resourceDescription').value);
    formData.append('icon', overlay.querySelector('#resourceIcon').value);
    formData.append('updated_date', overlay.querySelector('#resourceUpdatedDate').value);

    const fileInput = overlay.querySelector('#resourceFile');
    if (fileInput.files.length) {
        formData.append('file', fileInput.files[0]);
    }

    try {
        const url = editId ? `/api/resources/${editId}` : '/api/resources';
        const method = editId ? 'PUT' : 'POST';

        const res = await fetch(url, { method, body: formData });
        const data = await res.json();

        if (!data.success) {
            alert(data.message || 'Unable to save resource.');
            return;
        }
        closeResourceForm();
        showToast(editId ? 'Resource updated' : 'Resource added', 'success');
        loadResources();
    } catch (err) {
        console.error('Resource save failed:', err);
        alert('Something went wrong while saving.');
    }
}

async function deleteResource(id) {
    if (!confirm('Delete this resource?')) return;

    try {
        const res = await fetch(`/api/resources/${id}`, { method: 'DELETE' });
        const data = await res.json();

        if (!data.success) {
            alert(data.message || 'Unable to delete resource.');
            return;
        }
        showToast('Resource deleted', 'success');
        loadResources();
    } catch (err) {
        console.error('Resource delete failed:', err);
        alert('Something went wrong while deleting.');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadResources();
});