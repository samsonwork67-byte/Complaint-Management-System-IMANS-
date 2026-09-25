(function () {
    'use strict';

    const complaintId = document.getElementById('complaintDetailRoot')?.dataset.complaintId || '';

    const sidebar = document.getElementById('sectionsSidebar');
    const toggleBtn = document.getElementById('sectionsSidebarToggle');
    const closeBtn = document.getElementById('closeSectionsSidebar');
    const overlay = document.getElementById('sectionsSidebarOverlay');
    const addBtn = document.getElementById('addSectionBtn');
    const titleInput = document.getElementById('newSectionTitle');
    const list = document.getElementById('sectionsList');

    if (!sidebar || !toggleBtn) return;

    const SECTION_LABELS = {
        summary: 'Complaint Summary',
        investigation: 'Investigation Notes',
        decision: 'Committee Decision',
        followup: 'Follow-up Actions',
        evidence: 'Evidence Review',
        custom: 'Custom Section'
    };

    function openSidebar() {
        sidebar.classList.add('open');
        overlay.classList.add('active');
        toggleBtn.classList.add('open');
        loadSections();
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
        toggleBtn.classList.remove('open');
    }

    toggleBtn.addEventListener('click', () => {
        if (sidebar.classList.contains('open')) closeSidebar();
        else openSidebar();
    });
    closeBtn.addEventListener('click', closeSidebar);
    overlay.addEventListener('click', closeSidebar);

    async function loadSections() {
        try {
            const res = await fetch(`/api/complaint/${complaintId}/sections`);
            const data = await res.json();
            if (!data.success) return;
            renderSections(data.sections);
        } catch (e) {
            console.error('Failed to load sections:', e);
        }
    }

    function renderSections(sections) {
        list.innerHTML = '';
        if (!sections.length) {
            list.innerHTML = '<p style="text-align:center; color:var(--text-muted); font-size:0.85rem;">No sections yet.</p>';
            return;
        }
        sections.forEach(section => list.appendChild(buildSectionCard(section)));
    }

    function buildSectionCard(section) {
        const card = document.createElement('div');
        card.className = 'section-card';
        card.dataset.sectionId = section.id;

        card.innerHTML = `
            <div class="section-card-header">
                <span class="section-card-title" data-editable="true">${escapeHtml(section.title)}</span>
                <input type="text" class="section-title-input" style="display:none;" value="${escapeHtml(section.title)}">
                <div class="section-card-actions">
                    <button class="edit-section-btn" title="Edit">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="delete-section-btn" title="Delete">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                    </button>
                </div>
            </div>
            <div class="section-content-view">${escapeHtml(section.content) || '<em>No notes yet</em>'}</div>
            <textarea class="section-content-textarea" style="display:none;">${escapeHtml(section.content || '')}</textarea>
            <div style="display:none;" class="section-save-row">
                <button class="btn btn-success save-section-btn" style="margin-top:8px; font-size:0.78rem; padding:6px 12px;">Save</button>
                <button class="btn btn-secondary cancel-section-btn" style="margin-top:8px; font-size:0.78rem; padding:6px 12px;">Cancel</button>
            </div>
            <div class="section-file-list">
                ${(section.files || []).map(f => `
                    <div class="section-file-item" data-file-id="${f.id}">
                        <a href="${f.file_url}" target="_blank">${escapeHtml(f.file_name)}</a>
                        <button class="section-file-delete" data-file-id="${f.id}">&times;</button>
                    </div>
                `).join('')}
            </div>
            <div class="section-upload-row">
                <input type="file" class="section-file-input" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png,.xlsx">
            </div>
            <div class="section-meta">By ${escapeHtml(section.created_by || 'Unknown')} · ${new Date(section.updated_at).toLocaleString()}</div>
        `;

        const viewEl = card.querySelector('.section-content-view');
        const textareaEl = card.querySelector('.section-content-textarea');
        const saveRow = card.querySelector('.section-save-row');
        const titleViewEl = card.querySelector('.section-card-title');
        const titleInputEl = card.querySelector('.section-title-input');

        card.querySelector('.edit-section-btn').addEventListener('click', () => {
            viewEl.style.display = 'none';
            textareaEl.style.display = 'block';
            saveRow.style.display = 'flex';
            saveRow.style.gap = '8px';
            titleViewEl.style.display = 'none';
            titleInputEl.style.display = 'inline-block';
        });

        card.querySelector('.cancel-section-btn').addEventListener('click', () => {
            textareaEl.value = section.content || '';
            titleInputEl.value = section.title;
            viewEl.style.display = 'block';
            textareaEl.style.display = 'none';
            saveRow.style.display = 'none';
            titleViewEl.style.display = 'inline';
            titleInputEl.style.display = 'none';
        });

        card.querySelector('.save-section-btn').addEventListener('click', async () => {
            const newContent = textareaEl.value;
            const newTitle = titleInputEl.value.trim() || section.title;

            try {
                const res = await fetch(`/api/sections/${section.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle, content: newContent })
                });
                const data = await res.json();
                if (data.success) {
                    section.content = newContent;
                    section.title = newTitle;
                    viewEl.innerHTML = escapeHtml(newContent) || '<em>No notes yet</em>';
                    titleViewEl.textContent = newTitle;
                    viewEl.style.display = 'block';
                    textareaEl.style.display = 'none';
                    saveRow.style.display = 'none';
                    titleViewEl.style.display = 'inline';
                    titleInputEl.style.display = 'none';
                    if (window.showToast) showToast('Section updated', 'success');
                } else {
                    alert(data.message || 'Failed to save');
                }
            } catch (e) {
                console.error(e);
                alert('Error saving section');
            }
        });

        card.querySelector('.delete-section-btn').addEventListener('click', async () => {
            if (!confirm('Delete this section and all its files?')) return;
            try {
                const res = await fetch(`/api/sections/${section.id}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    card.remove();
                    if (window.showToast) showToast('Section deleted', 'success');
                } else {
                    alert(data.message || 'Failed to delete');
                }
            } catch (e) {
                console.error(e);
                alert('Error deleting section');
            }
        });

        card.querySelector('.section-file-input').addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch(`/api/sections/${section.id}/files`, {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (data.success) {
                    const fileListEl = card.querySelector('.section-file-list');
                    const item = document.createElement('div');
                    item.className = 'section-file-item';
                    item.dataset.fileId = data.file.id;
                    item.innerHTML = `
                        <a href="${data.file.file_url}" target="_blank">${escapeHtml(data.file.file_name)}</a>
                        <button class="section-file-delete" data-file-id="${data.file.id}">&times;</button>
                    `;
                    fileListEl.appendChild(item);
                    attachFileDeleteHandler(item.querySelector('.section-file-delete'));
                    if (window.showToast) showToast('File uploaded', 'success');
                } else {
                    alert(data.message || 'Upload failed');
                }
            } catch (e) {
                console.error(e);
                alert('Error uploading file');
            }
            e.target.value = '';
        });

        card.querySelectorAll('.section-file-delete').forEach(attachFileDeleteHandler);

        return card;
    }

    function attachFileDeleteHandler(btn) {
        btn.addEventListener('click', async () => {
            if (!confirm('Delete this file?')) return;
            const fileId = btn.dataset.fileId;
            try {
                const res = await fetch(`/api/section-files/${fileId}`, { method: 'DELETE' });
                const data = await res.json();
                if (data.success) {
                    btn.closest('.section-file-item').remove();
                } else {
                    alert(data.message || 'Failed to delete file');
                }
            } catch (e) {
                console.error(e);
            }
        });
    }

    addBtn.addEventListener('click', async () => {
        const title = titleInput.value.trim();

        if (!title) {
            alert('Please enter a section name.');
            return;
        }

        try {
            const res = await fetch(`/api/complaint/${complaintId}/sections`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ section_type: 'custom', title, content: '' })
            });
            const data = await res.json();
            if (data.success) {
                data.section.files = [];
                list.appendChild(buildSectionCard(data.section));
                titleInput.value = '';
                if (window.showToast) showToast('Section added', 'success');
            } else {
                alert(data.message || 'Failed to add section');
            }
        } catch (e) {
            console.error(e);
            alert('Error adding section');
        }
    });

    function escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[char]));
    }
})();