/**
 * complaint.js — Complaint Page Interactive Script
 * Handles: Complaint form submission with random ID generation,
 * file attachment label, and complaint status tracking.
 */
(function () {
  'use strict';

  // FILE INPUT LABEL UPDATE
  var fileInput = document.getElementById('compFile');
  var fileLabel = document.getElementById('fileName');
  if (fileInput && fileLabel) {
    fileInput.addEventListener('change', function () {
      if (fileInput.files && fileInput.files.length > 0) {
        fileLabel.textContent = fileInput.files[0].name;
        fileLabel.style.fontStyle = 'normal';
        fileLabel.style.color = 'var(--text-dark)';
      } else {
        fileLabel.textContent = 'No file chosen';
        fileLabel.style.fontStyle = 'italic';
        fileLabel.style.color = 'var(--text-medium)';
      }
    });
  }

  // COMPLAINT FORM SUBMISSION
  var complaintForm = document.getElementById('complaintForm');
  if (complaintForm) {
    complaintForm.addEventListener('submit', async function (e) {
      e.preventDefault();

      var formData = new FormData();
      formData.append('name', document.getElementById('compName').value);
      formData.append('email', document.getElementById('compEmail').value);
      formData.append('phone', document.getElementById('compPhone').value);
      formData.append('accused', document.getElementById('compAccused').value);
      formData.append('position', document.getElementById('compPosition').value);
      formData.append('company', document.getElementById('compCompany').value);
      formData.append('category', document.getElementById('compCategory').value);
      formData.append('incident_date', document.getElementById('compIncidentDate').value);
      formData.append('incident_time', document.getElementById('compIncidentTime').value);
      formData.append('location', document.getElementById('compLocation').value);
      formData.append('details', document.getElementById('compDetails').value);
      formData.append('other_parties', document.getElementById('compOtherParties').value);
      if (fileInput && fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
      }

      // Include CSRF token
      var csrfInput = document.querySelector('input[name="csrf_token"]');
      if (csrfInput) {
        formData.append('csrf_token', csrfInput.value);
      }

      // Show loading overlay
      var loadingOverlay = document.getElementById('submitLoadingOverlay');
      console.log('Loading overlay found:', loadingOverlay); // add this
      if (loadingOverlay) loadingOverlay.classList.add('active');

      var submitBtn = document.getElementById('submitComplaintBtn');
      if (submitBtn) submitBtn.disabled = true;

      try {
        const res = await fetch('/api/submit-complaint', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();

        if (data.success) {
          var refIdDisplay = document.getElementById('refIdDisplay');
          var refIdText = document.getElementById('refIdText');
          if (refIdDisplay) refIdDisplay.textContent = data.tracking_id;
          if (refIdText) refIdText.textContent = data.tracking_id;

          if (typeof openModal === 'function') {
            openModal('complaintModal');
          }

          complaintForm.reset();
          if (fileLabel) {
            fileLabel.textContent = 'No file chosen';
            fileLabel.style.fontStyle = 'italic';
            fileLabel.style.color = 'var(--text-medium)';
          }
        } else {
          if (typeof showToast === 'function') {
            showToast('Failed to submit complaint: ' + data.message, 'error');
          }
        }
      } catch (err) {
        console.error('Error submitting complaint:', err);
        if (typeof showToast === 'function') {
          showToast('An error occurred while submitting.', 'error');
        }
      } finally {
        // Always hide loading overlay and re-enable button
        if (loadingOverlay) loadingOverlay.classList.remove('active');
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  // RESET BUTTON HANDLER
  var resetBtn = document.getElementById('resetComplaintBtn');
  if (resetBtn) {
    resetBtn.addEventListener('click', function () {
      if (fileLabel) {
        fileLabel.textContent = 'No file chosen';
        fileLabel.style.fontStyle = 'italic';
        fileLabel.style.color = 'var(--text-medium)';
      }
    });
  }

  // ==========================================
  // COPY REFERENCE ID BUTTON
  // ==========================================
  var copyBtn = document.getElementById('copyRefBtn');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var refIdDisplay = document.getElementById('refIdDisplay');
      if (refIdDisplay) {
        var id = refIdDisplay.textContent;
        navigator.clipboard.writeText(id).then(function () {
          if (typeof showToast === 'function') {
            showToast('Reference ID copied to clipboard!', 'success');
          }
        }).catch(function () {
          // Fallback for environments without clipboard API
          if (typeof showToast === 'function') {
            showToast('Reference ID: ' + id, 'info');
          }
        });
      }
    });
  }

  // ==========================================
  // COMPLAINT TRACKING
  // ==========================================
  // TRACKING
  var trackForm = document.getElementById('trackForm');
  var trackSpinner = document.getElementById('trackSpinner');
  var trackingResults = document.getElementById('trackingResults');
  var trackResultId = document.getElementById('trackResultId');

  if (trackForm) {
    trackForm.addEventListener('submit', async function (e) {
      e.preventDefault();

      var enteredId = document.getElementById('trackId').value.trim();
      if (!enteredId) {
        if (typeof showToast === 'function') {
          showToast('Please enter a valid Tracking ID.', 'error');
        }
        return;
      }

      if (trackSpinner) trackSpinner.style.display = 'block';
      if (trackingResults) trackingResults.classList.remove('active');

      try {
        const res = await fetch('/api/track-complaint', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tracking_id: enteredId })
        });
        const data = await res.json();

        if (trackSpinner) trackSpinner.style.display = 'none';

        if (data.success) {
          const c = data.complaint;

          // Build the entire results block fresh
          trackingResults.innerHTML = `
            <span class="status-badge ${c.status ? c.status.toLowerCase() : 'unknown'}">● ${c.status || 'Unknown'}</span>
            <div class="status-info-row">
              <span class="status-label-small">Reference ID</span>
              <span class="status-value" id="trackResultId">${c.tracking_id || 'N/A'}</span>
            </div>
            <div class="status-info-row">
              <span class="status-label-small">Latest Update</span>
              <span class="status-value desc">${c.remarks || 'No remarks yet'}</span>
            </div>
            <div class="status-info-row">
              <span class="status-label-small">Last Updated</span>
              <span class="status-value">${c.last_updated || 'N/A'}</span>
            </div>
          `;

          trackingResults.classList.add('active');
        } else {
          if (typeof showToast === 'function') {
            showToast('Complaint not found.', 'error');
          }
        }


      } catch (err) {
        console.error('Error tracking complaint:', err);
        if (typeof showToast === 'function') {
          showToast('An error occurred while tracking.', 'error');
        }
      }
    });
  }

})();
