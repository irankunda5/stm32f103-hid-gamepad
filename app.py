import os
import json
import time
import serial
import serial.tools.list_ports
import threading
import math
import logging
import statistics
from collections import deque

from flask import Flask, render_template
from flask_socketio import SocketIO
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

mouse = MouseController()
keyboard = KeyboardController()

BAUD_RATE = 115200
CONFIG_FILE = 'profiles.json'
CENTER_RAW = 2048
MOUSE_SPEED_MAX = 16
SCROLL_SPEED_MAX = 2
PREFERRED_PORT = 'COM9'

joy_state = {"lx": CENTER_RAW, "ly": CENTER_RAW, "rx": CENTER_RAW, "ry": CENTER_RAW}
hardware_connected = False

DEFAULT_PROFILES = {
    "current_profile": "Standard Mapping",
    "profiles": {
        "Standard Mapping": {
            "UP": "w", "LEFT": "a", "DOWN": "s", "RIGHT": "d",
            "A": "space", "B": "x", "X": "left_click", "Y": "right_click",
            "L1": "q", "R1": "e", "L2": "1", "R2": "2",
            "SELECT": "escape", "START": "enter", "HOME": "h",
            "L3": "g", "R3": "f"
        }
    }
}


# --- SIGNAL DIAGNOSTICS (non-intrusive, reads joy_state only) ---
class SignalDiagnostics:
    def __init__(self, window_size=120):
        self.window_size = window_size
        self.packet_count = 0
        self.error_count = 0
        self.spike_count = 0
        self.rejected_count = 0
        self.history = {
            "lx": deque(maxlen=window_size), "ly": deque(maxlen=window_size),
            "rx": deque(maxlen=window_size), "ry": deque(maxlen=window_size),
        }
        self.last_packet_time = time.time()
        self.packets_per_second = 0.0
        self._pps_window_start = time.time()
        self._pps_window_count = 0

    def record_sample(self, axis_key, value):
        if axis_key in self.history:
            self.history[axis_key].append(value)

    def record_spike(self):
        self.spike_count += 1

    def record_rejection(self):
        self.rejected_count += 1

    def record_error(self):
        self.error_count += 1

    def record_packet(self):
        self.packet_count += 1
        self._pps_window_count += 1
        now = time.time()
        elapsed = now - self._pps_window_start
        if elapsed >= 1.0:
            self.packets_per_second = self._pps_window_count / elapsed
            self._pps_window_start = now
            self._pps_window_count = 0
        self.last_packet_time = now

    def get_noise_floor(self, axis_key):
        vals = self.history.get(axis_key, deque())
        if len(vals) < 10:
            return 0.0
        diffs = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
        return round(statistics.mean(diffs), 2) if diffs else 0.0

    def get_signal_quality(self):
        noise_scores = []
        for key in ["lx", "ly", "rx", "ry"]:
            nf = self.get_noise_floor(key)
            if nf <= 2.0:
                noise_scores.append(100)
            elif nf <= 5.0:
                noise_scores.append(80)
            elif nf <= 15.0:
                noise_scores.append(60)
            elif nf <= 40.0:
                noise_scores.append(40)
            else:
                noise_scores.append(20)
        base = statistics.mean(noise_scores) if noise_scores else 100
        error_penalty = min(30, (self.error_count / max(1, self.packet_count)) * 100)
        spike_penalty = min(20, (self.spike_count / max(1, self.packet_count)) * 100)
        return max(0, min(100, round(base - error_penalty - spike_penalty)))

    def to_dict(self):
        return {
            "noise_floor_lx": self.get_noise_floor("lx"),
            "noise_floor_ly": self.get_noise_floor("ly"),
            "noise_floor_rx": self.get_noise_floor("rx"),
            "noise_floor_ry": self.get_noise_floor("ry"),
            "quality_score": self.get_signal_quality(),
            "packets_per_second": round(self.packets_per_second, 1),
            "total_packets": self.packet_count,
            "total_errors": self.error_count,
            "total_spikes": self.spike_count,
            "total_rejected": self.rejected_count,
        }


signal_diag = SignalDiagnostics()


class BalancedJoystickCalibrator:
    def __init__(self, alpha=0.30, deadband_lsb=5, radial_deadzone=0.15, asym_weight=0.50, invert_y=False):
        self.alpha = alpha
        self.deadband_lsb = deadband_lsb
        self.radial_deadzone = radial_deadzone
        self.asym_weight = asym_weight
        self.invert_y = invert_y
        self.last_x = 2048.0
        self.last_y = 2048.0
        self.center_x = 2048.0
        self.center_y = 2048.0
        self.min_x = 0.0
        self.max_x = 4095.0
        self.min_y = 0.0
        self.max_y = 4095.0
        self.is_calibrated = False

    def calibrate_center(self, samples):
        if not samples: return
        self.center_x = sum(s[0] for s in samples) / len(samples)
        self.center_y = sum(s[1] for s in samples) / len(samples)
        self.is_calibrated = True

    def to_dict(self):
        return {
            "alpha": self.alpha,
            "deadband_lsb": self.deadband_lsb,
            "radial_deadzone": self.radial_deadzone,
            "asym_weight": self.asym_weight,
            "invert_y": self.invert_y
        }

    def filter_and_map(self, raw_x, raw_y):
        stable_x = raw_x if abs(raw_x - self.last_x) > self.deadband_lsb else self.last_x
        stable_y = raw_y if abs(raw_y - self.last_y) > self.deadband_lsb else self.last_y

        alpha_val = max(0.001, min(1.0, self.alpha))
        filt_x = (alpha_val * stable_x) + ((1.0 - alpha_val) * self.last_x)
        filt_y = (alpha_val * stable_y) + ((1.0 - alpha_val) * self.last_y)
        self.last_x, self.last_y = filt_x, filt_y

        if filt_x < self.center_x:
            denom_x = (1.0 - self.asym_weight) * 2048.0 + self.asym_weight * (self.center_x - self.min_x)
            x_norm = (filt_x - self.center_x) / max(1.0, denom_x)
        else:
            denom_x = (1.0 - self.asym_weight) * 2048.0 + self.asym_weight * (self.max_x - self.center_x)
            x_norm = (filt_x - self.center_x) / max(1.0, denom_x)

        if filt_y < self.center_y:
            denom_y = (1.0 - self.asym_weight) * 2048.0 + self.asym_weight * (self.center_y - self.min_y)
            y_norm = (filt_y - self.center_y) / max(1.0, denom_y)
        else:
            denom_y = (1.0 - self.asym_weight) * 2048.0 + self.asym_weight * (self.max_y - self.center_y)
            y_norm = (filt_y - self.center_y) / max(1.0, denom_y)

        x_norm = max(-1.0, min(1.0, x_norm))
        y_norm = max(-1.0, min(1.0, y_norm))

        if self.invert_y:
            y_norm = -y_norm

        magnitude = math.sqrt(x_norm**2 + y_norm**2)
        if magnitude <= self.radial_deadzone:
            x_dead, y_dead = 0.0, 0.0
        else:
            denom_deadzone = max(0.001, 1.0 - self.radial_deadzone)
            rescaled_mag = (magnitude - self.radial_deadzone) / denom_deadzone
            safe_magnitude = max(0.0001, magnitude)
            x_dead = (x_norm / safe_magnitude) * rescaled_mag
            y_dead = (y_norm / safe_magnitude) * rescaled_mag

        val_x = 1.0 - (y_dead**2) / 2.0
        val_y = 1.0 - (x_dead**2) / 2.0
        final_x = x_dead * math.sqrt(max(0.0, val_x))
        final_y = y_dead * math.sqrt(max(0.0, val_y))

        return final_x, final_y


left_calibrator = BalancedJoystickCalibrator(alpha=0.30, deadband_lsb=5, radial_deadzone=0.15, asym_weight=0.50, invert_y=False)
right_calibrator = BalancedJoystickCalibrator(alpha=0.35, deadband_lsb=5, radial_deadzone=0.10, asym_weight=0.50, invert_y=True)

left_boot_cache, right_boot_cache = [], []
BOOT_LIMIT = 60


def load_profiles():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f: json.dump(DEFAULT_PROFILES, f, indent=4)
        return DEFAULT_PROFILES.copy()
    try:
        with open(CONFIG_FILE, 'r') as f: return json.load(f)
    except Exception: return DEFAULT_PROFILES.copy()

def save_profiles(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f, indent=4)

profile_database = load_profiles()

def get_active_mapping():
    active_profile = profile_database.get("current_profile", "Standard Mapping")
    return profile_database["profiles"].get(active_profile, list(profile_database["profiles"].values())[0])

def resolve_key(key_str):
    key_str = key_str.lower().strip()
    lookup = {
        "space": Key.space, "enter": Key.enter, "shift": Key.shift,
        "ctrl": Key.ctrl, "alt": Key.alt, "backspace": Key.backspace,
        "tab": Key.tab, "escape": Key.esc, "up": Key.up,
        "down": Key.down, "left": Key.left, "right": Key.right,
        "home": Key.home, "end": Key.end, "page_up": Key.page_up,
        "page_down": Key.page_down, "delete": Key.delete, "insert": Key.insert,
        "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
        "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
        "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
        "caps_lock": Key.caps_lock, "num_lock": Key.num_lock,
        "scroll_lock": Key.scroll_lock, "print_screen": Key.print_screen,
        "pause": Key.pause, "menu": Key.menu,
    }
    return lookup.get(key_str, key_str)


def auto_find_com_port():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    port_list = ", ".join(f"{p.device}({p.description})" for p in ports)
    logging.info(f"Scanning ports: {port_list}")

    for port in ports:
        if port.device.upper() == PREFERRED_PORT.upper():
            return port.device

    for port in ports:
        desc = port.description.lower()
        if "bluetooth" in desc:
            continue
        if _probe_port_for_gamepad(port.device):
            logging.info(f"Auto-detected gamepad on {port.device}")
            return port.device

    # logging.warning(f"{PREFERRED_PORT} not found. Available: {port_list}")
    return None


def _probe_port_for_gamepad(port_name, baud=115200, timeout_s=0.8):
    try:
        ser = serial.Serial(port_name, baud, timeout=0.1)
        ser.reset_input_buffer()
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("AXIS") or line.startswith("PRESS") or line.startswith("RELEASE"):
                    ser.close()
                    return True
            time.sleep(0.01)
        ser.close()
    except (serial.SerialException, OSError):
        pass
    return False


def hardware_emulation_worker():
    while True:
        if not left_calibrator.is_calibrated or not right_calibrator.is_calibrated:
            time.sleep(0.01)
            continue

        lx, ly = left_calibrator.filter_and_map(joy_state["lx"], joy_state["ly"])
        rx, ry = right_calibrator.filter_and_map(joy_state["rx"], joy_state["ry"])

        mx = int(rx * MOUSE_SPEED_MAX)
        my = int(ry * MOUSE_SPEED_MAX)
        if mx != 0 or my != 0:
            mouse.move(mx, my)

        sx = int(lx * SCROLL_SPEED_MAX)
        sy = int(ly * SCROLL_SPEED_MAX)
        if sx != 0 or sy != 0:
            mouse.scroll(sx, sy)

        time.sleep(0.006)


def serial_reader_worker():
    global hardware_connected
    while True:
        active_port = auto_find_com_port()

        if not active_port:
            hardware_connected = False
            socketio.emit('hw_status', {'connected': False})
            time.sleep(2.0)
            continue

        try:
            ser = serial.Serial(active_port, BAUD_RATE, timeout=0.05)
            hardware_connected = True
            socketio.emit('hw_status', {'connected': True, 'port': active_port})
            logging.info(f"Connected to {active_port}")

            while True:
                if ser.in_waiting > 0:
                    raw_line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not raw_line: continue

                    if raw_line.startswith("AXIS"):
                        segments = raw_line.split()
                        try:
                            for item in segments[1:]:
                                k, v = item.split(":")
                                key = k.lower()
                                val = int(v)
                                joy_state[key] = val
                                signal_diag.record_sample(key, val)
                            signal_diag.record_packet()
                        except (ValueError, KeyError):
                            signal_diag.record_error()
                            continue

                        socketio.emit('telemetry', {
                            "state": joy_state,
                            "diagnostics": signal_diag.to_dict()
                        })

                        if not left_calibrator.is_calibrated:
                            left_boot_cache.append((joy_state["lx"], joy_state["ly"]))
                            right_boot_cache.append((joy_state["rx"], joy_state["ry"]))
                            if len(left_boot_cache) >= BOOT_LIMIT:
                                left_calibrator.calibrate_center(left_boot_cache)
                                right_calibrator.calibrate_center(right_boot_cache)
                                socketio.emit('sync_calibration', {
                                    "left": left_calibrator.to_dict(),
                                    "right": right_calibrator.to_dict()
                                })

                    elif raw_line.startswith("PRESS") or raw_line.startswith("RELEASE"):
                        action, button_id = raw_line.split()
                        socketio.emit('button_event', {"action": action, "button": button_id})

                        mapping = get_active_mapping()
                        if button_id in mapping:
                            target = mapping[button_id].lower().strip()
                            if target == "left_click":
                                mouse.press(Button.left) if action == "PRESS" else mouse.release(Button.left)
                            elif target == "right_click":
                                mouse.press(Button.right) if action == "PRESS" else mouse.release(Button.right)
                            else:
                                key_obj = resolve_key(target)
                                keyboard.press(key_obj) if action == "PRESS" else keyboard.release(key_obj)
                time.sleep(0.001)
        except Exception:
            hardware_connected = False
            socketio.emit('hw_status', {'connected': False})
            time.sleep(2.0)


@app.route('/')
def home():
    return render_template('index.html')

@socketio.on('connect')
def connect_handshake():
    socketio.emit('hw_status', {'connected': hardware_connected})
    socketio.emit('sync_profiles', profile_database)
    socketio.emit('sync_calibration', {
        "left": left_calibrator.to_dict(),
        "right": right_calibrator.to_dict()
    })
    socketio.emit('diagnostics_update', signal_diag.to_dict())

@socketio.on('update_calibration')
def process_cal_update(payload):
    stick = payload.get('stick')
    param = payload.get('param')
    val = payload.get('value')

    target = left_calibrator if stick == 'left' else right_calibrator

    if param == 'alpha':
        target.alpha = float(val)
    elif param == 'deadzone':
        target.radial_deadzone = float(val)
    elif param == 'deadband':
        target.deadband_lsb = int(val)
    elif param == 'asym_weight':
        target.asym_weight = float(val)
    elif param == 'invert_y':
        target.invert_y = bool(val)

    socketio.emit('sync_calibration', {
        "left": left_calibrator.to_dict(),
        "right": right_calibrator.to_dict()
    })

@socketio.on('switch_profile')
def change_profile(name):
    if name in profile_database["profiles"]:
        profile_database["current_profile"] = name
        save_profiles(profile_database)
        socketio.emit('sync_profiles', profile_database)

@socketio.on('update_mapping')
def alter_mapping(payload):
    current = profile_database.get("current_profile")
    btn = payload.get('button')
    key = payload.get('key')
    if current in profile_database["profiles"] and btn in profile_database["profiles"][current]:
        profile_database["profiles"][current][btn] = key
        save_profiles(profile_database)

@socketio.on('create_profile')
def generate_profile(name):
    if name and name not in profile_database["profiles"]:
        active = profile_database["current_profile"]
        profile_database["profiles"][name] = profile_database["profiles"][active].copy()
        profile_database["current_profile"] = name
        save_profiles(profile_database)
        socketio.emit('sync_profiles', profile_database)

@socketio.on('delete_profile')
def delete_profile(name):
    if name and name in profile_database["profiles"] and len(profile_database["profiles"]) > 1:
        del profile_database["profiles"][name]
        if profile_database["current_profile"] == name:
            profile_database["current_profile"] = list(profile_database["profiles"].keys())[0]
        save_profiles(profile_database)
        socketio.emit('sync_profiles', profile_database)

@socketio.on('request_diagnostics')
def send_diagnostics():
    socketio.emit('diagnostics_update', signal_diag.to_dict())


if __name__ == '__main__':
    threading.Thread(target=hardware_emulation_worker, daemon=True).start()
    threading.Thread(target=serial_reader_worker, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
