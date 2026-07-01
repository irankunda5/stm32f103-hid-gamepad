#include <Keyboard.h>
#include <Mouse.h>

// --- Pin Definitions ---
const int PIN_LEFT_X  = PA1;
const int PIN_LEFT_Y  = PA0;
const int PIN_RIGHT_X = PA3;
const int PIN_RIGHT_Y = PA2;

const int BUTTON_PINS[] = {
  PB11, PB10, PB13, PB0,  // Index 0-3:   D-Pad (Up, Left, Down, Right)
  PA7,  PB15, PA6,  PA5,  // Index 4-7:   Action Buttons (A, B, X, Y)
  PA4,  PB9,  PB8,  PB7,  // Index 8-11:  L1, R1, L2, R2
  PB6,  PB5,  PB4,  PB3,  PA15 // Index 12-16: Select, Start, Home, L3, R3
};
const int NUM_BUTTONS = sizeof(BUTTON_PINS) / sizeof(BUTTON_PINS[0]);

// --- Keyboard Key Mapping Matrix ---
// Customize these to whatever keyboard keys you want your controller to trigger!
const char KEY_MAPPINGS[] = {
  KEY_UP_ARROW, KEY_LEFT_ARROW, KEY_DOWN_ARROW, KEY_RIGHT_ARROW, // D-Pad mappings
  'z', 'x', 'c', 'v',     // Action A, B, X, Y
  'a', 's', 'q', 'w',     // L1, R1, L2, R2
  KEY_RETURN, KEY_BACKSPACE, KEY_ESC, ' ', 'f' // Select, Start, Home, L3, R3
};

void setup() {
  // Free JTAG lines dynamically so PB3, PB4, and PA15 function as normal buttons
  #if defined(MCU_STM32F1)
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_AFIO_REMAP_SWJ_NOJTAG(); 
  #endif

  // Initialize Native USB HID Interfaces
  Keyboard.begin();
  Mouse.begin();

  // Initialize Analog Joystick Pins
  pinMode(PIN_LEFT_X, INPUT_ANALOG);
  pinMode(PIN_LEFT_Y, INPUT_ANALOG);
  pinMode(PIN_RIGHT_X, INPUT_ANALOG);
  pinMode(PIN_RIGHT_Y, INPUT_ANALOG);

  // Initialize Digital Buttons with Internal Pull-Ups
  for (int i = 0; i < NUM_BUTTONS; i++) {
    pinMode(BUTTON_PINS[i], INPUT_PULLUP);
  }
}

void loop() {
  // --- 1. Process Left Analog Joystick (Mapped to Mouse Cursor Movement) ---
  int leftX = analogRead(PIN_LEFT_X);
  int leftY = analogRead(PIN_LEFT_Y);

  // Map 12-bit STM32 analog values (0-4095) to mouse cursor speed steps (-6 to 6)
  // Incorporates a structural deadzone (1800 to 2200) to neutralize joystick drift
  int moveX = 0;
  int moveY = 0;
  if (leftX < 1800) moveX = map(leftX, 0, 1800, -6, 0);
  else if (leftX > 2200) moveX = map(leftX, 2200, 4095, 0, 6);
  
  if (leftY < 1800) moveY = map(leftY, 0, 1800, -6, 0);
  else if (leftY > 2200) moveY = map(leftY, 2200, 4095, 0, 6);

  if (moveX != 0 || moveY != 0) {
    Mouse.move(moveX, moveY, 0);
  }

  // --- 2. Process Right Analog Joystick (Mapped to Mouse Scroll Wheel) ---
  int rightY = analogRead(PIN_RIGHT_Y);
  int scroll = 0;
  if (rightY < 1500) scroll = 1;       // Scroll Up
  else if (rightY > 2500) scroll = -1; // Scroll Down
  
  if (scroll != 0) {
    Mouse.move(0, 0, scroll);
    delay(40); // Controls scrolling velocity
  }

  // --- 3. Process Buttons (Mapped to Keyboard Keystrokes) ---
  for (int i = 0; i < NUM_BUTTONS; i++) {
    // Buttons are active LOW (reading 0/LOW when pressed against Ground)
    bool isPressed = (digitalRead(BUTTON_PINS[i]) == LOW);
    
    if (isPressed) {
      Keyboard.press(KEY_MAPPINGS[i]); 
    } else {
      Keyboard.release(KEY_MAPPINGS[i]);
    }
  }

  delay(10); // Standard 10ms frame debounce delay
}
