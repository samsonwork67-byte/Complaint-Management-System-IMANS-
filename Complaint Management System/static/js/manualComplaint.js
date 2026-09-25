document.addEventListener('DOMContentLoaded', () => {
    const openBtn = document.getElementById('openManualComplaintBtn');
    const closeBtn = document.getElementById('closeManualComplaintBtn');
    const overlay = document.getElementById('manualComplaintOverlay');
    const form = document.getElementById('manualComplaintForm');
    const submitBtn = document.getElementById('manualSubmitBtn');

    if (!openBtn || !overlay || !form) return;

    openBtn.addEventListener('click', () => {
        overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    });

    closeBtn.addEventListener('click', () => {
        overlay.classList.remove('show');
        document.body.style.overflow = '';
        form.reset();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.remove('show');
            document.body.style.overflow = '';
            form.reset();
        }
    });

    // Close with ESC
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && overlay.classList.contains("show")) {
            overlay.classList.remove("show");
            document.body.style.overflow = "";
            form.reset();
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        const formData = new FormData(form);

        try {
            const res = await fetch('/api/manual-complaint', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.success) {
                if (typeof showToast === 'function') {
                    showToast(`Complaint saved — Reference ID: ${data.complaint_ref_id}`, 'success');
                } else {
                    alert(`Complaint saved successfully!\nReference ID: ${data.complaint_ref_id}\nTracking ID: ${data.tracking_id}`);
                }
                form.reset();
                overlay.classList.remove('show');
                document.body.style.overflow = '';
                setTimeout(() => window.location.reload(), 1000);
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.message || 'Failed to save complaint', 'error');
                } else {
                    alert(data.message || 'Failed to save complaint');
                }
            }
        } catch (err) {
            console.error('Manual complaint submission error:', err);
            if (typeof showToast === 'function') {
                showToast('An error occurred while saving.', 'error');
            } else {
                alert('An error occurred while saving.');
            }
        }

        submitBtn.disabled = false;
        submitBtn.textContent = 'Save Complaint';
    });
});