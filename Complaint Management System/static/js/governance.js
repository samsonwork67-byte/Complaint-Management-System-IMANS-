let isAdmin = false;
let integrityEvents = [];
let activeEventIndex = 0;
let activeImageIndex = 0;
let editingEventId = null;
let editingFullEventId = null;

function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

async function checkAdmin() {
    try {
        const res = await fetch('/api/me');
        const data = await res.json();
        const role = (data.admin_role || '').toUpperCase();
        // Only users with landing edit permissions should see admin controls on the landing page
        const landingAllowed = ['LANDING_EDITOR', 'FULL_ACCESS', 'SUPER_ADMIN'];
        isAdmin = landingAllowed.includes(role);

        const controls = document.getElementById('governanceAdminControls');
        if (controls) controls.style.display = isAdmin ? 'block' : 'none';
    } catch (err) {
        console.error("Error checking admin:", err);
        const controls = document.getElementById('governanceAdminControls');
        if (controls) controls.style.display = 'none';
    }
    const integrityControls = document.getElementById('integrityAdminControls');
    if (integrityControls) integrityControls.style.display = isAdmin ? 'block' : 'none';
}

async function loadGovernanceDocs() {
    try {
        const res = await fetch('/api/governance');
        const docs = await res.json();
        window.currentDocs = docs;

        const grid = document.getElementById('governanceGrid');
        if (!grid) return;
        grid.innerHTML = "";

        docs.forEach(doc => {
            const card = document.createElement('div');
            card.className = "governance-card";

            card.innerHTML = `
                <div class="card-header">
                    <div class="governance-icon-wrapper">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                            <line x1="16" y1="13" x2="8" y2="13" />
                            <line x1="16" y1="17" x2="8" y2="17" />
                        </svg>
                    </div>
                    ${isAdmin ? `
                    <div class="card-menu">
                        <button class="menu-btn" onclick="toggleMenu(${doc.id})" aria-label="Document actions">...</button>
                        <div id="menu-${doc.id}" class="menu-dropdown">
                            <button onclick="editDoc(${doc.id})">Edit</button>
                            <button onclick="deleteDoc(${doc.id})">Remove</button>
                        </div>
                    </div>` : ''}
                </div>
                <h3>${escapeHtml(doc.title)}</h3>
                <p class="governance-meta">${escapeHtml(doc.description)}</p>
                <div class="card-actions">
                    <a href="${doc.file_url}" target="_blank" class="btn btn-outline-teal">View</a>
                    <a href="${doc.file_url}" download class="btn btn-secondary">Download</a>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        console.error("Failed to load docs:", err);
    }
}

async function deleteDoc(id) {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
        const res = await fetch(`/api/governance/${id}`, { method: 'DELETE' });
        const data = await res.json();

        if (data.success) {
            loadGovernanceDocs();
        } else {
            alert(data.message || "Failed to delete document.");
        }
    } catch (err) {
        console.error("Delete failed:", err);
        alert("Something went wrong while deleting.");
    }
}

function editDoc(id) {
    const doc = window.currentDocs.find(d => d.id === id);
    if (!doc) return;

    // Set editId FIRST before anything else
    const form = document.getElementById('addGovernanceForm');
    form.dataset.editId = id;

    document.getElementById('docTitle').value = doc.title;
    document.getElementById('docDescription').value = doc.description;

    const fileInput = document.getElementById('docFile');
    fileInput.value = "";
    fileInput.required = false;

    const existingFileNote = document.getElementById('existingFileNote');
    if (existingFileNote) existingFileNote.remove();
    fileInput.insertAdjacentHTML("afterend",
        `<small id="existingFileNote" style="display:block; margin-top:6px; color:var(--text-medium);">
            Current file: <a href="${doc.file_url}" target="_blank" style="color:var(--accent-teal);">View existing file</a><br>
            Leave blank to keep current file.
        </small>`
    );

    const overlayTitle = document.querySelector('#addFormOverlay h3');
    if (overlayTitle) overlayTitle.textContent = 'Edit Governance Document';

    document.getElementById('addFormOverlay').style.display = 'flex';
}

function openAddForm() {
    const form = document.getElementById('addGovernanceForm');
    if (form && !form.dataset.editId) {
        form.reset();
        document.getElementById('docFile').required = true;
        const title = document.querySelector('#addFormOverlay h3');
        if (title) title.textContent = 'Add Governance Document';
        const existingFileNote = document.getElementById('existingFileNote');
        if (existingFileNote) existingFileNote.remove();
    }
    document.getElementById('addFormOverlay').style.display = 'flex';
}

function closeAddForm() {
    const form = document.getElementById('addGovernanceForm');
    if (form) {
        form.reset();
        delete form.dataset.editId;
    }
    const existingFileNote = document.getElementById('existingFileNote');
    if (existingFileNote) existingFileNote.remove();
    document.getElementById('docFile').required = true;
    document.getElementById('addFormOverlay').style.display = 'none';
}

function toggleMenu(id) {
    const menu = document.getElementById(`menu-${id}`);
    if (menu) menu.style.display = menu.style.display === 'flex' ? 'none' : 'flex';
}

async function loadIntegrityEvents() {
    const grid = document.querySelector('.events-grid');
    if (!grid) return;

    try {
        const res = await fetch('/api/integrity-events');
        integrityEvents = await res.json();

        grid.innerHTML = '';

        integrityEvents.forEach((event, index) => {
            const card = document.createElement('div');
            card.className = 'event-card';
            card.dataset.eventIndex = index;

            const hasImage = event.images && event.images.length;
            const imageHtml = hasImage
                ? `<img src="${event.images[0]}" alt="${escapeHtml(event.title)}" class="event-cover-image">`
                : `<div class="placeholder-illustration">
                     <svg viewBox="0 0 24 24" fill="#fff">
                       <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-1 16l-4-4 1.41-1.41L11 14.17l6.59-6.59L19 9l-8 8z" />
                     </svg>
                   </div>`;

            card.innerHTML = `
                <div class="event-img-wrapper ${hasImage ? 'has-event-image' : ''}" style="${hasImage ? '' : 'background: linear-gradient(135deg, #0f766e, #134e4a);'}">
                    ${imageHtml}
                </div>
                <div class="event-info">
                    <span class="event-date">
                        <svg viewBox="0 0 24 24">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" fill="none" stroke="currentColor" stroke-width="2" />
                            <line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" stroke-width="2" />
                            <line x1="8" y1="2" x2="8" y2="6" stroke="currentColor" stroke-width="2" />
                            <line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" stroke-width="2" />
                        </svg>
                        ${escapeHtml(event.date)}
                    </span>
                    <h3>${escapeHtml(event.title)}</h3>
                    <p>${escapeHtml(event.description)}</p>
                </div>
            `;

            attachEventOverlay(card, index);
            if (isAdmin) addEventAdminMenu(card, event);
            grid.appendChild(card);
        });

        if (isAdmin) ensureAddEventButton(grid);
    } catch (err) {
        console.error("Failed to load integrity events:", err);
    }
}

function ensureAddEventButton(grid) {
    let btnWrapper = document.getElementById('addEventCardWrapper');
    if (btnWrapper) { btnWrapper.remove(); }

    btnWrapper = document.createElement('div');
    btnWrapper.id = 'addEventCardWrapper';
    btnWrapper.className = 'event-card reveal add-event-card';
    btnWrapper.innerHTML = `
        <button type="button" class="btn btn-primary add-event-btn" style="width:100%; height:100%; min-height:200px;">
            + Add Event
        </button>
    `;
    btnWrapper.querySelector('button').addEventListener('click', openAddEventForm);
    grid.appendChild(btnWrapper);
}

function renderEventImage(card, event) {
    const wrapper = card.querySelector('.event-img-wrapper');
    const placeholder = card.querySelector('.placeholder-illustration');
    if (!wrapper || !placeholder) return;

    if (!placeholder.dataset.defaultHtml) {
        placeholder.dataset.defaultHtml = placeholder.innerHTML;
    }
    if (!wrapper.dataset.defaultStyle) {
        wrapper.dataset.defaultStyle = wrapper.getAttribute('style') || '';
    }

    if (event.images && event.images.length) {
        placeholder.innerHTML = `<img src="${event.images[0]}" alt="${escapeHtml(event.title)}" class="event-cover-image">`;
        wrapper.classList.add('has-event-image');
        wrapper.style.background = '';
    } else {
        placeholder.innerHTML = placeholder.dataset.defaultHtml;
        wrapper.classList.remove('has-event-image');
        wrapper.setAttribute('style', wrapper.dataset.defaultStyle);
    }
}

function attachEventOverlay(card, index) {
    if (card.dataset.overlayAttached === 'true') return;
    card.dataset.overlayAttached = 'true';

    card.addEventListener('click', event => {
        if (event.target.closest('button, input, label, a, .event-admin-menu')) return;
        openIntegrityOverlay(index);
    });
    card.setAttribute('tabindex', '0');
    card.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        openIntegrityOverlay(index);
    });
}

function addEventAdminMenu(card, event) {
    const eventInfo = card.querySelector('.event-info');
    if (!eventInfo) return;

    const control = document.createElement('div');
    control.className = 'event-admin-menu card-menu';
    control.innerHTML = `
        <button class="menu-btn" onclick="toggleIntegrityMenu(${event.id})" aria-label="Event actions">...</button>
        <div id="integrity-menu-${event.id}" class="menu-dropdown">
            <button type="button" class="event-edit-details">Edit Details</button>
            <button type="button" class="event-edit-pictures">Edit Pictures</button>
            <button type="button" class="event-delete">Delete Event</button>
        </div>
    `;

    control.querySelector('.event-edit-details').addEventListener('click', e => {
        e.stopPropagation();
        toggleIntegrityMenu(event.id);
        openEditEventForm(event.id);
    });

    control.querySelector('.event-edit-pictures').addEventListener('click', e => {
        e.stopPropagation();
        toggleIntegrityMenu(event.id);
        openIntegrityPictureEditor(event.id);
    });

    control.querySelector('.event-delete').addEventListener('click', e => {
        e.stopPropagation();
        toggleIntegrityMenu(event.id);
        deleteEvent(event.id);
    });

    eventInfo.insertBefore(control, eventInfo.firstChild);
}

function toggleIntegrityMenu(id) {
    const menu = document.getElementById(`integrity-menu-${id}`);
    if (!menu) return;
    document.querySelectorAll('.event-admin-menu .menu-dropdown').forEach(dropdown => {
        if (dropdown !== menu) dropdown.style.display = 'none';
    });
    menu.style.display = menu.style.display === 'flex' ? 'none' : 'flex';
}

function ensureIntegrityPictureEditor() {
    let overlay = document.getElementById('integrityPictureEditor');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.id = 'integrityPictureEditor';
    overlay.className = 'overlay integrity-editor-overlay';
    overlay.innerHTML = `
        <div class="overlay-content integrity-editor-content">
            <button type="button" class="integrity-editor-close" aria-label="Close">&times;</button>
            <h3>Edit Event Pictures</h3>
            <p class="integrity-editor-subtitle" id="integrityEditorTitle"></p>
            <div class="integrity-picture-list" id="integrityPictureList"></div>
            <form id="integrityPictureForm" enctype="multipart/form-data">
                <div class="form-group">
                    <label>Add Pictures</label>
                    <input 
                        type="file" 
                        id="integrityPictureInput" 
                        accept="image/*" 
                        multiple
                    >
                </div>
                <div class="integrity-editor-actions">
                    <button type="submit" class="btn btn-success">Add Pictures</button>
                    <button type="button" class="btn btn-secondary integrity-editor-cancel">Close</button>
                </div>
            </form>
        </div>
    `;

    overlay.querySelector('.integrity-editor-close').addEventListener('click', closeIntegrityPictureEditor);
    overlay.querySelector('.integrity-editor-cancel').addEventListener('click', closeIntegrityPictureEditor);
    overlay.addEventListener('click', event => {
        if (event.target === overlay) closeIntegrityPictureEditor();
    });
    overlay.querySelector('#integrityPictureForm').addEventListener('submit', uploadIntegrityPictures);
    document.body.appendChild(overlay);
    return overlay;
}

function closeIntegrityPictureEditor() {
    const overlay = document.getElementById('integrityPictureEditor');

    if (overlay) {
        overlay.style.display = 'none';
    }

    editingEventId = null;

    const input = document.getElementById('integrityPictureInput');
    if (input) {
        input.value = '';
    }
}

function openIntegrityPictureEditor(eventId) {
    editingEventId = eventId;
    renderIntegrityPictureEditor();

    const overlay = ensureIntegrityPictureEditor();
    overlay.style.display = 'flex';

    // Close when clicking outside content
    overlay.onclick = function (e) {
        if (e.target === overlay) {
            closeIntegrityPictureEditor();
        }
    };
}

function renderIntegrityPictureEditor() {
    const overlay = ensureIntegrityPictureEditor();
    const event = integrityEvents.find(item => item.id === editingEventId);
    if (!event) return;

    overlay.querySelector('#integrityEditorTitle').textContent = event.title;
    const list = overlay.querySelector('#integrityPictureList');
    const images = event.images || [];

    if (!images.length) {
        list.innerHTML = '<p class="integrity-picture-empty">No pictures added yet.</p>';
        return;
    }

    list.innerHTML = images.map(imageUrl => `
        <div class="integrity-picture-item">
            <img src="${imageUrl}" alt="${escapeHtml(event.title)}">
            <button type="button" data-image-url="${escapeHtml(imageUrl)}">Delete</button>
        </div>
    `).join('');

    list.querySelectorAll('button[data-image-url]').forEach(button => {
        button.addEventListener('click', () => deleteIntegrityPicture(button.dataset.imageUrl));
    });
}

async function uploadIntegrityPictures(event) {
    event.preventDefault();

    const input = document.getElementById('integrityPictureInput');

    if (!editingEventId) {
        alert('No event selected.');
        return;
    }

    if (input.files.length === 0) {
        alert('Choose at least one picture to add.');
        return;
    }

    const formData = new FormData();

    Array.from(input.files).forEach(file => {
        formData.append('images', file);
    });

    try {
        const res = await fetch(`/api/integrity-events/${editingEventId}/images`, {
            method: 'POST',
            body: formData
        });

        const data = await res.json();

        if (!data.success) {
            alert(data.message || 'Unable to add pictures.');
            return;
        }

        // Clear selected files
        input.value = '';

        // Refresh pictures
        await loadIntegrityEvents();

        // Keep overlay open
        renderIntegrityPictureEditor();

    } catch (err) {
        console.error("Picture upload failed:", err);
        alert('Something went wrong while adding pictures.');
    }
}

async function deleteIntegrityPicture(imageUrl) {
    if (!editingEventId) return;
    if (!confirm('Delete this picture?')) return;

    try {
        const res = await fetch(`/api/integrity-events/${editingEventId}/images`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_url: imageUrl })
        });
        const data = await res.json();
        if (!data.success) {
            alert(data.message || 'Unable to delete picture.');
            return;
        }
        await loadIntegrityEvents();
        renderIntegrityPictureEditor();
    } catch (err) {
        console.error('Picture delete failed:', err);
        alert('Something went wrong while deleting the picture.');
    }
}

function ensureIntegrityOverlay() {
    let overlay = document.getElementById('integrityEventOverlay');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.id = 'integrityEventOverlay';
    overlay.className = 'integrity-overlay';
    overlay.innerHTML = `
        <div class="integrity-overlay-panel">
            <button class="integrity-overlay-close" aria-label="Close">&times;</button>
            <div class="integrity-overlay-gallery">
                <button class="gallery-nav prev" aria-label="Previous picture">‹</button>
                <img id="integrityOverlayImage" alt="">
                <div class="gallery-empty">No pictures uploaded yet.</div>
                <button class="gallery-nav next" aria-label="Next picture">›</button>
                <div class="gallery-count" id="integrityGalleryCount"></div>
            </div>
            <div class="integrity-overlay-info">
                <span class="event-date" id="integrityOverlayDate"></span>
                <h3 id="integrityOverlayTitle"></h3>
                <p id="integrityOverlayDescription"></p>
            </div>
        </div>
    `;

    overlay.querySelector('.integrity-overlay-close').addEventListener('click', closeIntegrityOverlay);
    overlay.addEventListener('click', event => {
        if (event.target === overlay) closeIntegrityOverlay();
    });
    overlay.querySelector('.gallery-nav.prev').addEventListener('click', () => moveIntegrityImage(-1));
    overlay.querySelector('.gallery-nav.next').addEventListener('click', () => moveIntegrityImage(1));
    document.body.appendChild(overlay);
    return overlay;
}

function openIntegrityOverlay(index) {
    if (window.auditLogger) {
        window.auditLogger.trackClick('MODAL_OPEN', 'integrity_event_detail', { index });
    }
    activeEventIndex = index;
    activeImageIndex = 0;
    updateIntegrityOverlay();
    ensureIntegrityOverlay().classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeIntegrityOverlay() {
    const overlay = document.getElementById('integrityEventOverlay');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
}

function moveIntegrityImage(direction) {
    const event = integrityEvents[activeEventIndex];
    if (!event || !event.images || !event.images.length) return;
    activeImageIndex = (activeImageIndex + direction + event.images.length) % event.images.length;
    updateIntegrityOverlay();
}

function updateIntegrityOverlay() {
    const overlay = ensureIntegrityOverlay();
    const event = integrityEvents[activeEventIndex];
    if (!event) return;

    const image = overlay.querySelector('#integrityOverlayImage');
    const empty = overlay.querySelector('.gallery-empty');
    const count = overlay.querySelector('#integrityGalleryCount');
    const prev = overlay.querySelector('.gallery-nav.prev');
    const next = overlay.querySelector('.gallery-nav.next');

    overlay.querySelector('#integrityOverlayDate').textContent = event.date;
    overlay.querySelector('#integrityOverlayTitle').textContent = event.title;
    overlay.querySelector('#integrityOverlayDescription').textContent = event.description;

    const images = event.images || [];
    image.style.display = images.length ? 'block' : 'none';
    empty.style.display = images.length ? 'none' : 'flex';
    prev.style.display = images.length > 1 ? 'flex' : 'none';
    next.style.display = images.length > 1 ? 'flex' : 'none';
    count.textContent = images.length ? `${activeImageIndex + 1} / ${images.length}` : '';

    if (images.length) {
        image.src = images[activeImageIndex];
        image.alt = event.title;
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    await checkAdmin();
    await loadGovernanceDocs();
    await loadIntegrityEvents();

    const form = document.getElementById('addGovernanceForm');
    if (!form) return;

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const formData = new FormData(this);
        const editId = this.dataset.editId; // ← read FIRST
        closeAddForm(); // ← then close

        try {
            const res = await fetch(editId ? `/api/governance/${editId}` : '/api/governance', {
                method: editId ? 'PUT' : 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.success) {
                loadGovernanceDocs();
            } else {
                alert(data.message || 'Unable to save document.');
            }
        } catch (err) {
            console.error("Upload failed:", err);
            alert("Something went wrong.");
        }
    });
});

function ensureEventFormOverlay() {
    let overlay = document.getElementById('eventFormOverlay');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.id = 'eventFormOverlay';
    overlay.className = 'overlay';
    overlay.innerHTML = `
        <div class="overlay-content">
            <h3 id="eventFormTitle">Add Event</h3>
            <form id="eventForm">
                <div class="form-group">
                    <label>Date</label>
                    <input type="text" id="eventDate" class="form-control" placeholder="e.g. 15 January 2026" required>
                </div>
                <div class="form-group">
                    <label>Title</label>
                    <input type="text" id="eventTitle" class="form-control" required>
                </div>
                <div class="form-group">
                    <label>Description</label>
                    <textarea id="eventDescription" class="form-control" required></textarea>
                </div>
                <div style="margin-top:15px; text-align:right;">
                    <button type="submit" class="btn btn-success">Save</button>
                    <button type="button" class="btn btn-secondary" id="eventFormCancel">Cancel</button>
                </div>
            </form>
        </div>
    `;

    overlay.querySelector('#eventFormCancel').addEventListener('click', closeEventForm);
    overlay.addEventListener('click', event => {
        if (event.target === overlay) closeEventForm();
    });
    overlay.querySelector('#eventForm').addEventListener('submit', submitEventForm);
    document.body.appendChild(overlay);
    return overlay;
}

function openAddEventForm() {
    editingFullEventId = null;
    const overlay = ensureEventFormOverlay();
    overlay.querySelector('#eventFormTitle').textContent = 'Add Event';
    overlay.querySelector('#eventForm').reset();
    overlay.style.display = 'flex';
}

function openEditEventForm(id) {
    const event = integrityEvents.find(item => item.id === id);
    if (!event) return;

    editingFullEventId = id;
    const overlay = ensureEventFormOverlay();
    overlay.querySelector('#eventFormTitle').textContent = 'Edit Event';
    overlay.querySelector('#eventDate').value = event.date;
    overlay.querySelector('#eventTitle').value = event.title;
    overlay.querySelector('#eventDescription').value = event.description;
    overlay.style.display = 'flex';
}

function closeEventForm() {
    const overlay = document.getElementById('eventFormOverlay');
    if (overlay) overlay.style.display = 'none';
    editingFullEventId = null;
}

async function submitEventForm(e) {
    e.preventDefault();
    const currentEditId = editingFullEventId; // ← read FIRST
    closeEventForm(); // ← then close

    const overlay = document.getElementById('eventFormOverlay');
    const payload = {
        date: document.getElementById('eventDate').value,
        title: document.getElementById('eventTitle').value,
        description: document.getElementById('eventDescription').value
    };

    try {
        const url = currentEditId ? `/api/integrity-events/${currentEditId}` : '/api/integrity-events';
        const method = currentEditId ? 'PUT' : 'POST';

        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!data.success) {
            alert(data.message || 'Unable to save event.');
            return;
        }
        await loadIntegrityEvents();
    } catch (err) {
        console.error('Event save failed:', err);
        alert('Something went wrong while saving the event.');
    }
}

async function deleteEvent(id) {
    if (!confirm('Delete this event? This cannot be undone.')) return;

    try {
        const res = await fetch(`/api/integrity-events/${id}`, { method: 'DELETE' });
        const data = await res.json();

        if (!data.success) {
            alert(data.message || 'Unable to delete event.');
            return;
        }
        await loadIntegrityEvents();
    } catch (err) {
        console.error('Event delete failed:', err);
        alert('Something went wrong while deleting the event.');
    }
}