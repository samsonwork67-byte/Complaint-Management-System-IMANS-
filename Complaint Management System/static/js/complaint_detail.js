let currentComplaintId = null;
let statusSelect = null;

function getCsrfToken() {
    var inp = document.querySelector('input[name="csrf_token"]');
    return inp ? inp.value : '';
}

function openRequestInfoModal(id) {
    if (window.auditLogger) {
        window.auditLogger.trackClick('MODAL_OPEN', 'request_info', { complaint_id: id });
    }
    currentComplaintId = id;
    const modal = document.getElementById("requestInfoModal");
    modal.style.display = "flex";
    modal.classList.add("active");
}

function sendRequestInfo() {
    const message = document.getElementById("requestMessage").value;
    if (!message.trim()) {
        alert('Please enter a message.');
        return;
    }
    fetch(`/api/review-complaint/${currentComplaintId}/request-info`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
        body: JSON.stringify({ message })
    })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.getElementById('requestInfoModal').style.display = 'none';
                document.getElementById('requestInfoModal').classList.remove('active');
                document.getElementById('requestMessage').value = '';
                alert('Information request sent successfully.');
            } else {
                alert(data.message || 'Unable to send request.');
            }
        });
}

document.addEventListener('DOMContentLoaded', () => {
    statusSelect = document.getElementById('statusSelect');
    const remarksInput = document.getElementById('remarksInput');
    const saveRemarksBtn = document.getElementById('saveRemarksBtn');
    const notifyCheckbox = document.getElementById('notifyComplainantCheckbox');

    function updateComplaint(newStatus, newRemarks, btnElement) {
        const complaintId = statusSelect.dataset.id;
        const notify = notifyCheckbox ? notifyCheckbox.checked : false;

        if (btnElement) btnElement.disabled = true;

        fetch(`/api/update-status/${complaintId}`, {
            method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
            body: JSON.stringify({ status: newStatus, remarks: newRemarks, notify: notify })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // notify other tabs/pages to refresh complaint stats
                    try { localStorage.setItem('statsUpdated', Date.now().toString()); } catch (e) { }
                    window.location.reload();
                } else {
                    alert('Failed to update: ' + data.message);
                    if (btnElement) btnElement.disabled = false;
                }
            })
            .catch(err => {
                console.error('Error updating:', err);
                alert('An error occurred while updating.');
                if (btnElement) btnElement.disabled = false;
            });
    }

    if (statusSelect) {
        statusSelect.addEventListener('change', () => {
            if (statusSelect.disabled) return;
            updateComplaint(statusSelect.value, null, statusSelect);
        });
    }

    if (saveRemarksBtn) {
        saveRemarksBtn.addEventListener('click', () => {
            if (saveRemarksBtn.disabled) return;
            saveRemarksBtn.innerText = 'Saving...';
            updateComplaint(null, remarksInput.value, saveRemarksBtn);
        });
    }
});

// Overlay-based card editor
let currentEditCard = null;
function openCardEditor(idx) {
    if (window.auditLogger) {
        window.auditLogger.trackClick('MODAL_OPEN', 'edit_field_overlay', { field_index: idx });
    }
    // allow 'details' special id
    const cards = document.querySelectorAll('.detail-card');
    let card;
    if (idx === 'details') card = document.querySelector('.detail-card[data-field="Details of Complaint"]');
    else card = cards[parseInt(idx, 10)];
    if (!card) return;
    const field = card.dataset.field;
    const view = card.querySelector('.view-val');
    const input = card.querySelector('.edit-val');
    const currentVal = input ? input.value : (view ? view.textContent : '');
    currentEditCard = card;
    document.getElementById('editOverlayTitle').textContent = 'Edit ' + field;
    document.getElementById('editFieldLabel').textContent = field;
    const overlayInput = document.getElementById('editFieldInput');
    overlayInput.value = currentVal || '';
    document.getElementById('editOverlay').classList.add('active');
    document.getElementById('editSaveBtn').disabled = false;
}

function closeEditOverlay() {
    document.getElementById('editOverlay').classList.remove('active');
    currentEditCard = null;
}

document.addEventListener('DOMContentLoaded', () => {
    // fallback binding (delegation) in case direct binding misses elements
    document.addEventListener('click', (ev) => {
        const btn = ev.target.closest && ev.target.closest('.detail-edit-btn');
        if (btn) {
            const idx = btn.dataset.editIndex;
            openCardEditor(idx);
        }
    });
    document.getElementById('editSaveBtn').addEventListener('click', async () => {
        if (!currentEditCard) return;
        const field = currentEditCard.dataset.field;
        const val = document.getElementById('editFieldInput').value.trim();
        const payload = {};
        if (field === 'Name of The Accused') payload.name = val;
        else if (field === 'Type of Complaint') payload.category = val;
        else if (field === 'Date of Incident') payload.incident_date = val;
        else if (field === 'Email address') payload.email = val;
        else if (field === 'Timestamp') payload.timestamp = val;
        else if (field === 'Position of The Accused') payload.position = val;
        else if (field === 'Company of The Accused') payload.company = val;
        else if (field === 'Location of Incident') payload.location = val;
        else if (field === 'Your Phone Number') payload.phone = val;
        else if (field === 'Your Name') payload.complainant_name = val;
        else if (field === 'Follow-up Response') payload.followup_response = val;
        else if (field === 'Tracking ID') payload.tracking_id = val;
        else if (field === 'Details of Complaint') payload.details = val;
        else if (field === 'Complaint Reference ID') payload.complaint_ref_id = val;
        else return alert('Field not editable');

        const btn = document.getElementById('editSaveBtn');
        btn.disabled = true;
        const complaintId = (statusSelect && statusSelect.dataset && statusSelect.dataset.id) || document.getElementById('statusSelect')?.dataset?.id;
        if (!complaintId) {
            alert('Complaint identifier is missing.');
            btn.disabled = false;
            return;
        }
        try {
            const res = await fetch(`/api/update-complaint/${complaintId}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() }, body: JSON.stringify(payload) });
            const data = await res.json();
            if (data.success) {

                if (window.auditLogger) {
                    window.auditLogger.log('UPDATE', field, {
                        complaint_id: complaintId,
                        field: field,
                        new_value: val
                    });
                }
                // update ref id display if it was the reference ID being edited
                const refDisplay = document.getElementById('refIdDisplay');
                if (refDisplay && field === 'Complaint Reference ID') {
                    refDisplay.textContent = val;
                }
                // update inline card view/edit values for all other fields
                const view = currentEditCard.querySelector && currentEditCard.querySelector('.view-val');
                const input = currentEditCard.querySelector && currentEditCard.querySelector('.edit-val');
                if (view) view.textContent = val || 'N/A';
                if (input) input.value = val || '';
                closeEditOverlay();
            } else {
                alert(data.message || 'Failed to save');
            }
        } catch (err) {
            console.error('Save error', err); alert('Error saving');
        }
        btn.disabled = false;
    });
});

// Add expand/collapse toggle for Details of Complaint card
document.addEventListener('DOMContentLoaded', () => {
    const detailsCard = document.querySelector('.detail-card[data-field="Details of Complaint"]');
    if (!detailsCard) return;
    // create toggle button
    const toggle = document.createElement('button');
    toggle.className = 'expand-toggle';
    toggle.type = 'button';
    toggle.textContent = 'Show more';
    toggle.addEventListener('click', () => {
        const expanded = detailsCard.classList.toggle('expanded');
        toggle.textContent = expanded ? 'Show less' : 'Show more';
    });
    // append after the detail-value element
    const valueEl = detailsCard.querySelector('.detail-value');
    if (valueEl) valueEl.parentNode.appendChild(toggle);
});

// Toggle the small per-card actions menu (used by the "..." button)
function toggleMenu(idx) {
    const el = document.getElementById('detailMenu-' + idx);
    if (!el) return;
    el.style.display = (el.style.display === 'block') ? 'none' : 'block';
}

function openRefIdEditor() {
    const current = document.getElementById('refIdDisplay').textContent.trim();
    document.getElementById('editOverlayTitle').textContent = 'Edit Reference ID';
    document.getElementById('editFieldLabel').textContent = 'Complaint Reference ID';
    document.getElementById('editFieldInput').value = current;

    // set a flag so the save button knows what to update
    document.getElementById('editFieldInput').dataset.fieldType = 'ref_id';

    currentEditCard = { dataset: { field: 'Complaint Reference ID' }, _isRefId: true };
    document.getElementById('editOverlay').classList.add('active');
    document.getElementById('editSaveBtn').disabled = false;
}