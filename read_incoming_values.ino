// --- Pin Definitions ---
const int PIN_LEFT_X  = PA3; 
const int PIN_LEFT_Y  = PA2; 
const int PIN_RIGHT_X = PA1; 
const int PIN_RIGHT_Y = PA0; 

const int BUTTON_PINS[] = {
  PB1, PB0, PB11, PB10,     // up, left, down, right
  PA7, PA6, PB15, PA4,      // a, b, x, y
  PB9, PB7, PA5, PB8,       // l2, r1, l1, r2 (FIXED: Flipped 1/2 and swapped Left/Right pairs)
  PB6, PB5, PB4, PA15, PB3  // select, start, home, r3, l3
};

const char* BUTTON_NAMES[] = {
  "UP", "LEFT", "DOWN", "RIGHT",
  "A", "B", "X", "Y",
  "L2", "R1", "L1", "R2",
  "SELECT", "START", "HOME", "R3", "L3"
};

const int NUM_BUTTONS = sizeof(BUTTON_PINS) / sizeof(BUTTON_PINS[0]);

bool lastState[NUM_BUTTONS];        // debounced state we last reported
bool rawLastReading[NUM_BUTTONS];   // last raw pin reading
unsigned long lastChangeTime[NUM_BUTTONS];
const unsigned long DEBOUNCE_MS = 15;

unsigned long lastAxisPrint = 0;
const unsigned long AXIS_INTERVAL_MS = 50; // how often to print joystick values

void setup() {
  #if defined(STM32F1xx)
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_AFIO_REMAP_SWJ_NOJTAG();
  #endif

  Serial.begin(115200);

  analogReadResolution(12); // ensure 0-4095 range

  pinMode(PIN_LEFT_X, INPUT_ANALOG);
  pinMode(PIN_LEFT_Y, INPUT_ANALOG);
  pinMode(PIN_RIGHT_X, INPUT_ANALOG);
  pinMode(PIN_RIGHT_Y, INPUT_ANALOG);

  for (int i = 0; i < NUM_BUTTONS; i++) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
    bool reading = (digitalRead(BUTTON_PINS[i]) == LOW);
    lastState[i] = reading;
    rawLastReading[i] = reading;
    lastChangeTime[i] = millis();
  }
}

void loop() {
  unsigned long now = millis();

  // --- Buttons: debounced edge detection ---
  for (int i = 0; i < NUM_BUTTONS; i++) {
    bool reading = (digitalRead(BUTTON_PINS[i]) == LOW);

    if (reading != rawLastReading[i]) {
      lastChangeTime[i] = now;
      rawLastReading[i] = reading;
    }

    if ((now - lastChangeTime[i]) > DEBOUNCE_MS && reading != lastState[i]) {
      lastState[i] = reading;
      Serial.print(reading ? "PRESS " : "RELEASE ");
      Serial.println(BUTTON_NAMES[i]);
    }
  }

  // --- Joysticks: periodic raw values ---
  if (now - lastAxisPrint >= AXIS_INTERVAL_MS) {
    lastAxisPrint = now;
    int lx = analogRead(PIN_LEFT_X);
    int ly = analogRead(PIN_LEFT_Y);
    int rx = analogRead(PIN_RIGHT_X);
    int ry = analogRead(PIN_RIGHT_Y);

    Serial.print("AXIS LX:");
    Serial.print(lx);
    Serial.print(" LY:");
    Serial.print(ly);
    Serial.print(" RX:");
    Serial.print(rx);
    Serial.print(" RY:");
    Serial.println(ry);
  }
}
