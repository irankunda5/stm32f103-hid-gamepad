const socket = io();

const hwBadge = document.getElementById('hw-badge');
const qualityBadge = document.getElementById('quality-badge');
const ppsBadge = document.getElementById('pps-badge');
const profileDropdown = document.getElementById('profile-dropdown');
const profileNameInput = document.getElementById('profile-name-input');
const profileCreateBtn = document.getElementById('profile-create-btn');
const routingTableContainer = document.getElementById('routing-table-container');
const buttonMatrixBus = document.getElementById('button-matrix-bus');

const pipLeft = document.getElementById('pip-left');
const pipRight = document.getElementById('pip-right');
const lblLx = document.getElementById('lbl-lx');
const lblLy = document.getElementById('lbl-ly');
const lblRx = document.getElementById('lbl-rx');
const lblRy = document.getElementById('lbl-ry');

const themeSwitch = document.getElementById('theme-switch');
const qualityBar = document.getElementById('quality-bar');

const CONTROLLER_BUTTONS = [
    "UP", "DOWN", "LEFT", "RIGHT", "A", "B", "X", "Y",
    "L1", "L2", "R1", "R2", "SELECT", "START", "HOME", "L3", "R3"
];

const AVAILABLE_KEYS = [
    "w", "a", "s", "d", "q", "e", "z", "x", "c", "f", "g", "h", "r", "t", "v", "b",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "space", "enter", "escape", "shift", "ctrl", "alt", "backspace", "tab",
    "up", "down", "left", "right",
    "left_click", "right_click"
];

/* =============================================
   THEME TOGGLE
   ============================================= */
function initTheme() {
    const saved = localStorage.getItem('fusedash-theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
        themeSwitch.checked = saved === 'light';
    }
}

themeSwitch.addEventListener('change', () => {
    const theme = themeSwitch.checked ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('fusedash-theme', theme);
});

initTheme();

/* =============================================
   BUTTON MATRIX INITIALIZATION
   ============================================= */
function initializeButtonMatrixBus() {
    buttonMatrixBus.innerHTML = "";
    CONTROLLER_BUTTONS.forEach(btn => {
        const div = document.createElement('div');
        div.className = 'bus-node';
        div.id = 'bus-node-' + btn;
        div.textContent = btn;
        buttonMatrixBus.appendChild(div);
    });
}
initializeButtonMatrixBus();

/* =============================================
   HARDWARE STATUS
   ============================================= */
socket.on('hw_status', (status) => {
    if (status.connected) {
        hwBadge.textContent = status.port ? 'ONLINE: ' + status.port : 'HARDWARE: ONLINE';
        hwBadge.className = 'badge badge-status-ok';
    } else {
        hwBadge.textContent = 'HARDWARE: OFFLINE';
        hwBadge.className = 'badge badge-status-err';
    }
});

/* =============================================
   CALIBRATION SYNC & SLIDER DISPATCH
   ============================================= */
socket.on('sync_calibration', (data) => {
    ['left', 'right'].forEach(stick => {
        const config = data[stick];
        if (!config) return;

        const alphaSlide = document.getElementById('slide-' + stick + '-alpha');
        const deadzoneSlide = document.getElementById('slide-' + stick + '-deadzone');
        const deadbandSlide = document.getElementById('slide-' + stick + '-deadband');
        const asymSlide = document.getElementById('slide-' + stick + '-asym');
        const invertToggle = document.getElementById('toggle-' + stick + '-invert');

        const alphaLbl = document.getElementById('lbl-' + stick + '-alpha');
        const deadzoneLbl = document.getElementById('lbl-' + stick + '-deadzone');
        const deadbandLbl = document.getElementById('lbl-' + stick + '-deadband');
        const asymLbl = document.getElementById('lbl-' + stick + '-asym');

        if (alphaSlide) { alphaSlide.value = config.alpha; alphaLbl.textContent = parseFloat(config.alpha).toFixed(2); }
        if (deadzoneSlide) { deadzoneSlide.value = config.radial_deadzone; deadzoneLbl.textContent = parseFloat(config.radial_deadzone).toFixed(2); }
        if (deadbandSlide) { deadbandSlide.value = config.deadband_lsb; deadbandLbl.textContent = config.deadband_lsb; }
        if (asymSlide) { asymSlide.value = config.asym_weight; asymLbl.textContent = parseFloat(config.asym_weight).toFixed(2); }
        if (invertToggle) { invertToggle.checked = config.invert_y; }
    });
});

function setupCalibrationListeners(stick) {
    const alphaSlide = document.getElementById('slide-' + stick + '-alpha');
    const deadzoneSlide = document.getElementById('slide-' + stick + '-deadzone');
    const deadbandSlide = document.getElementById('slide-' + stick + '-deadband');
    const asymSlide = document.getElementById('slide-' + stick + '-asym');
    const invertToggle = document.getElementById('toggle-' + stick + '-invert');

    const alphaLbl = document.getElementById('lbl-' + stick + '-alpha');
    const deadzoneLbl = document.getElementById('lbl-' + stick + '-deadzone');
    const deadbandLbl = document.getElementById('lbl-' + stick + '-deadband');
    const asymLbl = document.getElementById('lbl-' + stick + '-asym');

    const emitParamUpdate = (param, value) => {
        socket.emit('update_calibration', { stick, param, value });
    };

    alphaSlide.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        alphaLbl.textContent = val.toFixed(2);
        emitParamUpdate('alpha', val);
    });

    deadzoneSlide.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        deadzoneLbl.textContent = val.toFixed(2);
        emitParamUpdate('deadzone', val);
    });

    deadbandSlide.addEventListener('input', (e) => {
        const val = parseInt(e.target.value, 10);
        deadbandLbl.textContent = val;
        emitParamUpdate('deadband', val);
    });

    asymSlide.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value);
        asymLbl.textContent = val.toFixed(2);
        emitParamUpdate('asym_weight', val);
    });

    invertToggle.addEventListener('change', (e) => {
        emitParamUpdate('invert_y', e.target.checked);
    });
}
setupCalibrationListeners('left');
setupCalibrationListeners('right');

/* =============================================
   BUTTON EVENTS
   ============================================= */
socket.on('button_event', (event) => {
    const targetNode = document.getElementById('bus-node-' + event.button);
    if (targetNode) {
        if (event.action === 'PRESS') {
            targetNode.classList.add('active-firing');
        } else {
            targetNode.classList.remove('active-firing');
        }
    }
});

/* =============================================
   PROFILE MANAGEMENT
   ============================================= */
socket.on('sync_profiles', (database) => {
    const currentActiveProfile = database.current_profile;

    profileDropdown.innerHTML = "";
    Object.keys(database.profiles).forEach(p => {
        const item = document.createElement('option');
        item.value = p;
        item.textContent = p;
        if (p === currentActiveProfile) item.selected = true;
        profileDropdown.appendChild(item);
    });

    routingTableContainer.innerHTML = "";
    const activeMappings = database.profiles[currentActiveProfile];
    if (!activeMappings) return;

    Object.keys(activeMappings).forEach(btn => {
        const divRow = document.createElement('div');
        divRow.className = 'intercept-row';

        let customSelector = '<select data-btn-intercept="' + btn + '">';
        AVAILABLE_KEYS.forEach(key => {
            const isTarget = (activeMappings[btn] === key) ? 'selected' : '';
            customSelector += '<option value="' + key + '" ' + isTarget + '>' + key.toUpperCase() + '</option>';
        });
        customSelector += '</select>';

        divRow.innerHTML = '<label>' + btn + '</label>' + customSelector;
        routingTableContainer.appendChild(divRow);
    });

    document.querySelectorAll('.intercept-row select').forEach(element => {
        element.addEventListener('change', (e) => {
            socket.emit('update_mapping', {
                button: e.target.getAttribute('data-btn-intercept'),
                key: e.target.value
            });
        });
    });
});

profileDropdown.addEventListener('change', (e) => {
    socket.emit('switch_profile', e.target.value);
});

profileCreateBtn.addEventListener('click', () => {
    const rawVal = profileNameInput.value.trim();
    if (rawVal) {
        socket.emit('create_profile', rawVal);
        profileNameInput.value = "";
    }
});

profileNameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        profileCreateBtn.click();
    }
});

/* =============================================
   TELEMETRY & JOYSTICK SCOPE
   ============================================= */
const SCOPE_RADIUS = 62;

socket.on('telemetry', (data) => {
    const joy = data.state;
    const diag = data.diagnostics;

    lblLx.textContent = joy.lx;
    lblLy.textContent = joy.ly;
    lblRx.textContent = joy.rx;
    lblRy.textContent = joy.ry;

    const posLX = ((joy.lx - 2048) / 2048) * SCOPE_RADIUS;
    const posLY = ((joy.ly - 2048) / 2048) * SCOPE_RADIUS;
    const posRX = ((joy.rx - 2048) / 2048) * SCOPE_RADIUS;
    const posRY = ((joy.ry - 2048) / 2048) * SCOPE_RADIUS;

    pipLeft.style.transform = 'translate(' + posLX + 'px, ' + posLY + 'px)';
    pipRight.style.transform = 'translate(' + posRX + 'px, ' + posRY + 'px)';

    if (diag) {
        updateDiagnosticsPanel(diag);
    }
});

/* =============================================
   SIGNAL DIAGNOSTICS PANEL
   ============================================= */
function updateDiagnosticsPanel(diag) {
    setDiagValue('diag-nf-lx', diag.noise_floor_lx);
    setDiagValue('diag-nf-ly', diag.noise_floor_ly);
    setDiagValue('diag-nf-rx', diag.noise_floor_rx);
    setDiagValue('diag-nf-ry', diag.noise_floor_ry);

    document.getElementById('diag-spikes').textContent = diag.total_spikes;
    document.getElementById('diag-errors').textContent = diag.total_errors;
    document.getElementById('diag-rejected').textContent = diag.total_rejected;
    document.getElementById('diag-packets').textContent = diag.total_packets;

    ppsBadge.textContent = diag.packets_per_second + ' pkt/s';

    const q = diag.quality_score;
    qualityBadge.textContent = 'SIGNAL: ' + q + '%';
    qualityBar.style.width = q + '%';

    if (q >= 75) {
        qualityBar.style.background = 'var(--success)';
        qualityBadge.className = 'badge badge-status-ok';
    } else if (q >= 45) {
        qualityBar.style.background = 'var(--warning)';
        qualityBadge.className = 'badge badge-quality';
    } else {
        qualityBar.style.background = 'var(--danger)';
        qualityBadge.className = 'badge badge-status-err';
    }
}

function setDiagValue(elementId, value) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = value;

    el.className = 'diag-value';
    if (value <= 2.0) {
        el.classList.add('quality-good');
    } else if (value <= 15.0) {
        el.classList.add('quality-warn');
    } else {
        el.classList.add('quality-bad');
    }
}

/* =============================================
   DIAGNOSTICS UPDATE (standalone event)
   ============================================= */
socket.on('diagnostics_update', (diag) => {
    if (diag) {
        updateDiagnosticsPanel(diag);
    }
});

/* =============================================
   PERIODIC DIAGNOSTICS REQUEST
   ============================================= */
setInterval(() => {
    socket.emit('request_diagnostics');
}, 2000);
