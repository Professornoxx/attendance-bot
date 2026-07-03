// State Store
let appState = {
    employees: [],
    requests: [],
    activeTab: 'dashboard',
    performanceChart: null,
    shiftsEmployees: [],
    selectedShiftType: 'day'
};

// Application Bootstrap
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize clock
    startLiveClock();

    // 2. Load default values
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('current-date').innerText = formatDateString(today);
    document.getElementById('export-start-date').value = today;
    document.getElementById('export-end-date').value = today;

    // 3. Perform initial fetches
    fetchOverviewSummary();
    fetchEmployeeList();
    fetchRequestsQueue();
    fetchShiftsEmployees();

    // 4. Start automatic polling sync (every 10 seconds)
    setInterval(() => {
        fetchOverviewSummary();
        fetchEmployeeList();
        fetchRequestsQueue();
        if (appState.activeTab === 'shifts') {
            fetchShiftsEmployees();
        }
    }, 10000);
});

// Sidebar Clock
function startLiveClock() {
    const clockEl = document.getElementById('live-time');
    setInterval(() => {
        const now = new Date();
        clockEl.innerText = now.toLocaleTimeString('en-US', { hour12: false });
    }, 1000);
}

function formatDateString(dateStr) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(dateStr).toLocaleDateString('en-US', options);
}

// Client Routing Tabs
function switchTab(tabId) {
    // Update nav classes
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Highlight active nav item
    const targetNav = Array.from(document.querySelectorAll('.nav-item')).find(item => item.getAttribute('onclick').includes(tabId));
    if (targetNav) targetNav.classList.add('active');

    // Hide all screens
    document.querySelectorAll('.screen-section').forEach(screen => {
        screen.classList.add('hidden');
    });

    // Show target screen
    const targetScreen = document.getElementById(`screen-${tabId}`);
    if (targetScreen) targetScreen.classList.remove('hidden');

    appState.activeTab = tabId;

    // Auto-load data for attendance page when switching to it
    if (tabId === 'attendance') {
        initAttendanceDatePicker();
        fetchAttendancePage();
    } else if (tabId === 'shifts') {
        fetchShiftsEmployees();
    }
}

// REST API Methods
async function fetchOverviewSummary() {
    try {
        const res = await fetch('/api/summary');
        const data = await res.json();

        document.getElementById('kpi-total-employees').innerText = data.total_employees;
        document.getElementById('kpi-active-employees').innerText = data.active_employees;
        document.getElementById('kpi-on-break').innerText = data.on_break;
        document.getElementById('kpi-banned-employees').innerText = data.banned_employees;

        // Update early-logout requests pending badge
        const badge = document.getElementById('requests-pending-badge');
        if (data.pending_requests > 0) {
            badge.innerText = data.pending_requests;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    } catch (err) {
        console.error('Error fetching summaries:', err);
    }
}

async function fetchEmployeeList() {
    try {
        const res = await fetch('/api/employees');
        const data = await res.json();
        appState.employees = data;

        // Render to dashboard
        renderDashboardTable(data);

        // Render to employee directory list screen
        renderDirectoryTable(data);

        // Populate export filter options
        populateExportEmployeeDropdown(data);
    } catch (err) {
        console.error('Error loading employees:', err);
    }
}

function renderDashboardTable(employees) {
    const tbody = document.getElementById('dashboard-employees-body');
    if (!employees || employees.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="loading">No registered employees in database.</td></tr>`;
        return;
    }

    let html = '';
    employees.forEach(emp => {
        let statusBadge = '';
        switch (emp.current_status) {
            case 'Working':
                statusBadge = '<span class="badge badge-working">🟢 Working</span>'; break;
            case 'On Break':
                statusBadge = '<span class="badge badge-break">☕ On Break</span>'; break;
            case 'Field Visit':
                statusBadge = '<span class="badge badge-move">🚗 Field Visit</span>'; break;
            case 'Absent':
                statusBadge = '<span class="badge badge-error">🔴 Absent</span>'; break;
            default:
                statusBadge = '<span class="badge badge-offline">⚪ Offline</span>'; break;
        }

        // If the user is banned
        if (emp.status === 'banned') {
            statusBadge = '<span class="badge badge-error">🚫 Banned</span>';
        }

        const fineText = emp.fine_applied ? `<span class="badge badge-error">Yes (INR ${emp.fine_amount})</span>` : '<span class="badge badge-offline">No</span>';

        let halfDayText;
        if (emp.current_status === 'Absent') {
            halfDayText = '<span class="badge badge-error">🔴 Absent</span>';
        } else if (emp.current_status !== 'Offline') {
            halfDayText = '<span class="badge badge-move" title="Calculated at logout">⏳ In Progress</span>';
        } else if (emp.is_half_day) {
            halfDayText = '<span class="badge badge-warning">🟡 Half Day</span>';
        } else {
            halfDayText = '<span class="badge badge-working">🟢 Full Day</span>';
        }

        // Clean username display — never show literal "NoUsername"
        const usernameRaw = emp.username && emp.username !== 'NoUsername' ? emp.username : null;
        const usernameDisplay = usernameRaw
            ? `<span style="font-size:11px;color:var(--text-secondary)">@${usernameRaw}</span>`
            : `<span style="font-size:10px;color:var(--text-secondary);font-style:italic;">No Telegram username</span>`;

        html += `
            <tr>
                <td>
                    <strong style="cursor:pointer;" onclick="openProfileModal(${emp.telegram_id})">${emp.full_name}</strong>
                    <br>${usernameDisplay}
                </td>
                <td>${emp.shift_name}</td>
                <td>${statusBadge}</td>
                <td><code>${emp.net_working_str || '--:--:--'}</code></td>
                <td>${fineText}</td>
                <td>${halfDayText}</td>
                <td>
                    <div style="display:flex;gap:5px;">
                        <button class="btn btn-secondary btn-sm" onclick="openProfileModal(${emp.telegram_id})">
                            <i class="fa-solid fa-address-card"></i> Profile
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="toggleFinePrompt(${emp.telegram_id}, ${emp.fine_applied})">
                            <i class="fa-solid fa-receipt"></i> Fine
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;
}

function renderDirectoryTable(employees) {
    const tbody = document.getElementById('directory-employees-body');
    if (!employees || employees.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="loading">No employees registered.</td></tr>`;
        return;
    }

    let html = '';
    employees.forEach(emp => {
        const isBanned = emp.status === 'banned';

        // Clean username display — never show literal "NoUsername"
        const usernameRaw = emp.username && emp.username !== 'NoUsername' ? emp.username : null;
        const usernameCell = usernameRaw
            ? `@${usernameRaw}`
            : `<span style="color:var(--text-secondary);font-style:italic;font-size:11px;">Not linked</span>`;

        // ID Display: Telegram ID is the primary identifier; Employee ID is optional metadata
        const tgId = emp.telegram_id;
        let tgIdDisplay;
        if (tgId < 0) {
            tgIdDisplay = `<div style="font-weight:700;"><i class="fa-brands fa-telegram" style="color:var(--text-secondary);margin-right:4px;"></i><code style="color:var(--text-secondary);">Pre-created</code></div>`;
        } else {
            tgIdDisplay = `<div style="font-weight:700;"><i class="fa-brands fa-telegram" style="color:#2AABEE;margin-right:4px;"></i><code>${tgId}</code></div>`;
        }
        const empIdBadge = emp.employee_id
            ? `<div style="font-size:10px;color:var(--text-secondary);margin-top:3px;"><i class="fa-solid fa-id-badge" style="color:var(--primary);margin-right:3px;"></i>${emp.employee_id}</div>`
            : ``;
        const idDisplay = tgIdDisplay + empIdBadge;

        const actionBtn = isBanned
            ? `<button class="btn btn-success btn-sm" onclick="updateEmployeeBanStatus(${emp.telegram_id}, 'active')"><i class="fa-solid fa-check"></i> Activate</button>`
            : `<button class="btn btn-danger btn-sm" onclick="updateEmployeeBanStatus(${emp.telegram_id}, 'banned')"><i class="fa-solid fa-user-slash"></i> Deactivate</button>`;

        html += `
            <tr>
                <td>${idDisplay}</td>
                <td><strong>${emp.full_name}</strong></td>
                <td>${usernameCell}</td>
                <td><span class="badge badge-move">Project ${emp.project || 'N/A'}</span></td>
                <td>
                    <div style="font-weight:600;">${emp.shift_type === 'day' ? '🌅 Day' : '🌃 Night'}</div>
                    <div style="font-size:11px;color:var(--text-secondary);">${(emp.shift_start || '09:00:00').slice(0, 5)} - ${(emp.shift_end || '18:00:00').slice(0, 5)}</div>
                </td>
                <td><code>${emp.break_allowance || 65} min</code></td>
                <td>
                    ${isBanned ? '<span class="badge badge-error">INACTIVE</span>' : '<span class="badge badge-working">ACTIVE</span>'}
                </td>
                <td>
                    <div style="display:flex;gap:5px;flex-wrap:wrap;">
                        <button class="btn btn-secondary btn-sm" onclick="openProfileModal(${emp.telegram_id})"><i class="fa-solid fa-history"></i> History</button>
                        <button class="btn btn-primary btn-sm" onclick="openEditStaffModal(${emp.telegram_id})"><i class="fa-solid fa-edit"></i> Edit</button>
                        ${actionBtn}
                        <button class="btn btn-danger btn-sm" onclick="deleteStaff(${emp.telegram_id})"><i class="fa-solid fa-trash"></i> Delete</button>
                    </div>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function populateExportEmployeeDropdown(employees) {
    const select = document.getElementById('export-employee');
    const currentValue = select.value;

    let html = '<option value="">All Employees</option>';
    employees.forEach(emp => {
        html += `<option value="${emp.telegram_id}">${emp.full_name} (@${emp.username})</option>`;
    });
    select.innerHTML = html;
    select.value = currentValue;
}

// Modal Controllers: Employee details & growth charts
async function openProfileModal(telegram_id) {
    try {
        const res = await fetch(`/api/employee/${telegram_id}`);
        if (!res.ok) {
            pushToast('Failed to load employee details', 'error');
            return;
        }
        const data = await res.json();

        // Populate modal meta
        document.getElementById('modal-employee-name').innerText = data.profile.full_name;
        document.getElementById('modal-employee-uname').innerText = `@${data.profile.username}`;
        document.getElementById('meta-telegram-id').innerText = data.profile.telegram_id;
        document.getElementById('meta-role').innerText = data.profile.role.toUpperCase();
        document.getElementById('meta-shift-name').innerText = data.profile.shift_name;

        // Stats
        document.getElementById('stat-present-days').innerText = data.stats.days_present;
        document.getElementById('stat-net-hours').innerText = data.stats.total_working_hours;
        document.getElementById('stat-total-fines').innerText = `INR ${data.stats.total_fines}`;
        document.getElementById('stat-half-days').innerText = data.stats.half_days;

        // Progress / Productivity
        document.getElementById('meta-productivity-bar').style.width = `${data.stats.productivity_score}%`;
        document.getElementById('meta-productivity-text').innerText = `${data.stats.productivity_score}%`;

        const trendEl = document.getElementById('meta-growth-rate');
        const trend = data.stats.growth_trend;
        if (trend > 0) {
            trendEl.innerHTML = `<span style="color:var(--success)"><i class="fa-solid fa-arrow-trend-up"></i> +${trend}% (Growth)</span>`;
        } else if (trend < 0) {
            trendEl.innerHTML = `<span style="color:var(--error)"><i class="fa-solid fa-arrow-trend-down"></i> ${trend}% (Declined)</span>`;
        } else {
            trendEl.innerHTML = `<span><i class="fa-solid fa-minus"></i> 0.0% (Stable)</span>`;
        }

        // Render history logs
        renderProfileLogs(data.attendance_logs);

        // Display modal backdrop
        document.getElementById('modal-profile').classList.remove('hidden');

        // Render Chart.js
        setTimeout(() => {
            renderPerformanceChart(data.attendance_logs);
        }, 100);

    } catch (err) {
        console.error('Error loading employee details:', err);
    }
}

function closeProfileModal() {
    document.getElementById('modal-profile').classList.add('hidden');
    if (appState.performanceChart) {
        appState.performanceChart.destroy();
        appState.performanceChart = null;
    }
}

function renderProfileLogs(logs) {
    const tbody = document.getElementById('modal-attendance-logs');
    if (!logs || logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading">No attendance logs available.</td></tr>`;
        return;
    }

    let html = '';
    logs.forEach(log => {
        const halfDayText = log.is_half_day ? '<span class="badge badge-warning">Half Day</span>' : '<span class="badge badge-offline">Full</span>';
        const workHours = log.duration ? (log.duration / 3600.0).toFixed(2) + ' hrs' : 'Active';

        html += `
            <tr>
                <td><code>${log.date}</code></td>
                <td>${log.shift_start} - ${log.shift_end}</td>
                <td><code>${log.login_time}</code></td>
                <td><code>${log.logout_time || '--:--:--'}</code></td>
                <td>${workHours}</td>
                <td>${halfDayText}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function renderPerformanceChart(logs) {
    const canvas = document.getElementById('employeePerformanceChart');
    if (!canvas) return;

    // Sort logs ascending by date
    const sorted = [...logs].reverse().slice(-7); // Last 7 sessions
    const labels = sorted.map(l => l.date);
    const dataPoints = sorted.map(l => l.duration ? (l.duration / 3600.0) : 0);

    const ctx = canvas.getContext('2d');

    if (appState.performanceChart) {
        appState.performanceChart.destroy();
    }

    appState.performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Work Hours per Session',
                data: dataPoints,
                backgroundColor: 'rgba(99, 102, 241, 0.2)',
                borderColor: '#6366f1',
                borderWidth: 2,
                pointBackgroundColor: '#a855f7',
                pointBorderColor: '#fff',
                tension: 0.3,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 12,
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#9ca3af' }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Ban / Unban
async function updateEmployeeBanStatus(telegram_id, newStatus) {
    try {
        const res = await fetch(`/api/employees/${telegram_id}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });

        if (res.ok) {
            pushToast(`Employee status updated to ${newStatus.toUpperCase()}`, 'success');
            fetchEmployeeList();
        } else {
            pushToast('Failed to update status', 'error');
        }
    } catch (err) {
        console.error(err);
    }
}

// Fine dialog controls
function toggleFinePrompt(telegram_id, hasFineAlready) {
    // Load session info first
    // In our simplified logic, the admin will toggle fine for the employee's ACTIVE/LAST session of today
    // To do this, let's find the active attendance session
    const employee = appState.employees.find(e => e.telegram_id === telegram_id);
    if (!employee) return;

    // We fetch the employee's detail to get their last attendance session ID
    fetch(`/api/employee/${telegram_id}`)
        .then(res => res.json())
        .then(data => {
            const logs = data.attendance_logs;
            if (logs.length === 0) {
                pushToast('No attendance record found today to apply fine.', 'warning');
                return;
            }
            const lastSession = logs[0]; // newest

            if (hasFineAlready) {
                // If already has fine, directly toggle it OFF
                submitFineToggleDirectly(lastSession.id, false, 0, '');
            } else {
                // Otherwise, open the modal to specify amount and reason
                document.getElementById('fine-session-id').value = lastSession.id;
                document.getElementById('fine-current-state').value = 'apply';
                document.getElementById('modal-fine').classList.remove('hidden');
            }
        });
}

async function submitFineToggleDirectly(sessionId, apply, amount, reason, remarks = '') {
    try {
        const res = await fetch(`/api/attendance/${sessionId}/fine`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fine_applied: apply,
                fine_amount: amount,
                fine_reason: reason,
                remarks: remarks
            })
        });
        if (res.ok) {
            pushToast(apply ? 'Fine applied successfully' : 'Fine revoked successfully', 'success');
            fetchEmployeeList();
            fetchOverviewSummary();
            // Also refresh the attendance page if it's currently active
            if (appState.activeTab === 'attendance') {
                fetchAttendancePage();
            }
        } else {
            pushToast('Operation failed', 'error');
        }
    } catch (err) {
        console.error(err);
    }
}

function submitFineToggle(e) {
    e.preventDefault();
    const sessionId = document.getElementById('fine-session-id').value;
    const amount = document.getElementById('fine-amount').value;
    const reason = document.getElementById('fine-reason').value;
    const remarks = document.getElementById('fine-remarks').value.trim();

    closeFineModal();
    submitFineToggleDirectly(sessionId, true, amount, reason, remarks);
}

function closeFineModal() {
    document.getElementById('modal-fine').classList.add('hidden');
    document.getElementById('fine-remarks').value = '';
}

// Early Logout Requests Review Queue
async function fetchRequestsQueue() {
    try {
        const res = await fetch('/api/requests');
        const data = await res.json();
        appState.requests = data;
        renderRequestsTable(data);
    } catch (err) {
        console.error(err);
    }
}

function renderRequestsTable(requests) {
    const tbody = document.getElementById('requests-body');
    if (!requests || requests.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading">No early logout requests pending.</td></tr>`;
        return;
    }

    let html = '';
    requests.forEach(req => {
        let actionCell = '';
        if (req.status === 'pending') {
            actionCell = `
                <div style="display:flex;gap:5px;">
                    <button class="btn btn-success btn-sm" onclick="reviewRequest(${req.id}, 'approved')"><i class="fa-solid fa-check"></i> Approve (Half Day)</button>
                    <button class="btn btn-danger btn-sm" onclick="reviewRequest(${req.id}, 'rejected')"><i class="fa-solid fa-xmark"></i> Reject</button>
                </div>
            `;
        } else {
            const statusClass = req.status === 'approved' ? 'badge-working' : 'badge-error';
            actionCell = `<span class="badge ${statusClass}">${req.status.toUpperCase()}</span>`;
        }

        html += `
            <tr>
                <td><code>${req.date}</code></td>
                <td><strong>${req.name}</strong><br><span style="font-size:11px;color:var(--text-secondary)">${req.username && req.username !== 'NoUsername' ? '@' + req.username : '<em style="color:var(--text-secondary);font-style:italic;font-size:10px;">No username</em>'}</span></td>
                <td><code>${req.logout_time}</code></td>
                <td><em>"${req.reason}"</em></td>
                <td><span class="badge ${req.status === 'pending' ? 'badge-break' : (req.status === 'approved' ? 'badge-working' : 'badge-error')}">${req.status.toUpperCase()}</span></td>
                <td>${actionCell}</td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

async function reviewRequest(requestId, status) {
    try {
        const res = await fetch(`/api/requests/${requestId}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: status })
        });
        if (res.ok) {
            pushToast(`Request ${status}`, 'success');
            fetchRequestsQueue();
            fetchEmployeeList();
        } else {
            pushToast('Failed to review request', 'error');
        }
    } catch (err) {
        console.error(err);
    }
}

// Exports Trigger Form
function triggerExport(e) {
    e.preventDefault();
    const start = document.getElementById('export-start-date').value;
    const end = document.getElementById('export-end-date').value;
    const empId = document.getElementById('export-employee').value;
    const shiftType = document.getElementById('export-shift-type').value;
    const format = document.querySelector('input[name="format"]:checked').value;

    let url = `/api/export?format=${format}&start_date=${start}&end_date=${end}`;
    if (empId) {
        url += `&telegram_id=${empId}`;
    }
    if (shiftType) {
        url += `&shift_type=${shiftType}`;
    }

    const shiftLabel = shiftType === 'day' ? '☀️ Day Shift'
        : shiftType === 'night' ? '🌙 Night Shift'
            : shiftType === 'unassigned' ? '⚫ Unassigned'
                : 'All Shifts';
    pushToast(`Generating ${format.toUpperCase()} report · ${shiftLabel}...`, 'info');
    window.location.href = url;
}

// ─── Staff Attendance Page ────────────────────────────────────────────────────

let attendancePageData = [];

function initAttendanceDatePicker() {
    const picker = document.getElementById('attendance-date-picker');
    if (picker && !picker.value) {
        picker.value = new Date().toISOString().split('T')[0];
    }
}

async function fetchAttendancePage() {
    initAttendanceDatePicker();
    const date = document.getElementById('attendance-date-picker').value;
    const tbody = document.getElementById('attendance-page-body');
    tbody.innerHTML = `<tr><td colspan="9" class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>`;

    try {
        const res = await fetch(`/api/attendance/daily?date=${date}`);
        const data = await res.json();
        attendancePageData = data.records;
        renderAttendanceTable(data.records);
        renderAttendanceSummaryBar(data.summary, date);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="9" class="loading">⚠️ Failed to load attendance data.</td></tr>`;
        console.error(err);
    }
}

function renderAttendanceSummaryBar(summary, date) {
    const bar = document.getElementById('attendance-summary-bar');
    const chips = [
        { icon: 'fa-users', label: 'Total Staff', value: summary.total, color: '#a78bfa' },
        { icon: 'fa-circle-check', label: 'Present', value: summary.present, color: '#4ade80' },
        { icon: 'fa-circle-xmark', label: 'Absent', value: summary.absent, color: '#f87171' },
        { icon: 'fa-clock', label: 'Half Day', value: summary.half_day, color: '#fbbf24' },
        { icon: 'fa-chart-bar', label: 'Avg Net Hours', value: summary.avg_net_hours, color: '#60a5fa' },
    ];
    bar.innerHTML = chips.map(c => `
        <div style="display:flex; align-items:center; gap:8px; background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:8px 14px;">
            <i class="fa-solid ${c.icon}" style="color:${c.color};"></i>
            <span style="font-size:12px; color:var(--text-secondary);">${c.label}</span>
            <strong style="color:${c.color}; font-size:14px;">${c.value}</strong>
        </div>
    `).join('');
}

function renderAttendanceTable(records) {
    const tbody = document.getElementById('attendance-page-body');
    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="loading">No records found for this date.</td></tr>`;
        return;
    }
    let html = '';
    records.forEach((r, idx) => {
        const isAbsent = r.status === 'absent';
        const rowStyle = isAbsent ? 'opacity:0.55;' : '';

        let attendanceTypeBadge;
        if (isAbsent) {
            attendanceTypeBadge = '<span class="badge badge-error">🔴 Absent</span>';
        } else if (r.logout_time === 'Active (Logged In)') {
            attendanceTypeBadge = '<span class="badge badge-move">⏳ In Progress</span>';
        } else if (r.is_half_day) {
            attendanceTypeBadge = '<span class="badge badge-warning">🟡 Half Day</span>';
        } else {
            attendanceTypeBadge = '<span class="badge badge-working">🟢 Full Day</span>';
        }

        const loginDisplay = isAbsent ? '<span style="color:var(--text-secondary)">—</span>' : `<code>${r.login_time}</code>`;
        const logoutDisplay = isAbsent ? '<span style="color:var(--text-secondary)">—</span>' :
            r.logout_time === 'Active (Logged In)' ? '<span class="badge badge-working">🟢 Active</span>' : `<code>${r.logout_time}</code>`;
        const breakDisplay = isAbsent ? '—' : `<code>${r.total_break_str}</code>`;
        const netDisplay = isAbsent ? '—' : `<code style="color:var(--primary);font-weight:600;">${r.net_working_str}</code>`;
        const fineDisplay = r.fine_applied
            ? `<span class="badge badge-error">INR ${r.fine_amount}</span>`
            : '<span style="color:var(--text-secondary); font-size:12px;">—</span>';

        // Clean username display for attendance table
        const attUsernameRaw = r.username && r.username !== 'NoUsername' ? r.username : null;
        const attUsernameDisplay = attUsernameRaw
            ? `<span style="font-size:11px; color:var(--text-secondary);">@${attUsernameRaw}</span>`
            : `<span style="font-size:10px;color:var(--text-secondary);font-style:italic;">No username</span>`;

        html += `
            <tr style="${rowStyle}">
                <td style="color:var(--text-secondary); font-size:12px;">${idx + 1}</td>
                <td>
                     <strong style="cursor:pointer;" onclick="openProfileModal(${r.telegram_id})">${r.full_name}</strong>
                     <br>${attUsernameDisplay}
                </td>
                <td style="font-size:12px;">${r.shift_name}</td>
                <td>${loginDisplay}</td>
                <td>${logoutDisplay}</td>
                <td>${breakDisplay}</td>
                <td>${netDisplay}</td>
                <td>${attendanceTypeBadge}</td>
                <td>${fineDisplay}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="openEditAttendanceModal(${idx})">
                        <i class="fa-solid fa-pen-to-square"></i> Edit
                    </button>
                </td>
            </tr>
        `;
    });
    tbody.innerHTML = html;
}

function generateAttendanceReport(format) {
    document.getElementById('report-dropdown-menu').classList.add('hidden');
    const date = document.getElementById('attendance-date-picker').value;
    if (!date) { pushToast('Please select a date first.', 'warning'); return; }
    const url = `/api/export?format=${format}&start_date=${date}&end_date=${date}`;
    pushToast(`Generating ${format.toUpperCase()} report for ${date}...`, 'info');
    window.location.href = url;
}

function generateBreakDetailsReport() {
    const date = document.getElementById('attendance-date-picker').value;
    if (!date) { pushToast('Please select a date first.', 'warning'); return; }
    const url = `/api/export/breaks?date=${date}`;
    pushToast(`Generating break details report for ${date}...`, 'info');
    window.location.href = url;
}

function toggleReportDropdown() {
    const menu = document.getElementById('report-dropdown-menu');
    menu.classList.toggle('hidden');
    // Close on outside click
    const closer = (e) => {
        if (!document.getElementById('report-dropdown-btn').contains(e.target)) {
            menu.classList.add('hidden');
            document.removeEventListener('click', closer);
        }
    };
    if (!menu.classList.contains('hidden')) {
        setTimeout(() => document.addEventListener('click', closer), 10);
    }
}

// ─── Directory Searching filter ───────────────────────────────────────────────
function filterEmployees() {
    const query = document.getElementById('employee-search').value.toLowerCase().trim();
    const filtered = appState.employees.filter(emp => {
        return emp.full_name.toLowerCase().includes(query) ||
            emp.username.toLowerCase().includes(query) ||
            String(emp.telegram_id).includes(query);
    });
    renderDirectoryTable(filtered);
}

// Toast Notifier overlay
function pushToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let icon = '<i class="fa-solid fa-circle-info"></i>';
    if (type === 'success') icon = '<i class="fa-solid fa-circle-check"></i>';
    if (type === 'error') icon = '<i class="fa-solid fa-circle-xmark"></i>';
    if (type === 'warning') icon = '<i class="fa-solid fa-circle-exclamation"></i>';

    toast.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(toast);

    // Auto-remove after 4 seconds
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s reverse';
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 4000);
}

// ─── Shift Management Screen Logic ───────────────────────────────────────────
async function fetchShiftsEmployees() {
    try {
        const res = await fetch('/api/shifts/employees');
        if (!res.ok) {
            pushToast('Failed to fetch shift employee data', 'error');
            return;
        }
        appState.shiftsEmployees = await res.json();
        renderShiftsPage();
    } catch (err) {
        console.error('Error fetching shift employees:', err);
    }
}

function selectShiftType(type) {
    appState.selectedShiftType = type;

    // Toggle active state of shift buttons
    const btnDay = document.getElementById('btn-shift-day');
    const btnNight = document.getElementById('btn-shift-night');
    if (type === 'day') {
        btnDay.className = 'btn btn-primary';
        btnNight.className = 'btn btn-secondary';
    } else {
        btnDay.className = 'btn btn-secondary';
        btnNight.className = 'btn btn-primary';
    }

    renderShiftsPage();
}

function renderShiftsPage() {
    const container = document.getElementById('shifts-grouped-container');
    if (!appState.shiftsEmployees || appState.shiftsEmployees.length === 0) {
        container.innerHTML = `<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading shift categories...</div>`;
        return;
    }

    const query = document.getElementById('shift-search').value.toLowerCase().trim();
    const statusFilter = document.getElementById('shift-status-filter').value;

    // 1. Filter by selectedShiftType, search query, and status
    const filtered = appState.shiftsEmployees.filter(emp => {
        // Shift type filter
        if (emp.shift_type !== appState.selectedShiftType) return false;

        // Search query filter (name, username, or project)
        const matchQuery = (emp.full_name || '').toLowerCase().includes(query) ||
            (emp.username || '').toLowerCase().includes(query) ||
            (emp.project || '').toLowerCase().includes(query);
        if (!matchQuery) return false;

        // Status filter
        if (statusFilter !== 'all') {
            if (statusFilter === 'working' && emp.current_status !== 'Working' && emp.current_status !== 'On Break' && emp.current_status !== 'Field Visit') {
                return false;
            } else if (statusFilter === 'absent' && emp.current_status !== 'Absent') {
                return false;
            } else if (statusFilter === 'half_day' && emp.current_status !== 'Half Day') {
                return false;
            } else if (statusFilter === 'full_day' && emp.current_status !== 'Full Day') {
                return false;
            } else if (statusFilter === 'banned' && emp.current_status !== 'Banned') {
                return false;
            }
        }

        return true;
    });

    // 2. Group by project
    const groups = {};
    filtered.forEach(emp => {
        const proj = emp.project;
        if (!groups[proj]) {
            groups[proj] = [];
        }
        groups[proj].push(emp);
    });

    // Get sorted project keys
    const projKeys = Object.keys(groups).sort((a, b) => {
        const aNum = parseInt(a);
        const bNum = parseInt(b);
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return aNum - bNum;
        }
        return a.localeCompare(b);
    });

    if (projKeys.length === 0) {
        container.innerHTML = `<div class="loading">No employees match the current filters.</div>`;
        return;
    }

    let html = '';
    projKeys.forEach(proj => {
        const emps = groups[proj];
        const displayName = isNaN(proj) ? proj : `Project ${proj}`;

        html += `
            <div class="project-group-card">
                <div class="project-group-header">
                    <span>📁 ${displayName}</span>
                    <span class="project-group-count">${emps.length} Staff</span>
                </div>
                <div class="project-group-body">
        `;

        emps.forEach(emp => {
            let statusBadge = '';
            switch (emp.current_status) {
                case 'Working':
                    statusBadge = '<span class="badge badge-working">🟢 Working</span>'; break;
                case 'On Break':
                    statusBadge = '<span class="badge badge-break">☕ On Break</span>'; break;
                case 'Field Visit':
                    statusBadge = '<span class="badge badge-move">🚗 Field Visit</span>'; break;
                case 'Absent':
                    statusBadge = '<span class="badge badge-error">⚪ Absent</span>'; break;
                case 'Half Day':
                    statusBadge = '<span class="badge badge-warning">🟡 Half Day</span>'; break;
                case 'Full Day':
                    statusBadge = '<span class="badge badge-working">🟢 Full Day</span>'; break;
                case 'Banned':
                    statusBadge = '<span class="badge badge-error">🚫 Banned</span>'; break;
                default:
                    statusBadge = `<span class="badge badge-offline">${emp.current_status}</span>`; break;
            }

            const usernameRaw = emp.username && emp.username !== 'NoUsername' ? emp.username : null;
            const usernameLabel = emp.status === 'unregistered'
                ? (usernameRaw ? `@${usernameRaw} <span style="font-size:9px;color:var(--text-secondary);font-style:italic;">(Unreg)</span>` : `<span style="font-size:9px;color:var(--text-secondary);font-style:italic;">Not registered</span>`)
                : (usernameRaw ? `@${usernameRaw}` : `<span style="font-size:10px;color:var(--text-secondary);font-style:italic;">No username</span>`);

            const clickAttr = emp.telegram_id
                ? `onclick="openProfileModal(${emp.telegram_id})"`
                : `onclick="pushToast('Employee has not registered on Telegram yet.', 'warning')"`;

            const workingHoursStr = emp.current_status === 'Absent' ? '--:--:--' : emp.net_working_str;

            html += `
                <div class="employee-shift-card" ${clickAttr}>
                    <div class="employee-shift-card-header">
                        <div>
                            <div class="employee-shift-card-name">${emp.full_name}</div>
                            <div class="employee-shift-card-username">${usernameLabel}</div>
                        </div>
                        <div>${statusBadge}</div>
                    </div>
                    <div class="employee-shift-card-times">
                        <i class="fa-solid fa-clock"></i> ${(emp.shift_start || '09:00:00').slice(0, 5)} - ${(emp.shift_end || '18:00:00').slice(0, 5)}
                    </div>
                    <div class="employee-shift-card-footer" style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size:11px;color:var(--text-secondary);">Today Hours:</span>
                            <span class="employee-shift-card-duration">${workingHoursStr}</span>
                        </div>
                        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); openEditStaffModal(${emp.telegram_id})" style="padding: 4px 8px; font-size: 11px;">
                            <i class="fa-solid fa-edit"></i> Edit
                        </button>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function filterShiftsPage() {
    renderShiftsPage();
}

// Utility: convert seconds to HH:MM:SS string
function secondsToHMS(sec) {
    if (!sec || sec <= 0) return '00:00:00';
    const h = Math.floor(sec / 3600).toString().padStart(2, '0');
    const m = Math.floor((sec % 3600) / 60).toString().padStart(2, '0');
    const s = Math.floor(sec % 60).toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
}

// Utility: escape HTML to prevent XSS
function escapeHtml(str) {
    if (!str) return '';
    return str.toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ══════════════════════════════════════════════════
// STAFF MANAGEMENT MODAL AND CRUD LOGIC
// ══════════════════════════════════════════════════

function openAddStaffModal() {
    document.getElementById('staff-modal-title').innerText = 'Add New Staff Member';
    document.getElementById('staff-mode').value = 'add';
    document.getElementById('staff-orig-telegram-id').value = '';

    // Clear inputs
    document.getElementById('staff-name').value = '';
    document.getElementById('staff-username').value = '';
    document.getElementById('staff-emp-id').value = '';
    document.getElementById('staff-telegram-id').value = '';   // Required — must be filled
    document.getElementById('staff-project').value = '1';
    document.getElementById('staff-shift-type').value = 'day';
    document.getElementById('staff-shift-start').value = '09:00:00';
    document.getElementById('staff-shift-end').value = '18:00:00';
    document.getElementById('staff-break-allowance').value = '65';
    document.getElementById('staff-status').value = 'active';
    document.getElementById('staff-settings').value = '';

    // Show Telegram ID field as required; make emp-id clearly optional
    document.getElementById('staff-telegram-id').required = true;
    document.getElementById('staff-emp-id').required = false;

    document.getElementById('modal-staff').classList.remove('hidden');
}

function openEditStaffModal(telegramId) {
    const emp = appState.employees.find(e => e.telegram_id === telegramId);
    if (!emp) {
        pushToast('Employee details not found.', 'error');
        return;
    }

    document.getElementById('staff-modal-title').innerText = 'Edit Staff Details';
    document.getElementById('staff-mode').value = 'edit';
    document.getElementById('staff-orig-telegram-id').value = telegramId;

    document.getElementById('staff-name').value = emp.full_name || '';
    document.getElementById('staff-username').value = emp.username === 'NoUsername' ? '' : emp.username;
    document.getElementById('staff-emp-id').value = emp.employee_id || '';
    document.getElementById('staff-telegram-id').value = emp.telegram_id > 0 ? emp.telegram_id : '';
    document.getElementById('staff-project').value = emp.project || '';
    document.getElementById('staff-shift-type').value = emp.shift_type || 'day';
    document.getElementById('staff-shift-start').value = emp.shift_start || '09:00:00';
    document.getElementById('staff-shift-end').value = emp.shift_end || '18:00:00';
    document.getElementById('staff-break-allowance').value = emp.break_allowance || 65;
    document.getElementById('staff-status').value = emp.status || 'active';
    document.getElementById('staff-settings').value = emp.attendance_settings || '';

    document.getElementById('modal-staff').classList.remove('hidden');
}

function closeStaffModal() {
    document.getElementById('modal-staff').classList.add('hidden');
}

function onShiftTypeChange() {
    const shiftType = document.getElementById('staff-shift-type').value;
    const startInput = document.getElementById('staff-shift-start');
    const endInput = document.getElementById('staff-shift-end');

    if (shiftType === 'day') {
        startInput.value = '09:00:00';
        endInput.value = '18:00:00';
    } else {
        startInput.value = '20:30:00';
        endInput.value = '08:30:00';
    }
}

async function submitStaffForm(event) {
    event.preventDefault();

    const mode = document.getElementById('staff-mode').value;
    const origTelegramId = document.getElementById('staff-orig-telegram-id').value;

    const telegramIdRaw = document.getElementById('staff-telegram-id').value.trim();

    // Telegram ID is required — validate it
    if (!telegramIdRaw) {
        pushToast('Telegram User ID is required to identify the staff member.', 'error');
        return;
    }
    const telegramIdNum = parseInt(telegramIdRaw, 10);
    if (isNaN(telegramIdNum)) {
        pushToast('Telegram User ID must be a valid number.', 'error');
        return;
    }

    const payload = {
        full_name: document.getElementById('staff-name').value.trim(),
        username: document.getElementById('staff-username').value.trim(),
        employee_id: document.getElementById('staff-emp-id').value.trim() || null,   // Optional
        telegram_id: telegramIdNum,
        project: document.getElementById('staff-project').value.trim(),
        shift_type: document.getElementById('staff-shift-type').value,
        shift_start: document.getElementById('staff-shift-start').value.trim(),
        shift_end: document.getElementById('staff-shift-end').value.trim(),
        break_allowance: parseInt(document.getElementById('staff-break-allowance').value) || 65,
        attendance_settings: document.getElementById('staff-settings').value.trim(),
        status: document.getElementById('staff-status').value
    };

    let url = '/api/employees';
    let method = 'POST';

    if (mode === 'edit') {
        url = `/api/employees/${origTelegramId}`;
        method = 'PUT';
    }

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            let msg;
            if (mode === 'edit') {
                msg = 'Staff details updated!';
            } else if (data.updated) {
                msg = 'Existing staff record updated with new details!';
            } else {
                msg = 'Staff member added successfully!';
            }
            pushToast(msg, 'success');
            closeStaffModal();
            fetchEmployeeList();
            fetchShiftsEmployees();
            fetchOverviewSummary();
        } else {
            pushToast(data.error || 'Operation failed', 'error');
        }
    } catch (err) {
        console.error('Error submitting staff form:', err);
        pushToast('Connection error. Failed to save staff.', 'error');
    }
}

async function deleteStaff(telegramId) {
    const emp = appState.employees.find(e => e.telegram_id === telegramId);
    const name = emp ? emp.full_name : 'this employee';
    if (!confirm(`Are you absolutely sure you want to delete ${name}?\nAll attendance history, break logs, and settings will be permanently removed.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/employees/${telegramId}`, {
            method: 'DELETE'
        });

        const data = await res.json();
        if (res.ok) {
            pushToast('Staff record successfully deleted.', 'success');
            fetchEmployeeList();
            fetchShiftsEmployees();
            fetchOverviewSummary();
        } else {
            pushToast(data.error || 'Failed to delete staff', 'error');
        }
    } catch (err) {
        console.error('Error deleting staff:', err);
        pushToast('Connection error. Failed to delete staff.', 'error');
    }
}

// --- Edit Attendance Modal Logic ---

function openEditAttendanceModal(idx) {
    const record = attendancePageData[idx];
    if (!record) return;

    document.getElementById('edit-att-telegram-id').value = record.telegram_id;
    document.getElementById('edit-att-date').value = document.getElementById('attendance-date-picker').value;
    document.getElementById('edit-att-employee-name').innerText = record.full_name;

    if (record.status === 'absent') {
        document.getElementById('edit-att-status').value = 'absent';
        document.getElementById('edit-att-login-time').value = '09:00:00';
        document.getElementById('edit-att-logout-time').value = '';
        document.getElementById('edit-att-half-day').value = '0';
        document.getElementById('edit-att-fine-applied').value = '0';
        document.getElementById('edit-att-fine-amount').value = '500';
        document.getElementById('edit-att-fine-reason').value = '';
        document.getElementById('edit-att-login-time').removeAttribute('required');
    } else {
        document.getElementById('edit-att-status').value = 'present';
        document.getElementById('edit-att-login-time').value = record.login_time || '09:00:00';
        document.getElementById('edit-att-logout-time').value = record.logout_time === 'Active (Logged In)' ? '' : (record.logout_time || '');
        document.getElementById('edit-att-half-day').value = record.is_half_day ? '1' : '0';
        document.getElementById('edit-att-fine-applied').value = record.fine_applied ? '1' : '0';
        document.getElementById('edit-att-fine-amount').value = record.fine_amount || '500';
        document.getElementById('edit-att-fine-reason').value = record.fine_reason || '';
        document.getElementById('edit-att-login-time').setAttribute('required', 'true');
    }

    toggleEditTimeInputs();
    toggleEditFineInputs();

    document.getElementById('modal-edit-attendance').classList.remove('hidden');
}

function closeEditAttendanceModal() {
    document.getElementById('modal-edit-attendance').classList.add('hidden');
    document.getElementById('edit-att-fine-remarks').value = '';
}

function toggleEditTimeInputs() {
    const status = document.getElementById('edit-att-status').value;
    const timeFields = document.getElementById('edit-att-time-fields');
    if (status === 'absent') {
        timeFields.classList.add('hidden');
        document.getElementById('edit-att-login-time').removeAttribute('required');
    } else {
        timeFields.classList.remove('hidden');
        document.getElementById('edit-att-login-time').setAttribute('required', 'true');
    }
}

function toggleEditFineInputs() {
    const fineApplied = document.getElementById('edit-att-fine-applied').value;
    const fineFields = document.getElementById('edit-att-fine-fields');
    if (fineApplied === '1') {
        fineFields.classList.remove('hidden');
    } else {
        fineFields.classList.add('hidden');
    }
}

async function submitEditAttendanceForm(event) {
    event.preventDefault();

    const telegram_id = parseInt(document.getElementById('edit-att-telegram-id').value);
    const date = document.getElementById('edit-att-date').value;
    const status = document.getElementById('edit-att-status').value;

    let login_time = null;
    let logout_time = null;
    let is_half_day = 0;
    let fine_applied = 0;
    let fine_amount = 0.0;
    let fine_reason = '';
    let remarks = '';

    if (status === 'present') {
        login_time = document.getElementById('edit-att-login-time').value.trim();
        logout_time = document.getElementById('edit-att-logout-time').value.trim();
        is_half_day = parseInt(document.getElementById('edit-att-half-day').value);
        fine_applied = parseInt(document.getElementById('edit-att-fine-applied').value);
        if (fine_applied === 1) {
            fine_amount = parseFloat(document.getElementById('edit-att-fine-amount').value) || 0.0;
            fine_reason = document.getElementById('edit-att-fine-reason').value.trim();
            remarks = document.getElementById('edit-att-fine-remarks').value.trim();
        }
    }

    try {
        const res = await fetch('/api/attendance/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_id,
                date,
                status,
                login_time,
                logout_time,
                is_half_day,
                fine_applied,
                fine_amount,
                fine_reason,
                remarks
            })
        });

        const data = await res.json();
        if (data.error) {
            pushToast(data.error, 'error');
        } else {
            pushToast('Attendance record updated successfully!', 'success');
            closeEditAttendanceModal();
            fetchAttendancePage();
            // Refresh dashboard list & KPIs too
            fetchOverviewSummary();
            fetchEmployeeList();
        }
    } catch (err) {
        console.error(err);
        pushToast('Error saving changes.', 'error');
    }
}
